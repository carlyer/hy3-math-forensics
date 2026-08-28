"""多采样解题生成器.

对同一道题在 temperature > 0 下独立采样 N 次，生成多个候选解答.
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.prompt_templates import build_messages
from app.solution_parser import parse_solution
from dataset.answer_checker import check_answer


def _step_to_dict(step: Any) -> Dict[str, Any]:
    """将 Step 数据类或对象序列化为字典."""
    return {
        "index": step.index,
        "text": step.text,
        "latex_expressions": step.latex_expressions,
        "depends_on": step.depends_on,
    }


def generate_multiple_solutions(
    client: Any,
    problem: Dict[str, Any],
    n_samples: int = 5,
    temperature: float = 0.8,
    top_p: float = 0.95,
    max_tokens: int = 3072,
) -> List[Dict[str, Any]]:
    """对同一道题生成 N 个独立样本.

    Args:
        client: Hy3MathClient 或任何实现了 chat_generate(messages_list, ...) 的客户端.
        problem: 题目字典，需包含 id / problem / answer / verification 字段.
        n_samples: 采样次数.
        temperature: 采样温度.
        top_p: nucleus sampling 参数.
        max_tokens: 最大生成 token 数.

    Returns:
        每个元素为样本结果字典，包含 raw_output、steps、final_answer、
        answer_correct、token_usage、finish_reason 等字段.
    """
    if n_samples <= 0:
        return []

    messages = build_messages(problem["problem"])
    # 构造 N 份独立请求（内容相同但为独立采样）
    messages_list = [messages for _ in range(n_samples)]

    outputs = client.chat_generate(
        messages_list,
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens,
    )

    verification = problem.get("verification", {"method": "exact_match"})
    samples: List[Dict[str, Any]] = []

    for out in outputs:
        raw_output = out.get("text", "")
        parsed = parse_solution(
            problem_id=problem["id"],
            raw_output=raw_output,
            reasoning_content=out.get("reasoning_content"),
        )

        answer_correct, answer_detail = check_answer(
            parsed.final_answer,
            problem.get("answer"),
            verification,
        )

        samples.append(
            {
                "problem_id": problem["id"],
                "raw_output": parsed.raw_output,
                "reasoning_content": parsed.reasoning_content,
                "steps": [_step_to_dict(s) for s in parsed.steps],
                "final_answer": parsed.final_answer,
                "answer_correct": answer_correct,
                "answer_check_detail": answer_detail,
                "token_usage": out.get("token_usage"),
                "finish_reason": out.get("finish_reason"),
                "model_name": out.get("model_name"),
                "timestamp": out.get("timestamp"),
            }
        )

    return samples


if __name__ == "__main__":
    """自检：使用 DummyClient 验证多采样生成与解析链路."""

    class DummyClient:
        """模拟客户端，返回若干固定格式的解答."""

        def chat_generate(self, messages_list: List[List[Dict[str, Any]]], **kwargs: Any) -> List[Dict[str, Any]]:
            results = []
            for idx in range(len(messages_list)):
                text = (
                    f"步骤 1：设未知数为 x，则 x = {idx + 1}。\n"
                    "depends_on: []\n\n"
                    f"\\boxed{{{idx + 1}}}"
                )
                results.append(
                    {
                        "text": text,
                        "finish_reason": "stop",
                        "token_usage": {
                            "prompt_tokens": 10,
                            "completion_tokens": 20,
                            "total_tokens": 30,
                        },
                    }
                )
            return results

    problem = {
        "id": "demo",
        "problem": "求一个整数。",
        "answer": "1",
        "verification": {"method": "exact_match"},
    }

    samples = generate_multiple_solutions(
        DummyClient(), problem, n_samples=3, temperature=0.8
    )
    print(json.dumps(samples, ensure_ascii=False, indent=2))
    assert len(samples) == 3
    assert samples[0]["answer_correct"] is True
    print("\n多采样生成器自检通过")
