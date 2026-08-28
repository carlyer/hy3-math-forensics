#!/bin/bash
# 418 题完整主实验集评测流程
# 分两段生成：L1/L2 用 3k token，L3/L4 用 6k token

set -e

cd /path/to/workspace/hy3-math-eval

if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

echo "===== 1/4 生成 L1/L2 解答（206 题，3k token，20 并发） ====="
python app/generate_solutions.py \
    --input dataset/problems_merged_full_l1l2.jsonl \
    --output results/solutions_merged_full_l1l2.jsonl \
    --max_tokens 3072 \
    --temperature 0.6 \
    --batch_size 20

echo "===== 2/4 生成 L3/L4 解答（212 题，6k token，20 并发） ====="
python app/generate_solutions.py \
    --input dataset/problems_merged_full_l3l4.jsonl \
    --output results/solutions_merged_full_l3l4.jsonl \
    --max_tokens 6144 \
    --temperature 0.6 \
    --batch_size 20

echo "===== 3/4 合并解答 ====="
cat results/solutions_merged_full_l1l2.jsonl results/solutions_merged_full_l3l4.jsonl > results/solutions_merged_full.jsonl
wc -l results/solutions_merged_full.jsonl

echo "===== 4/4 过程评估（单 judge GPT-5.6-terra，20 并发） ====="
python evaluator/evaluate.py \
    --input results/solutions_merged_full.jsonl \
    --output results/evaluation_merged_full.json \
    --use_llm \
    --batch_size 20

echo "===== 完成 ====="
echo "结果文件:"
echo "  dataset/problems_merged_full.jsonl"
echo "  results/solutions_merged_full.jsonl"
echo "  results/evaluation_merged_full.json"
