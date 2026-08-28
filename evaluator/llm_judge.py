"""LLM-as-judge 过程审查.

利用 LLM 对每个解题步骤进行语义和逻辑审查，判断是否存在：
- 题意误读
- 概念理解错误
- 定理/公式误用
- 条件遗漏
- 跳步推导
- 循环论证
- 幻觉
"""

import json
import os
from typing import Dict, List, Optional

from app.hy3_client import Hy3MathClient, load_judge_client_from_env


JUDGE_SYSTEM_PROMPT = """你是一位严格的数学解题过程审查专家。你的任务是对比题目和解题步骤，判断每一步是否存在逻辑或概念错误，并给出最贴切的错误类型。

请按以下 JSON 格式输出：
{
  "overall_valid": true/false,
  "first_error_step": null 或 整数,
  "error_type": "题意误读" | "概念理解错误" | "定理/公式误用" | "计算错误" | "条件遗漏" | "跳步推导" | "循环论证" | "幻觉/无中生有" | "单位/格式不符" | "其他/无法归类" | "无错误",
  "error_detail": "具体说明，若无错误则为空",
  "suggestion": "若存在错误，给出正确写法建议"
}

审查原则：
1. 步骤必须能被题目条件和前面步骤逻辑推出；
2. 使用的每个定理、公式必须满足适用条件；
3. 不允许凭空引入未给出的条件或结论；
4. 不允许用结论证明结论（循环论证）；
5. 关键步骤缺失视为跳步；
6. 优先匹配最具体的错误类型，只有在既无概念/定理/计算/条件等具体错误、又确实存在中间环节缺失时，才归为“跳步推导”；
7. 只输出 JSON，不要输出其他内容。

错误类型判定示例（请务必先匹配具体类型，再落为“跳步”或“其他”）：
- 题意误读：把“至少有一个”理解为“恰好有一个”，或把“互斥”当成“独立”。
- 概念理解错误：把排列当成组合，把集合的补集当成交集。
- 定理/公式误用：在非直角三角形中直接用勾股定理，或在等比数列求和时公比 q=1 仍套公式。
- 计算错误：明确的数值、符号、代数运算错误，如 2×3=5 或去括号未变号。
- 条件遗漏：漏用 x>0、整数约束、等号成立条件等关键限制。
- 跳步推导：从条件直接跳到结论，缺少可验证的中间环节（无具体概念/计算错误可归时才用）。
- 循环论证：用待证结论作为推理依据。
- 幻觉/无中生有：引入题目未给定的数字、定理或“显然成立”的断言。
- 单位/格式不符：单位不统一、数量级错误、答案形式与题目要求不符。

Few-shot 判例：
Q: 解方程 2x+4=10。步骤1: 2x+4=10；步骤2: 2x=6；步骤3: x=3。
A: {"overall_valid":true,"first_error_step":null,"error_type":"无错误","error_detail":"","suggestion":""}

Q: 解方程 2x+4=10。步骤1: 2x+4=10；步骤2: 2x=8；步骤3: x=4。
A: {"overall_valid":false,"first_error_step":2,"error_type":"计算错误","error_detail":"步骤2移项计算错误，10-4=6而非8。","suggestion":"步骤2应为 2x=10-4=6。"}

Q: 直角三角形两直角边为3、4，求斜边。步骤1: 斜边=3+4=7。
A: {"overall_valid":false,"first_error_step":1,"error_type":"定理/公式误用","error_detail":"误用加法代替勾股定理，应使用 c=√(3²+4²)=5。","suggestion":"步骤1应为 斜边=√(3²+4²)=5。"}

Q: 求 x>0 时 f(x)=x+1/x 最小值。步骤1: 由均值不等式 f(x)≥2；步骤2: 最小值为2。
A: {"overall_valid":false,"first_error_step":2,"error_type":"条件遗漏","error_detail":"未验证等号成立条件 x=1 是否在定义域 x>0 内。","suggestion":"补充：当且仅当 x=1/x 即 x=1 时取等，满足 x>0。"}

Q: 证明对任意正整数 n，n²+n 为偶数。步骤1: 假设 n²+n 为偶数；步骤2: 则结论成立。
A: {"overall_valid":false,"first_error_step":1,"error_type":"循环论证","error_detail":"用待证结论作为证明前提。","suggestion":"应分解 n²+n=n(n+1)，说明连续两整数必有一偶。"}"""


