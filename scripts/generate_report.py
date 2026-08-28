"""根据 evaluation_results.json 生成评测报告.

用法:
    python scripts/generate_report.py \
        --input results/evaluation_results.json \
        --output results/metrics_report.md
"""

import argparse
import json
from pathlib import Path
from typing import Dict, List


def load_results(path: str) -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def render_report(data: Dict) -> str:
    metrics = data.get("metrics", {})
    evaluations = data.get("evaluations", [])

    total = metrics.get("total", 0)
    gradable_count = metrics.get("gradable_count", total)
    answer_correct = metrics.get("answer_correct", 0)
    process_correct = metrics.get("process_correct", 0)
    strict_process_correct = metrics.get("strict_process_correct", 0)
    wrong_answer_but_valid_process = metrics.get("wrong_answer_but_valid_process", 0)
    cbu_count = metrics.get("correct_but_unjustified_count", 0)

    lines = []
    lines.append("# Hy3 数学解题过程评估报告\n")
    lines.append("## 一、核心指标\n")
    lines.append(f"- **总题数**: {total}（其中可自动判题 {gradable_count} 道）")
    lines.append(f"- **最终答案正确数**: {answer_correct} / {gradable_count} ({metrics.get('answer_accuracy', 0):.2%})")
    lines.append(f"- **过程正确数**: {process_correct} / {total} ({metrics.get('process_accuracy', 0):.2%})")
    lines.append(f"- **严格过程正确数**（答案正确且过程正确）: {strict_process_correct} / {gradable_count} ({metrics.get('strict_process_accuracy', 0):.2%})")
    lines.append(f"- **结果正确但过程不成立数**: {cbu_count} / {gradable_count} ({metrics.get('correct_but_unjustified_rate', 0):.2%})")
    lines.append(f"- **答案错误但过程被判正确数**: {wrong_answer_but_valid_process} / {gradable_count} ({metrics.get('wrong_answer_but_valid_process_rate', 0):.2%})")
    lines.append("")
    lines.append("> 说明：过程正确率高于答案正确率，是因为 LLM-as-judge 主要审查步骤间逻辑自洽性；部分题目（尤其选择题）模型得到错误答案但推导链条在局部逻辑上自洽，导致被判定为'过程正确'。严格过程正确率要求答案与过程同时正确，更能反映真实推理能力。\n")

    lines.append("## 二、难度分层分析\n")
    lines.append("| 难度 | 题数 | 答案正确率 | 过程正确率 | 严格过程正确率 | 结果正确但过程不成立率 | 答案错但过程对率 |")
    lines.append("|---|---|---|---|---|---|---|")
    level_stats = metrics.get("level_stats", {})
    for lv in sorted(level_stats.keys()):
        s = level_stats[lv]
        lines.append(
            f"| {lv} | {s['total']} | {s['answer_accuracy']:.2%} | "
            f"{s['process_accuracy']:.2%} | {s['strict_process_accuracy']:.2%} | "
            f"{s['cbu_rate']:.2%} | {s['wrong_answer_but_valid_process_rate']:.2%} |"
        )
    lines.append("")

    lines.append("## 三、错误类型分布\n")
    lines.append("| 错误类型 | 出现次数 |")
    lines.append("|---|---|")
    error_dist = metrics.get("error_distribution", {})
    # 按次数降序
    for et, cnt in sorted(error_dist.items(), key=lambda x: -x[1]):
        if cnt > 0:
            lines.append(f"| {et} | {cnt} |")
    lines.append("")

    lines.append("## 四、结果正确但过程不成立的典型案例\n")
    cbu_cases = [
        e for e in evaluations
        if e.get("correct_but_unjustified", {}).get("correct_but_unjustified")
    ]
    if cbu_cases:
        for i, e in enumerate(cbu_cases[:10], 1):
            lines.append(f"### {i}. {e.get('problem_id')}")
            lines.append(f"- **最终答案**: {e.get('final_answer')}")
            lines.append(f"- **标准答案**: {e.get('gold_answer')}")
            lines.append(f"- **错误步骤**: {e.get('first_error_step')}")
            lines.append(f"- **错误类型**: {e.get('error_type')}")
            lines.append(f"- **详情**: {e.get('error_detail', '')}\n")
    else:
        lines.append("暂无比类样本。\n")

    lines.append("## 五、模型能力边界与临界点分析\n")
    # 简单自动分析：找出准确率下降最大的相邻难度区间
    levels = sorted(level_stats.keys())
    if len(levels) >= 2:
        max_drop_level = None
        max_drop = 0.0
        for i in range(1, len(levels)):
            prev_acc = level_stats[levels[i - 1]]["answer_accuracy"]
            curr_acc = level_stats[levels[i]]["answer_accuracy"]
            drop = prev_acc - curr_acc
            if drop > max_drop:
                max_drop = drop
                max_drop_level = f"{levels[i-1]} → {levels[i]}"
        if max_drop_level:
            lines.append(f"- 答案准确率下降最显著的区间：**{max_drop_level}**，下降约 {max_drop:.2%}")
        max_proc_drop = 0.0
        max_proc_drop_level = None
        for i in range(1, len(levels)):
            prev = level_stats[levels[i - 1]]["process_accuracy"]
            curr = level_stats[levels[i]]["process_accuracy"]
            drop = prev - curr
            if drop > max_proc_drop:
                max_proc_drop = drop
                max_proc_drop_level = f"{levels[i-1]} → {levels[i]}"
        if max_proc_drop_level:
            lines.append(f"- 过程正确率下降最显著的区间：**{max_proc_drop_level}**，下降约 {max_proc_drop:.2%}")
    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate evaluation report")
    parser.add_argument(
        "--input",
        type=str,
        default="results/evaluation_results.json",
        help="Path to evaluation_results.json",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="results/metrics_report.md",
        help="Path to output markdown report",
    )
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    data = load_results(args.input)
    report = render_report(data)

    with output_path.open("w", encoding="utf-8") as f:
        f.write(report)

    print(f"报告已生成: {output_path}")


if __name__ == "__main__":
    main()
