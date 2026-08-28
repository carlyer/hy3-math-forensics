"""批量过程评估脚本.

用法:
    python evaluator/evaluate.py \
        --input results/solutions.jsonl \
        --output results/evaluation_results.json \
        --use_llm
"""

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).parent.parent))

# 自动加载 .env，确保多 judge 配置生效
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    try:
        from dotenv import load_dotenv

        load_dotenv(env_path, override=False)
    except ImportError:
        pass

from tqdm import tqdm

from evaluator.error_classifier import aggregate_error_distribution
from evaluator.llm_judge import LLMJudge
from evaluator.multi_judge import MultiLLMJudge
from evaluator.process_evaluator import ProcessEvaluator, evaluate_record


def load_solutions(path: str) -> List[Dict]:
    """加载模型生成的解题结果."""
    solutions = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                solutions.append(json.loads(line))
    return solutions


def compute_metrics(evaluations: List[Dict]) -> Dict:
    """计算核心指标.

    注意：answer_correct 可能为 None（如 manual_check 题），此时不计入答案相关指标。
    """
    total = len(evaluations)
    if total == 0:
        return {}

    gradable = [e for e in evaluations if e.get("answer_correct") is not None]
    gradable_count = len(gradable)

    answer_correct = sum(1 for e in gradable if e["answer_correct"])
    process_correct = sum(1 for e in evaluations if e.get("process_correct"))
    # 严格过程正确：答案正确且过程也正确（仅在可判题上统计）
    strict_process_correct = sum(
        1 for e in gradable if e["answer_correct"] and e.get("process_correct")
    )
    # 答案错误但过程被判正确：通常意味着评估器漏判了隐藏错误
    wrong_answer_but_valid_process = sum(
        1 for e in gradable if not e["answer_correct"] and e.get("process_correct")
    )
    cbu = sum(
        1
        for e in gradable
        if e["answer_correct"]
        and e.get("correct_but_unjustified", {}).get("correct_but_unjustified")
    )

    # 按难度分层
    level_stats = {}
    for e in evaluations:
        lv = e.get("level", "unknown")
        if lv not in level_stats:
            level_stats[lv] = {
                "total": 0,
                "gradable": 0,
                "answer_correct": 0,
                "process_correct": 0,
                "strict_process_correct": 0,
                "wrong_answer_but_valid_process": 0,
                "cbu": 0,
            }
        level_stats[lv]["total"] += 1
        is_gradable = e.get("answer_correct") is not None
        if is_gradable:
            level_stats[lv]["gradable"] += 1
        if is_gradable and e["answer_correct"]:
            level_stats[lv]["answer_correct"] += 1
        if e.get("process_correct"):
            level_stats[lv]["process_correct"] += 1
        if is_gradable and e["answer_correct"] and e.get("process_correct"):
            level_stats[lv]["strict_process_correct"] += 1
        if is_gradable and not e["answer_correct"] and e.get("process_correct"):
            level_stats[lv]["wrong_answer_but_valid_process"] += 1
        if is_gradable and e["answer_correct"] and e.get("correct_but_unjustified", {}).get("correct_but_unjustified"):
            level_stats[lv]["cbu"] += 1

    for lv, stats in level_stats.items():
        stats["answer_accuracy"] = (
            stats["answer_correct"] / stats["gradable"] if stats["gradable"] else 0.0
        )
        stats["process_accuracy"] = stats["process_correct"] / stats["total"]
        stats["strict_process_accuracy"] = (
            stats["strict_process_correct"] / stats["gradable"] if stats["gradable"] else 0.0
        )
        stats["wrong_answer_but_valid_process_rate"] = (
            stats["wrong_answer_but_valid_process"] / stats["gradable"] if stats["gradable"] else 0.0
        )
        stats["cbu_rate"] = stats["cbu"] / stats["gradable"] if stats["gradable"] else 0.0

    return {
        "total": total,
        "gradable_count": gradable_count,
        "answer_correct": answer_correct,
        "process_correct": process_correct,
        "strict_process_correct": strict_process_correct,
        "wrong_answer_but_valid_process": wrong_answer_but_valid_process,
        "correct_but_unjustified_count": cbu,
        "answer_accuracy": answer_correct / gradable_count if gradable_count else 0.0,
        "process_accuracy": process_correct / total if total else 0.0,
        "strict_process_accuracy": strict_process_correct / gradable_count if gradable_count else 0.0,
        "wrong_answer_but_valid_process_rate": wrong_answer_but_valid_process / gradable_count if gradable_count else 0.0,
        "correct_but_unjustified_rate": cbu / gradable_count if gradable_count else 0.0,
        "level_stats": level_stats,
        "error_distribution": aggregate_error_distribution(evaluations),
    }


def main():
    parser = argparse.ArgumentParser(description="Evaluate generated math solutions")
    parser.add_argument(
        "--input",
        type=str,
        default="results/solutions.jsonl",
        help="Path to solutions jsonl",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="results/evaluation_results.json",
        help="Path to output evaluation results",
    )
    parser.add_argument(
        "--use_llm",
        action="store_true",
        help="是否启用 LLM-as-judge（需要模型已加载）",
    )
    parser.add_argument(
        "--batch_size",
        type=int,
        default=8,
        help="LLM judge 批大小（当前对单 judge 生效）",
    )
    parser.add_argument(
        "--multi_judge",
        action="store_true",
        help="启用多 judge 交叉复核（通过 JUDGE_* 环境变量配置）",
    )
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"加载解题结果: {args.input}")
    solutions = load_solutions(args.input)
    print(f"共 {len(solutions)} 条")

    if args.use_llm:
        if args.multi_judge:
            print("启用多 judge 交叉复核...")
            llm_judge = MultiLLMJudge()
        else:
            llm_judge = LLMJudge()
    else:
        llm_judge = None
    evaluator = ProcessEvaluator(llm_judge=llm_judge)

    print(f"开始过程评估（并发数={args.batch_size}）...")
    evaluations = [None] * len(solutions)

    def _eval_one(idx, record):
        return idx, evaluate_record(record, evaluator, use_llm=args.use_llm)

    with ThreadPoolExecutor(max_workers=args.batch_size) as executor:
        futures = {
            executor.submit(_eval_one, idx, record): idx
            for idx, record in enumerate(solutions)
        }
        for future in tqdm(as_completed(futures), total=len(futures), desc="Evaluating"):
            idx = futures[future]
            try:
                _, ev = future.result()
                evaluations[idx] = ev
            except Exception as e:
                evaluations[idx] = {
                    "problem_id": solutions[idx].get("problem_id", f"unknown-{idx}"),
                    "error": str(e),
                }

    # 过滤掉异常记录，保证 compute_metrics 输入干净
    valid_evaluations = [e for e in evaluations if e is not None and "error" not in e]
    if len(valid_evaluations) < len(evaluations):
        print(f"警告: {len(evaluations) - len(valid_evaluations)} 条评估异常，已剔除")

    metrics = compute_metrics(valid_evaluations)

    result = {
        "evaluations": evaluations,
        "metrics": metrics,
    }

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n评估完成，结果保存至: {output_path}")
    print(f"总题数: {metrics['total']}")
    print(f"答案正确率: {metrics['answer_accuracy']:.2%}")
    print(f"过程正确率: {metrics['process_accuracy']:.2%}")
    print(f"结果正确但过程不成立: {metrics['correct_but_unjustified_rate']:.2%}")


if __name__ == "__main__":
    main()
