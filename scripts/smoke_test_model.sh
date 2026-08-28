#!/bin/bash
# Hy3 模型加载/API 冒烟测试

set -e

cd /path/to/workspace/hy3-math-eval

# 默认使用 API 服务；如需本地推理，取消设置 HY3_API_BASE
export HY3_API_BASE=${HY3_API_BASE:-http://0.0.0.0:8002/v1}
export HY3_MODEL_NAME=${HY3_MODEL_NAME:-hy3-gptq-int4}

# 本地模式参数（仅在未设置 HY3_API_BASE 时生效）
export HY3_MODEL_PATH=${HY3_MODEL_PATH:-/path/to/workspace/bifrost-2026082410005000-内部网关/path/to/hy3-gptq-int4}
export HY3_TP_SIZE=${HY3_TP_SIZE:-2}
export HY3_MAX_MODEL_LEN=${HY3_MAX_MODEL_LEN:-4096}
export VLLM_FLASHINFER_ALLREDUCE_BACKEND=${VLLM_FLASHINFER_ALLREDUCE_BACKEND:-trtllm}

if [ -n "$HY3_API_BASE" ]; then
    echo "API 模式: $HY3_API_BASE, model=$HY3_MODEL_NAME"
else
    echo "本地模型路径: $HY3_MODEL_PATH"
    echo "Tensor Parallel: $HY3_TP_SIZE"
fi

python - <<'PY'
import json
from app.hy3_client import load_client_from_env
from app.prompt_templates import build_messages

client = load_client_from_env()

# 简单问答
print("===== 简单问答 =====")
results = client.generate(["1+1等于几？请直接回答。"], max_tokens=128, temperature=0.6)
print(results[0]["text"])
print()

# 完整数学题
print("===== 数学题测试 =====")
problem = "解方程 2x + 5 = 13。"
messages = build_messages(problem)
results = client.chat_generate([messages], max_tokens=512, temperature=0.6)
print(results[0]["text"])
PY
