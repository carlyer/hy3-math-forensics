#!/usr/bin/env python3
"""生成 README 可视化图表（assets/figures/*.png）。

数据来源（均为真实实验结果，脚本可复跑）：
- results/evaluation_merged_full_enriched.json     418 题单裁判（GPT-5.6-terra）评估结果
- results/evaluation_merged_full_multi_judge.json  418 题三裁判（Hy3+GPT+Gemini）投票结果
- dataset/problems_merged_full.jsonl               418 题题集（多维标签）
- results/consistency_analysis_subset_small.json   多采样一致性（20 题 × 3 样本）
- README.md 中的扰动对照 / 有效性验证 / 迭代记录表（图表 6/9/10 的数值取自这些表格）

用法：python scripts/generate_figures.py
"""

import json
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
DATASET = ROOT / "dataset"
OUT = ROOT / "assets" / "figures"
OUT.mkdir(parents=True, exist_ok=True)

# 中文字体（系统装有 Noto Sans CJK SC）
plt.rcParams["font.sans-serif"] = ["Noto Sans CJK SC", "Noto Sans CJK JP", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 150
plt.rcParams["savefig.dpi"] = 150
plt.rcParams["axes.spines.top"] = False
plt.rcParams["axes.spines.right"] = False

# 统一配色
C_MAIN = "#4C78A8"   # 蓝
C_ALT = "#F58518"    # 橙
C_GREEN = "#54A24B"  # 绿
C_RED = "#E45756"    # 红
C_PURPLE = "#B279A2"
C_GRAY = "#9D9DA5"
LEVEL_COLORS = {"L1": "#54A24B", "L2": "#4C78A8", "L3": "#F58518", "L4": "#E45756"}
RISK_COLORS = {"high": "#E45756", "medium": "#F2CF5B", "low": "#54A24B"}
RISK_LABELS = {"high": "high（高）", "medium": "medium（中）", "low": "low（低）"}


def save(fig, name):
    path = OUT / name
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"saved {path} ({path.stat().st_size / 1024:.0f} KB)")


def load_json(name):
    return json.load(open(RESULTS / name, encoding="utf-8"))


# ---------------------------------------------------------------- 数据加载
ENRICHED = load_json("evaluation_merged_full_enriched.json")
MULTI = load_json("evaluation_merged_full_multi_judge.json")
CONSISTENCY = load_json("consistency_analysis_subset_small.json")
PROBLEMS = [json.loads(l) for l in open(DATASET / "problems_merged_full.jsonl", encoding="utf-8")]

LEVELS = ["L1", "L2", "L3", "L4"]


