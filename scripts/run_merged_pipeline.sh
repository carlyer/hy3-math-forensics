#!/bin/bash
# 合并题集（146 题主库 + 12 题 FrontierMath v2）完整评测流程
#
# 默认使用 API 模式（通过 .env 或环境变量配置 HY3_API_BASE）。
# 若未配置 API，请确保本地模型路径与显存充足。

set -e

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# 加载 .env（如果存在）
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

# 本地模型回退配置（仅未设置 HY3_API_BASE 时生效）
export HY3_MODEL_PATH=${HY3_MODEL_PATH:-/path/to/hy3-gptq-int4}
export HY3_TP_SIZE=${HY3_TP_SIZE:-2}
export HY3_MAX_MODEL_LEN=${HY3_MAX_MODEL_LEN:-8192}
export VLLM_FLASHINFER_ALLREDUCE_BACKEND=${VLLM_FLASHINFER_ALLREDUCE_BACKEND:-trtllm}

echo "===== 1/3 生成解题过程（合并题集 158 题） ====="
python app/generate_solutions.py \
    --input dataset/problems_merged.jsonl \
    --output results/solutions_merged.jsonl \
    --max_tokens 4096 \
    --temperature 0.6 \
    --batch_size 4

echo "===== 2/3 过程评估（启用 LLM-as-judge） ====="
python evaluator/evaluate.py \
    --input results/solutions_merged.jsonl \
    --output results/evaluation_results_merged.json \
    --use_llm \
    --batch_size 4

echo "===== 3/3 生成报告 ====="
python scripts/generate_report.py \
    --input results/evaluation_results_merged.json \
    --output results/metrics_report_merged.md

echo "===== 完成 ====="
echo "结果文件:"
echo "  dataset/problems_merged.jsonl"
echo "  results/solutions_merged.jsonl"
echo "  results/evaluation_results_merged.json"
echo "  results/metrics_report_merged.md"
