"""多采样一致性与推理路径分析器.

基于同一道题的多个样本，分析：
- 答案一致性（按答案正确性与归一化答案分组）
- 过程一致性（对答案一致且正确的样本比较推理路径）
- 按难度层汇总自一致性指标
"""

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dataset.answer_checker import canonicalize_answer
from evaluator.dependency_graph import build_dependency_graph


def _normalize_answer_text(ans: Any) -> str:
    """对答案文本做规范化，用于分组比较."""
    if ans is None or str(ans).strip() == "":
        return "__NO_ANSWER__"
    return canonicalize_answer(str(ans))


def _edges_from_graph(graph: Dict[int, List[int]]) -> Set[Tuple[int, int]]:
    """将依赖图邻接表转换为有向边集合."""
    edges: Set[Tuple[int, int]] = set()
    for src, deps in graph.items():
        for dep in deps:
            edges.add((src, dep))
    return edges


def _latex_set(steps: List[Dict[str, Any]]) -> Set[str]:
    """提取所有步骤中的规范化 LaTeX 表达式集合."""
    s: Set[str] = set()
    for step in steps:
        for expr in step.get("latex_expressions", []) or []:
            s.add(_normalize_answer_text(expr))
    return s


def _jaccard_distance(a: Set[Any], b: Set[Any]) -> float:
    """Jaccard 距离：1 - |A∩B| / |A∪B|，空集且空集时距离为 0."""
    if not a and not b:
        return 0.0
    intersection = len(a & b)
    union = len(a | b)
    return 1.0 - intersection / union if union else 0.0


def analyze_answer_consistency(
    samples: List[Dict[str, Any]],
    problem: Dict[str, Any],
    consistency_threshold: float = 0.5,
) -> Dict[str, Any]:
    """分析答案一致性.

    按 (answer_correct, 归一化答案) 分组，返回多数答案及一致性指标.

    Args:
        samples: 多采样结果列表.
        problem: 题目字典（用于读取 gold_answer，实际分组以样本自身 answer 为主）.
        consistency_threshold: 多数组占比达到该阈值时认为答案一致.

    Returns:
        包含 answer_consistent、majority_answer、majority_ratio 等字段的字典.
    """
    total = len(samples)
    if total == 0:
        return {
            "answer_consistent": False,
            "majority_answer": None,
            "majority_normalized_answer": None,
            "majority_answer_correct": False,
            "majority_count": 0,
            "majority_ratio": 0.0,
            "total_samples": 0,
            "num_unique_groups": 0,
            "answer_correct_count": 0,
            "answer_correct_ratio": 0.0,
            "answer_groups": [],
        }

    groups: Counter[Tuple[bool, str]] = Counter()
    correct_count = 0
    representative: Dict[Tuple[bool, str], Any] = {}

    for s in samples:
        is_correct = bool(s.get("answer_correct"))
        norm_ans = _normalize_answer_text(s.get("final_answer"))
        key = (is_correct, norm_ans)
        groups[key] += 1
        if is_correct:
            correct_count += 1
        if key not in representative:
            representative[key] = s.get("final_answer")

    (maj_correct, maj_norm), maj_count = groups.most_common(1)[0]
    majority_answer = representative[(maj_correct, maj_norm)]
    majority_ratio = maj_count / total

    answer_groups = [
        {
            "answer_correct": key[0],
            "normalized_answer": key[1],
            "representative_answer": representative[key],
            "count": count,
            "ratio": count / total,
        }
        for key, count in groups.items()
    ]

    return {
        "answer_consistent": majority_ratio >= consistency_threshold,
        "majority_answer": majority_answer,
        "majority_normalized_answer": maj_norm,
        "majority_answer_correct": maj_correct,
        "majority_count": maj_count,
        "majority_ratio": majority_ratio,
        "total_samples": total,
        "num_unique_groups": len(groups),
        "answer_correct_count": correct_count,
        "answer_correct_ratio": correct_count / total,
        "answer_groups": answer_groups,
    }


