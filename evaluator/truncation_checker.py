"""检测模型输出是否截断或推理未完成.

主要启发式：
1. finish_reason != "stop"/"eos"（如 "length"）
2. 输出未以完整句末标点/数学定界符结尾
3. 未出现要求的 \\boxed{} 最终答案标记
4. 括号 / LaTeX 定界符未闭合
5. 已用 token 数接近 max_tokens（辅助信号）
"""

from typing import Dict, List, Optional


def detect_truncation(
    raw_output: Optional[str],
    finish_reason: Optional[str] = None,
    max_tokens: Optional[int] = None,
    completion_tokens: Optional[int] = None,
) -> Dict:
    """判断模型输出是否截断/未完成.

    Returns:
        {
            "truncated": bool,
            "reasons": [str, ...],
            "detail": str,
        }
    """
    reasons: List[str] = []
    text = (raw_output or "").rstrip()

    # 强截断信号：finish_reason 不是正常结束（vLLM/OpenAI 通常为 "stop" 或 "eos"）
    strong_truncation_signal = False
    if finish_reason and finish_reason not in ("stop", "eos"):
        reasons.append(f"finish_reason={finish_reason}，非正常结束")
        strong_truncation_signal = True

    if not text:
        reasons.append("输出为空")
        return {"truncated": True, "reasons": reasons, "detail": "; ".join(reasons)}

    # 只有在存在强截断信号时，才进一步检查完整性细节，避免对正常停止的完整输出误报
    if strong_truncation_signal:
        # 末尾字符是否像完整终止
        last_char = text[-1]
        if last_char not in ".。!！?？)}】）」』]$…":
            reasons.append(f"输出以非终止字符 '{last_char}' 结尾，疑似截断")

        # 未给出最终答案标记
        if r"\boxed{" not in text:
            reasons.append("未出现 \\boxed{} 最终答案标记")

        # 括号不平衡
        if text.count("{") != text.count("}"):
            reasons.append("花括号未闭合")
        if text.count("\\[") != text.count("\\]"):
            reasons.append("display math 定界符 \\[ / \\] 未闭合")
        if text.count("$") % 2 != 0:
            reasons.append("inline math 定界符 $ 未闭合")

        # 已用 token 接近上限（辅助信号）
        near_limit = bool(
            max_tokens
            and completion_tokens is not None
            and completion_tokens >= int(max_tokens * 0.95)
        )
        if near_limit:
            reasons.append(f"已用 token 数({completion_tokens})接近 max_tokens={max_tokens}")

    truncated = bool(reasons)
    detail = "; ".join(reasons) if truncated else "输出看起来完整"
    return {"truncated": truncated, "reasons": reasons, "detail": detail}
