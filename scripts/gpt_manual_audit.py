"""使用 GPT-5.6-Terra 按《过程评估人工标注规范》进行人工式审查.

产出 JSONL 标注文件，用于计算定位准确率、误报率、CBU 真实性等指标。
"""

import argparse
import json
import os
import random
import re
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from openai import OpenAI


ERROR_TYPES = [
    "题意误读",
    "概念理解错误",
    "定理/公式误用",
    "计算错误",
    "条件遗漏",
    "跳步推导",
    "循环论证",
    "幻觉/无中生有",
    "单位/格式不符",
    "其他/无法归类",
]

GUIDELINE_SUMMARY = """
你正在执行《过程评估人工标注规范》。核心规则：
1. 语义步：以解题输出中 Step/步骤 编号为准；若未分步或分步不合理，按“一步=一个不可再分推理动作”重切分，并设置 resegmented=true。
2. 首个错误步：推理链中第一个不成立的步骤。包括前提合法但推导不合法、引入非法内容、题意偏离。首个错误之后的“将错就错”不算新错误。
3. 跳步：结论无法由前文+题目条件+中学/竞赛常规定理直接推出，且省略的不是机械计算。首错步=“跳”到的结论步。
4. 循环论证：结论被后续步骤用作前提，后续结论又支撑该结论。首错步=先使用待证结论的那一步。
5. 题意误读：模型建立的数学对象/目标与题面不符。首错步=错误理解首次影响数学内容的那一步。
6. 截断：finish_reason=length 或输出明显中断（无 \\boxed{}、句末不完整、括号未闭合）。中断前无错误则 process_valid=false, first_error_step=null, error_type="输出截断"。
7. 答案错但过程成立：优先怀疑答案等价性问题（分数/小数、单位差异、x=5 vs 5），标注 suspected_answer_equivalence=true，不记为模型错误。
8. 多解/非常规解法：只要推理成立就不得判错。
9. 错误类型优先级（同一步多候选）：题意误读 > 幻觉 > 概念理解错误/定理误用 > 条件遗漏 > 循环论证 > 跳步推导 > 计算错误 > 单位/格式不符。
10. CBU 专项（仅批次 B）：答案正确但评估器判过程错时，判定 cbu_audit：true_positive_fatal（真实致命错误导致蒙对）、true_positive_benign（无害笔误，结论仍有效支撑）、false_positive（过程实际成立，评估器误报）。
"""


def load_jsonl(path: str) -> List[Dict]:
    data = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data.append(json.loads(line))
    return data


def load_json(path: str) -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_prompt(
    problem: str,
    gold_answer: str,
    raw_output: str,
    finish_reason: Optional[str],
    answer_correct: bool,
    batch: str,
    evaluator_claim: Optional[str] = None,
) -> str:
    base = f"""题目：
{problem}

标准答案：{gold_answer}

模型最终答案是否被判正确：{'是' if answer_correct else '否'}

模型原始解答：
{raw_output}

finish_reason：{finish_reason or 'unknown'}
"""
    if batch == "B" and evaluator_claim:
        base += f"\n评估器声称该样本属于：{evaluator_claim}\n"

    base += f"""
{GUIDELINE_SUMMARY}

请严格按上述规范，对该解答进行独立审查（不要受任何外部评估结果影响），并只输出如下 JSON（不要输出任何其他文字）：
"""
    if batch == "B":
        base += """
{
  "resegmented": false,
  "n_steps": <步骤总数（按规范切分后）>,
  "process_valid": <true/false>,
  "first_error_step": <首个错误步的1-based编号，若过程成立则为 null>,
  "error_type": "<十类错误之一或 输出截断 或 null（若过程成立）>",
  "error_detail": "<详细说明，包括涉及的步骤编号、错误原因、引用内容。若过程成立则空字符串>",
  "truncated": <true/false>,
  "cbu_audit": "<true_positive_fatal / true_positive_benign / false_positive 之一>",
  "cbu_detail": "<若 cbu_audit 为 true_positive_*，说明为何答案对但过程不能支撑结论；若为 false_positive，说明过程为何实际成立>",
  "suspected_answer_equivalence": <true/false>,
  "needs_adjudication": <true/false>,
  "adjudicated": false
}
"""
    else:
        base += """
{
  "resegmented": false,
  "n_steps": <步骤总数（按规范切分后）>,
  "process_valid": <true/false>,
  "first_error_step": <首个错误步的1-based编号，若过程成立则为 null>,
  "error_type": "<十类错误之一或 输出截断 或 null（若过程成立）>",
  "error_detail": "<详细说明，包括涉及的步骤编号、错误原因、引用内容。若过程成立则空字符串>",
  "truncated": <true/false>,
  "cbu_audit": null,
  "suspected_answer_equivalence": <true/false>,
  "needs_adjudication": <true/false>,
  "adjudicated": false
}
"""
    return base


def parse_json_from_text(text: str) -> Optional[Dict]:
    text = text.strip()
    # 尝试直接解析
    try:
        return json.loads(text)
    except Exception:
        pass
    # 尝试提取 fenced code block
    m = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    # 尝试从第一个 { 到最后一个 }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except Exception:
            pass
    return None


