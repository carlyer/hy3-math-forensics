"""评估器有效性验证脚本.

在人工注入错误的标注集上验证：
1. 定位准确率：错误样本中，评估器能否正确指出注入步骤
2. 误报率：正确样本中，评估器错误标记为有问题的比例
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).parent.parent))

from evaluator.llm_judge import LLMJudge
from evaluator.process_evaluator import ProcessEvaluator


def load_labeled(path: str) -> List[Dict]:
    """加载标注验证集."""
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def load_problems(path: str) -> Dict[str, Dict]:
    """加载题库."""
    problems = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            p = json.loads(line)
            problems[p["id"]] = p
    return problems


def validate(
    labeled_path: str,
    problems_path: str,
    evaluator: ProcessEvaluator,
    use_llm: bool = False,
) -> Dict:
    """运行验证并返回指标."""
    records = load_labeled(labeled_path)
    problems = load_problems(problems_path)

    error_samples = [r for r in records if r["error_type"] != "无错误"]
    correct_samples = [r for r in records if r["error_type"] == "无错误"]

    localization_results = []
    false_positive_results = []

    for r in error_samples:
        problem = problems.get(r["problem_id"], {})
        problem_text = problem.get("problem", "")
        eval_result = evaluator.evaluate(
            problem_text,
            r["steps"],
            answer_correct=r.get("answer_correct", True),
            use_llm=use_llm,
        )
        detected_step = eval_result.get("first_error_step")
        expected_step = r.get("expected_first_error_step")
        matched = detected_step == expected_step
        localization_results.append({
            "mutation_id": r["mutation_id"],
            "expected_step": expected_step,
            "detected_step": detected_step,
            "matched": matched,
            "error_type": r["error_type"],
            "eval_error_type": eval_result.get("error_type"),
            "detail": eval_result.get("error_detail"),
        })

    for r in correct_samples:
        problem = problems.get(r["problem_id"], {})
        problem_text = problem.get("problem", "")
        eval_result = evaluator.evaluate(
            problem_text,
            r["steps"],
            answer_correct=r.get("answer_correct", True),
            use_llm=use_llm,
        )
        flagged = not eval_result.get("process_correct", True)
        false_positive_results.append({
            "mutation_id": r["mutation_id"],
            "flagged": flagged,
            "detected_step": eval_result.get("first_error_step"),
            "error_type": eval_result.get("error_type"),
            "detail": eval_result.get("error_detail"),
        })

    localization_accuracy = (
        sum(1 for x in localization_results if x["matched"]) / len(localization_results)
        if localization_results else 0.0
    )
    false_positive_rate = (
        sum(1 for x in false_positive_results if x["flagged"]) / len(false_positive_results)
        if false_positive_results else 0.0
    )

    return {
        "localization_accuracy": localization_accuracy,
        "false_positive_rate": false_positive_rate,
        "error_sample_count": len(error_samples),
        "correct_sample_count": len(correct_samples),
        "localization_details": localization_results,
        "false_positive_details": false_positive_results,
    }


def main():
    parser = argparse.ArgumentParser(description="Validate process evaluator")
    parser.add_argument(
        "--labeled",
        type=str,
        default="dataset/problems_labeled.jsonl",
        help="Path to labeled validation set",
    )
    parser.add_argument(
        "--problems",
        type=str,
        default="dataset/problems.jsonl",
        help="Path to problems jsonl",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="results/validation_results.json",
        help="Path to output validation results",
    )
    parser.add_argument(
        "--use_llm",
        action="store_true",
        help="是否启用 LLM-as-judge",
    )
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    llm_judge = LLMJudge() if args.use_llm else None
    evaluator = ProcessEvaluator(llm_judge=llm_judge)
    result = validate(args.labeled, args.problems, evaluator, use_llm=args.use_llm)

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"验证完成，结果保存至: {output_path}")
    print(f"错误样本数: {result['error_sample_count']}")
    print(f"定位准确率: {result['localization_accuracy']:.2%}")
    print(f"正确样本数: {result['correct_sample_count']}")
    print(f"误报率: {result['false_positive_rate']:.2%}")

    print("\n定位详情:")
    for x in result["localization_details"]:
        status = "✓" if x["matched"] else "✗"
        print(
            f"  {status} {x['mutation_id']}: "
            f"expected={x['expected_step']}, detected={x['detected_step']}, "
            f"type={x['eval_error_type']}"
        )

    print("\n误报详情:")
    for x in result["false_positive_details"]:
        status = "✗ FP" if x["flagged"] else "✓ OK"
        print(f"  {status} {x['mutation_id']}")


if __name__ == "__main__":
    main()