def analyze_process_consistency(
    samples: List[Dict[str, Any]],
    problem: Dict[str, Any],
    divergence_threshold: float = 0.3,
) -> Dict[str, Any]:
    """分析过程一致性.

    仅对“答案一致且正确”的样本比较推理路径：
    - 步骤数差异
    - 依赖图结构（邻接集合）差异
    - 关键结论 / 公式引用（LaTeX 表达式集合）差异

    Args:
        samples: 多采样结果列表.
        problem: 题目字典.
        divergence_threshold: 平均发散分数低于该阈值时认为过程一致.

    Returns:
        包含 process_consistent、process_divergence_score 及详细对比指标的字典.
    """
    answer_analysis = analyze_answer_consistency(samples, problem)
    majority_norm = answer_analysis["majority_normalized_answer"]

    # 仅保留答案与多数答案一致且被判为正确的样本
    consistent_correct = [
        s
        for s in samples
        if s.get("answer_correct")
        and _normalize_answer_text(s.get("final_answer")) == majority_norm
    ]

    n = len(consistent_correct)
    if n == 0:
        return {
            "process_consistent": False,
            "process_divergence_score": 1.0,
            "consistent_correct_sample_count": 0,
            "pairwise_divergences": [],
            "average_step_count": 0.0,
            "step_count_std": 0.0,
            "common_edge_ratio": 0.0,
            "common_latex_ratio": 0.0,
            "answer_analysis": answer_analysis,
        }

    pairwise: List[Dict[str, Any]] = []
    for i in range(n):
        for j in range(i + 1, n):
            s_i = consistent_correct[i]
            s_j = consistent_correct[j]
            steps_i = s_i.get("steps", []) or []
            steps_j = s_j.get("steps", []) or []

            len_i = len(steps_i)
            len_j = len(steps_j)
            max_len = max(len_i, len_j, 1)
            step_count_diff = abs(len_i - len_j) / max_len

            edges_i = _edges_from_graph(build_dependency_graph(steps_i))
            edges_j = _edges_from_graph(build_dependency_graph(steps_j))
            graph_divergence = _jaccard_distance(edges_i, edges_j)

            latex_i = _latex_set(steps_i)
            latex_j = _latex_set(steps_j)
            latex_divergence = _jaccard_distance(latex_i, latex_j)

            # 综合发散分数：三维度等权平均
            divergence_score = (
                step_count_diff + graph_divergence + latex_divergence
            ) / 3.0

            pairwise.append(
                {
                    "sample_indices": (i, j),
                    "step_count_diff": step_count_diff,
                    "graph_divergence": graph_divergence,
                    "latex_divergence": latex_divergence,
                    "divergence_score": divergence_score,
                }
            )

    avg_divergence = (
        sum(p["divergence_score"] for p in pairwise) / len(pairwise)
        if pairwise
        else 0.0
    )

    step_counts = [len(s.get("steps", []) or []) for s in consistent_correct]
    avg_step_count = sum(step_counts) / len(step_counts)
    step_count_std = (
        (sum((x - avg_step_count) ** 2 for x in step_counts) / len(step_counts)) ** 0.5
        if step_counts
        else 0.0
    )

    # 公共边占比 = 所有样本共有的边 / 所有出现过的边
    edge_sets = [
        _edges_from_graph(build_dependency_graph(s.get("steps", []) or []))
        for s in consistent_correct
    ]
    union_edges = set().union(*edge_sets) if edge_sets else set()
    common_edges = set.intersection(*edge_sets) if edge_sets else set()
    common_edge_ratio = len(common_edges) / len(union_edges) if union_edges else 1.0

    # 公共公式占比
    latex_sets = [_latex_set(s.get("steps", []) or []) for s in consistent_correct]
    union_latex = set().union(*latex_sets) if latex_sets else set()
    common_latex = set.intersection(*latex_sets) if latex_sets else set()
    common_latex_ratio = len(common_latex) / len(union_latex) if union_latex else 1.0

    return {
        "process_consistent": avg_divergence <= divergence_threshold,
        "process_divergence_score": avg_divergence,
        "consistent_correct_sample_count": n,
        "pairwise_divergences": pairwise,
        "average_step_count": avg_step_count,
        "step_count_std": step_count_std,
        "common_edge_ratio": common_edge_ratio,
        "common_latex_ratio": common_latex_ratio,
        "answer_analysis": answer_analysis,
    }


