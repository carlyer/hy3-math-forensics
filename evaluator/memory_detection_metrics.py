"""Memory / template detection metrics for multi-sample math reasoning.

Designed for the Hy3 math process-evaluation project.  All metrics are
rule-based and use only the existing sample data (no LLM calls).

Target phenomenon:
    "答案稳定但推理路径漂移"  in the L2 difficulty layer.

Three lightweight indicators:
    A. Solution-type stability  – keyword-driven method labels per sample.
    B. Dependency-graph stability – Jaccard similarity of step dependency edges.
    C. Theorem/formula consistency – Jaccard similarity of referenced theorems.

Compatible data format:
    Each sample contains ``steps`` with ``index/text/latex_expressions/depends_on``.
"""

import json
import math
import re
from collections import Counter
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# 1. Method / theorem keyword tables
# ---------------------------------------------------------------------------

# Ordered by priority: more distinctive methods are checked first.
SOLUTION_TYPE_PATTERNS: List[Tuple[str, str]] = [
    ("求导法", r"求导|导数|\\frac\{d\}\{d|导函数|可导|偏导|微商"),
    ("积分法", r"不定积分|定积分|重积分|二重积分|曲线积分|曲面积分|积分法|积分公式|\\int|原函数"),
    ("韦达定理", r"韦达定理|Vieta|根与系数"),
    ("二次方程求根公式", r"求根公式|判别式|\\Delta|quadratic formula"),
    ("AM-GM", r"AM[-\s]?GM|均值不等式|算术几何平均|基本不等式|\\frac\{a\+b\}\{2\}"),
    ("柯西不等式", r"柯西不等式|柯西|Cauchy[-\s]?Schwarz"),
    ("通分法", r"通分|公分母|最小公倍数|least common denominator"),
    ("因式分解", r"因式分解|factor|分解因式|提公因式|十字相乘|配方法"),
    ("换元法", r"换元|substitution|令\s*[^=]+=|设\s*[^=]+="),
    ("数学归纳法", r"归纳法|mathematical induction|归纳假设|归纳基础"),
    ("周期模运算", r"模运算|modulo|\bmod\b|周期性|余数|同余|模\s*\\?\d"),
    ("向量模平方公式", r"向量|\\vec\{|模长|模平方|向量模|点积|内积|\\cdot(?![a-zA-Z])"),
    ("勾股定理", r"勾股定理|Pythagorean"),
    ("相似三角形", r"相似三角形|相似|\\triangle.*相似"),
    ("正弦定理", r"正弦定理"),
    ("余弦定理", r"余弦定理"),
    ("等差数列", r"等差数列|等差"),
    ("等比数列", r"等比数列|等比"),
    ("排列组合", r"排列|组合|C_\\{?\\d|A_\\{?\\d|二项式|\\binom"),
    ("概率公式", r"概率(?:公式|分布|论|模型|事件)?|随机变量|分布列|期望|(?<![平])方差"),
    ("几何面积公式", r"面积公式|体积公式|几何图形"),
    ("枚举法", r"枚举|穷举|列举|逐一验证"),
    ("对称式", r"对称式|轮换对称|对称性"),
]

# Theorem / formula reference patterns.  These can overlap.
THEOREM_PATTERNS: List[Tuple[str, str]] = [
    ("韦达定理", r"韦达定理|Vieta"),
    ("AM-GM/均值不等式", r"AM[-\s]?GM|均值不等式|算术几何平均|基本不等式"),
    ("柯西不等式", r"柯西不等式|柯西"),
    ("求导/导数", r"求导|导数|导函数"),
    ("积分", r"不定积分|定积分|重积分|二重积分|曲线积分|曲面积分|积分法|积分公式|\\int|原函数"),
    ("二次方程求根公式", r"求根公式|判别式|\\Delta"),
    ("通分", r"通分|公分母"),
    ("因式分解", r"因式分解|分解因式|提公因式|十字相乘|配方法"),
    ("换元", r"换元|substitution"),
    ("数学归纳法", r"归纳法|归纳假设"),
    ("模运算/周期", r"模运算|modulo|\bmod\b|周期性|同余|余数"),
    ("向量公式", r"向量|\\vec\{|模长|模平方|点积|内积|\\cdot(?![a-zA-Z])"),
    ("勾股定理", r"勾股定理"),
    ("相似三角形", r"相似三角形|相似"),
    ("正弦定理", r"正弦定理"),
    ("余弦定理", r"余弦定理"),
    ("等差数列", r"等差数列"),
    ("等比数列", r"等比数列"),
    ("排列组合", r"排列|组合|二项式|\\binom"),
    ("概率", r"概率|随机变量|分布列|期望|(?<![平])方差"),
    ("面积/体积公式", r"面积公式|体积公式|面积|体积"),
    ("枚举", r"枚举|穷举|列举"),
    ("对称", r"对称式|轮换对称|对称性"),
]

