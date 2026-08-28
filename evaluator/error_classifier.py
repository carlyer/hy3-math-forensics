"""错误类型分类与标准化."""

from typing import Dict, List, Optional

# 错误类型体系
ERROR_TYPES = [
    "题意误读",
    "概念理解错误",
    "定理/公式误用",
    "计算错误",
    "条件遗漏",
    "跳步推导",
    "循环论证",
    "幻觉/无中生有",
    "单位/格式不符",
    "其他/无法归类",
    "无错误",
]

ERROR_TYPE_ALIASES = {
    "misreading": "题意误读",
    "concept_error": "概念理解错误",
    "theorem_misuse": "定理/公式误用",
    "calculation_error": "计算错误",
    "missing_condition": "条件遗漏",
    "skipped_step": "跳步推导",
    "circular_reasoning": "循环论证",
    "hallucination": "幻觉/无中生有",
    "unit_format_error": "单位/格式不符",
    "other": "其他/无法归类",
    "no_error": "无错误",
    # 中文别名
    "题意误读": "题意误读",
    "概念理解错误": "概念理解错误",
    "概念错误": "概念理解错误",
    "定理误用": "定理/公式误用",
    "公式误用": "定理/公式误用",
    "定理/公式误用": "定理/公式误用",
    "计算错误": "计算错误",
    "条件遗漏": "条件遗漏",
    "跳步": "跳步推导",
    "跳步推导": "跳步推导",
    "循环论证": "循环论证",
    "幻觉": "幻觉/无中生有",
    "无中生有": "幻觉/无中生有",
    "单位错误": "单位/格式不符",
    "格式不符": "单位/格式不符",
    "其他": "其他/无法归类",
    "无错误": "无错误",
}


def normalize_error_type(error_type: Optional[str]) -> str:
    """将错误类型标准化为预定义类别."""
    if not error_type:
        return "其他/无法归类"
    key = error_type.strip()
    return ERROR_TYPE_ALIASES.get(key, "其他/无法归类")


def classify_dependency_issue(issue_type: str) -> str:
    """将依赖图 issue 类型映射为错误类型."""
    if issue_type == "circular_dependency":
        return "循环论证"
    if issue_type in {"missing_reference", "future_reference", "disconnected_step"}:
        return "跳步推导"
    return "其他/无法归类"


def classify_error(
    step_valid: bool,
    calculation_correct: Optional[bool],
    judge_result: Optional[Dict],
    step_text: str,
    dependency_issue: Optional[Dict] = None,
) -> str:
    """根据多种信息综合判断错误类型.

    优先级：
    1. 依赖图 issue（算法判定零幻觉）
    2. LLM judge 给出的错误类型
    3. 计算错误（如果符号验证失败）
    4. 结构问题（跳步/重复等）
    5. 无法归类
    """
    if step_valid and not dependency_issue:
        return "无错误"

    if dependency_issue:
        return classify_dependency_issue(dependency_issue.get("type", ""))

    # 符号层计算错误优先级高于 judge 的语义标签，避免把可确定性计算错误误判为跳步
    if calculation_correct is False:
        return "计算错误"

    if judge_result and judge_result.get("error_type"):
        et = normalize_error_type(judge_result.get("error_type"))
        if et != "无错误":
            return et

    step_lower = step_text.lower()
    if "重复" in step_lower or "循环" in step_lower:
        return "循环论证"
    if "缺少" in step_lower or "跳步" in step_lower:
        return "跳步推导"

    return "其他/无法归类"


def aggregate_error_distribution(evaluations: List[Dict]) -> Dict[str, int]:
    """统计错误类型分布."""
    dist = {et: 0 for et in ERROR_TYPES}
    for ev in evaluations:
        et = ev.get("error_type", "其他/无法归类")
        et = normalize_error_type(et)
        dist[et] = dist.get(et, 0) + 1
    return dist


if __name__ == "__main__":
    print(normalize_error_type("theorem_misuse"))
    print(normalize_error_type("计算错误"))
    print(classify_error(False, False, None, ""))
