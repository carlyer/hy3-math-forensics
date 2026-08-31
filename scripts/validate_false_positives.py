#!/usr/bin/env python3
"""Validate the false-positive rate of the process evaluator on Hy3 samples.

Filter: answer_correct == True and process_correct == True, excluding
manual_check problems. Randomly sample up to 35 records (seed 42) and ask
GPT-5.6-Terra (as the human auditor) whether the reasoning process is truly
valid despite the correct final answer.

Outputs:
  results/validation_false_positives.json
  results/validation_false_positives_report.md
"""

import json
import random
import re
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.hy3_client import load_judge_client_from_env


EVAL_PATH = ROOT / "results" / "evaluation_results_merged_gpt_judge.json"
PROBLEMS_PATH = ROOT / "dataset" / "problems_merged.jsonl"
SOLUTIONS_PATH = ROOT / "results" / "solutions_merged.jsonl"

DETAILED_OUTPUT_PATH = ROOT / "results" / "validation_false_positives.json"
REPORT_PATH = ROOT / "results" / "validation_false_positives_report.md"

SAMPLE_SIZE = 35
RANDOM_SEED = 42
BATCH_SIZE = 4

AUDITOR_SYSTEM_PROMPT = """你是一位极其严格的数学解题过程审计专家。用户会提供一道题目、标准答案、模型给出的最终答案以及模型的分步解题过程。

最终答案虽然与标准答案一致，但你必须独立审查推理过程是否真正成立。请重点检查：跳步、循环论证、定理/公式误用、条件遗漏、幻觉/无中生有、计算错误、符号或单位错误等。

请只输出纯 JSON，不要输出 markdown 代码块、解释或其他任何内容。"""


def build_user_prompt(item: Dict[str, Any]) -> str:
    problem = item.get("problem", "")
    gold_answer = item.get("gold_answer", "")
    final_answer = item.get("final_answer", "")
    steps = item.get("steps", [])

    steps_text = "\n\n".join(
        f"步骤 {s.get('index', i + 1)}：\n{s.get('text', '')}"
        for i, s in enumerate(steps)
    )
    if not steps_text:
        steps_text = "（无分步信息）"

    return (
        f"题目：\n{problem}\n\n"
        f"标准答案：{gold_answer}\n"
        f"模型最终答案：{final_answer}\n\n"
        f"模型解题过程：\n{steps_text}\n\n"
        "最终答案是正确的，但请你严格审查模型的推理过程是否真正成立。"
        "是否存在跳步、循环论证、定理误用、条件遗漏、幻觉等问题？\n"
        "请只输出 JSON：\n"
        '{"truly_valid": true/false, "issue_step": int 或 null, "issue_type": "...", "reason": "..."}'
    )