# --------------------------------------------- 1. dataset_composition.png
def fig_dataset_composition():
    groups = Counter(r["dataset_group"] for r in PROBLEMS)
    levels = Counter(r["level"] for r in PROBLEMS)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.2))

    labels = ["original_158", "ext_228", "perturbation_32"]
    sizes = [groups[k] for k in labels]
    colors = [C_MAIN, C_ALT, C_PURPLE]
    wedges, _, autotexts = ax1.pie(
        sizes, labels=[f"{k}\n({v} 题)" for k, v in zip(labels, sizes)],
        autopct="%1.1f%%", colors=colors, startangle=90,
        wedgeprops=dict(width=0.42, edgecolor="white"), pctdistance=0.78,
    )
    for t in autotexts:
        t.set_color("white")
        t.set_fontsize(9)
    ax1.text(0, 0, "418 题", ha="center", va="center", fontsize=13, fontweight="bold")
    ax1.set_title("按数据集分组")

    vals = [levels[l] for l in LEVELS]
    bars = ax2.bar(LEVELS, vals, color=[LEVEL_COLORS[l] for l in LEVELS], width=0.6)
    for b, v in zip(bars, vals):
        ax2.text(b.get_x() + b.get_width() / 2, v + 1.5, str(v), ha="center", fontsize=10)
    ax2.set_title("按难度分层")
    ax2.set_ylabel("题数")
    ax2.set_ylim(0, max(vals) * 1.18)

    fig.suptitle("数据集构成（418 题主实验集）", fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    save(fig, "dataset_composition.png")


# ------------------------------------------------ 2. dataset_sources.png
def fig_dataset_sources():
    def base_name(s):
        if s.startswith("Omni-MATH"):
            return "Omni-MATH"
        if s == "MATH" or s.startswith("MATH/"):
            return "MATH"
        if s.startswith("GSM-Plus"):
            return "GSM-Plus"
        if s in ("2026-Gaokao", "AIME-2025"):
            return "手工/新考试补充"
        return s

    grouped = defaultdict(list)
    for r in PROBLEMS:
        grouped[base_name(r["source"])].append(r["contamination_risk"])

    items = sorted(grouped.items(), key=lambda x: len(x[1]))
    names = [k for k, _ in items]
    counts = [len(v) for _, v in items]
    risks = [Counter(v).most_common(1)[0][0] for _, v in items]

    fig, ax = plt.subplots(figsize=(8.5, 5.5))
    bars = ax.barh(names, counts, color=[RISK_COLORS[r] for r in risks], height=0.65)
    for b, c in zip(bars, counts):
        ax.text(c + 0.8, b.get_y() + b.get_height() / 2, str(c), va="center", fontsize=9)
    ax.set_xlabel("题数")
    ax.set_title("418 题题源分布（按污染风险着色）", fontsize=13, fontweight="bold")
    ax.set_xlim(0, max(counts) * 1.12)
    handles = [plt.Rectangle((0, 0), 1, 1, color=RISK_COLORS[r]) for r in ("high", "medium", "low")]
    ax.legend(handles, [RISK_LABELS[r] for r in ("high", "medium", "low")],
              title="污染风险", loc="lower right")
    fig.tight_layout()
    save(fig, "dataset_sources.png")


# -------------------------------------------------- 3. level_metrics.png
def fig_level_metrics():
    stats = ENRICHED["metrics"]["level_stats"]
    metric_defs = [
        ("answer_accuracy", "答案正确率"),
        ("process_accuracy", "过程正确率"),
        ("strict_process_accuracy", "严格过程正确率"),
        ("cbu_rate", "CBU 率"),
    ]
    x = np.arange(len(LEVELS))
    width = 0.2
    colors = [C_MAIN, C_GREEN, C_ALT, C_RED]

    fig, ax = plt.subplots(figsize=(9, 4.8))
    for i, ((key, label), color) in enumerate(zip(metric_defs, colors)):
        vals = [stats[l][key] * 100 for l in LEVELS]
        bars = ax.bar(x + (i - 1.5) * width, vals, width, label=label, color=color)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v + 1, f"{v:.1f}",
                    ha="center", fontsize=7.5, rotation=90)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{l}\n(n={stats[l]['total']})" for l in LEVELS])
    ax.set_ylabel("百分比 (%)")
    ax.set_ylim(0, 108)
    ax.set_title("按难度分层的核心指标（单裁判 GPT-5.6-terra，418 题）",
                 fontsize=13, fontweight="bold")
    ax.legend(loc="upper right", ncol=4, fontsize=9, framealpha=0.9)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    save(fig, "level_metrics.png")


