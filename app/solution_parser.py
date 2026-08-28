"""解题过程结构化解析.

将模型原始输出切分为步骤，并提取最终答案。
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class Step:
    """解题步骤."""

    index: int
    text: str
    latex_expressions: List[str] = field(default_factory=list)
    depends_on: List[int] = field(default_factory=list)


@dataclass
class ParsedSolution:
    """结构化解题结果."""

    problem_id: str
    raw_output: str
    reasoning_content: Optional[str] = None
    steps: List[Step] = field(default_factory=list)
    final_answer: Optional[str] = None


def extract_latex_expressions(text: str) -> List[str]:
    """从文本中提取 latex 数学表达式.

    目前支持 $...$, \\[...\\], \\(...\\) 以及独立公式环境。
    """
    patterns = [
        r"\$\$(.+?)\$\$",
        r"\$(.+?)\$",
        r"\\\[(.+?)\\\]",
        r"\\\((.+?)\\\)",
    ]
    results = []
    for pat in patterns:
        for m in re.finditer(pat, text, re.DOTALL):
            expr = m.group(1).strip()
            if expr and expr not in results:
                results.append(expr)
    return results


def extract_depends_on(text: str) -> List[int]:
    """从步骤文本中提取依赖的前置步骤编号.

    支持以下格式变体：
    - depends_on: [1, 3]
    - depends_on: [1,2,3]
    - depends on: 1, 3
    - depends_on: 1, 2

    返回按升序排列的去重整数列表。若未匹配到依赖标注，返回空列表。
    """
    if not text:
        return []

    # 统一小写并兼容下划线/空格
    patterns = [
        r"depends[_\s]on\s*[:：]\s*\[\s*([\d,，\s]*)\s*\]",
        r"depends[_\s]on\s*[:：]\s*([\d,，\s]+)",
    ]

    deps: List[int] = []
    for pat in patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            nums_str = m.group(1)
            if not nums_str:
                continue
            for num in re.split(r"[,，\s]+", nums_str.strip()):
                if num.isdigit():
                    n = int(num)
                    if n not in deps:
                        deps.append(n)

    return sorted(deps)


def _find_strict_step_headers(text: str) -> List[Tuple[int, int, int]]:
    """查找严格位于行首的 "步骤 N：" / "Step N:" 类标题.

    Returns:
        列表，每个元素为 (start_pos, end_pos, step_number)
    """
    pattern = re.compile(
        r"(?:^|\n)\s*(?:步骤|Step|STEP)\s*(\d+)\s*[:：\.\)]?\s*",
        re.MULTILINE,
    )
    headers = []
    for m in pattern.finditer(text):
        step_num = int(m.group(1))
        # end_pos 为标题之后的正文起始位置
        headers.append((m.start(), m.end(), step_num))
    return headers


def split_into_steps(text: str) -> List[Step]:
    """将解题过程切分为步骤.

    优先识别严格位于行首的 "步骤 N：" / "Step N:" 标题（避免把
    "依据：步骤 1 的结论" 中的步骤字样误判为新步骤），
    未识别到时回退到旧版显式编号/段落切分逻辑。
    """
    if not text:
        return []

    # 1) 优先使用严格行首标题切分
    headers = _find_strict_step_headers(text)
    if len(headers) >= 2:
        chunks: List[Tuple[int, str]] = []
        for idx, (start, end, step_num) in enumerate(headers):
            content_start = end
            content_end = headers[idx + 1][0] if idx + 1 < len(headers) else len(text)
            content = text[content_start:content_end].strip()
            if content:
                chunks.append((step_num, content))
        # 如果按标题切分成功，直接构造 Step
        if chunks:
            steps = []
            for step_num, content in chunks:
                if len(content) < 5:
                    continue
                latex_exprs = extract_latex_expressions(content)
                deps = extract_depends_on(content)
                steps.append(Step(index=step_num, text=content, latex_expressions=latex_exprs, depends_on=deps))
            return steps

    # 2) 回退：旧版显式编号/段落切分
    explicit_patterns = [
        r"(?:^|\n)\s*(?:步骤|Step|STEP)\s*[\d一二三四五六七八九十]+\s*[:：\.\)]?\s*",
        r"(?:^|\n)\s*[\d一二三四五六七八九十]+[\.、\)]\s+",
        r"\n\s*(?:第[一二三四五六七八九十]+步|[①②③④⑤⑥⑦⑧⑨⑩])",
    ]

    split_regex = "|".join(f"({p})" for p in explicit_patterns)

    if re.search(split_regex, text, re.MULTILINE):
        parts = re.split(split_regex, text)
        chunks = [p for p in parts if p and not re.match(f"^({split_regex})$", p, re.MULTILINE)]
    else:
        chunks = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 10]

    steps = []
    for i, chunk in enumerate(chunks, start=1):
        chunk = chunk.strip()
        if not chunk:
            continue
        if len(chunk) < 5:
            continue
        latex_exprs = extract_latex_expressions(chunk)
        deps = extract_depends_on(chunk)
        steps.append(Step(index=i, text=chunk, latex_expressions=latex_exprs, depends_on=deps))

    return steps


def extract_boxed_answer(text: str) -> Optional[str]:
    """提取 \\boxed{...} 中的答案，支持嵌套大括号."""
    if not text:
        return None

    # 从后往前找最后一个 \boxed{
    idx = text.rfind("\\boxed{")
    if idx == -1:
        return None

    start = idx + len("\\boxed{")
    depth = 1
    end = start
    while end < len(text) and depth > 0:
        if text[end] == "{":
            depth += 1
        elif text[end] == "}":
            depth -= 1
        end += 1

    if depth == 0:
        return text[start : end - 1].strip()
    return None


def extract_final_answer(text: str) -> Optional[str]:
    """提取最终答案，优先使用 \\boxed{}，其次关键词匹配."""
    boxed = extract_boxed_answer(text)
    if boxed:
        return boxed

    # 关键词匹配
    markers = ["最终答案", "答案是", "答案为", "答案:", "answer is", "answer:", "\\therefore"]
    lower_text = text.lower()
    for marker in markers:
        idx = lower_text.rfind(marker.lower())
        if idx != -1:
            tail = text[idx + len(marker) :].strip()
            # 取第一行或第一个句号/分号前的内容
            line = re.split(r"[。；;\n]", tail)[0].strip()
            # 去掉前导冒号
            line = line.lstrip(":").strip()
            if line:
                return line

    # 兜底：取最后一段非空文本
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    if lines:
        return lines[-1]
    return None


def parse_solution(problem_id: str, raw_output: str, reasoning_content: Optional[str] = None) -> ParsedSolution:
    """解析模型原始输出为结构化解题过程.

    Args:
        problem_id: 题目 ID
        raw_output: 模型完整输出
        reasoning_content: 从 reasoning parser 提取的 thinking 内容（可选）

    Returns:
        ParsedSolution 对象
    """
    # 如果存在 reasoning_content，通常 raw_output 是正式回答
    # 但 raw_output 本身也可能包含 think 标签，这里做简化处理
    text_to_parse = reasoning_content if reasoning_content else raw_output

    steps = split_into_steps(text_to_parse)
    final_answer = extract_final_answer(raw_output)

    return ParsedSolution(
        problem_id=problem_id,
        raw_output=raw_output,
        reasoning_content=reasoning_content,
        steps=steps,
        final_answer=final_answer,
    )


if __name__ == "__main__":
    sample = """
