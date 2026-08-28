#!/bin/bash
# 完整评测流程：生成解题过程 -> 过程评估 -> 生成报告
#
# 默认使用 API 模式（通过 .env 或环境变量配置 HY3_API_BASE）。
# 若未配置 API，请确保本地模型路径与显存充足。

set -e

cd /path/to/workspace/hy3-math-eval

# 加载 .env（如果存在）
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

# 本地模型回退配置（仅未设置 HY3_API_BASE 时生效）
export HY3_MODEL_PATH=${HY3_MODEL_PATH:-/path/to/workspace/bifrost-2026082410005000-内部网关/path/to/hy3-gptq-int4}
export HY3_TP_SIZE=${HY3_TP_SIZE:-2}
export HY3_MAX_MODEL_LEN=${HY3_MAX_MODEL_LEN:-8192}
export VLLM_FLASHINFER_ALLREDUCE_BACKEND=${VLLM_FLASHINFER_ALLREDUCE_BACKEND:-trtllm}

echo "===== 1/3 生成解题过程 ====="
python app/generate_solutions.py \
    --input dataset/problems.jsonl \
    --output results/solutions_v2.jsonl \
    --max_tokens 2048 \
    --temperature 0.6 \
    --batch_size 4

echo "===== 2/3 过程评估（启用 LLM-as-judge） ====="
python evaluator/evaluate.py \
    --input results/solutions_v2.jsonl \
    --output results/evaluation_results_v2.json \
    --use_llm \
    --batch_size 4

echo "===== 3/3 生成报告 ====="
python scripts/generate_report.py \
    --input results/evaluation_results_v2.json \
    --output results/metrics_report_v2.md

echo "===== 完成 ====="
echo "结果文件:"
echo "  results/solutions_v2.jsonl"
echo "  results/evaluation_results_v2.json"
echo "  results/metrics_report_v2.md"
