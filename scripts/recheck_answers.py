"""在不重新调用 LLM judge 的情况下，用改进后的答案校验器重新判定答案正确性.

用法:
    python scripts/recheck_answers.py \
        --solutions results/solutions_merged.jsonl \
        --eval_input results/evaluation_results_merged.json \
        --eval_output results/evaluation_results_merged_rechecked.json
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dataset import answer_checker
from evaluator.correct_but_wrong_process import detect_correct_but_unjustified
from evaluator.evaluate import compute_metrics


def load_solutions(path: str) -> Dict[str, Dict[str, Any]]:
    """按 problem_id 索引解题结果."""
    solutions = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            solutions[rec["problem_id"]] = rec
    return solutions


def load_evaluations(path: str) -> List[Dict[str, Any]]:
    """加载已有评估结果中的 evaluations 列表."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("evaluations", [])


def main():
    parser = argparse.ArgumentParser(description="Recheck answer correctness with improved checker")
    parser.add_argument(
        "--solutions",
        type=str,
        default="results/solutions_merged.jsonl",
        help="Path to solutions jsonl",
    )
    parser.add_argument(
        "--eval_input",
        type=str,
        default="results/evaluation_results_merged.json",
        help="Path to original evaluation results",
    )
    parser.add_argument(
        "--eval_output",
        type=str,
        default="results/evaluation_results_merged_rechecked.json",
        help="Path to rechecked evaluation results",
    )
    args = parser.parse_args()

    solutions = load_solutions(args.solutions)
    evaluations = load_evaluations(args.eval_input)

    updated = []
    skipped = 0
    for ev in evaluations:
        pid = ev.get("problem_id")
        sol = solutions.get(pid)
        if sol is None:
            skipped += 1
            updated.append(ev)
            continue

        verification = sol.get("verification", {})
        pred = sol.get("final_answer")
        gold = sol.get("gold_answer")

        answer_ok, answer_detail = answer_checker.check_answer(pred, gold, verification)

        # 保留原评估中的过程判定，仅更新答案相关字段
        new_ev = dict(ev)
        new_ev["answer_correct"] = answer_ok
        new_ev["final_answer"] = pred
        new_ev["gold_answer"] = gold
        if answer_detail:
            new_ev["answer_check_detail"] = answer_detail

        cbu = detect_correct_but_unjustified(
            bool(answer_ok) if answer_ok is not None else False,
            bool(new_ev.get("process_correct")),
            new_ev.get("first_error_step"),
        )
        new_ev["correct_but_unjustified"] = cbu
        updated.append(new_ev)

    metrics = compute_metrics(updated)

    output_path = Path(args.eval_output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump({"evaluations": updated, "metrics": metrics}, f, ensure_ascii=False, indent=2)

    print(f"重新判定完成：共 {len(updated)} 条，跳过 {skipped} 条（未找到对应 solution）")
    print(f"结果保存至：{output_path}")
    print()
    print("整体指标：")
    print(f"  总题数: {metrics['total']}")
    print(f"  可判题数: {metrics['gradable_count']}")
    print(f"  答案正确率: {metrics['answer_accuracy']:.2%}")
    print(f"  过程正确率: {metrics['process_accuracy']:.2%}")
    print(f"  CBU 数量: {metrics['correct_but_unjustified_count']}")
    print(f"  CBU 占比: {metrics['correct_but_unjustified_rate']:.2%}")

    l2 = metrics.get("level_stats", {}).get("L2")
    if l2:
        print()
        print("L2 指标：")
        print(f"  总题数: {l2['total']}")
        print(f"  可判题数: {l2['gradable']}")
        print(f"  答案正确率: {l2['answer_accuracy']:.2%}")
        print(f"  过程正确率: {l2['process_accuracy']:.2%}")
        print(f"  CBU 数量: {l2['cbu']}")
        print(f"  CBU 占比: {l2['cbu_rate']:.2%}")


if __name__ == "__main__":
    main()
