"""Pure-algorithm dependency graph validation for multi-step reasoning.

No LLM calls; only Python standard library.

兼容输入：
- 步骤为 dict 时，读取 index / text / depends_on 字段；
- 步骤为 Step 数据类时，读取对应属性。
当步骤未提供 depends_on 信息或均为空列表时，默认认为依赖图合法，
以保持对旧数据的向后兼容。
"""

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Dict, List, Set


@dataclass
class Step:
    index: int
    text: str
    depends_on: List[int]


def _step_index(step: Any) -> int:
    if isinstance(step, dict):
        return step.get("index", 0)
    return getattr(step, "index", 0)


def _step_text(step: Any) -> str:
    if isinstance(step, dict):
        return step.get("text", "")
    return getattr(step, "text", "")


def _step_deps(step: Any) -> List[int]:
    if isinstance(step, dict):
        deps = step.get("depends_on", [])
        return list(deps) if isinstance(deps, (list, tuple)) else []
    return list(getattr(step, "depends_on", []) or [])


def build_dependency_graph(steps: List[Any]) -> Dict[int, List[int]]:
    """Return adjacency_list: step_index -> list of dependency step indices."""
    return {_step_index(step): _step_deps(step) for step in steps}


def _find_elementary_cycles(graph: Dict[int, List[int]]) -> List[List[int]]:
    """Enumerate all elementary cycles in a directed graph.

    Each cycle is returned once as an ordered list of nodes (no repeated start
    node at the end).  The search restricts traversal to nodes >= the current
    start node so that every cycle is discovered exactly once.
    """
    nodes = sorted(graph.keys())
    cycles: List[List[int]] = []

    def dfs(start: int, current: int, path: List[int], visited: Set[int]) -> None:
        for neighbor in graph.get(current, []):
            if neighbor == start:
                # Found a cycle back to the start node.
                cycles.append(path[:])
            elif neighbor > start and neighbor not in visited:
                visited.add(neighbor)
                dfs(start, neighbor, path + [neighbor], visited)
                visited.remove(neighbor)

    for start in nodes:
        dfs(start, start, [start], {start})

    return cycles


def validate_dependencies(steps: List[Any]) -> Dict[str, Any]:
    """Validate a list of reasoning steps and their dependency relations.

    Args:
        steps: 步骤列表，元素可为 dict 或 Step 数据类，包含 index/text/depends_on。

    Returns:
        {
            "valid": bool,
            "issues": [
                {
                    "type": str,       # circular_dependency / missing_reference /
                                        # future_reference / disconnected_step
                    "step_index": int,
                    "detail": str,
                    "related_indices": List[int],
                },
                ...
            ],
            "has_cycle": bool,
            "cycle_nodes": List[List[int]],
            "is_connected": bool,
            "graph": Dict[int, List[int]],
        }
    """
    if not steps:
        return {
            "valid": True,
            "issues": [],
            "has_cycle": False,
            "cycle_nodes": [],
            "is_connected": True,
            "graph": {},
        }

    # 向后兼容：如果没有任何步骤显式提供 depends_on，则跳过验证
    has_dep_info = any(
        (isinstance(step, dict) and "depends_on" in step)
        or (not isinstance(step, dict) and getattr(step, "depends_on", None) is not None)
        for step in steps
    )
    if not has_dep_info:
        return {
            "valid": True,
            "issues": [],
            "has_cycle": False,
            "cycle_nodes": [],
            "is_connected": True,
            "graph": build_dependency_graph(steps),
        }

    n = len(steps)
    indices: Set[int] = {_step_index(step) for step in steps}
    graph = build_dependency_graph(steps)
    issues: List[Dict[str, Any]] = []

    # 1. missing_reference & future_reference
    for step in steps:
        step_index = _step_index(step)
        for dep in _step_deps(step):
            if dep < 1 or dep > n:
                issues.append(
                    {
                        "type": "missing_reference",
                        "step_index": step_index,
                        "detail": (
                            f"Step {step_index} references dependency {dep}, "
                            f"which is outside the valid range [1, {n}]."
                        ),
                        "related_indices": [dep],
                    }
                )
            elif dep > step_index:
                issues.append(
                    {
                        "type": "future_reference",
                        "step_index": step_index,
                        "detail": (
                            f"Step {step_index} references future step {dep}; "
                            "dependencies must point to earlier steps."
                        ),
                        "related_indices": [dep],
                    }
                )

    # 2. circular_dependency (use only valid, in-range edges)
    valid_graph: Dict[int, List[int]] = {idx: [] for idx in indices}
    for step in steps:
        step_index = _step_index(step)
        valid_graph[step_index] = [dep for dep in _step_deps(step) if 1 <= dep <= n]

    cycle_nodes = _find_elementary_cycles(valid_graph)
    if cycle_nodes:
        for cycle in cycle_nodes:
            issues.append(
                {
                    "type": "circular_dependency",
                    "step_index": cycle[0],
                    "detail": f"Circular dependency detected involving steps {cycle}.",
                    "related_indices": list(cycle),
                }
            )

    # 3. disconnected_step
    # Treat dependencies as undirected edges. Any step with empty depends_on is
    # a legitimate entry point (it derives directly from the problem statement),
    # so we BFS from all entry points. A step is disconnected only if it cannot
    # be reached from any entry point.
    undirected: Dict[int, List[int]] = defaultdict(list)
    for step in steps:
        step_index = _step_index(step)
        for dep in _step_deps(step):
            if 1 <= dep <= n:
                undirected[step_index].append(dep)
                undirected[dep].append(step_index)

    entry_points = sorted(idx for idx in indices if not valid_graph.get(idx))
    if not entry_points and indices:
        # Fallback: if every step has dependencies, use step 1 as the only entry
        # point to avoid silently passing a fully cyclic chain.
        entry_points = [min(indices)]

    reachable: Set[int] = set()
    queue: deque = deque(entry_points)
    reachable.update(entry_points)
    while queue:
        node = queue.popleft()
        for neighbor in undirected.get(node, []):
            if neighbor not in reachable:
                reachable.add(neighbor)
                queue.append(neighbor)

    disconnected = sorted(indices - reachable)
    for idx in disconnected:
        issues.append(
            {
                "type": "disconnected_step",
                "step_index": idx,
                "detail": (
                    f"Step {idx} is unreachable from any entry step through the "
                    "dependency graph."
                ),
                "related_indices": [],
            }
        )

    valid = not any(
        issue["type"]
        in (
            "missing_reference",
            "future_reference",
            "circular_dependency",
            "disconnected_step",
        )
        for issue in issues
    )

    return {
        "valid": valid,
        "issues": issues,
        "has_cycle": bool(cycle_nodes),
        "cycle_nodes": cycle_nodes,
        "is_connected": len(disconnected) == 0,
        "graph": graph,
    }


