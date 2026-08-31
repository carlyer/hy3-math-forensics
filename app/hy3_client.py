"""Hy3 推理客户端封装.

支持两种模式：
1. 本地 vLLM 离线推理（LLM 类）
2. OpenAI 兼容 API 服务（OpenAI 客户端）

通过环境变量切换：
- HY3_API_BASE：API 服务地址，如 http://0.0.0.0:8002/v1
- HY3_API_KEY：API key（本地服务可留空）
- HY3_MODEL_NAME：服务上的模型名，如 hy3-gptq-int4

如果设置了 HY3_API_BASE，则优先使用 API 模式；否则加载本地模型。
"""

import json
import os
import time
from pathlib import Path
from typing import Dict, List, Optional


class Hy3MathClient:
    """基于 vLLM 本地或 API 服务的 Hy3 数学解题客户端."""

    def __init__(
        self,
        model_path: Optional[str] = None,
        api_base: Optional[str] = None,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        tensor_parallel_size: int = 2,
        max_model_len: int = 8192,
        dtype: str = "auto",
        gpu_memory_utilization: float = 0.9,
        **kwargs,
    ):
        """初始化客户端.

        Args:
            model_path: 本地模型路径
            api_base: OpenAI 兼容 API base URL
            api_key: API key
            model_name: API 服务上的模型名
            tensor_parallel_size: 本地 Tensor 并行数
            max_model_len: 本地最大序列长度
            dtype: 本地数据类型
            gpu_memory_utilization: 本地 GPU 显存占用比例
            **kwargs: 额外参数
        """
        self.api_mode = api_base is not None
        self.model_path = model_path
        self.api_base = api_base
        self.api_key = api_key
        self.model_name = model_name
        # 部分 OpenAI 推理模型（网关上的 gpt-5.6-terra 等）不支持 temperature/top_p
        self.is_reasoning_model = bool(
            model_name
            and any(model_name.startswith(p) for p in ("o1", "o3", "gpt-5.6"))
        )
        # Gemini 模型在该网关下传 max_tokens/max_completion_tokens 会返回空 message
        self.is_gemini_model = bool(
            model_name and "gemini" in model_name.lower()
        )

        if self.api_mode:
            from openai import OpenAI

            self.client = OpenAI(
                base_url=api_base.rstrip("/"),
                api_key=api_key or "dummy",
            )
            print(f"使用 API 模式: {api_base}, model={model_name}")
        else:
            from vllm import LLM, SamplingParams

            self.LLM = LLM
            self.SamplingParams = SamplingParams
            print(f"正在加载本地模型: {model_path}")
            self.llm = LLM(
                model=model_path,
                tensor_parallel_size=tensor_parallel_size,
                max_model_len=max_model_len,
                dtype=dtype,
                gpu_memory_utilization=gpu_memory_utilization,
                trust_remote_code=True,
                **kwargs,
            )
            print("本地模型加载完成")

    def generate(
        self,
        prompts: List[str],
        temperature: float = 0.6,
        top_p: float = 0.9,
        max_tokens: int = 2048,
        stop: Optional[List[str]] = None,
        **kwargs,
    ) -> List[Dict]:
        """批量生成解题过程."""
        if self.api_mode:
            return self._generate_api(prompts, temperature, top_p, max_tokens, stop, **kwargs)
        return self._generate_local(prompts, temperature, top_p, max_tokens, stop, **kwargs)

    def _generate_local(
        self,
        prompts: List[str],
        temperature: float,
        top_p: float,
        max_tokens: int,
        stop: Optional[List[str]],
        **kwargs,
    ) -> List[Dict]:
        sampling_params = self.SamplingParams(
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            stop=stop,
            **kwargs,
        )
        outputs = self.llm.generate(prompts, sampling_params)
        results = []
        for out in outputs:
            generated = out.outputs[0]
            item = {
                "text": generated.text,
                "token_ids": generated.token_ids,
                "finish_reason": generated.finish_reason,
            }
            if hasattr(generated, "reasoning_content"):
                item["reasoning_content"] = generated.reasoning_content
            results.append(item)
        return results

    def _generate_api(
        self,
        prompts: List[str],
        temperature: float,
        top_p: float,
        max_tokens: int,
        stop: Optional[List[str]],
        **kwargs,
    ) -> List[Dict]:
        results = []
        for prompt in prompts:
            # API 通常接收 messages，这里 prompt 已经是格式化后的字符串
            # 为了兼容，我们把 prompt 作为 user message
            messages = [{"role": "user", "content": prompt}]
            create_kwargs = {
                "model": self.model_name,
                "messages": messages,
            }
            # Gemini 在该网关下传 max_completion_tokens 会返回空 message
            if not self.is_gemini_model:
                create_kwargs["max_completion_tokens"] = max_tokens
            if not self.is_reasoning_model:
                if temperature is not None:
                    create_kwargs["temperature"] = temperature
                if top_p is not None:
                    create_kwargs["top_p"] = top_p
            if stop is not None:
                create_kwargs["stop"] = stop
            response = self.client.chat.completions.create(**create_kwargs)
            if response.choices is None:
                err = getattr(response, "data", None) or getattr(response, "msg", "unknown API error")
                raise RuntimeError(f"API 返回空 choices: {err}")
            choice = response.choices[0]
            usage = response.usage
            # Gemini 在 token 受限时可能返回空 message
            msg_content = ""
            if choice.message is not None:
                msg_content = choice.message.content or ""
            item = {
                "text": msg_content,
                "finish_reason": choice.finish_reason,
                "messages": messages,
                "prompt": prompt,
                "token_usage": {
                    "prompt_tokens": usage.prompt_tokens if usage else None,
                    "completion_tokens": usage.completion_tokens if usage else None,
                    "total_tokens": usage.total_tokens if usage else None,
                },
                "model_name": self.model_name,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            }
            # vLLM API 可能返回 reasoning 字段
            if choice.message is not None and hasattr(choice.message, "reasoning") and choice.message.reasoning:
                item["reasoning_content"] = choice.message.reasoning
            results.append(item)
            # 简单流控，避免压垮服务
            time.sleep(0.05)
        return results

    def chat_generate(
        self,
        messages_list: List[List[Dict]],
        temperature: float = 0.6,
        top_p: float = 0.9,
        max_tokens: int = 2048,
        **kwargs,
    ) -> List[Dict]:
        """使用 chat 格式批量生成."""
        if self.api_mode:
            return self._chat_generate_api(messages_list, temperature, top_p, max_tokens, **kwargs)
        return self._chat_generate_local(messages_list, temperature, top_p, max_tokens, **kwargs)

    def _chat_generate_local(
        self,
        messages_list: List[List[Dict]],
        temperature: float,
        top_p: float,
        max_tokens: int,
        **kwargs,
    ) -> List[Dict]:
        tokenizer = self.llm.get_tokenizer()
        prompts = []
        for messages in messages_list:
            prompt = tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )
            prompts.append(prompt)
        return self.generate(
            prompts,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            **kwargs,
        )

    def _chat_generate_api(
        self,
        messages_list: List[List[Dict]],
        temperature: float,
        top_p: float,
        max_tokens: int,
        **kwargs,
    ) -> List[Dict]:
        results = []
        for messages in messages_list:
            create_kwargs = {
                "model": self.model_name,
                "messages": messages,
            }
            # Gemini 在该网关下传 max_completion_tokens 会返回空 message
            if not self.is_gemini_model:
                create_kwargs["max_completion_tokens"] = max_tokens
            if not self.is_reasoning_model:
                if temperature is not None:
                    create_kwargs["temperature"] = temperature
                if top_p is not None:
                    create_kwargs["top_p"] = top_p
            response = self.client.chat.completions.create(**create_kwargs)
            if response.choices is None:
                err = getattr(response, "data", None) or getattr(response, "msg", "unknown API error")
                raise RuntimeError(f"API 返回空 choices: {err}")
            choice = response.choices[0]
            usage = response.usage
            # Gemini 在 token 受限时可能返回空 message
            msg_content = ""
            if choice.message is not None:
                msg_content = choice.message.content or ""
            item = {
                "text": msg_content,
                "finish_reason": choice.finish_reason,
                "messages": messages,
                "prompt": None,  # chat 模式下 prompt 由 messages 完整表示
                "token_usage": {
                    "prompt_tokens": usage.prompt_tokens if usage else None,
                    "completion_tokens": usage.completion_tokens if usage else None,
                    "total_tokens": usage.total_tokens if usage else None,
                },
                "model_name": self.model_name,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            }
            if choice.message is not None and hasattr(choice.message, "reasoning") and choice.message.reasoning:
                item["reasoning_content"] = choice.message.reasoning
            results.append(item)
            time.sleep(0.05)
        return results