def call_gpt(
    client: OpenAI,
    prompt: str,
    model: str = "gpt-5.6-terra",
    max_tokens: int = 2048,
    retries: int = 3,
) -> Optional[str]:
    for attempt in range(retries):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_completion_tokens=max_tokens,
            )
            return resp.choices[0].message.content or ""
        except Exception as e:
            print(f"  GPT call failed (attempt {attempt+1}/{retries}): {e}")
            time.sleep(2 ** attempt)
    return None


def annotate_sample(
    client: OpenAI,
    problem: str,
    gold_answer: str,
    raw_output: str,
    finish_reason: Optional[str],
    answer_correct: bool,
    batch: str,
    evaluator_claim: Optional[str] = None,
) -> Dict[str, Any]:
    prompt = build_prompt(
        problem, gold_answer, raw_output, finish_reason, answer_correct, batch, evaluator_claim
    )
    text = call_gpt(client, prompt)
    if text is None:
        return {"parse_error": True, "raw": None}
    parsed = parse_json_from_text(text)
    if parsed is None:
        return {"parse_error": True, "raw": text}
    parsed["parse_error"] = False
    parsed["raw"] = text
    return parsed


def stratified_sample(
    items: List[Dict],
    group_key: str,
    total: int,
    seed: int = 42,
) -> List[Dict]:
    rng = random.Random(seed)
    groups = defaultdict(list)
    for it in items:
        groups[it[group_key]].append(it)
    if not groups:
        return []
    # 按比例分配，最少每 group 1 个（若 group 数量 <= total）
    group_names = sorted(groups.keys())
    weights = {g: len(groups[g]) for g in group_names}
    total_weight = sum(weights.values())
    allocations = {}
    remaining = total
    for g in group_names[:-1]:
        alloc = min(len(groups[g]), max(1, round(total * weights[g] / total_weight)))
        allocations[g] = alloc
        remaining -= alloc
    allocations[group_names[-1]] = min(len(groups[group_names[-1]]), max(1, remaining))

    # 如果按比例分配后还有剩余额度，按组内可抽数量补充
    while sum(allocations.values()) < total:
        added = False
        for g in group_names:
            if allocations[g] < len(groups[g]):
                allocations[g] += 1
                if sum(allocations.values()) == total:
                    added = True
                    break
        if not added and sum(allocations.values()) < total:
            break

    selected = []
    for g in group_names:
        pool = groups[g][:]
        rng.shuffle(pool)
        selected.extend(pool[: allocations[g]])
    rng.shuffle(selected)
    return selected


def uniform_sample(
    items: List[Dict],
    group_key: str,
    per_group: int,
    seed: int = 42,
) -> List[Dict]:
    rng = random.Random(seed)
    groups = defaultdict(list)
    for it in items:
        groups[it[group_key]].append(it)
    selected = []
    for g in sorted(groups.keys()):
        pool = groups[g][:]
        rng.shuffle(pool)
        selected.extend(pool[:per_group])
    rng.shuffle(selected)
    return selected


def run_batch(
    client: OpenAI,
    samples: List[Dict],
    batch_label: str,
    output_path: Path,
    evaluator_claim_fn: Optional[Any] = None,
):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    records = []
    for i, s in enumerate(samples, 1):
        print(f"[{batch_label}] {i}/{len(samples)}: {s['problem_id']}")
        claim = None
        if evaluator_claim_fn:
            claim = evaluator_claim_fn(s)
        result = annotate_sample(
            client,
            problem=s["problem"],
            gold_answer=s.get("gold_answer", ""),
            raw_output=s.get("raw_output", ""),
            finish_reason=s.get("finish_reason"),
            answer_correct=s.get("answer_correct", False),
            batch=batch_label,
            evaluator_claim=claim,
        )
        record = {
            "id": s["problem_id"],
            "batch": batch_label,
            "annotator": "gpt-5.6-terra",
            "level": s.get("level"),
            "answer_correct": s.get("answer_correct"),
        }
        record.update(result)
        records.append(record)
        # 流控
        time.sleep(0.1)

    with open(output_path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"[{batch_label}] 标注已保存到 {output_path}")
    return records


def compute_batch_a_metrics(annotations: List[Dict], eval_map: Dict[str, Dict]):
    # 只保留成功解析且 process_valid 为 false 的样本
    valid = [a for a in annotations if not a.get("parse_error") and a.get("process_valid") is False]
    exact = 0
    pm1 = 0
    for a in valid:
        e = eval_map.get(a["id"])
        if not e:
            continue
        eval_step = e.get("first_error_step")
        ann_step = a.get("first_error_step")
        try:
            eval_step = int(eval_step) if eval_step is not None else None
            ann_step = int(ann_step) if ann_step is not None else None
        except Exception:
            continue
        if eval_step is None:
            continue
        if ann_step == eval_step:
            exact += 1
        elif ann_step is not None and abs(ann_step - eval_step) <= 1:
            pm1 += 1
    n = len(valid)
    print(f"\n[Batch A 定位准确率] 有效标注数: {n}")
    if n:
        print(f"  完全命中: {exact}/{n} = {exact/n:.2%}")
        print(f"  ±1 步命中: {pm1}/{n} = {pm1/n:.2%}")
        print(f"  未命中: {n - exact - pm1}/{n} = {(n-exact-pm1)/n:.2%}")