def compute_self_consistency_metrics(
    results_by_problem: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """按难度层汇总自一致性指标.

    Args:
        results_by_problem: 每个元素包含 answer_analysis / process_analysis 的结果字典.

    Returns:
        包含整体指标与按难度层指标的字典.
    """

    def _empty_stats() -> Dict[str, int]:
        return {
            "total": 0,
            "answer_consistent_count": 0,
            "majority_correct_count": 0,
            "process_consistent_count": 0,
            "process_valid_count": 0,
            "answer_consistent_but_process_inconsistent_count": 0,
        }

    def _ratios(stats: Dict[str, int]) -> Dict[str, Optional[float]]:
        t = stats["total"]
        if t == 0:
            return {
                "answer_consistency_rate": None,
                "self_consistency_rate": None,
                "process_consistency_rate": None,
                "answer_consistent_but_process_inconsistent_rate": None,
                "conditional_process_consistency_rate": None,
            }
        valid = stats["process_valid_count"]
        return {
            "answer_consistency_rate": stats["answer_consistent_count"] / t,
            "self_consistency_rate": stats["majority_correct_count"] / t,
            "process_consistency_rate": stats["process_consistent_count"] / t,
            "answer_consistent_but_process_inconsistent_rate": stats[
                "answer_consistent_but_process_inconsistent_count"
            ]
            / t,
            "conditional_process_consistency_rate": (
                stats["process_consistent_count"] / valid if valid else None
            ),
        }

    overall = _empty_stats()
    level_stats: Dict[str, Dict[str, int]] = {}

    for r in results_by_problem:
        level = r.get("level") or "unknown"
        aa = r.get("answer_analysis", {})
        pa = r.get("process_analysis", {})

        answer_consistent = bool(aa.get("answer_consistent"))
        majority_correct = bool(aa.get("majority_answer_correct"))
        process_consistent = bool(pa.get("process_consistent"))
        process_valid = bool(pa.get("consistent_correct_sample_count", 0) > 0)

        overall["total"] += 1
        stats = level_stats.setdefault(level, _empty_stats())
        stats["total"] += 1

        if answer_consistent:
            overall["answer_consistent_count"] += 1
            stats["answer_consistent_count"] += 1
        if majority_correct:
            overall["majority_correct_count"] += 1
            stats["majority_correct_count"] += 1
        if process_consistent:
            overall["process_consistent_count"] += 1
            stats["process_consistent_count"] += 1
        if process_valid:
            overall["process_valid_count"] += 1
            stats["process_valid_count"] += 1
        if answer_consistent and not process_consistent:
            overall["answer_consistent_but_process_inconsistent_count"] += 1
            stats["answer_consistent_but_process_inconsistent_count"] += 1

    metrics = {
        "overall": {**overall, **_ratios(overall)},
        "by_level": {
            level: {**stats, **_ratios(stats)} for level, stats in level_stats.items()
        },
    }
    return metrics


if __name__ == "__main__":
    """自检：使用人造样本验证答案/过程一致性分析."""

    problem = {"id": "demo", "problem": "test"}

    # 样本 A/B 答案一致且正确，过程结构相同但公式略有差异
    sample_a = {
        "final_answer": "16",
        "answer_correct": True,
        "steps": [
            {"index": 1, "text": "Mimi has 24 shells.", "latex_expressions": ["2 \\times 12 = 24"], "depends_on": []},
            {"index": 2, "text": "Kyle has 48.", "latex_expressions": ["24 \\times 2 = 48"], "depends_on": [1]},
            {"index": 3, "text": "Leigh has 16.", "latex_expressions": ["48 / 3 = 16"], "depends_on": [2]},
        ],
    }
    sample_b = {
        "final_answer": "16",
        "answer_correct": True,
        "steps": [
            {"index": 1, "text": "Mimi has 24 shells.", "latex_expressions": ["2 \\times 12 = 24"], "depends_on": []},
            {"index": 2, "text": "Kyle has 48.", "latex_expressions": ["24 \\times 2 = 48"], "depends_on": [1]},
            {"index": 3, "text": "Leigh has 16.", "latex_expressions": ["48 \\div 3 = 16"], "depends_on": [2]},
        ],
    }
    # 样本 C 答案错误
    sample_c = {
        "final_answer": "15",
        "answer_correct": False,
        "steps": [
            {"index": 1, "text": "Mimi has 24.", "latex_expressions": ["2 \\times 12 = 24"], "depends_on": []},
            {"index": 2, "text": "Wrong division.", "latex_expressions": ["48 / 4 = 12"], "depends_on": [1]},
        ],
    }

    samples = [sample_a, sample_b, sample_c]
    aa = analyze_answer_consistency(samples, problem)
    pa = analyze_process_consistency(samples, problem)
    metrics = compute_self_consistency_metrics(
        [{"level": "L1", "answer_analysis": aa, "process_analysis": pa}]
    )

    print(json.dumps(aa, ensure_ascii=False, indent=2))
    print(json.dumps(pa, ensure_ascii=False, indent=2))
    print(json.dumps(metrics, ensure_ascii=False, indent=2))

    assert aa["majority_answer"] == "16"
    assert aa["answer_consistent"] is True
    assert pa["process_consistent"] is True
    assert 0.0 <= pa["process_divergence_score"] <= 1.0
    print("\n一致性分析器自检通过")