if __name__ == "__main__":
    import json

    def show(title: str, steps: List[Any]) -> None:
        print(f"\n{'=' * 60}")
        print(title)
        print(f"{'=' * 60}")
        result = validate_dependencies(steps)
        print(json.dumps(result, indent=2, ensure_ascii=False))

    # 1. 正常链：1 -> 2 -> 3
    show(
        "1) Valid chain",
        [
            {"index": 1, "text": "premise", "depends_on": []},
            {"index": 2, "text": "use step 1", "depends_on": [1]},
            {"index": 3, "text": "use step 2", "depends_on": [2]},
        ],
    )

    # 2. 循环论证：2 <-> 3
    show(
        "2) Circular dependency",
        [
            {"index": 1, "text": "premise", "depends_on": []},
            {"index": 2, "text": "depends on 3", "depends_on": [3]},
            {"index": 3, "text": "depends on 2", "depends_on": [2]},
        ],
    )

    # 3. 跳步引用未来步骤
    show(
        "3) Future reference",
        [
            {"index": 1, "text": "premise", "depends_on": []},
            {"index": 2, "text": "references step 3", "depends_on": [3]},
            {"index": 3, "text": "later step", "depends_on": []},
        ],
    )

    # 4. 引用不存在步骤
    show(
        "4) Missing reference",
        [
            {"index": 1, "text": "premise", "depends_on": []},
            {"index": 2, "text": "references step 5", "depends_on": [5]},
            {"index": 3, "text": "another step", "depends_on": [1]},
        ],
    )

    # 5. 空依赖的独立入口步骤不应被视为孤立
    show(
        "5) Independent premise (not disconnected)",
        [
            {"index": 1, "text": "premise", "depends_on": []},
            {"index": 2, "text": "uses step 1", "depends_on": [1]},
            {"index": 3, "text": "another premise", "depends_on": []},
        ],
    )

    # 5b. 真正的孤立步骤：有依赖但无法从任何入口到达
    show(
        "5b) Truly disconnected step",
        [
            {"index": 1, "text": "premise", "depends_on": []},
            {"index": 2, "text": "uses step 1", "depends_on": [1]},
            {"index": 3, "text": "uses step 5", "depends_on": [5]},
            {"index": 4, "text": "uses step 3", "depends_on": [3]},
            {"index": 5, "text": "uses step 4", "depends_on": [4]},
        ],
    )

    # 6. 向后兼容：无 depends_on 信息
    show(
        "6) Backward compatible (no depends_on)",
        [
            {"index": 1, "text": "premise"},
            {"index": 2, "text": "next step"},
        ],
    )

    # 7. 空 depends_on 列表
    show(
        "7) Empty depends_on",
        [
            {"index": 1, "text": "premise", "depends_on": []},
            {"index": 2, "text": "next step", "depends_on": []},
        ],
    )
