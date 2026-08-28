"""用改进后的 answer_checker 与 step_validator 重建评估结果，不重新调用 LLM judge.

用法:
    python scripts/rebuild_evaluation.py \
        --solutions results/solutions_merged.jsonl \
        --eval_input results/evaluation_results_merged.json \
        --eval_output results/evaluation_results_merged_fixed.json
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dataset import answer_checker
from evaluator.evaluate import compute_metrics
from evaluator.process_evaluator import ProcessEvaluator, evaluate_record


class StoredLLMJudge:
    """返回预先保存的 LLM judge 结果，避免重复调用模型."""

    def __init__(self, stored_result: Dict[str, Any]):
        self.stored = stored_result or {
            "overall_valid": None,
            "first_error_step": None,
            "error_type": "其他/无法归类",
            "error_detail": "无已保存的 LLM judge 结果",
            "suggestion": "",
        }

    def judge(self, *args, **kwargs) -> Dict[str, Any]:
        return dict(self.stored)

    def judge_batch(self, items: List[Dict], **kwargs) -> List[Dict[str, Any]]:
        return [dict(self.stored) for _ in items]


def load_solutions(path: str) -> Dict[str, Dict[str, Any]]:
    solutions = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            solutions[rec["problem_id"]] = rec
    return solutions


def main():
    parser = argparse.ArgumentParser(description="Rebuild evaluation with fixed checkers")
    parser.add_argument("--solutions", type=str, default="results/solutions_merged.jsonl")
    parser.add_argument("--eval_input", type=str, default="results/evaluation_results_merged.json")
    parser.add_argument("--eval_output", type=str, default="results/evaluation_results_merged_fixed.json")
    args = parser.parse_args()

    solutions = load_solutions(args.solutions)
    with open(args.eval_input, "r", encoding="utf-8") as f:
        old_data = json.load(f)
    old_evaluations = old_data.get("evaluations", [])

    updated = []
    skipped = 0
    for ev in old_evaluations:
        pid = ev.get("problem_id")
        sol = solutions.get(pid)
        if sol is None:
            skipped += 1
            updated.append(ev)
            continue

        # 用新的 answer_checker 重新判定答案
        verification = sol.get("verification", {})
        pred = sol.get("final_answer")
        gold = sol.get("gold_answer")
        answer_ok, answer_detail = answer_checker.check_answer(pred, gold, verification)

        # 构造供 process evaluator 使用的记录
        record = {
            "problem_id": pid,
            "problem": sol.get("problem", ""),
            "level": sol.get("level"),
            "steps": sol.get("steps", []),
            "final_answer": pred,
            "gold_answer": gold,
            "verification": verification,
            "answer_correct": answer_ok,
            "raw_output": sol.get("raw_output"),
            "finish_reason": sol.get("finish_reason"),
            "generation_params": sol.get("generation_params", {}),
            "token_usage": sol.get("token_usage", {}),
        }

        # 用保存的 LLM judge 结果作为语义审查层
        stored_llm = ev.get("llm_judge_result")
        judge = StoredLLMJudge(stored_llm)
        evaluator = ProcessEvaluator(llm_judge=judge)
        new_ev = evaluate_record(record, evaluator, use_llm=True)

        # 保留一些原始审计字段，便于追溯
        new_ev["answer_check_detail"] = answer_detail
        if stored_llm:
            new_ev["llm_judge_result"] = stored_llm
        updated.append(new_ev)

    metrics = compute_metrics(updated)

    output_path = Path(args.eval_output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump({"evaluations": updated, "metrics": metrics}, f, ensure_ascii=False, indent=2)

    print(f"重建完成：共 {len(updated)} 条，跳过 {skipped} 条（未找到对应 solution）")
    print(f"结果保存至：{output_path}")
    print()
    print("整体指标（固定后）：")
    print(f"  总题数: {metrics['total']}")
    print(f"  可判题数: {metrics['gradable_count']}")
    print(f"  答案正确率: {metrics['answer_accuracy']:.2%}")
    print(f"  过程正确率: {metrics['process_accuracy']:.2%}")
    print(f"  严格过程正确率: {metrics['strict_process_accuracy']:.2%}")
    print(f"  CBU 数量: {metrics['correct_but_unjustified_count']}")
    print(f"  CBU 占比: {metrics['correct_but_unjustified_rate']:.2%}")
    print(f"  答案错但过程对: {metrics['wrong_answer_but_valid_process_rate']:.2%}")
    print()
    print("按难度分层：")
    for lv in ["L1", "L2", "L3", "L4"]:
        s = metrics.get("level_stats", {}).get(lv)
        if s:
            print(
                f"  {lv}: 答案正确率={s['answer_accuracy']:.2%}, "
                f"过程正确率={s['process_accuracy']:.2%}, "
                f"严格过程正确率={s['strict_process_accuracy']:.2%}, "
                f"CBU={s['cbu_rate']:.2%}, 答案错但过程对={s['wrong_answer_but_valid_process_rate']:.2%}"
            )


if __name__ == "__main__":
    main()
