"""测试单一 judge（Hy3）在相同样本上重复评估的稳定性."""

import json
import random
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from evaluator.llm_judge import LLMJudge


def main():
    sample_size = 20
    random.seed(42)
    with open("results/solutions_merged.jsonl", "r", encoding="utf-8") as f:
        solutions = [json.loads(l) for l in f if l.strip()]
    sample = random.sample(solutions, sample_size)

    judge = LLMJudge()
    runs = []
    for run_id in range(3):
        print(f"Run {run_id + 1}...")
        results = []
        for rec in sample:
            res = judge.judge(
                rec["problem"],
                rec.get("steps", []),
                level=rec.get("level"),
                temperature=0.2,
                max_tokens=1024,
            )
            results.append(
                {
                    "problem_id": rec["problem_id"],
                    "level": rec.get("level"),
                    "overall_valid": res.get("overall_valid"),
                    "first_error_step": res.get("first_error_step"),
                    "error_type": res.get("error_type"),
                }
            )
        runs.append(results)

    # 比较三次结果
    exact_valid_agree = 0
    step_exact_agree = 0
    step_pm1_agree = 0
    type_agree = 0
    changed = 0
    for i in range(sample_size):
        vals = [runs[r][i]["overall_valid"] for r in range(3)]
        steps = [runs[r][i]["first_error_step"] for r in range(3)]
        types = [runs[r][i]["error_type"] for r in range(3)]
        if vals[0] == vals[1] == vals[2]:
            exact_valid_agree += 1
        else:
            changed += 1
        if steps[0] == steps[1] == steps[2]:
            step_exact_agree += 1
        if all(s is None for s in steps) or (all(s is not None for s in steps) and max(steps) - min(steps) <= 1):
            step_pm1_agree += 1
        if types[0] == types[1] == types[2]:
            type_agree += 1

    print(f"\n样本数: {sample_size}")
    print(f"三次 overall_valid 完全一致: {exact_valid_agree}/{sample_size} ({exact_valid_agree / sample_size:.1%})")
    print(f"三次首错步完全匹配: {step_exact_agree}/{sample_size} ({step_exact_agree / sample_size:.1%})")
    print(f"三次首错步 ±1 内: {step_pm1_agree}/{sample_size} ({step_pm1_agree / sample_size:.1%})")
    print(f"三次错误类型一致: {type_agree}/{sample_size} ({type_agree / sample_size:.1%})")
    print(f"发生变动的样本数: {changed}")

    out_path = Path("results/single_judge_stability.json")
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "sample_size": sample_size,
                "overall_valid_agree": exact_valid_agree,
                "overall_valid_agree_rate": exact_valid_agree / sample_size,
                "step_exact_agree": step_exact_agree,
                "step_pm1_agree": step_pm1_agree,
                "type_agree": type_agree,
                "changed_count": changed,
                "runs": runs,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"结果保存至 {out_path}")


if __name__ == "__main__":
    main()
