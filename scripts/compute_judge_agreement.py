"""计算多 judge 一致率、Cohen's κ，并列出分歧案例.

用法:
    python scripts/compute_judge_agreement.py --input results/evaluation_results_merged_multi_judge_fixed.json
"""

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np


def cohen_kappa(a, b):
    """计算两个二分类序列的 Cohen's κ."""
    n = len(a)
    if n == 0:
        return 0.0
    # 仅考虑明确 true/false 的票
    valid = [(x, y) for x, y in zip(a, b) if x is not None and y is not None]
    if not valid:
        return 0.0
    a_vals = [x for x, _ in valid]
    b_vals = [y for _, y in valid]
    n = len(valid)
    p_a = sum(a_vals) / n
    p_b = sum(b_vals) / n
    p_e = p_a * p_b + (1 - p_a) * (1 - p_b)
    p_o = sum(1 for x, y in valid if x == y) / n
    if p_e >= 0.999999:
        return 1.0 if p_o >= 0.999999 else 0.0
    return (p_o - p_e) / (1 - p_e)


def step_agreement(a, b, tolerance=1):
    """判断两个首错步是否在 tolerance 步内."""
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return abs(a - b) <= tolerance


def main():
    parser = argparse.ArgumentParser(description="Compute multi-judge agreement metrics")
    parser.add_argument("--input", type=str, default="results/evaluation_results_merged_multi_judge.json",
                        help="Path to evaluation results JSON with judge_votes")
    parser.add_argument("--output", type=str, default="results/judge_agreement_stats.json",
                        help="Path to output stats JSON")
    args = parser.parse_args()

    path = args.input
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    evs = data["evaluations"]

    judge_names = ["Hy3", "GPT", "Gemini"]
    votes_list = []
    for e in evs:
        votes = e.get("llm_judge_result", {}).get("judge_votes", [])
        # 补齐长度
        while len(votes) < 3:
            votes.append({"overall_valid": None, "first_error_step": None, "error_type": None})
        votes_list.append(votes)

    # 总体过程正确性一致率
    overalls = [[v.get("overall_valid") for v in votes] for votes in votes_list]
    all_agree = sum(1 for vals in overalls if vals[0] == vals[1] == vals[2] and vals[0] is not None)
    two_agree = sum(
        1
        for vals in overalls
        if None not in vals and (sum(vals) >= 2 or sum(vals) <= 1)
    )
    print(f"三 judge 全部同意: {all_agree} / {len(overalls)} ({all_agree / len(overalls):.1%})")
    print(f"多数一致（≥2 票相同）: {two_agree} / {len(overalls)} ({two_agree / len(overalls):.1%})")

    # 两两一致率与 κ
    print("\n两两过程正确性一致率 / Cohen's κ:")
    for i, j in [(0, 1), (0, 2), (1, 2)]:
        a = [vals[i] for vals in overalls]
        b = [vals[j] for vals in overalls]
        agree = sum(1 for x, y in zip(a, b) if x is not None and y is not None and x == y)
        valid = sum(1 for x, y in zip(a, b) if x is not None and y is not None)
        kappa = cohen_kappa(a, b)
        print(f"  {judge_names[i]} vs {judge_names[j]}: {agree}/{valid} = {agree / valid:.1%}, κ={kappa:.3f}")

    # 错误类型一致率（在至少有一方判错的样本上）
    print("\n错误类型一致率（样本：至少一个 judge 判错）:")
    type_agree = 0
    type_total = 0
    for votes in votes_list:
        vals = [v.get("overall_valid") for v in votes]
        if all(v is True for v in vals):
            continue
        types = [v.get("error_type") for v in votes]
        if types[0] == types[1] == types[2]:
            type_agree += 1
        type_total += 1
    print(f"  三 judge 错误类型全同: {type_agree}/{type_total} ({type_agree / type_total:.1%})")

    # 首错步 ±1 一致率（在判错的样本上）
    print("\n首错步一致率（样本：至少一个 judge 判错）:")
    step_agree_exact = step_agree_pm1 = 0
    step_total = 0
    for votes in votes_list:
        vals = [v.get("overall_valid") for v in votes]
        if all(v is True for v in vals):
            continue
        steps = [v.get("first_error_step") for v in votes]
        if all(s is None for s in steps):
            continue
        step_total += 1
        if steps[0] == steps[1] == steps[2]:
            step_agree_exact += 1
            step_agree_pm1 += 1
        elif all(s is not None for s in steps) and max(steps) - min(steps) <= 1:
            step_agree_pm1 += 1
    print(f"  完全匹配: {step_agree_exact}/{step_total} ({step_agree_exact / step_total:.1%})")
    print(f"  ±1 步内: {step_agree_pm1}/{step_total} ({step_agree_pm1 / step_total:.1%})")

    # 列出分歧案例
    print("\n典型分歧案例（overall_valid 不全相同）:")
    count = 0
    for e, votes in zip(evs, votes_list):
        vals = [v.get("overall_valid") for v in votes]
        if len(set(vals)) > 1 and None not in vals:
            print(f"  {e['problem_id']} {e['level']}: " + ", ".join(
                f"{name}={v.get('overall_valid')}/{v.get('error_type')}/{v.get('first_error_step')}"
                for name, v in zip(judge_names, votes)
            ))
            count += 1
            if count >= 10:
                break

    # 保存统计
    out_path = Path(args.output)
    stats = {
        "total": len(overalls),
        "all_agree_count": all_agree,
        "all_agree_rate": all_agree / len(overalls),
        "majority_agree_count": two_agree,
        "majority_agree_rate": two_agree / len(overalls),
        "pairwise": {},
        "error_type_agree_rate": type_agree / type_total if type_total else 0,
        "first_error_step_exact_rate": step_agree_exact / step_total if step_total else 0,
        "first_error_step_pm1_rate": step_agree_pm1 / step_total if step_total else 0,
    }
    for i, j in [(0, 1), (0, 2), (1, 2)]:
        a = [vals[i] for vals in overalls]
        b = [vals[j] for vals in overalls]
        stats["pairwise"][f"{judge_names[i]}_vs_{judge_names[j]}"] = {
            "agreement_rate": sum(1 for x, y in zip(a, b) if x is not None and y is not None and x == y)
            / sum(1 for x, y in zip(a, b) if x is not None and y is not None),
            "cohens_kappa": cohen_kappa(a, b),
        }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(f"\n统计已保存至 {out_path}")


if __name__ == "__main__":
    main()