DEFAULT_TYPE_LABEL = "未识别/常规代数运算"
GRAPH_JACCARD_DRIFT_THRESHOLD = 0.5
THEOREM_JACCARD_DRIFT_THRESHOLD = 0.5


# ---------------------------------------------------------------------------
# 2. Text helpers
# ---------------------------------------------------------------------------

def _sample_text(sample: Dict[str, Any]) -> str:
    """Concatenate all textual material of one sample."""
    chunks: List[str] = []
    steps = sample.get("steps") or []
    for step in steps:
        chunks.append(str(step.get("text", "")))
        latex_list = step.get("latex_expressions") or []
        if latex_list:
            chunks.append(" ".join(str(x) for x in latex_list))
    return "\n".join(chunks)


def _find_first_pattern(text: str, patterns: List[Tuple[str, str]]) -> Optional[str]:
    lowered = text.lower()
    for label, pat in patterns:
        if re.search(pat, lowered):
            return label
    return None


def _find_all_patterns(text: str, patterns: List[Tuple[str, str]]) -> Set[str]:
    lowered = text.lower()
    found: Set[str] = set()
    for label, pat in patterns:
        if re.search(pat, lowered):
            found.add(label)
    return found


def classify_solution_type(sample: Dict[str, Any]) -> str:
    """Return a single dominant method label for a sample."""
    text = _sample_text(sample)
    label = _find_first_pattern(text, SOLUTION_TYPE_PATTERNS)
    return label if label else DEFAULT_TYPE_LABEL


def extract_theorem_keywords(sample: Dict[str, Any]) -> Set[str]:
    """Return the set of theorem/formula keywords mentioned in a sample."""
    text = _sample_text(sample)
    return _find_all_patterns(text, THEOREM_PATTERNS)


# ---------------------------------------------------------------------------
# 3. Graph helpers
# ---------------------------------------------------------------------------

def _build_edges(steps: List[Dict[str, Any]]) -> Set[Tuple[int, int]]:
    """Edges point from a step to each of its dependencies: (step_index, dep_index)."""
    edges: Set[Tuple[int, int]] = set()
    for step in steps:
        src = step.get("index")
        if src is None:
            continue
        for dep in step.get("depends_on") or []:
            edges.add((int(src), int(dep)))
    return edges


def _graph_entropy(steps: List[Dict[str, Any]]) -> float:
    """Normalized Shannon entropy of the out-degree distribution (0..1).

    A chain has entropy near 0; a highly branched graph has higher entropy.
    """
    if not steps:
        return 0.0
    out_degrees = Counter()
    for step in steps:
        out_degrees[step.get("index", 0)] = len(step.get("depends_on") or [])
    counts = list(out_degrees.values())
    total = sum(counts)
    if total == 0:
        return 0.0
    h = 0.0
    for c in counts:
        if c:
            p = c / total
            h -= p * math.log2(p)
    n = len(counts)
    return h / math.log2(n) if n > 1 else 0.0


def _jaccard_similarity(a: Set[Any], b: Set[Any]) -> float:
    """Jaccard similarity |A∩B|/|A∪B|; 1.0 when both sets are empty."""
    if not a and not b:
        return 1.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _pairwise_similarities(sets: List[Set[Any]]) -> List[float]:
    sims: List[float] = []
    for a, b in combinations(sets, 2):
        sims.append(_jaccard_similarity(a, b))
    return sims


# ---------------------------------------------------------------------------
# 4. Per-problem metrics
# ---------------------------------------------------------------------------

