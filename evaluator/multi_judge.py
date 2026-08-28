"""多 Judge 交叉复核.

支持通过环境变量配置多个 LLM-as-judge，例如：
  JUDGE_HY3_API_BASE=http://0.0.0.0:8002/v1
  JUDGE_HY3_API_KEY=dummy
  JUDGE_HY3_MODEL=hy3-gptq-int4

  JUDGE_GPT_API_BASE=https://...
  JUDGE_GPT_API_KEY=...
  JUDGE_GPT_MODEL=gpt-5.6-terra

  JUDGE_GEMINI_API_BASE=https://...
  JUDGE_GEMINI_API_KEY=...
  JUDGE_GEMINI_MODEL=gemini-3.5-flash

若未配置额外 judge，则默认使用 HY3_* 环境变量创建一个 judge。
"""

import os
from collections import Counter
from statistics import median
from typing import Dict, List, Optional

from app.hy3_client import Hy3MathClient
from evaluator.llm_judge import LLMJudge


JUDGE_ENV_PREFIXES = ["JUDGE_HY3", "JUDGE_GPT", "JUDGE_GEMINI"]


def _load_judge_from_env(prefix: str) -> Optional[LLMJudge]:
    """从环境变量加载指定前缀的 judge."""
    api_base = os.environ.get(f"{prefix}_API_BASE")
    api_key = os.environ.get(f"{prefix}_API_KEY")
    model_name = os.environ.get(f"{prefix}_MODEL")
    if not api_base or not model_name:
        return None
    client = Hy3MathClient(api_base=api_base, api_key=api_key, model_name=model_name)
    return LLMJudge(client=client)


def load_judges_from_env() -> List[LLMJudge]:
    """加载所有已配置的多 judge."""
    judges = []
    for prefix in JUDGE_ENV_PREFIXES:
        judge = _load_judge_from_env(prefix)
        if judge:
            judges.append(judge)

    # 兜底：至少使用默认 Hy3 judge
    if not judges:
        from evaluator.llm_judge import LLMJudge as BaseLLMJudge

        judges.append(BaseLLMJudge())

    return judges


def _majority_vote_bool(values: List[Optional[bool]]) -> bool:
    """对布尔/None 值做多数投票：无效票视为弃权，若平票则偏保守（判为 False）."""
    valid = [v for v in values if v is not None]
    if not valid:
        return False
    true_count = sum(valid)
    false_count = len(valid) - true_count
    # 只有明确多数认为正确，才判正确
    return true_count > false_count


def _mode_or_first(values: List) -> Optional:
    """取众数；若无众数取第一个非空值."""
    non_empty = [v for v in values if v is not None and v != ""]
    if not non_empty:
        return None
    counter = Counter(non_empty)
    most_common = counter.most_common(1)[0][0]
    return most_common


def _median_step(values: List[Optional[int]]) -> Optional[int]:
    """取错误步的中位数，避免极端值."""
    valid = [v for v in values if v is not None]
    if not valid:
        return None
    return int(median(valid))


class MultiLLMJudge:
    """多 Judge 投票审查器."""

    def __init__(self, judges: Optional[List[LLMJudge]] = None):
        """初始化.

        Args:
            judges: judge 列表。若为 None，则从环境变量自动加载。
        """
        self.judges = judges if judges is not None else load_judges_from_env()
        if not self.judges:
            raise RuntimeError("未配置任何可用的 LLM judge")

    def judge(
        self,
        problem_text: str,
        steps: List[Dict],
        max_tokens: int = 1024,
        temperature: float = 0.2,
        level: Optional[str] = None,
    ) -> Dict:
        """调用多个 judge 并聚合结果."""
        results = []
        for j in self.judges:
            try:
                res = j.judge(
                    problem_text,
                    steps,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    level=level,
                )
                results.append(res)
            except Exception as e:
                results.append(
                    {
                        "overall_valid": None,
                        "first_error_step": None,
                        "error_type": "其他/无法归类",
                        "error_detail": f"judge 调用失败: {e}",
                        "suggestion": "",
                    }
                )

        overall_valids = [r.get("overall_valid") for r in results]
        first_error_steps = [r.get("first_error_step") for r in results]
        error_types = [r.get("error_type") for r in results]
        error_details = [r.get("error_detail", "") for r in results]

        # 聚合
        aggregated_valid = _majority_vote_bool(overall_valids)
        aggregated_step = _median_step(first_error_steps)
        aggregated_type = _mode_or_first(error_types)
        # detail 选择与聚合类型一致的一条
        aggregated_detail = ""
        if aggregated_type:
            for et, ed in zip(error_types, error_details):
                if et == aggregated_type and ed:
                    aggregated_detail = ed
                    break
        if not aggregated_detail:
            aggregated_detail = _mode_or_first(error_details) or ""

        return {
            "overall_valid": aggregated_valid,
            "first_error_step": None if aggregated_valid else aggregated_step,
            "error_type": aggregated_type or "其他/无法归类",
            "error_detail": aggregated_detail,
            "suggestion": "",
            "judge_votes": results,
        }

    def judge_batch(
        self,
        items: List[Dict],
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> List[Dict]:
        """批量多 judge 审查（顺序执行，每个 judge 独立调用）."""
        return [
            self.judge(
                item["problem"],
                item["steps"],
                max_tokens=max_tokens,
                temperature=temperature,
                level=item.get("level"),
            )
            for item in items
        ]
