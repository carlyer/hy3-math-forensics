# 题库扩充包说明（140 条新增题目）

已按项目 problems.jsonl 的 schema 整理，可直接 `cat 扩展题集_合并.jsonl >> dataset/problems_merged.jsonl` 合并。
建议合并前先跑 answer_checker 冒烟测试。

## 文件清单

| 文件 | 条数 | 层级 | 来源 | 用途 |
|---|---|---|---|---|
| GSM8K_新增.jsonl | 20 | L1 | GSM8K 测试集 | 题簇种子 + 误报率正样本池 |
| GSM-Plus_新增.jsonl | 40 | L1 | GSM-Plus（每种子 2 变体） | 去污染 A/B 对照、鲁棒性、干扰审计 |
| MATH_新增.jsonl | 25 | L2 | MATH Level 2-3 | 加厚异常层 L2，带完整分步参考解 |
| MMLU-Pro_新增.jsonl | 20 | L3 | MMLU-Pro math（10选项选择） | 大学数学空白 + 选项置换测试素材 |
| Omni-MATH_新增.jsonl | 20 | L3×12 / L4×8 | Omni-MATH 难度5-7 / ≥8 | 核心发现层加厚 |
| AIME2025_新增.jsonl | 15 | L4 | AIME 2025 I+II | 低污染难题，contamination_risk=low |
| 扩展题集_合并.jsonl | 140 | 全部 | 上述合并 | 直接合并用 |

## 字段说明（新增字段）

- `contamination_risk`: high（GSM8K/MATH，模型大概率见过）/ medium（MMLU-Pro、Omni-MATH）/ low（GSM-Plus 变体、AIME 2025）
- `problem_form`: open / choice / proof
- `cluster_id`: 同一题簇共享（GSM-Plus 变体通过它与种子题关联）
- `is_adversarial`: true 表示干扰反例（distraction insertion，含无关子句）

## 统计注意事项

1. 主指标（答案准确率/过程正确率）按 cluster 只计种子题一次，变体单独用于鲁棒性分析
2. GSM-Plus 变体即"原题 vs 换数字/加干扰"的 A/B 对照组，两组正确率差 = 记忆依赖度
3. MMLU-Pro 为 10 选项选择题，天然降低蒙对概率至 10%，适合做选项置换/去选项实验
4. AIME 2025 发布于 2025 年 2 月，大概率晚于 Hy3 训练数据截止，作为低污染参照组

## 数据来源

- GSM8K: github.com/openai/grade-school-math (MIT)
- GSM-Plus: github.com/qtli/GSM-Plus
- MATH: ModelScope AI-ModelScope/MATH-lighteval（hendrycks/math 清洗版）
- MMLU-Pro: ModelScope TIGER-Lab/MMLU-Pro
- Omni-MATH: github.com/KbsdJames/Omni-MATH
- AIME 2025: ModelScope opencompass/AIME2025