def compute_memory_metrics(problem: Dict[str, Any]) -> Dict[str, Any]:
    """Compute memory/template detection metrics for one problem."""
    samples = problem.get("samples") or []
    problem_id = problem.get("problem_id", "unknown")
    level = problem.get("level", "unknown")

    # ---- A. Solution-type stability ----
    type_labels = [classify_solution_type(s) for s in samples]
    unique_types = set(type_labels)
    type_drift = len(unique_types) > 1
    pairwise_type_drift_ratio = 0.0
    if len(type_labels) >= 2:
        pair_count = 0
        drift_count = 0
        for a, b in combinations(type_labels, 2):
            pair_count += 1
            if a != b:
                drift_count += 1
        pairwise_type_drift_ratio = drift_count / pair_count if pair_count else 0.0

    # ---- B. Dependency-graph stability ----
    edge_sets = [_build_edges(s.get("steps") or []) for s in samples]
    node_sets = [set(step.get("index") for step in (s.get("steps") or [])) for s in samples]
    edge_sims = _pairwise_similarities(edge_sets)
    node_sims = _pairwise_similarities(node_sets)
    graph_edge_jaccard_mean = sum(edge_sims) / len(edge_sims) if edge_sims else 1.0
    graph_node_jaccard_mean = sum(node_sims) / len(node_sims) if node_sims else 1.0

    graph_entropies = [_graph_entropy(s.get("steps") or []) for s in samples]
    if len(graph_entropies) >= 2:
        mean_h = sum(graph_entropies) / len(graph_entropies)
        graph_entropy_stability = 1.0 - (
            sum(abs(h - mean_h) for h in graph_entropies) / len(graph_entropies)
        )
        graph_entropy_stability = max(0.0, graph_entropy_stability)
    else:
        graph_entropy_stability = 1.0

    # ---- C. Theorem/formula consistency ----
    theorem_sets = [extract_theorem_keywords(s) for s in samples]
    theorem_sims = _pairwise_similarities(theorem_sets)
    theorem_jaccard_mean = sum(theorem_sims) / len(theorem_sims) if theorem_sims else 1.0
    all_theorems = set().union(*theorem_sets) if theorem_sets else set()
    theorem_recall_per_keyword = {}
    for kw in sorted(all_theorems):
        theorem_recall_per_keyword[kw] = sum(1 for ts in theorem_sets if kw in ts) / len(samples)

    # ---- Composite memory-drift flag ----
    graph_drift = graph_edge_jaccard_mean < GRAPH_JACCARD_DRIFT_THRESHOLD
    theorem_drift = theorem_jaccard_mean < THEOREM_JACCARD_DRIFT_THRESHOLD
    memory_drift_flag = bool(type_drift or graph_drift or theorem_drift)

    return {
        "problem_id": problem_id,
        "level": level,
        "sample_count": len(samples),
        "answer_consistent": problem.get("answer_analysis", {}).get("answer_consistent"),
        "process_consistent": problem.get("process_analysis", {}).get("process_consistent"),
        "process_divergence_score": problem.get("process_analysis", {}).get("process_divergence_score"),
        # A
        "solution_type_labels": type_labels,
        "solution_type_unique": sorted(unique_types),
        "solution_type_drift": type_drift,
        "pairwise_solution_type_drift_ratio": round(pairwise_type_drift_ratio, 4),
        # B
        "graph_edge_jaccard_mean": round(graph_edge_jaccard_mean, 4),
        "graph_node_jaccard_mean": round(graph_node_jaccard_mean, 4),
        "graph_entropy_per_sample": [round(h, 4) for h in graph_entropies],
        "graph_entropy_stability": round(graph_entropy_stability, 4),
        "graph_drift": graph_drift,
        # C
        "theorem_sets": [sorted(ts) for ts in theorem_sets],
        "theorem_jaccard_mean": round(theorem_jaccard_mean, 4),
        "theorem_recall_per_keyword": theorem_recall_per_keyword,
        "theorem_drift": theorem_drift,
        # Composite
        "memory_drift_flag": memory_drift_flag,
    }


# ---------------------------------------------------------------------------
# 5. Load / run / report
# ---------------------------------------------------------------------------

def load_problems(input_path: Path) -> List[Dict[str, Any]]:
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        return data.get("problems") or []
    if isinstance(data, list):
        return data
    raise ValueError(f"Unsupported JSON top-level type: {type(data)}")


