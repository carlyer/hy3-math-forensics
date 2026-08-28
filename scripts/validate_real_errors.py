"""Validate the process evaluator's localization accuracy on real Hy3 wrong-answer samples.

Uses GPT-5.6-Terra as the auditor. The auditor's judgment is treated as the
"human" audit result and compared against the evaluator's first_error_step
and error_type stored in the merged GPT-judge evaluation file.

Inputs:
- results/evaluation_results_merged_gpt_judge.json
- dataset/problems_merged.jsonl
- results/solutions_merged.jsonl

Outputs:
- results/validation_real_errors.json
- results/validation_real_errors_report.md
"""

import json
import os
import random
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.hy3_client import load_judge_client_from_env


EVALUATION_FILE = ROOT / "results" / "evaluation_results_merged_gpt_judge.json"
PROBLEMS_FILE = ROOT / "dataset" / "problems_merged.jsonl"
SOLUTIONS_FILE = ROOT / "results" / "solutions_merged.jsonl"
OUTPUT_JSON = ROOT / "results" / "validation_real_errors.json"
OUTPUT_REPORT = ROOT / "results" / "validation_real_errors_report.md"

SAMPLE_SIZE = 30
RANDOM_SEED = 42
AUDITOR_TEMPERATURE = 0.2
AUDITOR_MAX_TOKENS = 1024
FALLBACK_MAX_TOKENS = 2048

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

SYSTEM_PROMPT = """你是一位严格的数学解题过程审计专家，正在执行《过程评估人工标注规范》。

任务：阅读题目、标准答案和模型给出的分步解答，判断推理链是否存在逻辑/概念/计算错误。若存在，定位首个错误步骤并给出最具体的错误类型；若不存在，first_error_step 必须为 null。

只能输出如下 JSON，不要输出 markdown 代码块、解释或其他任何内容：
{
  "has_error": true/false,
  "first_error_step": <整数（从 1 开始计数）或 null>,
  "error_type": "<十类错误之一 或 null（若 has_error 为 false）>",
  "reason": "<简短说明判断理由>"
}

错误类型必须从以下十类中选取：
题意误读、概念理解错误、定理/公式误用、计算错误、条件遗漏、跳步推导、循环论证、幻觉/无中生有、单位/格式不符、其他/无法归类。

审查原则：
1. 步骤必须能从题目条件和前面已证结论逻辑推出；
2. 不允许凭空引入未给出的条件或结论（幻觉/无中生有）；
3. 关键步骤缺失视为跳步推导；
4. 用结论证明结论视为循环论证；
5. 计算错误包括符号、数值、等式不成立；
6. 题意误读以模型建立的数学对象/目标与题面不符为准；
7. 答案错但过程完全成立时，has_error 应为 false（可能是答案等价性问题）；
8. 仅因表述啰嗦但逻辑正确应判为无错误。"""


def load_json(path: Path) -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_jsonl(path: Path) -> List[Dict]:
    data = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                data.append(json.loads(line))
    return data


