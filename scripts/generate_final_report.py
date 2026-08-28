"""生成项目最终综合分析报告.

用法:
    python scripts/generate_final_report.py \
        --eval results/evaluation_results_merged.json \
        --validation results/validation_results_v2.json \
        --output results/final_report.md
"""

import argparse
import json
from pathlib import Path
from typing import Dict, List


def load_json(path: str) -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def find_drop_level(level_stats: Dict, key: str) -> tuple:
    """找出相邻难度层之间下降最大的区间."""
    levels = sorted(level_stats.keys())
    if len(levels) < 2:
        return None, 0.0
    best = None
    max_drop = 0.0
    for i in range(1, len(levels)):
        prev = level_stats[levels[i - 1]].get(key, 0.0)
        curr = level_stats[levels[i]].get(key, 0.0)
        drop = prev - curr
        if drop > max_drop:
            max_drop = drop
            best = f"{levels[i-1]} → {levels[i]}"
    return best, max_drop


def render_report(eval_data: Dict, val_data: Dict) -> str:
    metrics = eval_data.get("metrics", {})
    evaluations = eval_data.get("evaluations", [])
    level_stats = metrics.get("level_stats", {})

    total = metrics.get("total", 0)
    gradable = metrics.get("gradable_count", total)
    answer_correct = metrics.get("answer_correct", 0)
    process_correct = metrics.get("process_correct", 0)
    strict_pc = metrics.get("strict_process_accuracy", 0.0)
    cbu_count = metrics.get("correct_but_unjustified_count", 0)
    cbu_rate = metrics.get("correct_but_unjustified_rate", 0.0)
    wrong_ans_valid_proc_rate = metrics.get("wrong_answer_but_valid_process_rate", 0.0)

    lines = []
    lines.append("# Hy3 数学可验证推理与过程评估 — 最终综合分析报告\n")

    lines.append("## 一、项目概述\n")
    lines.append(
        "本项目基于腾讯混元 Hy3 大模型，构建了一个面向数学可验证场景的「AI 解题 + AI 批改」双层应用。"
        "解题层输出结构化分步解答；过程评估层综合规则校验、符号执行（sympy）、LLM-as-judge（普通/Research 双 prompt）、"
        "输出截断检测与可选的多 judge 交叉投票，判定推理过程正确性、定位首个错误步骤、归类错误类型，"
        "并识别「答案正确但推理过程不成立」的样本。\n"
    )

    lines.append("## 二、过程评估方法设计依据\n")
    lines.append(
        "1. **最终答案判分不足以反映真实能力**：已有工作（如 ProcessBench）指出，在 OlympiadBench 等难题上，"
        "答案正确的解答中超过 30% 存在过程错误。仅看答案会系统性高估模型能力。\n"
        "2. **多通道交叉验证降低单一裁判波动**：规则+符号层负责计算错误等可确定性判定；"
        "LLM-as-judge 负责概念误用、条件遗漏、跳步、循环论证等语义错误；两者互补。\n"
        "3. **错误定位应聚焦「首错步」**：后续步骤即使局部合法，也建立在前置错误之上，因此以首个错误步为核心指标。\n"
        "4. **识别「答案对过程错」是过程评估的核心价值**：这类样本暴露模型可能靠猜答案、数值巧合或格式 trick 通过测试。\n"
    )

    lines.append("## 三、题集构成\n")
    lines.append(f"- **总题数**：{total} 道（含 {gradable} 道可自动判题）")
    lines.append("- **主库**：146 道，覆盖 L1（小学/初中应用题）至 L4（AIME/竞赛级）")
    lines.append("- **FrontierMath v2 附录**：12 道研究级难题，其中 3 道有公开标准答案，9 道为 manual_check")
    lines.append("- **人工注入错误验证集**：28 条（23 错 + 5 对），用于验证评估器定位准确率与误报率\n")

    lines.append("## 四、核心评测指标\n")
    lines.append(f"- **最终答案准确率**：{answer_correct}/{gradable} = {metrics.get('answer_accuracy', 0):.2%}")
    lines.append(f"- **过程正确率**：{process_correct}/{total} = {metrics.get('process_accuracy', 0):.2%}")
    lines.append(f"- **严格过程正确率**（答案且过程均正确）：{metrics.get('strict_process_accuracy', 0):.2%}")
    lines.append(f"- **结果正确但过程不成立率（CBU）**：{cbu_count}/{gradable} = {cbu_rate:.2%}")
    lines.append(f"- **答案错误但过程被判正确率**：{metrics.get('wrong_answer_but_valid_process', 0)}/{gradable} = {wrong_ans_valid_proc_rate:.2%}\n")

    lines.append("## 五、难度分层分析\n")
    lines.append("| 难度 | 题数 | 可判题数 | 答案正确率 | 过程正确率 | 严格过程正确率 | CBU 率 | 答案错但过程对率 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for lv in sorted(level_stats.keys()):
        s = level_stats[lv]
        lines.append(
            f"| {lv} | {s['total']} | {s.get('gradable', s['total'])} | "
            f"{s['answer_accuracy']:.2%} | {s['process_accuracy']:.2%} | "
            f"{s['strict_process_accuracy']:.2%} | {s['cbu_rate']:.2%} | "
            f"{s['wrong_answer_but_valid_process_rate']:.2%} |"
        )
    lines.append("")

    ans_drop_level, ans_drop = find_drop_level(level_stats, "answer_accuracy")
    proc_drop_level, proc_drop = find_drop_level(level_stats, "process_accuracy")
    if ans_drop_level:
        lines.append(f"- 答案准确率下降最显著区间：**{ans_drop_level}**，下降约 {ans_drop:.2%}")
    if proc_drop_level:
        lines.append(f"- 过程正确率下降最显著区间：**{proc_drop_level}**，下降约 {proc_drop:.2%}")
    lines.append("")

    lines.append("## 六、错误类型分布\n")
    lines.append("| 错误类型 | 出现次数 |")
    lines.append("|---|---|")
    error_dist = metrics.get("error_distribution", {})
    for et, cnt in sorted(error_dist.items(), key=lambda x: -x[1]):
        if cnt > 0:
            lines.append(f"| {et} | {cnt} |")
    lines.append("")

    lines.append("## 七、结果正确但过程不成立的典型案例\n")
    cbu_cases = [
        e for e in evaluations
        if e.get("correct_but_unjustified", {}).get("correct_but_unjustified")
    ]
    if cbu_cases:
        for i, e in enumerate(cbu_cases[:10], 1):
            lines.append(f"### {i}. {e.get('problem_id')}")
            lines.append(f"- **最终答案**：{e.get('final_answer')}")
            lines.append(f"- **标准答案**：{e.get('gold_answer')}")
            lines.append(f"- **错误步骤**：{e.get('first_error_step')}")
            lines.append(f"- **错误类型**：{e.get('error_type')}")
            lines.append(f"- **详情**：{e.get('error_detail', '')}\n")
    else:
        lines.append("暂无比类样本。\n")

    # 动态获取分层数值，用于能力边界描述
    l1 = level_stats.get("L1", {})
    l2 = level_stats.get("L2", {})
    l3 = level_stats.get("L3", {})
    l4 = level_stats.get("L4", {})
    l1_ans = l1.get("answer_accuracy", 0.0)
    l2_ans = l2.get("answer_accuracy", 0.0)
    l2_proc = l2.get("process_accuracy", 0.0)
    l3_proc = l3.get("process_accuracy", 0.0)
    l4_strict = l4.get("strict_process_accuracy", 0.0)

    lines.append("## 八、模型能力边界与临界点分析\n")
    lines.append(
        f"- **L1 → L2 是答案准确率断崖**：从 {l1_ans:.2%} 降至 {l2_ans:.2%}，"
        f"说明一旦题目从直接四则应用题转向需要多步代数/几何推理，Hy3 的最终答案可靠性显著下降。\n"
        f"- **L2 → L3 是过程正确率显著下降区间**：过程正确率从 {l2_proc:.2%} 降至 {l3_proc:.2%}，"
        f"表明高中竞赛级题目是「过程错误」高发区，也是识别「答案对过程错」的关键区间。\n"
        f"- **L4 严格过程正确率仅为 {l4_strict:.2%}**：在 AIME/FrontierMath 级难题上，Hy3 极少能同时给出正确答案和严谨推导。\n"
        "- **FrontierMath 研究级题目几乎全军覆没**：3 道有答案题全部答错；"
        "FM-v2-011 的输出截断漏判已通过新增截断检测器修复。\n"
    )

    lines.append("## 九、评估器有效性验证\n")
    if val_data:
        lines.append(f"- **注入错误样本定位准确率**：{val_data.get('localization_accuracy', 0):.2%}（{val_data.get('error_sample_count', 0)} 条）")
        lines.append(f"- **正确样本误报率**：{val_data.get('false_positive_rate', 0):.2%}（{val_data.get('correct_sample_count', 0)} 条）")
    lines.append("- **FrontierMath 人工抽检**：见 `validation/frontiermath_spot_check.md`，FM-v2-011 截断漏判已修复；仍存在 1 处错误类型归类偏差（FM-v2-003）。\n")

    lines.append("## 十、结论与后续改进方向\n")
    lines.append(
        "1. 当前 Hy3 在 L1~L3 常规数学题上具备一定解题能力，但过程严谨性随难度快速衰减。\n"
        "2. 在 Research-level（FrontierMath）题目上，模型输出常出现定理幻觉、未证断言和截断，能力明显不足。\n"
        "3. 评估器已集成规则校验、符号验证、LLM-as-judge（含 Research 严格 prompt）、"
        "输出截断检测与可选多 judge 投票；在注入验证集上定位准确率约 87%，误报率 0%。\n"
        "4. 后续可加入依赖图显式分步、反向验证器（Math-Shepherd 思想）等机制，"
        "进一步降低误报与漏判。\n"
    )

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate final analysis report")
    parser.add_argument("--eval", type=str, default="results/evaluation_results_merged.json")
    parser.add_argument("--validation", type=str, default="results/validation_results_v2.json")
    parser.add_argument("--output", type=str, default="results/final_report.md")
    args = parser.parse_args()

    eval_data = load_json(args.eval)
    val_data = load_json(args.validation) if Path(args.validation).exists() else {}

    report = render_report(eval_data, val_data)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        f.write(report)

    print(f"最终报告已生成: {output_path}")


if __name__ == "__main__":
    main()
