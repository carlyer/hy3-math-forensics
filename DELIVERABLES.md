# 项目交付物清单

> 本项目为「犀牛鸟开源实战任务 · 任务二」个人/活动作品，基于腾讯混元 Hy3 大模型构建数学解题与过程评估应用。

## 1. 应用源码

| 路径 | 说明 |
|---|---|
| `app/hy3_client.py` | Hy3 API / 本地 vLLM 调用封装 |
| `app/generate_solutions.py` | 批量生成解题过程，保存完整复现元数据 |
| `app/prompt_templates.py` | 解题与审查提示词模板 |
| `app/solution_parser.py` | 模型输出解析为结构化步骤 |
| `evaluator/process_evaluator.py` | 过程评估主入口 |
| `evaluator/step_validator.py` | 单步规则 + 符号验证 |
| `evaluator/llm_judge.py` | LLM-as-judge 语义审查 |
| `evaluator/error_classifier.py` | 错误类型归类 |
| `evaluator/correct_but_wrong_process.py` | 结果正确但过程不成立检测 |
| `evaluator/evaluate.py` | 批量评测与指标计算 |
| `evaluator/validate_evaluator.py` | 评估器有效性验证 |
| `dataset/answer_checker.py` | 标准答案自动校验（精确/数值/符号/列表/正则/选择） |
| `scripts/generate_report.py` | 生成 Markdown 评测报告 |
| `scripts/run_full_pipeline.sh` | 146 题主库一键评测 |
| `scripts/run_merged_pipeline.sh` | 158 题合并题集一键评测 |

## 2. 评测题集

| 路径 | 说明 |
|---|---|
| `dataset/problems.jsonl` | 主库 146 题（L1~L4，来源：GSM8K / MATH / AGIEval / OlympiadBench / AMC / AIME 等） |
| `dataset/frontiermath_v2_converted.jsonl` | FrontierMath v2 公开样本 12 题（L4，3 道有答案，9 道 manual_check） |
| `dataset/problems_merged.jsonl` | 合并题集 158 题 |
| `dataset/problems_labeled_merged.jsonl` | 人工注入错误验证集 28 条（23 错 + 5 对） |

## 3. 完整结果

| 路径 | 说明 |
|---|---|
| `results/solutions_v2.jsonl` | 146 题模型回答快照（含 prompt、参数、token 用量、finish_reason 等） |
| `results/frontiermath_solutions.jsonl` | FrontierMath 12 题模型回答快照 |
| `results/solutions_merged.jsonl` | 合并 158 题模型回答快照 |
| `results/evaluation_results_merged.json` | 合并题集过程评估结果与指标 |
| `results/metrics_report_merged.md` | 合并题集 Markdown 评测报告 |
| `results/validation_results_v2.json` | 评估器有效性验证结果 |

## 4. 有效性验证与人工抽检

| 路径 | 说明 |
|---|---|
| `validation/validation_summary.md` | 定位准确率 / 误报率综合结论 |
| `validation/frontiermath_spot_check.md` | FrontierMath 12 题人工抽检记录 |

## 5. 文档

| 路径 | 说明 |
|---|---|
| `README.md` | 项目介绍、运行方式、环境要求、核心指标 |
| `.env.example` | API/本地模型配置样例 |
| `requirements.txt` | Python 依赖 |
| `plan.md` | 项目规划文档 |

## 6. 未包含项

- Demo 视频/GIF：由用户手动录制，不在本仓库自动交付范围内。
- 本地模型权重：通过 `.env` 或 `scripts/download_model_from_modelscope.py` 自行准备。