步骤 1：设钢笔数量为 x 支。
根据题意，笔记本花费 5 × 8 = 40 元，钢笔花费 12x 元，总花费为 104 元。
depends_on: []

步骤 2：列方程。
40 + 12x = 104。
depends_on: [1]

步骤 3：解方程。
12x = 104 - 40 = 64，因此 x = 64 / 12。这显然不对，应该重新检查。
depends_on: [1, 2]

实际上：12x = 64，x = 16/3，不是整数。让我重新审题。

重新步骤 2：5 本笔记本花费 5×8=40 元，所以钢笔花费 104-40=64 元，因此 x = 64/12。还是不对。
depends_on: [1]

再检查：笔记本 8 元一本，5 本 40 元；钢笔 12 元一支；64 不是 12 的倍数，说明题目数据可能有误。若按 104-40=64，x=16/3。

为了得到整数答案，假设总花费应为 100 元，则 12x=60，x=5。但题目给的是 104。

正确答案应为：x = 16/3。

\\boxed{16/3}
"""
    parsed = parse_solution("demo", sample)
    print(f"final_answer: {parsed.final_answer}")
    for s in parsed.steps:
        print(f"Step {s.index}: depends_on={s.depends_on}, text={s.text[:60]}...")

    # 验证 extract_depends_on 兼容多种变体
    assert extract_depends_on("depends_on: [1, 3]") == [1, 3]
    assert extract_depends_on("depends_on: [1,2,3]") == [1, 2, 3]
    assert extract_depends_on("depends on: 1, 3") == [1, 3]
    assert extract_depends_on("depends_on: 1, 2") == [1, 2]
    assert extract_depends_on("无依赖标注") == []
    print("extract_depends_on 变体测试通过")