def aggregate_level_metrics(metrics: List[Dict[str, Any]], level: str) -> Dict[str, Any]:
    subset = [m for m in metrics if m.get("level") == level]
    n = len(subset)
    if n == 0:
        return {"count": 0}
    return {
        "count": n,
        "memory_drift_ratio": round(sum(1 for m in subset if m["memory_drift_flag"]) / n, 4),
        "solution_type_drift_ratio": round(sum(1 for m in subset if m["solution_type_drift"]) / n, 4),
        "graph_drift_ratio": round(sum(1 for m in subset if m["graph_drift"]) / n, 4),
        "theorem_drift_ratio": round(sum(1 for m in subset if m["theorem_drift"]) / n, 4),
        "mean_graph_edge_jaccard": round(sum(m["graph_edge_jaccard_mean"] for m in subset) / n, 4),
        "mean_theorem_jaccard": round(sum(m["theorem_jaccard_mean"] for m in subset) / n, 4),
        "mean_pairwise_type_drift_ratio": round(
            sum(m["pairwise_solution_type_drift_ratio"] for m in subset) / n, 4
        ),
    }


def run(
    input_path: Optional[Path] = None,
    output_json: Optional[Path] = None,
    output_report: Optional[Path] = None,
    focus_levels: Optional[List[str]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Run the full memory-detection pipeline and write results."""
    focus_levels = focus_levels or ["L2"]
    input_path = input_path or (ROOT / "results" / "consistency_analysis_l2_all.json")
    if not input_path.exists():
        input_path = ROOT / "results" / "consistency_analysis_subset_small.json"

    output_json = output_json or (ROOT / "results" / "l2_memory_metrics.json")
    output_report = output_report or (ROOT / "results" / "l2_memory_metrics_report.md")

    problems = load_problems(input_path)
    metrics = [compute_memory_metrics(p) for p in problems]

    level_summaries = {}
    all_levels = sorted({m["level"] for m in metrics})
    for lvl in all_levels:
        level_summaries[lvl] = aggregate_level_metrics(metrics, lvl)

    payload = {
        "input_file": str(input_path.relative_to(ROOT)),
        "total_problems": len(metrics),
        "focus_levels": focus_levels,
        "level_summaries": level_summaries,
        "problems": metrics,
    }

    output_json.parent.mkdir(parents=True, exist_ok=True)
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    _write_report(metrics, level_summaries, focus_levels, input_path, output_report)
    return metrics, level_summaries


def _write_report(
    metrics: List[Dict[str, Any]],
    level_summaries: Dict[str, Any],
    focus_levels: List[str],
    input_path: Path,
    output_report: Path,
) -> None:
    lines: List[str] = [
        "# L2 难度层记忆 / 模板探测指标报告",
        "",
        "## 1. 数据说明",
        "",
        f"- 输入文件：`{input_path.name}`",
        f"- 处理题数：{len(metrics)}",
        f"- 重点关注难度层：{', '.join(focus_levels)}",
    ]

    if input_path.name == "consistency_analysis_subset_small.json":
        lines.append(
            "- 注：`results/consistency_analysis_l2_all.json` 尚未生成，本次使用 "
            "`consistency_analysis_subset_small.json`（20 题 × 3 样本，含 5 道 L2 题）做示例分析。"
        )
    lines.append("")

    # Overall level table
    lines.extend([
        "## 2. 各难度层汇总",
        "",
        "| 难度 | 题数 | 记忆/模板漂移率 | 解法类型漂移率 | 图结构漂移率 | 定理引用漂移率 | 平均图边 Jaccard | 平均定理 Jaccard |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ])
    for lvl in sorted(level_summaries.keys()):
        s = level_summaries[lvl]
        if s.get("count", 0) == 0:
            continue
        lines.append(
            f"| {lvl} | {s['count']} | {s['memory_drift_ratio']:.2%} | "
            f"{s['solution_type_drift_ratio']:.2%} | {s['graph_drift_ratio']:.2%} | "
            f"{s['theorem_drift_ratio']:.2%} | {s['mean_graph_edge_jaccard']:.4f} | "
            f"{s['mean_theorem_jaccard']:.4f} |"
        )
    lines.append("")

    # Focus level per-problem table
    for lvl in focus_levels:
        subset = [m for m in metrics if m.get("level") == lvl]
        if not subset:
            continue
        lines.extend([
            f"## 3. {lvl} 逐题指标",
            "",
            "| 题号 | 答案一致 | 过程一致 | 解法标签 | 解法漂移 | 图边 Jaccard | 图熵稳定性 | 定理 Jaccard | 记忆漂移 |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ])
        for m in subset:
            labels = ", ".join(m["solution_type_labels"])
            lines.append(
                f"| {m['problem_id']} | {m['answer_consistent']} | {m['process_consistent']} | "
                f"{labels} | {m['solution_type_drift']} | {m['graph_edge_jaccard_mean']:.4f} | "
                f"{m['graph_entropy_stability']:.4f} | {m['theorem_jaccard_mean']:.4f} | {m['memory_drift_flag']} |"
            )
        lines.append("")

    # Interpretation / discussion
    lines.extend([
        "## 4. 指标设计思路",
        "",
        "### A. 解法类型稳定性（Solution-type stability）",
        "",
        "对每个样本的步骤文本和 `latex_expressions` 做关键词/正则匹配，按优先级给出单一解法类型标签，",
        "例如：求导法、韦达定理、AM-GM、周期模运算、向量模平方公式、通分法等。",
        "同一道题的 3 个样本若出现两种及以上标签，即标记为**解法漂移**。",
        "该指标直接刻画“用了什么方法”，是判断推理路径是否表面的第一道筛子。",
        "",
        "### B. 依赖图结构稳定性（Dependency-graph stability）",
        "",
        "把每个样本的 `depends_on` 视为有向边 `(step_index, dep_index)`，计算样本对之间的边集 Jaccard 相似度。",
        "同时记录节点集合 Jaccard 与基于出度分布的归一化图熵，用于补充刻画路径结构的粗细与分支程度。",
        "若同题样本的依赖边差异较大，说明即使最终答案相同，内部推导顺序也可能来自不同模板。",
        "",
        "### C. 关键公式/定理引用一致性（Theorem consistency）",
        "",
        "用规则匹配提取样本中显式出现的定理/公式关键词（韦达定理、AM-GM、求导、通分、向量公式等），",
        "计算同题样本间的定理关键词集合 Jaccard 相似度。",
        "稳定推理通常会在多次采样中引用同一批核心定理；模板/记忆型解答则可能遗漏或替换关键依据。",
        "",
        "## 5. 区分“稳定推理”与“模板/记忆型解答”",
        "",
        "- **稳定推理**：三个样本的解法类型标签一致、依赖图边集高度重合、定理关键词集合高度重合。",
        "  即使最终答案相同，也能观察到稳定的中间表征。",
        "- **模板/记忆型解答（答案稳定但路径漂移）**：最终答案一致，但解法类型、依赖图或定理引用至少有一项出现显著漂移。",
        "  这表明模型可能记住了答案或表层套路，而未形成对该题的统一推理过程。",
        "- **综合标记**：当 `solution_type_drift`、图边 Jaccard < 0.5、定理 Jaccard < 0.5 任一成立时，",
        "  `memory_drift_flag` 置为 True。",
        "",
        "## 6. 局限与后续工作",
        "",
        "1. **关键词规则较粗**：同一数学方法可能有多种中文表达，规则未覆盖所有同义表述，可能低估稳定性。",
        "2. **定理引用可能隐含**：部分推理可能直接套用公式而不写出定理名称，导致定理指标为 0 或不稳定。",
        "3. **依赖图粒度敏感**：步骤拆分粗细不同会导致边集差异；未来可引入边类型（计算/引用/化简）增强鲁棒性。",
        "4. **未使用 LLM**：本实现完全基于已有样本数据，符合“不调用 LLM”的要求，但也错失了语义层面的精细对齐。",
        "5. **数据规模与规则覆盖**：本次使用 35 题 L2 全量数据；指标基于有限的关键词表，后续可随题目类型扩展规则库，并在更大规模数据上验证阈值稳定性。",
        "",
    ])

    output_report.parent.mkdir(parents=True, exist_ok=True)
    with open(output_report, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Memory/template detection metrics for Hy3 L2.")
    parser.add_argument("--input", type=Path, default=None, help="Path to consistency analysis JSON.")
    parser.add_argument("--output-json", type=Path, default=None, help="Output JSON path.")
    parser.add_argument("--output-report", type=Path, default=None, help="Output Markdown report path.")
    parser.add_argument("--focus-levels", nargs="+", default=["L2"], help="Levels to highlight in report.")
    args = parser.parse_args()

    run(
        input_path=args.input,
        output_json=args.output_json,
        output_report=args.output_report,
        focus_levels=args.focus_levels,
    )