def load_client_from_env() -> Hy3MathClient:
    """从环境变量加载客户端.

    若项目根目录存在 .env 文件且未显式设置相关变量，则自动加载。
    """
    # 自动加载 .env（如果存在且环境变量未显式设置）
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        try:
            from dotenv import load_dotenv

            load_dotenv(env_path, override=False)
        except ImportError:
            pass

    api_base = os.environ.get("HY3_API_BASE")
    api_key = os.environ.get("HY3_API_KEY")
    model_name = os.environ.get("HY3_MODEL_NAME", "hy3-gptq-int4")

    if api_base:
        return Hy3MathClient(
            api_base=api_base,
            api_key=api_key,
            model_name=model_name,
        )

    default_path = "/path/to/hy3-gptq-int4"
    model_path = os.environ.get("HY3_MODEL_PATH", default_path)
    tp_size = int(os.environ.get("HY3_TP_SIZE", "2"))
    max_model_len = int(os.environ.get("HY3_MAX_MODEL_LEN", "8192"))

    return Hy3MathClient(
        model_path=model_path,
        tensor_parallel_size=tp_size,
        max_model_len=max_model_len,
    )


def load_judge_client_from_env() -> Hy3MathClient:
    """加载专门用于 LLM-as-judge 的客户端.

    为防止模型自评（Hy3 评 Hy3）导致分数虚高，默认优先使用外部裁判：
    - 优先读取 JUDGE_GPT_API_BASE / JUDGE_GPT_API_KEY / JUDGE_GPT_MODEL
    - 若未配置 GPT 裁判，则回退到 JUDGE_HY3_* 配置
    - 若仍无配置，最后回退到通用 load_client_from_env()（并打印警告）
    """
    # 自动加载 .env（如果存在且环境变量未显式设置）
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        try:
            from dotenv import load_dotenv

            load_dotenv(env_path, override=False)
        except ImportError:
            pass

    # 1. 优先使用 GPT 外部裁判
    gpt_base = os.environ.get("JUDGE_GPT_API_BASE")
    gpt_key = os.environ.get("JUDGE_GPT_API_KEY")
    gpt_model = os.environ.get("JUDGE_GPT_MODEL", "gpt-5.6-terra")
    if gpt_base:
        print(f"[JudgeClient] 使用 GPT 外部裁判: {gpt_model} @ {gpt_base}")
        return Hy3MathClient(
            api_base=gpt_base,
            api_key=gpt_key,
            model_name=gpt_model,
        )

    # 2. 回退到专用 Hy3 裁判配置（兼容 multi_judge 的 JUDGE_HY3_*）
    hy3_base = os.environ.get("JUDGE_HY3_API_BASE")
    hy3_key = os.environ.get("JUDGE_HY3_API_KEY")
    hy3_model = os.environ.get("JUDGE_HY3_MODEL")
    if hy3_base and hy3_model:
        print(f"[JudgeClient] 使用 Hy3 专用裁判: {hy3_model} @ {hy3_base}")
        return Hy3MathClient(
            api_base=hy3_base,
            api_key=hy3_key,
            model_name=hy3_model,
        )

    # 3. 最后回退到默认客户端（通常就是 Hy3 自身）
    print("[JudgeClient] 警告：未配置 JUDGE_GPT_* 或 JUDGE_HY3_*，回退到默认模型（可能是 Hy3 自评）")
    return load_client_from_env()


if __name__ == "__main__":
    # 简单冒烟测试
    client = load_client_from_env()
    results = client.generate(["1+1等于几？请给出答案。"], max_tokens=256)
    print(json.dumps(results, ensure_ascii=False, indent=2))