def compute_batch_c_metrics(annotations: List[Dict]):
    valid = [a for a in annotations if not a.get("parse_error")]
    false_positives = [a for a in valid if a.get("process_valid") is False]
    n = len(valid)
    print(f"\n[Batch C 误报率] 抽检数: {n}")
    if n:
        print(f"  GPT 认为过程有问题: {len(false_positives)}/{n} = {len(false_positives)/n:.2%}")


def compute_batch_b_metrics(annotations: List[Dict]):
    valid = [a for a in annotations if not a.get("parse_error")]
    counts = Counter(a.get("cbu_audit") for a in valid)
    print(f"\n[Batch B CBU 审计] 全量数: {len(valid)}")
    for k, v in counts.items():
        print(f"  {k}: {v}")


def main():
    parser = argparse.ArgumentParser(description="GPT manual audit per annotation guideline")
    parser.add_argument("--base_url", type=str, default=os.getenv("JUDGE_GPT_API_BASE", "https://your-openai-compatible-endpoint/v1"))
    parser.add_argument("--api_key", type=str, default=os.getenv("JUDGE_GPT_API_KEY", ""))
    parser.add_argument("--model", type=str, default="gpt-5.6-terra")
    parser.add_argument("--problems", type=str, default="dataset/problems_merged.jsonl")
    parser.add_argument("--solutions", type=str, default="results/solutions_merged.jsonl")
    parser.add_argument("--eval_single", type=str, default="results/evaluation_results_merged_final.json")
    parser.add_argument("--eval_multi", type=str, default="results/evaluation_results_merged_multi_judge_fixed.json")
    parser.add_argument("--output_dir", type=str, default="audit_outputs")
    parser.add_argument("--batch", type=str, default="all", choices=["A", "B", "C", "all"])
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    client = OpenAI(base_url=args.base_url.rstrip("/"), api_key=args.api_key or "dummy")

    problems = {p["id"]: p for p in load_jsonl(args.problems)}
    solutions = {s["problem_id"]: s for s in load_jsonl(args.solutions)}
    eval_single = load_json(args.eval_single)
    eval_single_map = {e["problem_id"]: e for e in eval_single.get("evaluations", [])}
    eval_multi = load_json(args.eval_multi)
    eval_multi_map = {e["problem_id"]: e for e in eval_multi.get("evaluations", [])}

    def merge(pid: str, answer_correct: bool) -> Dict:
        p = problems[pid]
        s = solutions.get(pid, {})
        return {
            "problem_id": pid,
            "level": p.get("level"),
            "problem": p.get("problem"),
            "gold_answer": str(p.get("answer", "")),
            "raw_output": s.get("raw_output", ""),
            "finish_reason": s.get("finish_reason"),
            "answer_correct": answer_correct,
        }

    output_dir = Path(args.output_dir)

    # Batch A: real wrong answers, stratified sample 30
    if args.batch in ("A", "all"):
        wrong_pids = [pid for pid, e in eval_single_map.items() if not e.get("answer_correct")]
        samples = [merge(pid, False) for pid in wrong_pids]
        sampled = stratified_sample(samples, "level", 30, seed=args.seed)
        out = output_dir / "gpt_annotation_batch_A.jsonl"
        ann = run_batch(client, sampled, "A", out)
        compute_batch_a_metrics(ann, eval_single_map)

    # Batch C: correct samples, uniform 5 per level = 20
    if args.batch in ("C", "all"):
        correct_pids = [
            pid
            for pid, e in eval_single_map.items()
            if e.get("answer_correct") and e.get("process_correct")
        ]
        samples = [merge(pid, True) for pid in correct_pids]
        sampled = uniform_sample(samples, "level", 5, seed=args.seed)
        out = output_dir / "gpt_annotation_batch_C.jsonl"
        ann = run_batch(client, sampled, "C", out)
        compute_batch_c_metrics(ann)

    # Batch B: multi-judge CBU samples
    if args.batch in ("B", "all"):
        cbu_pids = [
            pid
            for pid, e in eval_multi_map.items()
            if e.get("correct_but_unjustified", {}).get("correct_but_unjustified")
        ]
        samples = [merge(pid, True) for pid in cbu_pids]

        def claim_fn(s):
            e = eval_multi_map.get(s["problem_id"], {})
            step = e.get("first_error_step")
            etype = e.get("error_type")
            return f"结果正确但过程不成立，评估器定位首错步={step}，错误类型={etype}"

        out = output_dir / "gpt_annotation_batch_B.jsonl"
        ann = run_batch(client, samples, "B", out, evaluator_claim_fn=claim_fn)
        compute_batch_b_metrics(ann)


if __name__ == "__main__":
    main()