def parse_json_output(text: str) -> Dict[str, Any]:
    """Extract the JSON object from the model response."""
    text = text.strip()
    # Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Markdown fenced block
    blocks = re.findall(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    for block in blocks:
        try:
            return json.loads(block.strip())
        except json.JSONDecodeError:
            continue
    # Fallback: first '{' to last '}'
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    return {
        "parse_error": True,
        "has_error": None,
        "first_error_step": None,
        "error_type": None,
        "reason": f"无法解析 JSON 输出: {text[:200]}",
    }


def normalize_step(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def normalize_error_type(value: Any) -> Optional[str]:
    if value is None:
        return None
    value = str(value).strip()
    if not value or value in ("无错误", "null", "None"):
        return None
    return value


def build_user_prompt(
    problem: str,
    gold_answer: str,
    final_answer: str,
    steps: List[Dict],
) -> str:
    steps_text = "\n\n".join(
        f"步骤 {s.get('index', i + 1)}：\n{s.get('text', '')}"
        for i, s in enumerate(steps)
    )
    return (
        f"题目：\n{problem}\n\n"
        f"标准答案：{gold_answer}\n\n"
        f"模型最终答案：{final_answer}\n\n"
        f"模型解题过程（按步骤编号）：\n{steps_text}\n\n"
        "请判断该推理链是否存在逻辑、概念或计算错误，并只输出要求的 JSON。"
    )


def _call_auditor(client, messages: List[Dict], max_tokens: int) -> Dict:
    """Single auditor API call; return result item dict."""
    results = client.chat_generate(
        [messages],
        temperature=AUDITOR_TEMPERATURE,
        max_tokens=max_tokens,
    )
    if results:
        return results[0]
    return {"text": "", "finish_reason": None}


def audit_sample(client, item: Dict) -> Dict[str, Any]:
    """Call the auditor for one sample and return parsed audit fields."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(
            problem=item["problem"],
            gold_answer=item["gold_answer"],
            final_answer=item["final_answer"],
            steps=item["steps"],
        )},
    ]
    used_max_tokens = AUDITOR_MAX_TOKENS
    try:
        result = _call_auditor(client, messages, AUDITOR_MAX_TOKENS)
        raw_text = result.get("text", "")
        finish_reason = result.get("finish_reason")
        # If the response is empty because the reasoning model consumed the
        # whole token budget before emitting visible text, retry with a larger
        # budget once while still recording the original attempt.
        if not raw_text.strip() and finish_reason == "length":
            print(f"  {item['problem_id']}: 1024 tokens exhausted, retrying with {FALLBACK_MAX_TOKENS} ...")
            used_max_tokens = FALLBACK_MAX_TOKENS
            result = _call_auditor(client, messages, FALLBACK_MAX_TOKENS)
            raw_text = result.get("text", "")
            finish_reason = result.get("finish_reason")
        audit = parse_json_output(raw_text)
        audit.setdefault("raw_response", raw_text)
        audit.setdefault("finish_reason", finish_reason)
        audit.setdefault("api_error", None)
        audit.setdefault("max_tokens_used", used_max_tokens)
    except Exception as exc:
        audit = {
            "parse_error": True,
            "has_error": None,
            "first_error_step": None,
            "error_type": None,
            "reason": f"API 调用失败: {exc}",
            "raw_response": "",
            "finish_reason": None,
            "api_error": str(exc),
            "max_tokens_used": used_max_tokens,
        }
    return audit


def main():
    # Load data
    evaluation = load_json(EVALUATION_FILE)
    evaluations = evaluation.get("evaluations", [])
    problems = {p["id"]: p for p in load_jsonl(PROBLEMS_FILE)}
    solutions = {s["problem_id"]: s for s in load_jsonl(SOLUTIONS_FILE)}

    # Filter: answer wrong and a standard answer exists; skip manual_check if present
    candidates = []
    for rec in evaluations:
        if rec.get("answer_correct") is not False:
            continue
        if rec.get("manual_check"):
            continue
        gold = rec.get("gold_answer") or ""
        if not str(gold).strip():
            continue
        candidates.append(rec)

    print(f"找到答案错误的候选样本: {len(candidates)}")

    # Random sample (deterministic after sorting by problem_id)
    candidates = sorted(candidates, key=lambda r: r["problem_id"])
    rng = random.Random(RANDOM_SEED)
    sampled_records = rng.sample(candidates, min(SAMPLE_SIZE, len(candidates)))

    # Enrich with problem text, gold answer, and steps
    samples = []
    for rec in sampled_records:
        pid = rec["problem_id"]
        problem = rec.get("problem") or ""
        gold = rec.get("gold_answer") or ""
        if not problem or not gold:
            prob = problems.get(pid, {})
            problem = problem or prob.get("problem", "")
            gold = gold or str(prob.get("answer", ""))
        sol = solutions.get(pid, {})
        steps = sol.get("steps", [])
        if not steps and sol.get("raw_output"):
            # Fallback: treat the whole raw output as a single step
            steps = [{"index": 1, "text": sol["raw_output"]}]
        samples.append({
            "problem_id": pid,
            "level": rec.get("level"),
            "problem": problem,
            "gold_answer": gold,
            "final_answer": rec.get("final_answer", ""),
            "steps": steps,
            "evaluator_first_error_step": normalize_step(rec.get("first_error_step")),
            "evaluator_error_type": normalize_error_type(rec.get("error_type")),
            "evaluator_process_correct": rec.get("process_correct"),
        })

    print(f"随机抽取样本数: {len(samples)}")

    # Initialize auditor client
    client = load_judge_client_from_env()

    # Run audit
    results = []
    for i, item in enumerate(samples, 1):
        print(f"[{i}/{len(samples)}] 审计 {item['problem_id']} ...")
        audit = audit_sample(client, item)
        # Normalize auditor fields
        auditor_has_error = bool(audit.get("has_error"))
        auditor_step = normalize_step(audit.get("first_error_step"))
        auditor_type = normalize_error_type(audit.get("error_type"))
        if not auditor_has_error:
            auditor_step = None
            auditor_type = None

        eval_step = item["evaluator_first_error_step"]
        eval_type = item["evaluator_error_type"]

        exact_match = auditor_has_error and eval_step is not None and auditor_step == eval_step
        pm1_match = (
            auditor_has_error
            and eval_step is not None
            and auditor_step is not None
            and abs(auditor_step - eval_step) == 1
        )
        type_match = (
            auditor_type is not None
            and eval_type is not None
            and auditor_type == eval_type
        )
        evaluator_missed = eval_step is None and auditor_has_error
        evaluator_different_step = (
            auditor_has_error
            and (eval_step is None or auditor_step != eval_step)
        )

        record = {
            **item,
            "auditor_has_error": auditor_has_error,
            "auditor_first_error_step": auditor_step,
            "auditor_error_type": auditor_type,
            "auditor_reason": audit.get("reason", ""),
            "auditor_raw_response": audit.get("raw_response", ""),
            "auditor_finish_reason": audit.get("finish_reason"),
            "auditor_api_error": audit.get("api_error"),
            "auditor_parse_error": audit.get("parse_error", False),
            "auditor_max_tokens_used": audit.get("max_tokens_used", AUDITOR_MAX_TOKENS),
            "exact_step_match": exact_match,
            "pm1_step_match": pm1_match,
            "error_type_match": type_match,
            "evaluator_missed_error": evaluator_missed,
            "evaluator_different_step": evaluator_different_step,
        }
        results.append(record)
        time.sleep(0.1)

    # Compute summary
    total = len(results)
    valid_audits = [r for r in results if r["auditor_has_error"] is not None]
    parse_error_count = total - len(valid_audits)
    fallback_count = sum(1 for r in results if r.get("auditor_max_tokens_used") == FALLBACK_MAX_TOKENS)

    auditor_errors = [r for r in valid_audits if r["auditor_has_error"]]
    evaluator_errors = [r for r in results if r["evaluator_first_error_step"] is not None]
    exact_matches = sum(r["exact_step_match"] for r in valid_audits)
    pm1_matches = sum(r["pm1_step_match"] for r in valid_audits)
    type_matches = sum(r["error_type_match"] for r in valid_audits)

    auditor_error_count = len(auditor_errors)
    evaluator_error_count = len(evaluator_errors)

    exact_rate_over_auditor = exact_matches / auditor_error_count if auditor_error_count else 0.0
    pm1_rate_over_auditor = pm1_matches / auditor_error_count if auditor_error_count else 0.0
    combined_rate_over_auditor = (
        (exact_matches + pm1_matches) / auditor_error_count if auditor_error_count else 0.0
    )

    both_typed = [r for r in valid_audits if r["auditor_error_type"] and r["evaluator_error_type"]]
    type_match_rate = type_matches / len(both_typed) if both_typed else 0.0

    missed = [r for r in valid_audits if r["evaluator_missed_error"]]
    different = [r for r in valid_audits if r["evaluator_different_step"]]

    summary = {
        "total_sampled": total,
        "valid_audits": len(valid_audits),
        "auditor_parse_errors": parse_error_count,
        "auditor_fallback_to_2048_count": fallback_count,
        "auditor_detected_errors": auditor_error_count,
        "evaluator_detected_errors": evaluator_error_count,
        "exact_step_matches": exact_matches,
        "exact_step_match_rate_over_auditor_errors": exact_rate_over_auditor,
        "exact_step_match_rate_over_total": exact_matches / total if total else 0.0,
        "pm1_step_matches": pm1_matches,
        "pm1_step_match_rate_over_auditor_errors": pm1_rate_over_auditor,
        "exact_or_pm1_step_match_rate_over_auditor_errors": combined_rate_over_auditor,
        "error_type_matches": type_matches,
        "error_type_match_rate_over_both_typed": type_match_rate,
        "evaluator_missed_count": len(missed),
        "evaluator_different_step_count": len(different),
    }

    output_data = {
        "metadata": {
            "evaluation_file": str(EVALUATION_FILE.relative_to(ROOT)),
            "dataset_file": str(PROBLEMS_FILE.relative_to(ROOT)),
            "solutions_file": str(SOLUTIONS_FILE.relative_to(ROOT)),
            "output_json": str(OUTPUT_JSON.relative_to(ROOT)),
            "output_report": str(OUTPUT_REPORT.relative_to(ROOT)),
            "random_seed": RANDOM_SEED,
            "sample_size": SAMPLE_SIZE,
            "auditor_model": "gpt-5.6-terra",
            "temperature": AUDITOR_TEMPERATURE,
            "max_tokens": AUDITOR_MAX_TOKENS,
        },
        "summary": summary,
        "samples": results,
    }

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    # Build report
    report_lines = [
        "# 过程评估器真实错题定位准确性验证报告",
        "",
        f"- 审计模型：GPT-5.6-Terra（temperature={AUDITOR_TEMPERATURE}, primary max_tokens={AUDITOR_MAX_TOKENS}）",
        f"- 随机种子：{RANDOM_SEED}",
        f"- 抽取样本数：{total}",
        f"- 来源评估文件：`{output_data['metadata']['evaluation_file']}`",
        "",
        "## 核心指标",
        "",
        f"- 成功获得审计结果：{len(valid_audits)} / {total}",
        f"- 审计解析失败 / 空响应：{parse_error_count} / {total}",
        f"- 因 1024 tokens 耗尽而使用 2048 fallback：{fallback_count} / {total}",
        f"- 审计模型判定存在错误：{auditor_error_count} / {len(valid_audits)} ({auditor_error_count/len(valid_audits):.2%})" if valid_audits else "- 审计模型判定存在错误：0",
        f"- 评估器原判定存在错误：{evaluator_error_count} / {total} ({evaluator_error_count/total:.2%})",
        "",
        "### 首错步匹配",
        "",
        f"- 以审计模型判定有错误为分母：",
        f"  - 完全命中：{exact_matches} / {auditor_error_count} = {exact_rate_over_auditor:.2%}",
        f"  - ±1 步命中：{pm1_matches} / {auditor_error_count} = {pm1_rate_over_auditor:.2%}",
        f"  - 完全或 ±1 命中：{exact_matches + pm1_matches} / {auditor_error_count} = {combined_rate_over_auditor:.2%}",
        f"- 以全部抽取样本为分母：",
        f"  - 完全命中：{exact_matches} / {total} = {exact_matches/total:.2%}",
        "",
        "### 错误类型匹配",
        "",
        f"- 双方均给出错误类型的样本数：{len(both_typed)}",
        f"- 类型一致数：{type_matches} / {len(both_typed)} = {type_match_rate:.2%}",
        "",
        "## 评估器漏检 / 定位偏差案例",
        "",
        f"- 评估器漏检（审计判有错但评估器无首错步）：{len(missed)} 条",
        f"- 评估器定位不同步（含漏检）：{len(different)} 条",
        "",
    ]

    if different:
        report_lines.append("| 题号 | 难度 | 评估器首错步 | 评估器类型 | 审计首错步 | 审计类型 | 备注 |")
        report_lines.append("|------|------|--------------|------------|------------|----------|------|")
        for r in different:
            note = "漏检" if r["evaluator_missed_error"] else "定位偏差"
            report_lines.append(
                f"| {r['problem_id']} | {r['level']} | "
                f"{r['evaluator_first_error_step'] if r['evaluator_first_error_step'] is not None else '—'} | "
                f"{r['evaluator_error_type'] or '—'} | "
                f"{r['auditor_first_error_step'] if r['auditor_first_error_step'] is not None else '—'} | "
                f"{r['auditor_error_type'] or '—'} | {note} |"
            )
    else:
        report_lines.append("未发现评估器漏检或定位偏差。")

    report_lines.extend([
        "",
        "## 样本明细",
        "",
        f"完整样本明细见：`{output_data['metadata']['output_json']}`",
        "",
    ])

    report = "\n".join(report_lines)
    with open(OUTPUT_REPORT, "w", encoding="utf-8") as f:
        f.write(report)

    print("\n" + "=" * 60)
    print(report)
    print("=" * 60)


if __name__ == "__main__":
    main()