# ------------------------------------------- 4. single_vs_multi_judge.png
def fig_single_vs_multi():
    s, m = ENRICHED["metrics"], MULTI["metrics"]
    panels = [("总体", s, m), ("L4（最难层）", s["level_stats"]["L4"], m["level_stats"]["L4"])]
    metric_defs = [
        ("process_accuracy", "过程正确率"),
        ("strict_process_accuracy", "严格过程正确率"),
        ("correct_but_unjustified_rate", "CBU 率"),
    ]
    # level_stats 中 CBU 字段名为 cbu_rate
    def get(d, key):
        return d.get(key, d.get("cbu_rate")) * 100

    fig, axes = plt.subplots(1, 2, figsize=(10, 4.4), sharey=True)
    x = np.arange(len(metric_defs))
    width = 0.34
    for ax, (title, sd, md) in zip(axes, panels):
        sv = [get(sd, k) for k, _ in metric_defs]
        mv = [get(md, k) for k, _ in metric_defs]
        b1 = ax.bar(x - width / 2, sv, width, label="单裁判（GPT-5.6-terra）", color=C_MAIN)
        b2 = ax.bar(x + width / 2, mv, width, label="三裁判投票（Hy3+GPT+Gemini）", color=C_ALT)
        for bars in (b1, b2):
            for b in bars:
                ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 1.2,
                        f"{b.get_height():.1f}", ha="center", fontsize=8)
        ax.set_xticks(x)
        ax.set_xticklabels([l for _, l in metric_defs], fontsize=9)
        ax.set_title(title, fontsize=11)
        ax.grid(axis="y", alpha=0.3)
        ax.set_ylim(0, 100)
    axes[0].set_ylabel("百分比 (%)")
    axes[1].legend(loc="upper right", fontsize=8.5)
    fig.suptitle("单裁判 vs 三裁判投票（418 题主实验集）", fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    save(fig, "single_vs_multi_judge.png")


# --------------------------------------------- 5. contamination_gap.png
def fig_contamination_gap():
    # 按 contamination_risk 分组统计（与 README「按污染风险分层」表同口径：
    # 答案正确率与过程正确率的分母均为可判分题）
    groups = defaultdict(lambda: {"total": 0, "gradable": 0, "ans": 0, "proc": 0})
    for e in ENRICHED["evaluations"]:
        g = groups[e["contamination_risk"]]
        g["total"] += 1
        if e["answer_correct"] is not None:
            g["gradable"] += 1
            g["ans"] += bool(e["answer_correct"])
            g["proc"] += bool(e["process_correct"])
    risks = ["high", "medium", "low"]
    ans = [groups[r]["ans"] / groups[r]["gradable"] * 100 for r in risks]
    proc = [groups[r]["proc"] / groups[r]["gradable"] * 100 for r in risks]

    x = np.arange(len(risks))
    width = 0.34
    fig, ax = plt.subplots(figsize=(7.5, 4.6))
    b1 = ax.bar(x - width / 2, ans, width, label="答案正确率", color=C_MAIN)
    b2 = ax.bar(x + width / 2, proc, width, label="过程正确率", color=C_GREEN)
    for bars in (b1, b2):
        for b in bars:
            ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 1.2,
                    f"{b.get_height():.1f}", ha="center", fontsize=9)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{RISK_LABELS[r]}\n(n={groups[r]['total']})" for r in risks])
    ax.set_ylabel("百分比 (%)")
    ax.set_ylim(0, 100)
    ax.set_title("污染风险分组的答案 vs 过程正确率（单裁判）", fontsize=13, fontweight="bold")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    save(fig, "contamination_gap.png")


