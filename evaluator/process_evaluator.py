"""过程评估主入口.

综合规则校验、符号执行和 LLM-as-judge，输出：
- process_correct: 推理过程是否成立
- first_error_step: 首个错误步骤编号
- error_type: 错误类型
- error_detail: 错误详情
- correct_but_unjustified: 是否结果正确但过程不成立
"""

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from evaluator.back_substitution import verify_by_substitution
from evaluator.correct_but_wrong_process import detect_correct_but_unjustified
from evaluator.dependency_graph import validate_dependencies
from evaluator.error_classifier import classify_error, normalize_error_type
from evaluator.step_validator import validate_step
from evaluator.truncation_checker import detect_truncation


class ProcessEvaluator:
    """解题过程评估器."""

    def __init__(self, llm_judge: Optional[Any] = None):
        """初始化.

        Args:
            llm_judge: LLM 审查器（LLMJudge 或 MultiLLMJudge）。若为 None，则仅使用规则+符号验证。
        """
        self.llm_judge = llm_judge

    def evaluate(
        self,
        problem_text: str,
        steps: List[Dict],
        answer_correct: bool,
        use_llm: bool = True,
        verification_method: Optional[str] = None,
        raw_output: Optional[str] = None,
        finish_reason: Optional[str] = None,
        max_tokens: Optional[int] = None,
        completion_tokens: Optional[int] = None,
        level: Optional[str] = None,
        final_answer: Optional[str] = None,
    ) -> Dict:
        """评估单个解题过程.

        Args:
            problem_text: 原始题目
            steps: 步骤列表，每个元素包含 index 和 text
            answer_correct: 最终答案是否正确
            use_llm: 是否使用 LLM judge（若不可用则自动降级）
            verification_method: 答案校验方式，manual_check 时降低符号层误报
            raw_output: 原始模型输出，用于截断检测
            finish_reason: 模型停止原因
            max_tokens: 生成时的最大 token 数
            completion_tokens: 实际生成的 token 数
            level: 题目难度层级
            final_answer: 模型输出的最终答案，用于回代验证

        Returns:
            评估结果字典
        """
        if not steps:
            return {
                "process_correct": False,
                "first_error_step": None,
                "error_type": "跳步推导",
                "error_detail": "解题过程为空，没有任何步骤",
                "step_results": [],
                "llm_judge_result": None,
                "correct_but_unjustified": detect_correct_but_unjustified(
                    answer_correct, False, None
                ),
                "dependency_validation": {"valid": True, "issues": []},
            }

        # 依赖图验证（算法零幻觉判定，优先级最高）
        dependency_validation = validate_dependencies(steps)
        first_dep_issue = (
            dependency_validation["issues"][0] if dependency_validation["issues"] else None
        )

        step_results = []
        prev_steps = []

        # 逐层检查
        for step in steps:
            result = validate_step(
                step, prev_steps, problem_text, verification_method=verification_method, all_steps=steps
            )
            step_results.append(result)
            prev_steps.append(step)

        # 找出第一个规则/符号层面错误的步骤
        first_rule_error = None
        for r in step_results:
            if r["valid"] is False:
                first_rule_error = r
                break

        # LLM 语义审查（可选）
        llm_result = None
        first_llm_error_step = None
        if use_llm and self.llm_judge is not None:
            try:
                llm_result = self.llm_judge.judge(problem_text, steps, level=level)
                first_llm_error_step = llm_result.get("first_error_step")
            except Exception as e:
                llm_result = {
                    "overall_valid": None,
                    "first_error_step": None,
                    "error_type": "其他/无法归类",
                    "error_detail": f"LLM judge 调用失败: {e}",
                    "suggestion": "",
                }

        # 综合判定第一个错误步骤（依赖图错误优先级最高）
        first_error_step = None
        error_detail = None

        if first_dep_issue is not None:
            first_error_step = first_dep_issue["step_index"]
            error_detail = first_dep_issue["detail"]
        elif first_rule_error is not None:
            first_error_step = first_rule_error["step_index"]
            error_detail = first_rule_error["detail"]
        elif first_llm_error_step is not None:
            first_error_step = first_llm_error_step
            error_detail = llm_result.get("error_detail", "LLM judge 判定该步骤存在逻辑或概念错误")

        # 若 LLM 认为整体正确且无规则错误，则过程正确
        process_correct = first_error_step is None

        # 错误类型归类
        if first_error_step is not None and first_dep_issue is not None:
            error_type = classify_error(
                step_valid=False,
                calculation_correct=None,
                judge_result=llm_result,
                step_text=steps[first_error_step - 1].get("text", "") if first_error_step <= len(steps) else "",
                dependency_issue=first_dep_issue,
            )
        elif first_error_step is not None and first_rule_error is not None:
            error_type = classify_error(
                step_valid=False,
                calculation_correct=first_rule_error["checks"].get("calculation_correct"),
                judge_result=llm_result,
                step_text=steps[first_error_step - 1].get("text", "") if first_error_step <= len(steps) else "",
            )
        elif first_error_step is not None and llm_result:
            error_type = normalize_error_type(llm_result.get("error_type"))
        else:
            error_type = "无错误"

        # 截断/未完成检测：即使 LLM judge 未报错，也要检查输出是否完整
        truncation = detect_truncation(raw_output, finish_reason, max_tokens, completion_tokens)
        if truncation["truncated"]:
            process_correct = False
            first_error_step = steps[-1].get("index", len(steps)) if steps else None
            error_type = "跳步推导"
            error_detail = f"输出截断或推理未完成: {truncation['detail']}"

        # 结果正确但过程不成立检测
        cbu = detect_correct_but_unjustified(answer_correct, process_correct, first_error_step)

        # 回代验证：作为 CBU 的额外证据，或发现 answer_checker 等价性问题
        substitution_verification = None
        suspected_answer_equivalence = False
        if final_answer and problem_text:
            if answer_correct and not process_correct:
                substitution_verification = verify_by_substitution(
                    problem_text, final_answer, expected_type="auto"
                )
                if substitution_verification.get("verified"):
                    cbu["substitution_verified"] = True
                    cbu["substitution_detail"] = substitution_verification.get("detail")
            elif not answer_correct:
                substitution_verification = verify_by_substitution(
                    problem_text, final_answer, expected_type="auto"
                )
                if substitution_verification.get("verified"):
                    suspected_answer_equivalence = True

        result: Dict[str, Any] = {
            "process_correct": process_correct,
            "first_error_step": first_error_step,
            "error_type": error_type,
            "error_detail": error_detail,
            "step_results": step_results,
            "llm_judge_result": llm_result,
            "correct_but_unjustified": cbu,
            "truncation_check": truncation,
            "dependency_validation": dependency_validation,
        }

        if substitution_verification is not None:
            result["substitution_verification"] = substitution_verification
        if suspected_answer_equivalence:
            result["suspected_answer_equivalence"] = True

        return result


