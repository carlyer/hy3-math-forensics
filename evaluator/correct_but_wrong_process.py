"""识别“结果正确但推理过程不成立”的样本."""

from typing import Dict, Optional


def detect_correct_but_unjustified(
    answer_correct: bool,
    process_correct: bool,
    first_error_step: Optional[int],
) -> Dict:
    """判断是否为结果正确但过程不成立.

    判定条件：
    1. 最终答案正确；
    2. 过程被判为不正确，或存在明确的错误步骤。

    Returns:
        {
            "correct_but_unjustified": bool,
            "reason": str
        }
    """
    if not answer_correct:
        return {
            "correct_but_unjustified": False,
            "reason": "最终答案错误，不属于结果正确但过程不成立",
        }

    if not process_correct or first_error_step is not None:
        return {
            "correct_but_unjustified": True,
            "reason": f"最终答案正确，但步骤 {first_error_step} 存在无法支撑的推理",
        }

    return {
        "correct_but_unjustified": False,
        "reason": "最终答案正确且过程无明显错误",
    }


if __name__ == "__main__":
    print(detect_correct_but_unjustified(True, False, 2))
    print(detect_correct_but_unjustified(True, True, None))
    print(detect_correct_but_unjustified(False, False, 1))