def parse_json_output(text: str) -> Dict[str, Any]:
    text = text.strip()
    # Direct parse first.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try to extract from markdown code blocks.
    blocks = re.findall(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    for block in blocks:
        try:
            return json.loads(block.strip())
        except json.JSONDecodeError:
            continue
    # Last resort: grab the first JSON-ish object.
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return {
        "truly_valid": None,
        "issue_step": None,
        "issue_type": "解析失败",
        "reason": f"无法解析为 JSON：{text[:200]}",
    }


def load_evaluations(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("evaluations", [])


def load_problems(path: Path) -> Dict[str, Dict[str, Any]]:
    problems = {}
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            p = json.loads(line)
            problems[p["id"]] = p
    return problems


def load_solutions(path: Path) -> Dict[str, Dict[str, Any]]:
    solutions = {}
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            s = json.loads(line)
            solutions[s["problem_id"]] = s
    return solutions


def is_manual_check(problem: Dict[str, Any]) -> bool:
    return problem.get("verification", {}).get("method") == "manual_check"


def merge_record(eval_rec: Dict[str, Any], problem: Dict[str, Any], solution: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "problem_id": eval_rec["problem_id"],
        "level": eval_rec.get("level", problem.get("level")),
        "problem": problem.get("problem", ""),
        "gold_answer": eval_rec.get("gold_answer", problem.get("answer", "")),
        "final_answer": eval_rec.get("final_answer", solution.get("final_answer", "")),
        "steps": solution.get("steps", []),
        "evaluator_error_type": eval_rec.get("error_type", ""),
        "evaluator_first_error_step": eval_rec.get("first_error_step"),
        "answer_correct": eval_rec.get("answer_correct"),
        "process_correct": eval_rec.get("process_correct"),
    }


def run_audit(items: List[Dict[str, Any]], client, batch_size: int = BATCH_SIZE) -> List[Dict[str, Any]]:
    results = []
    batch_messages: List[List[Dict[str, str]]] = []
    batch_items: List[Dict[str, Any]] = []

    def flush_batch():
        nonlocal batch_messages, batch_items
        if not batch_messages:
            return
        try:
            api_results = client.chat_generate(
                batch_messages,
                temperature=0.2,
                max_tokens=1024,
            )
        except Exception as exc:
            print(f"  批次 API 调用失败：{exc}", file=sys.stderr)
            for item in batch_items:
                item["audit"] = {
                    "truly_valid": None,
                    "issue_step": None,
                    "issue_type": "API 调用失败",
                    "reason": str(exc),
                    "raw_output": "",
                }
                results.append(item)
            batch_messages = []
            batch_items = []
            return

        for item, res in zip(batch_items, api_results):
            raw_text = res.get("text", "")
            audit = parse_json_output(raw_text)
            audit.setdefault("truly_valid", None)
            audit.setdefault("issue_step", None)
            audit.setdefault("issue_type", "")
            audit.setdefault("reason", "")
            audit["raw_output"] = raw_text
            item["audit"] = audit
            results.append(item)
        batch_messages = []
        batch_items = []

    for idx, item in enumerate(items, 1):
        messages = [
            {"role": "system", "content": AUDITOR_SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(item)},
        ]
        batch_messages.append(messages)
        batch_items.append(item)
        print(f"  准备审计 {idx}/{len(items)}: {item['problem_id']}")
        if len(batch_messages) >= batch_size:
            flush_batch()
            time.sleep(0.2)

    flush_batch()
    return results


def compute_metrics(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(results)
    valid_audits = [r for r in results if r["audit"].get("truly_valid") is not None]
    valid_total = len(valid_audits)

    flagged = [r for r in valid_audits if r["audit"]["truly_valid"] is False]
    agreed = [r for r in valid_audits if r["audit"]["truly_valid"] is True]

    false_positive_rate = len(flagged) / valid_total if valid_total else 0.0
    agreement_rate = len(agreed) / valid_total if valid_total else 0.0

    issue_type_counter = Counter(
        r["audit"].get("issue_type", "") for r in flagged
    )

    level_counter = Counter(r["level"] for r in results)
    flagged_level_counter = Counter(r["level"] for r in flagged)

    return {
        "total_sampled": total,
        "valid_audits": valid_total,
        "flagged_count": len(flagged),
        "agreed_count": len(agreed),
        "false_positive_rate": false_positive_rate,
        "auditor_agreement_rate": agreement_rate,
        "issue_type_distribution": dict(issue_type_counter),
        "level_distribution": dict(level_counter),
        "flagged_level_distribution": dict(flagged_level_counter),
    }


def build_report(metrics: Dict[str, Any], results: List[Dict[str, Any]]) -> str:
    lines = [
        "# 过程评估器假阳性率验证报告",
        "",
        f"生成时间：{datetime.now().isoformat()}",
        f"审计模型：GPT-5.6-Terra",
        f"输入评估结果：`results/evaluation_results_merged_gpt_judge.json`",
        "",
        "## 摘要",
        "",
        f"- 采样总数：{metrics['total_sampled']}",
        f"- 有效审计数：{metrics['valid_audits']}",
        f"- 审计判定过程不真正成立（假阳性）数：{metrics['flagged_count']}",
        f"- 审计判定过程真正成立（与评估器一致）数：{metrics['agreed_count']}",
        f"- **过程评估器假阳性率**：{metrics['false_positive_rate']:.1%}",
        f"- **审计与评估器一致率**：{metrics['auditor_agreement_rate']:.1%}",
        "",
        "## 问题类型分布（被审计 flagged）",
        "",
    ]
    if metrics["issue_type_distribution"]:
        for issue_type, count in metrics["issue_type_distribution"].items():
            lines.append(f"- {issue_type or '（未指定）'}：{count}")
    else:
        lines.append("- 无")
    lines.append("")

    lines.extend([
        "## 等级分布",
        "",
        "| 等级 | 采样数 | 被 flagged 数 |",
        "|------|--------|---------------|",
    ])
    for level in sorted(metrics["level_distribution"].keys()):
        total = metrics["level_distribution"].get(level, 0)
        flagged = metrics["flagged_level_distribution"].get(level, 0)
        lines.append(f"| {level} | {total} | {flagged} |")
    lines.append("")

    lines.extend([
        "## 被 flagged 的样本详情",
        "",
    ])
    flagged = [r for r in results if r["audit"].get("truly_valid") is False]
    if flagged:
        for r in flagged:
            audit = r["audit"]
            lines.append(
                f"- `{r['problem_id']}`（{r['level']}）"
                f" issue_step={audit.get('issue_step')}, issue_type={audit.get('issue_type')!r}"
            )
            lines.append(f"  - 原因：{audit.get('reason', '')}")
    else:
        lines.append("- 无")
    lines.append("")

    lines.extend([
        "## 方法说明",
        "",
        "1. 从 `evaluation_results_merged_gpt_judge.json` 中筛选 `answer_correct == true` 且 `process_correct == true` 的记录；",
        "2. 排除 `verification.method == 'manual_check'` 的题目；",
        f"3. 使用随机种子 {RANDOM_SEED} 无放回抽取最多 {SAMPLE_SIZE} 条；",
        "4. 将题目、标准答案、模型最终答案及分步过程输入 GPT-5.6-Terra；",
        "5. 要求模型仅输出 JSON：`{truly_valid, issue_step, issue_type, reason}`；",
        "6. 假阳性率 = `flagged 数 / 有效审计数`。",
        "",
        f"详细结果已保存至：`{DETAILED_OUTPUT_PATH.relative_to(ROOT)}`",
    ])
    return "\n".join(lines)


def main():
    print("加载评估结果、题目与解题过程...")
    evaluations = load_evaluations(EVAL_PATH)
    problems = load_problems(PROBLEMS_PATH)
    solutions = load_solutions(SOLUTIONS_PATH)
    print(f"  评估记录：{len(evaluations)} 条")
    print(f"  题目记录：{len(problems)} 条")
    print(f"  解题记录：{len(solutions)} 条")

    filtered = []
    for rec in evaluations:
        if rec.get("answer_correct") is not True:
            continue
        if rec.get("process_correct") is not True:
            continue
        pid = rec["problem_id"]
        problem = problems.get(pid)
        if problem is None:
            print(f"  警告：找不到题目 {pid}，跳过")
            continue
        if is_manual_check(problem):
            continue
        solution = solutions.get(pid, {})
        merged = merge_record(rec, problem, solution)
        filtered.append(merged)

    print(f"符合条件（answer_correct=True, process_correct=True, 非 manual_check）：{len(filtered)} 条")

    rng = random.Random(RANDOM_SEED)
    sampled = rng.sample(filtered, min(SAMPLE_SIZE, len(filtered)))
    print(f"随机采样（seed={RANDOM_SEED}）：{len(sampled)} 条")

    print("初始化 GPT 审计客户端...")
    client = load_judge_client_from_env()

    print("开始审计...")
    audited_results = run_audit(sampled, client)

    metrics = compute_metrics(audited_results)
    report = build_report(metrics, audited_results)

    # Save detailed JSON.
    DETAILED_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with DETAILED_OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "metadata": {
                    "generated_at": datetime.now().isoformat(),
                    "auditor_model": "gpt-5.6-terra",
                    "sample_size": len(sampled),
                    "random_seed": RANDOM_SEED,
                    "metrics": metrics,
                },
                "results": audited_results,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    # Save markdown report.
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with REPORT_PATH.open("w", encoding="utf-8") as f:
        f.write(report)

    print("\n" + "=" * 60)
    print(report)
    print("=" * 60)
    print(f"\n详细结果已保存至：{DETAILED_OUTPUT_PATH}")
    print(f"报告已保存至：{REPORT_PATH}")


if __name__ == "__main__":
    main()