# --------------------------------------------------- 6. perturbation.png
def fig_perturbation():
    # 数值取自 README「🌀 扰动变体对照实验」表
    gsm = [("原题\n(GSM8K)", 100.0, 100.0),
           ("数值替换\n(GSM-Plus)", 80.0, 95.0),
           ("干扰插入\n(GSM-Plus)", 95.0, 90.0)]
    pert = [("原题", 56.25, 87.50),
            ("surface_rewrite", 56.25, 81.25),
            ("add_noise", 50.0, 87.50)]

    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.4), sharey=True)
    for ax, data, title in zip(
        axes, (gsm, pert),
        ("GSM-Plus 20 簇（n=20/组）", "16 原题扰动簇（n=16/组）"),
    ):
        labels = [d[0] for d in data]
        ans = [d[1] for d in data]
        proc = [d[2] for d in data]
        x = np.arange(len(labels))
        width = 0.34
        b1 = ax.bar(x - width / 2, ans, width, label="答案正确率", color=C_MAIN)
        b2 = ax.bar(x + width / 2, proc, width, label="过程正确率", color=C_GREEN)
        for bars in (b1, b2):
            for b in bars:
                ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 1.5,
                        f"{b.get_height():.1f}", ha="center", fontsize=8)
        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=9)
        ax.set_title(title, fontsize=11)
        ax.set_ylim(0, 112)
        ax.grid(axis="y", alpha=0.3)
    axes[0].set_ylabel("百分比 (%)")
    axes[0].legend(loc="lower left", fontsize=9)
    fig.suptitle("扰动变体对照实验（记忆/污染指纹）", fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    save(fig, "perturbation.png")


# --------------------------------------------------- 7. error_types.png
def fig_error_types():
    dist = {k: v for k, v in ENRICHED["metrics"]["error_distribution"].items()
            if v > 0 and k != "无错误"}
    items = sorted(dist.items(), key=lambda x: x[1])
    names = [k for k, _ in items]
    counts = [v for _, v in items]

    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    colors = plt.cm.YlOrRd(np.linspace(0.35, 0.85, len(items)))
    bars = ax.barh(names, counts, color=colors, height=0.62)
    total = sum(counts)
    for b, c in zip(bars, counts):
        ax.text(c + 0.3, b.get_y() + b.get_height() / 2,
                f"{c}（{c / total * 100:.1f}%）", va="center", fontsize=9)
    ax.set_xlabel("出现次数")
    ax.set_xlim(0, max(counts) * 1.28)
    ax.set_title(f"错误类型分布（单裁判，共 {total} 道错误样本）", fontsize=13, fontweight="bold")
    ax.grid(axis="x", alpha=0.3)
    fig.tight_layout()
    save(fig, "error_types.png")


# ------------------------------------------- 8. consistency_by_level.png
def fig_consistency_by_level():
    by = CONSISTENCY["metrics"]["by_level"]
    metric_defs = [
        ("self_consistency_rate", "自一致率"),
        ("answer_consistency_rate", "答案一致率"),
        ("process_consistency_rate", "过程一致率"),
        ("answer_consistent_but_process_inconsistent_rate", "答案一致但过程不一致率"),
    ]
    colors = [C_MAIN, C_GREEN, C_ALT, C_RED]
    x = np.arange(len(LEVELS))
    width = 0.2

    fig, ax = plt.subplots(figsize=(9, 4.8))
    for i, ((key, label), color) in enumerate(zip(metric_defs, colors)):
        vals = [by[l][key] * 100 for l in LEVELS]
        bars = ax.bar(x + (i - 1.5) * width, vals, width, label=label, color=color)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v + 1.5, f"{v:.0f}",
                    ha="center", fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{l}\n(n=5)" for l in LEVELS])
    ax.set_ylabel("百分比 (%)")
    ax.set_ylim(0, 112)
    ax.set_title("多采样一致性按难度分层（代表性子集 20 题 × 3 样本）",
                 fontsize=13, fontweight="bold")
    ax.legend(loc="upper right", ncol=2, fontsize=9)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    save(fig, "consistency_by_level.png")


# ------------------------------------------- 9. validation_metrics.png
def fig_validation_metrics():
    # 数值取自 README「✅ 评估器有效性验证」表（三裁判一致率取 418 全量口径，见迭代 9）
    items = [
        ("合成注入错误定位准确率（20/23）", 86.96),
        ("真实错题定位准确率·精确（14/27）", 51.85),
        ("真实错题定位准确率·±1 步（15/27）", 55.56),
        ("答案正确样本误报率（2/55）", 3.64),
        ("CBU 注入样本检出率（7/9）", 77.78),
        ("三裁判过程判定完全一致率（418 全量）", 79.94),
    ]
    items = items[::-1]
    names = [i[0] for i in items]
    vals = [i[1] for i in items]

    fig, ax = plt.subplots(figsize=(9, 4.4))
    colors = [C_GREEN if v >= 70 else (C_ALT if v >= 40 else C_RED) for v in vals]
    # 误报率越低越好，单独着色
    colors[names.index("答案正确样本误报率（2/55）")] = C_GREEN
    bars = ax.barh(names, vals, color=colors, height=0.6)
    for b, v in zip(bars, vals):
        ax.text(v + 1, b.get_y() + b.get_height() / 2, f"{v:.2f}%", va="center", fontsize=9)
    ax.set_xlim(0, 100)
    ax.set_xlabel("百分比 (%)")
    ax.set_title("评估器有效性验证指标汇总", fontsize=13, fontweight="bold")
    ax.grid(axis="x", alpha=0.3)
    fig.tight_layout()
    save(fig, "validation_metrics.png")


# ------------------------------------------ 10. iteration_progress.png
def fig_iteration_progress():
    # 数值取自 README「🔁 实验进展与迭代记录」表（过程正确率口径）：
    # 158 题阶段：初版 ~62%（单层评估）；迭代 1 55.06%；迭代 2 51.90%（三 judge 投票）；
    # 迭代 4 61.39%（多 judge，149 道可判）；迭代 5 56.33%（GPT 单 judge）。
    # 418 题阶段（迭代 9，口径切换）：单裁判 84.45%，三裁判 69.86%。
    stage158_x = [0, 1, 2, 3, 4]
    stage158_y = [62.0, 55.06, 51.90, 61.39, 56.33]
    stage158_labels = ["初版", "迭代 1", "迭代 2*", "迭代 4*", "迭代 5"]
    x418 = 6

    fig, ax = plt.subplots(figsize=(9.5, 4.8))
    ax.plot(stage158_x, stage158_y, "-o", color=C_MAIN, lw=2, ms=7,
            label="158 题阶段（过程正确率）")
    for x, y in zip(stage158_x, stage158_y):
        ax.annotate(f"{y:.2f}%", (x, y), textcoords="offset points",
                    xytext=(0, 9), ha="center", fontsize=8.5)

    # 口径切换后的 418 题阶段
    ax.plot([stage158_x[-1], x418], [stage158_y[-1], 84.45], "--", color=C_GRAY, lw=1.2)
    ax.plot([x418], [84.45], "s", color=C_GREEN, ms=9, label="迭代 9 · 418 题单裁判（84.45%）")
    ax.plot([x418], [69.86], "D", color=C_ALT, ms=8, label="迭代 9 · 418 题三裁判（69.86%）")
    ax.annotate("84.45%", (x418, 84.45), textcoords="offset points", xytext=(0, 10),
                ha="center", fontsize=9, color=C_GREEN)
    ax.annotate("69.86%", (x418, 69.86), textcoords="offset points", xytext=(0, -16),
                ha="center", fontsize=9, color=C_ALT)

    # 口径切换分隔线
    ax.axvline(5, color=C_RED, ls=":", lw=1.5)
    ax.text(5, 30, "口径切换\n158 题 → 418 题", ha="center", fontsize=9, color=C_RED)

    ax.set_xticks(stage158_x + [x418])
    ax.set_xticklabels(stage158_labels + ["迭代 9"])
    ax.set_ylabel("过程正确率 (%)")
    ax.set_ylim(25, 95)
    ax.set_title("迭代进程：过程正确率演进（158 题阶段 → 418 题主实验集）",
                 fontsize=13, fontweight="bold")
    ax.legend(loc="upper left", fontsize=8.5)
    ax.grid(alpha=0.3)
    ax.text(0.01, -0.16,
            "* 迭代 2 为三 judge 投票口径、迭代 4 为多 judge（149 道可判）口径；"
            "158 阶段各轮判定口径不完全一致，趋势仅供参考。",
            transform=ax.transAxes, fontsize=8, color=C_GRAY)
    fig.tight_layout()
    save(fig, "iteration_progress.png")


def main():
    fig_dataset_composition()
    fig_dataset_sources()
    fig_level_metrics()
    fig_single_vs_multi()
    fig_contamination_gap()
    fig_perturbation()
    fig_error_types()
    fig_consistency_by_level()
    fig_validation_metrics()
    fig_iteration_progress()


if __name__ == "__main__":
    main()