def evaluate_record(record: Dict, evaluator: ProcessEvaluator, use_llm: bool = True) -> Dict:
    """对生成结果记录（solutions.jsonl 中的一条）进行评估."""
    problem_text = record.get("problem", "")
    steps = record.get("steps", [])
    answer_correct = record.get("answer_correct", False)
    verification_method = record.get("verification", {}).get("method")
    raw_output = record.get("raw_output")
    finish_reason = record.get("finish_reason")
    max_tokens = record.get("generation_params", {}).get("max_tokens")
    completion_tokens = record.get("token_usage", {}).get("completion_tokens")
    level = record.get("level")

    eval_result = evaluator.evaluate(
        problem_text,
        steps,
        answer_correct,
        use_llm=use_llm,
        verification_method=verification_method,
        raw_output=raw_output,
        finish_reason=finish_reason,
        max_tokens=max_tokens,
        completion_tokens=completion_tokens,
        level=level,
        final_answer=record.get("final_answer"),
    )

    return {
        "problem_id": record.get("problem_id"),
        "level": record.get("level"),
        "answer_correct": answer_correct,
        "gold_answer": record.get("gold_answer"),
        "final_answer": record.get("final_answer"),
        **eval_result,
    }


if __name__ == "__main__":
    # 自检：回代验证集成到过程评估器
    evaluator = ProcessEvaluator(llm_judge=None)
    steps = [
        {"index": 1, "text": "设未知数为 x。"},
        {"index": 2, "text": "因为 1 + 1 = 3，所以 x = 3。"},
    ]

    # CBU 场景：答案正确但过程不成立，回代应通过
    result = evaluator.evaluate(
        "若 x + 2 = 5，求 x。",
        steps,
        answer_correct=True,
        use_llm=False,
        final_answer="x=3",
    )
    assert result["correct_but_unjustified"]["correct_but_unjustified"] is True
    assert result["correct_but_unjustified"].get("substitution_verified") is True
    print("CBU 回代增强证据:", result["correct_but_unjustified"])

    # 答案被判错但回代通过：提示 answer_checker 等价性问题
    result2 = evaluator.evaluate(
        "解方程 2x - 1 = 7。",
        steps,
        answer_correct=False,
        use_llm=False,
        final_answer="4",
    )
    assert result2.get("suspected_answer_equivalence") is True
    print(" suspected_answer_equivalence:", result2.get("suspected_answer_equivalence"))

    print("process_evaluator 回代集成自检通过")
