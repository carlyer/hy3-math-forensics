"""解题提示词模板."""

SYSTEM_PROMPT = """你是一位极其严谨的数学解题专家。你的任务是针对用户给出的数学题目，给出完整、分步、可验证的解题过程。

要求：
1. 仔细阅读题目，明确已知条件、约束和求解目标；
2. 输出必须分步骤，每步以 "步骤 N：" 开头（N 为步骤编号）；
3. 每一步推导必须写明依据（定义、公理、定理、公式或前一步结论）；
4. 每步末尾必须用一行独立的小字标注本步依赖的前置步骤编号，格式为 `depends_on: [1, 3]`；若没有依赖则写 `depends_on: []`；
5. 不允许引用不存在的步骤或后续步骤，也不允许循环依赖；
6. 若使用定理或公式，必须确认其适用条件已满足；
7. 中间计算必须准确，注意符号、单位和边界条件；
8. 最后必须用 \boxed{...} 给出最终答案。

请用中文输出完整解题过程。"""


def build_math_prompt(problem: str) -> str:
    """构建数学解题提示词.

    Args:
        problem: 题目文本

    Returns:
        完整的 user prompt
    """
    return f"题目：\n{problem}\n\n请给出完整、分步的解题过程，每步以 \"步骤 N：\" 开头，并在每步末尾用一行独立的小字标注 `depends_on: [...]` 以说明本步依赖的前置步骤编号（没有依赖则写 `depends_on: []`）。最后必须用 \\boxed{{}} 给出最终答案。"


def build_messages(problem: str) -> list:
    """构建标准 chat messages 格式，供 vLLM apply_chat_template 使用."""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_math_prompt(problem)},
    ]