JUDGE_RESEARCH_SYSTEM_PROMPT = """你是一位极其严格的数学研究论文审稿人，正在审查一道研究级数学题的解题过程。该题可能涉及高等数论、代数几何、分析等前沿领域。

请按以下 JSON 格式输出：
{
  "overall_valid": true/false,
  "first_error_step": null 或 整数,
  "error_type": "题意误读" | "概念理解错误" | "定理/公式误用" | "计算错误" | "条件遗漏" | "跳步推导" | "循环论证" | "幻觉/无中生有" | "单位/格式不符" | "其他/无法归类" | "无错误",
  "error_detail": "具体说明，若无错误则为空",
  "suggestion": "若存在错误，给出正确写法建议"
}

审查原则（比普通题目更严格）：
1. 任何引用“已知结论/已被某某证明/显然”的地方，若该结论并非题目给定或大学本科以下常识，必须给出证明或可靠来源；否则视为幻觉或无证据断言。
2. 每一步推导必须显式说明依据，不能依赖“由对称性/显然/不难看出”等模糊表述。
3. 使用的定理必须严格核对适用条件；研究级定理（如 GRH、Chebotarev、Riemann 假设等）不能默认成立，除非题目明确允许。
4. 对于构造性证明或具体计算，必须验证构造确实满足所有约束，不能仅说明“可以验证”。
5. 若解题过程在关键处戛然而止、未给出最终答案或未证明核心断言，视为跳步/不完整。
6. 只输出 JSON，不要输出其他内容。"""


def build_judge_prompt(problem_text: str, steps: List[Dict]) -> str:
    """构建审查 prompt."""
    steps_text = "\n\n".join(
        f"步骤 {s.get('index', i+1)}：\n{s.get('text', '')}"
        for i, s in enumerate(steps)
    )
    return f"题目：\n{problem_text}\n\n解题过程：\n{steps_text}\n\n请审查上述解题过程，返回 JSON 结果。"


def parse_judge_output(text: str) -> Dict:
    """解析 judge 输出的 JSON."""
    text = text.strip()
    # 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 尝试从 markdown 代码块中提取
    import re
    blocks = re.findall(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    for block in blocks:
        try:
            return json.loads(block.strip())
        except json.JSONDecodeError:
            continue
    # 兜底：返回无法解析
    return {
        "overall_valid": None,
        "first_error_step": None,
        "error_type": "其他/无法归类",
        "error_detail": f"Judge 输出无法解析为 JSON: {text[:200]}",
        "suggestion": "",
    }


class LLMJudge:
    """LLM 过程审查器."""

    # 部分 OpenAI 推理模型（如 o1/o3 系列及该网关上的 gpt-5.6-terra）不支持 temperature != 1
    REASONING_MODEL_PREFIXES = ("o1", "o3", "gpt-5.6")

    def __init__(self, client: Optional[Hy3MathClient] = None):
        """初始化.

        Args:
            client: Hy3 客户端。若为 None，则尝试从环境变量加载；若加载失败，则进入 fallback 模式。
        """
        self.client = client
        self._fallback = False
        if self.client is None:
            try:
                # 默认使用外部裁判（如 GPT-5.6-terra），避免 Hy3 自评虚高
                self.client = load_judge_client_from_env()
            except Exception as e:
                print(f"[LLMJudge] 无法加载模型客户端: {e}")
                self._fallback = True

    def _select_prompt(self, level: Optional[str] = None) -> str:
        """根据题目难度选择审查 prompt."""
        if level == "L4":
            return JUDGE_RESEARCH_SYSTEM_PROMPT
        return JUDGE_SYSTEM_PROMPT

    def _default_temperature(self) -> float:
        """根据模型类型选择默认 temperature：推理模型通常只支持 1.0。"""
        model_name = getattr(self.client, "model_name", "") or ""
        if any(model_name.startswith(p) for p in self.REASONING_MODEL_PREFIXES):
            return 1.0
        return 0.2

    def judge(
        self,
        problem_text: str,
        steps: List[Dict],
        max_tokens: int = 1024,
        temperature: Optional[float] = None,
        level: Optional[str] = None,
    ) -> Dict:
        """对解题过程进行 LLM 审查.

        Returns:
            包含 overall_valid, first_error_step, error_type, error_detail 的字典
        """
        if self._fallback or self.client is None:
            return {
                "overall_valid": None,
                "first_error_step": None,
                "error_type": "其他/无法归类",
                "error_detail": "LLM judge 不可用（模型未加载），跳过语义审查",
                "suggestion": "",
            }

        if temperature is None:
            temperature = self._default_temperature()

        system_prompt = self._select_prompt(level)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": build_judge_prompt(problem_text, steps)},
        ]

        results = self.client.chat_generate(
            [messages],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        raw = results[0]["text"]
        return parse_judge_output(raw)

    def judge_batch(
        self,
        items: List[Dict],
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> List[Dict]:
        """批量审查.

        Args:
            items: 每个元素包含 problem、steps、level（可选）
        """
        if temperature is None:
            temperature = self._default_temperature()

        if self._fallback or self.client is None:
            return [
                {
                    "overall_valid": None,
                    "first_error_step": None,
                    "error_type": "其他/无法归类",
                    "error_detail": "LLM judge 不可用，跳过语义审查",
                    "suggestion": "",
                }
                for _ in items
            ]

        messages_list = []
        for item in items:
            level = item.get("level")
            system_prompt = self._select_prompt(level)
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": build_judge_prompt(item["problem"], item["steps"])},
            ]
            messages_list.append(messages)

        results = self.client.chat_generate(
            messages_list,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return [parse_judge_output(r["text"]) for r in results]
