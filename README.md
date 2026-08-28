# Hy3 数学可验证推理与过程评估

基于腾讯 Hunyuan **Hy3** 大模型构建的数学解题应用，以及面向可验证场景的过程评估系统。本项目不仅判断最终答案是否正确，还对解题过程的推导链条进行逐层审查，定位错误步骤、归类错误类型，并识别“结果正确但推理过程不成立”的样本。

> 本项目为「犀牛鸟开源实战任务 · 任务二」个人/活动作品，非腾讯官方发布。
> 完整项目报告见 [`PROJECT_REPORT.md`](PROJECT_REPORT.md)，踩坑记录与经验总结见 [`PROJECT_LESSONS.md`](PROJECT_LESSONS.md)。

---

## 项目背景

大型语言模型在数学推理任务上往往只输出最终答案，难以判断其推理过程是否严谨。本项目针对这一问题，设计并实现了一套多层混合的过程评估方案：

- **规则校验**：检查步骤结构、重复、循环复制等
- **符号执行**：使用 `sympy` 自动验证数学等式与数值计算
- **LLM-as-judge**：调用模型自身对每步推导进行语义审查；L4/Research 题启用更严格 prompt
- **多 Judge 交叉复核**：支持配置多个 OpenAI 兼容端点进行投票，降低单一裁判波动
- **截断/未完成检测**：基于 `finish_reason`、输出末尾、最终答案标记与长度，识别输出被截断的解答
- **结果-过程一致性检测**：识别猜中答案、数值巧合、定理误用却结果正确等情况

---

## 目录结构

```text
hy3-math-eval/
├── README.md                        # 本文件
├── PROJECT_REPORT.md                # 完整项目报告（方法、设计、数据、评估、结果）
├── PROJECT_LESSONS.md               # 踩坑记录、解决思路与项目经验
├── DELIVERABLES.md                  # 交付物清单
├── .env.example                     # API/本地模型配置样例
├── requirements.txt                 # Python 依赖
├── app/                             # 应用侧：推理、提示词、解析
│   ├── hy3_client.py                # vLLM / OpenAI 兼容 API 封装
│   ├── prompt_templates.py          # 解题提示词（含 depends_on 要求）
│   ├── solution_parser.py           # 解题过程结构化解析
│   ├── generate_solutions.py        # 批量生成入口
│   ├── multi_sample_generator.py    # 多采样一致性生成
│   ├── web_app.py                   # FastAPI 可视化 Web 应用后端
│   └── static/                      # Web 应用前端（单页应用）
│       └── index.html
├── dataset/                         # 题库与校验
│   ├── build_dataset.py             # 构造 legacy 题库
│   ├── convert_math_data.py         # 转换外部公开数据集
│   ├── convert_frontiermath.py      # FrontierMath v2 样本转换
│   ├── answer_checker.py            # 标准答案自动校验
│   ├── problems.jsonl               # 主库：146 题（L1~L4）
│   ├── frontiermath_v2_converted.jsonl  # FrontierMath v2：12 题
│   ├── problems_merged.jsonl        # 合并题集：158 题
│   ├── problems_merged_full.jsonl   # 完整主实验集：418 题（158 原题 + 228 新题 + 32 扰动变体）
│   ├── problems_merged_full_stats.md # 418 题多维分类统计
│   ├── problems_consistency_subset.jsonl  # 多采样一致性子集：40 题
│   ├── problems_l2_all.jsonl        # 全量 L2 题：35 题
│   ├── problems_labeled_merged.jsonl# 注入错误验证集：28 条
│   ├── cbu_injection_samples.jsonl  # CBU 注入样本：9 条
│   ├── problems_perturbed.jsonl     # 16 原题 × 2 种扰动变体：32 条
│   └── problems_merged_v2.jsonl     # 扩展评测集：386 题
├── evaluator/                       # 过程评估模块
│   ├── process_evaluator.py         # 评估主入口
│   ├── step_validator.py            # 单步规则+符号验证
│   ├── llm_judge.py                 # LLM-as-judge（含 Research 严格 prompt）
│   ├── multi_judge.py               # 多 judge 交叉投票
│   ├── truncation_checker.py        # 输出截断/未完成检测
│   ├── error_classifier.py          # 错误类型归类
│   ├── correct_but_wrong_process.py # 结果正确但过程不成立检测
│   ├── dependency_graph.py          # 依赖图显式验证
│   ├── back_substitution.py         # 回代验证器
│   ├── consistency_analyzer.py      # 多采样一致性分析
│   ├── memory_detection_metrics.py  # 记忆 / 模板探测指标
│   ├── evaluate.py                  # 批量评估
│   └── validate_evaluator.py        # 评估器有效性验证
├── scripts/                         # 运行脚本
│   ├── run_full_pipeline.sh         # 146 题主库一键评测
│   ├── run_merged_pipeline.sh       # 158 题合并题集一键评测
│   ├── generate_report.py           # 生成评测报告
│   ├── generate_final_report.py     # 生成最终综合分析报告
│   ├── rebuild_evaluation.py        # 用新 checker 重建评估结果
│   ├── expand_dataset_v2.py         # 从 new_expand 生成 386 题扩展集
│   ├── merge_full_dataset.py        # 合并 386 + 32 扰动变体为 418 题并打多维标签
│   ├── run_consistency_analysis.py  # 多采样一致性分析
│   ├── compute_judge_agreement.py   # 多 judge 一致率与 Cohen's κ
│   ├── single_judge_stability.py    # 单 judge 重复稳定性测试
│   ├── gpt_manual_audit.py          # 使用 GPT-5.6-Terra 按人工标注规范审查
│   ├── download_model_from_modelscope.py  # ModelScope 下载
│   ├── run_web_app.sh               # 启动 FastAPI 可视化 Web 应用
│   ├── hy3_proxy.py                 # 为 React 工作台提供 CORS 代理
│   ├── validate_real_errors.py      # 真实答错题定位准确率验证
│   ├── validate_false_positives.py  # 正确样本误报率验证
│   └── validate_cbu_injection.py    # CBU 注入样本检出率验证
├── frontend/                        # React + Vite 可视化工作台（浏览器端直连 Hy3 API）
│   ├── package.json
│   ├── src/
│   │   ├── App.tsx
│   │   ├── sections/                # Workbench / Dashboard / Cases / Dataset
│   │   └── lib/hy3.ts               # 浏览器端 Hy3 客户端与过程评估 prompt
│   └── index.html
├── demo/                            # 单次解题 demo
│   └── demo.py
├── validation/                      # 有效性验证与人工抽检
│   ├── validation_summary.md
│   └── frontiermath_spot_check.md
├── audit_outputs/                   # GPT 复核审计记录（作为人工审计依据）
│   ├── l2_gold_verify.jsonl
│   ├── spot_correct_audit.jsonl
│   ├── wrong_answer_fixed_audit.jsonl
│   └── cbu_injection_audit.jsonl
└── results/                         # 输出结果
    ├── solutions_v2.jsonl
    ├── frontiermath_solutions.jsonl
    ├── solutions_merged.jsonl
    ├── solutions_merged_depgraph_6k.jsonl
    ├── evaluation_merged_depgraph_6k_gpt.json
    ├── evaluation_results_merged_gpt_judge.json
    ├── evaluation_results_merged_multi_judge_fixed.json
    ├── metrics_report_merged_gpt_judge.md
    ├── metrics_report_merged_multi_judge_final.md
    ├── final_report_gpt_judge.md
    ├── final_report_multi_judge_final.md
    ├── consistency_analysis_subset.json
    ├── consistency_analysis_subset_report.md
    ├── consistency_analysis_l2_all.json
    ├── consistency_analysis_l2_all_report.md
    ├── l2_memory_metrics.json
    ├── l2_memory_metrics_report.md
    ├── l2_case_analysis.md
    ├── l2_consistency_summary.json
    ├── dataset_expansion_report.md
    ├── judge_agreement_stats.json
    ├── single_judge_stability.json
    ├── evaluation_cbu_injection.json
    ├── evaluation_results_perturbed.json
    ├── perturbation_analysis.md
    └── validation_results_v2.json
```

---

## 环境配置

### 基础环境

本项目复用工作空间中的 `/path/to/venv`（已预装 PyTorch 2.11.0+cu130、vLLM 0.22.0、transformers 等）：

```bash
source /path/to/venv/bin/activate
```

### 安装额外依赖

```bash
cd /path/to/workspace/hy3-math-eval
pip install -r requirements.txt
```

### 模型准备

推荐通过 OpenAI 兼容 API 调用已部署的 Hy3 服务。在项目根目录创建 `.env` 文件：

```bash
HY3_API_BASE=http://0.0.0.0:8002/v1
HY3_MODEL_NAME=hy3-gptq-int4
HY3_API_KEY=dummy
```

`app/hy3_client.py` 启动时会自动加载 `.env` 中的变量。若未设置 `HY3_API_BASE`，则回退到本地 vLLM 加载（需充足显存）。详见 `.env.example`。

### LLM-as-judge 裁判配置

为防止 **Hy3 自评（自己给自己打分）** 导致分数虚高，单 judge 模式已默认优先使用外部 GPT 裁判。请在 `.env` 中配置：

```bash
# 单 judge 默认裁判（强烈推荐使用外部模型）
JUDGE_GPT_API_BASE=https://your-openai-compatible-endpoint/api/v1
JUDGE_GPT_API_KEY=your_key
JUDGE_GPT_MODEL=gpt-5.6-terra
```

若未配置 `JUDGE_GPT_*`，则会回退到 `JUDGE_HY3_*`，最后回退到 `HY3_API_BASE`（即 Hy3 自评，不推荐用于正式评测）。

### 多 Judge 交叉复核配置（可选）

若希望进一步降低单一裁判波动，可在 `.env` 中同时配置 Hy3 + GPT + Gemini 三个端点：

```bash
# 本地 Hy3 作为第三裁判（多 judge 模式）
JUDGE_HY3_API_BASE=http://0.0.0.0:8002/v1
JUDGE_HY3_API_KEY=dummy
JUDGE_HY3_MODEL=hy3-gptq-int4

# 外部 GPT/Gemini 裁判
JUDGE_GPT_API_BASE=https://your-openai-compatible-endpoint/api/v1
JUDGE_GPT_API_KEY=your_key
JUDGE_GPT_MODEL=gpt-5.6-terra

JUDGE_GEMINI_API_BASE=https://your-openai-compatible-endpoint/api/v1
JUDGE_GEMINI_API_KEY=your_key
JUDGE_GEMINI_MODEL=gemini-3-flash-preview
```

> 注意：请勿将真实 API key 提交到仓库，`.env` 已加入 `.gitignore`。
> 对于 `gpt-5.6-terra` 等推理模型，客户端会自动忽略 `temperature`/`top_p`。

启用方式：

```bash
# 单 judge（默认 GPT-5.6-terra 外部裁判）
python evaluator/evaluate.py \
  --input results/solutions_merged.jsonl \
  --output results/evaluation_results_merged.json \
  --use_llm \
  --batch_size 4

# 多 judge 交叉复核（Hy3 + GPT + Gemini 投票）
python evaluator/evaluate.py \
  --input results/solutions_merged.jsonl \
  --output results/evaluation_results_merged_multi_judge.json \
  --use_llm \
  --multi_judge \
  --batch_size 4
```

多 judge 采用多数投票聚合：只有明确多数裁判认为过程正确时才判为正确；错误步骤取中位数，错误类型取众数。

---

## 快速开始

### 1. 构建题库

```bash
# 146 题主库（已生成，可直接使用）
python dataset/convert_math_data.py

# FrontierMath v2 12 题（已生成）
python dataset/convert_frontiermath.py

# 合并为 158 题
cat dataset/problems.jsonl dataset/frontiermath_v2_converted.jsonl > dataset/problems_merged.jsonl
```

### 2. 模型/API 冒烟测试

```bash
python test_api_smoke.py
```

### 3. 运行完整评测流程

```bash
# 146 题主库
bash scripts/run_full_pipeline.sh

# 158 题合并题集（含 FrontierMath）
bash scripts/run_merged_pipeline.sh
```

或分步执行：

```bash
python app/generate_solutions.py \
  --input dataset/problems_merged.jsonl \
  --output results/solutions_merged.jsonl \
  --batch_size 4

python evaluator/evaluate.py \
  --input results/solutions_merged.jsonl \
  --output results/evaluation_results_merged.json \
  --use_llm \
  --batch_size 4

python scripts/generate_report.py \
  --input results/evaluation_results_merged.json \
  --output results/metrics_report_merged.md

python scripts/generate_final_report.py \
  --eval results/evaluation_results_merged.json \
  --validation results/validation_results_v2.json \
  --output results/final_report.md
```

### 4. 可视化 Web 应用（推荐）

提供基于 FastAPI + 纯前端的交互式 Web 界面，支持：
- 手动输入题目或从 386 题扩展题库中选择
- 生成完整解题过程与步骤化展示
- 自动答案校验、过程评估、依赖图可视化
- 可选 GPT 单裁判 / 三裁判交叉复核
- 高亮首个错误步骤与「结果正确但过程不成立」提示

启动：

```bash
bash scripts/run_web_app.sh
# 或
WEBAPP_PORT=7860 /path/to/venv/bin/python3 -m uvicorn app.web_app:app --host 0.0.0.0 --port 7860
```

访问 http://localhost:7860 即可使用。

> 前端通过 CDN 引入 Tailwind CSS、KaTeX 与 Mermaid，首次使用需可访问公网；核心功能在不联网时仍可正常使用。

### 5. React 可视化工作台（独立前端）

如果你希望获得更现代化的交互界面（解题工作台、评测仪表盘、案例与方法、题集与验证四个 Tab），可使用 `frontend/` 下的 React + Vite 项目。该前端直接在浏览器中调用 Hy3 OpenAI 兼容 API，API Key 仅保存在浏览器 localStorage。

启动步骤：

```bash
cd frontend
npm install

# 方式 A：浏览器直接访问 Hy3 端点（要求端点已开启 CORS）
npm run dev

# 方式 B：通过本地代理解决 CORS（推荐本地 vLLM 服务使用）
# 终端 1：启动代理
HY3_UPSTREAM=http://0.0.0.0:8002/v1 python3 ../scripts/hy3_proxy.py 8787
# 终端 2：启动前端
npm run dev
```

打开浏览器访问 `http://localhost:5173`，在「⚙ 配置 Hy3 接口」中填入：
- Base URL：`http://localhost:8787/v1`（使用代理时）或直接填 Hy3 端点
- API Key：本地服务可填 `dummy`，远程服务填真实 key
- 模型名：`hy3-gptq-int4`

> 注意：React 工作台内置了少量 2026 高考数学演示题，自定义题目直接在左侧输入即可。

### 6. 命令行 Demo

```bash
python demo/demo.py --problem "解方程 2x + 5 = 13。"
```

---

## 最终评测结果（完整主实验集 418 题）

> 以下结果为 **L1/L2 使用 3k token、L3/L4 使用 6k token** 的合并评测，并已启用 `dependency_graph.py` 依赖图验证与 `back_substitution.py` 回代验证。单 judge 使用外部 **GPT-5.6-terra**，避免 Hy3 自评虚高。
> 数据集为 `dataset/problems_merged_full.jsonl`（158 原题 + 228 扩展新题 + 32 扰动变体），生成脚本见 `scripts/merge_full_dataset.py`。

| 指标 | 数值 |
|---|---|
| 总题数 | **418** |
| 可自动判分题 | 394 |
| 最终答案准确率 | **269 / 394 = 68.27%** |
| 过程正确率 | **353 / 418 = 84.45%** |
| 严格过程正确率（答案对且过程对） | **249 / 394 = 63.20%** |
| 结果正确但过程不成立率（CBU） | **20 / 394 = 5.08%** |
| 答案错误但过程被判正确率 | **84 / 394 = 21.32%** |

### 难度分层结果

| 难度 | 题数 | 可判分 | 答案正确率 | 过程正确率 | 严格过程正确率 | CBU 率 | 答案错但过程对率 |
|---|---|---|---|---|---|---|---|
| L1 | 98 | 98 | 93.88% | 95.92% | 91.84% | 2.04% | 4.08% |
| L2 | 108 | 108 | 71.30% | 83.33% | 63.89% | 7.41% | 19.44% |
| L3 | 101 | 91 | 50.55% | 86.81% | 46.15% | 4.40% | 40.66% |
| L4 | 111 | 97 | 55.67% | 72.16% | 49.48% | 6.19% | 22.68% |

- 答案准确率下降最显著区间：**L1 → L2**（93.88% → 71.30%）与 **L2 → L3**（71.30% → 50.55%）。
- L2 层包含大量 AGIEval 选择题，答案正确率明显低于 158 题旧集（71.30% vs 94.29%），说明新扩展题更真实地区分了模型能力。
- 严格过程正确率（答案对且过程对）在 L3/L4 仅 **46%~49%**，说明高难度题上“答对”和“推理严谨”之间存在显著 gap。

### 按问题类型分层

| 类型 | 题数 | 可判分 | 答案正确率 | 过程正确率 |
|---|---|---|---|---|
| 初等数学 | 225 | 222 | 79.73% | 89.64% |
| 高等数学 | 20 | 20 | 10.00% | 85.00% |
| 竞赛数学 | 161 | 152 | 59.21% | 76.97% |
| 形式数学 | 12 | 0 | N/A | N/A |

- 高等数学（MMLU-Pro-Math）答案正确率仅 **10%**，但过程正确率 85%，说明该题型上答案校验器/标准答案可能存在格式问题，需进一步人工复核。
- 竞赛数学是最大难点类别，答案正确率 59.21%。

### 按验证方式分层

| 验证方式 | 题数 | 可判分 | 答案正确率 | 过程正确率 |
|---|---|---|---|---|
| 可计算答案 | 394 | 394 | 68.27% | 84.52% |
| 形式化证明 | 12 | 0 | N/A | N/A |
| 人工评判 | 12 | 0 | N/A | N/A |

### 按数据集分组

| 分组 | 题数 | 可判分 | 答案正确率 | 过程正确率 | CBU 率 |
|---|---|---|---|---|---|
| original_158 | 158 | 149 | 75.17% | 85.91% | 3.36% |
| ext_228 | 228 | 213 | 65.73% | 83.57% | 6.10% |
| perturbation_32 | 32 | 32 | 53.12% | 84.38% | 6.25% |

- 扰动变体（perturbation_32）答案正确率最低（53.12%），说明表面改写和干扰插入确实破坏了模型的“模板匹配”能力。

### 按污染风险分层

| 风险 | 题数 | 可判分 | 答案正确率 | 过程正确率 |
|---|---|---|---|---|
| high | 182 | 182 | 82.42% | 88.46% |
| medium | 121 | 109 | 47.71% | 80.73% |
| low | 115 | 103 | 65.05% | 81.55% |

- high 风险组（GSM8K/MATH 等常见数据集）答案正确率显著高于 medium 组，但 medium 组过程正确率仍保持 80%+，说明过程评估在区分记忆与推理上有效。

### 扰动变体对照实验

#### GSM-Plus 20 簇（原题 vs 数值替换 vs 干扰插入）

| 组 | 答案正确率 | 过程正确率 |
|---|---|---|
| 原题（GSM8K） | 100.00% | 100.00% |
| 数值替换（GSM-Plus） | 80.00% | 95.00% |
| 干扰插入（GSM-Plus） | 95.00% | 90.00% |

**关键发现**：GSM8K 原题 100% 全对，但仅替换数字后准确率降至 80%，这是**记忆/背诵**的典型指纹。

#### 16 原题扰动簇（surface_rewrite / add_noise）

| 组 | 答案正确率 | 过程正确率 |
|---|---|---|
| 原题 | 56.25% | 87.50% |
| surface_rewrite | 56.25% | 81.25% |
| add_noise | 50.00% | 87.50% |

### 错误类型分布

| 错误类型 | 出现次数 |
|---|---|
| 无错误 | 353 |
| 跳步推导 | 20 |
| 计算错误 | 14 |
| 其他/无法归类 | 9 |
| 概念理解错误 | 8 |
| 条件遗漏 | 7 |
| 定理/公式误用 | 4 |
| 题意误读 | 3 |

> 注：依赖图显式验证后，循环论证从“无法检出”提升为可算法检出的结构性错误。完整分析见 [`PROJECT_REPORT.md`](PROJECT_REPORT.md) 第 8 章。

### 多采样一致性（代表性子集 20 题 × 3 样本）

| 指标 | 整体 | L1 | L2 | L3 | L4 |
|---|---|---|---|---|---|
| 自一致率 | 65.00% | 80.00% | 80.00% | 60.00% | 40.00% |
| 答案一致率 | 75.00% | 100.00% | 100.00% | 60.00% | 40.00% |
| 过程一致率 | 25.00% | 80.00% | 20.00% | 0.00% | 0.00% |
| 答案一致但过程不一致率 | 50.00% | 20.00% | 80.00% | 60.00% | 40.00% |

L2 出现典型的“答案稳定但路径漂移”现象：答案一致率 100%，但过程一致率仅 20%，提示部分答对题目可能依赖记忆/模板而非稳定推理。详见 `results/consistency_analysis_subset_small_report.md`。

### L2 记忆 / 模板探测（全量 35 题 × 3 样本）

| 指标 | 数值 |
|---|---|
| 答案一致率 | **100.00%** |
| 自一致率 | **91.43%** |
| 过程一致率 | **34.29%** |
| 答案一致但过程不一致率 | **65.71%** |
| 综合记忆/模板漂移率 | **54.29%** |

探测指标（实现见 `evaluator/memory_detection_metrics.py`）：

| 指标 | 漂移率 / 平均值 |
|---|---|
| 解法类型漂移率 | 28.57% |
| 依赖图结构漂移率 | 37.14%（平均边 Jaccard 0.6053） |
| 定理 / 公式引用漂移率 | 20.00%（平均定理 Jaccard 0.8476） |

结论：L2 层答案准确率虽高，但超过一半题目存在中间表征不稳定，与 MATH/AGIEval 高污染风险下“记忆/模板调用”的假说高度吻合。详细案例分析见 `results/l2_case_analysis.md`，指标报告见 `results/l2_memory_metrics_report.md`。

---

## 过程评估方法

评估采用五层混合架构：

| 层次 | 名称 | 方法 | 检测问题 |
|---|---|---|---|
| L0 | 答案层 | 与标准答案比对 | 最终答案错误 |
| L1 | 结构层 | 非空检查、重复/循环检测 | 空过程、循环复制 |
| L2 | 符号验证层 | sympy 解析与数值验证 | 计算错误、等式不成立 |
| L3 | 语义审查层 | LLM-as-judge（普通/Research 双 prompt） | 题意误读、定理误用、条件遗漏、跳步、循环论证、幻觉 |
| L4 | 截断/完整性层 | `finish_reason`、末尾字符、答案标记、长度启发式 | 输出截断、未完成推理 |

### 错误类型体系

- 题意误读
- 概念理解错误
- 定理/公式误用
- 计算错误
- 条件遗漏
- 跳步推导
- 循环论证
- 幻觉/无中生有
- 单位/格式不符
- 其他/无法归类

### 新增结构性验证层

在原有五层基础上，新增三层零/低成本验证：

| 层次 | 名称 | 方法 | 检测问题 |
|---|---|---|---|
| L5 | 依赖图验证 | 要求模型每步标注 `depends_on`，构建有向图 | 跳步（依赖链断裂）、循环论证（图环） |
| L6 | 回代验证 | sympy 将最终答案代回原题约束 | 答案等价性争议、CBU 铁证 |
| L7 | 多采样一致性 | temperature > 0 采样 N 次，比较答案/路径 | 记忆/背诵、推理不稳定、侥幸猜中 |

### 结果正确但过程不成立

当 `answer_correct == true` 但 `process_correct == false` 时，系统会标记为 `correct_but_unjustified`，并记录首个错误步骤，用于识别猜答案、数值巧合、定理误用却得到正确结果等情况。

---

## 评估器有效性验证（修复后）

| 指标 | 数值 | 说明 |
|---|---|---|
| 合成注入错误定位准确率 | **86.96%**（20/23） | 原验证集，保留；脚本 `evaluator/validate_evaluator.py` |
| 真实答错题定位准确率（精确） | **51.85%**（14/27） | GPT-5.6-Terra 审计 30 道真实答错题，27 道确实存在过程错误；脚本 `scripts/validate_real_errors.py` |
| 真实答错题定位准确率（±1 步） | **55.56%**（15/27） | 同上 |
| 答案正确样本误报/漏判率（扩展抽检） | **1 / 35 = 2.86%** | 从答案正确的样本中扩展抽检 35 道，GPT 复核发现 1 道过程存在结构性缺口；脚本 `scripts/validate_false_positives.py` |
| 答案正确样本误报/漏判率（规范批次 C） | **1 / 20 = 5.00%** | 按《过程评估人工标注规范》批次 C 抽检 20 道；明细见 `audit_outputs/gpt_annotation_batch_C.jsonl` |
| 答案正确样本误报/漏判率（合并） | **2 / 55 ≈ 3.64%** | 合并上述 20 + 35 道抽检结果 |
| CBU 注入样本检出率 | **7 / 9 = 77.78%** | 将 CBU 注入集扩充至 9 道，覆盖计算/定理/概念/幻觉/跳步/循环等机制；脚本 `scripts/validate_cbu_injection.py` |
| 三 judge 过程正确性完全一致率 | **48.10%**（76/158） | Hy3 + GPT-5.6-terra + Gemini-3-flash-preview；脚本 `scripts/compute_judge_agreement.py` |
| 三 judge 首错步完全匹配率 | **2.60%**（2/77） | 至少一方判错的样本上；说明“错误位置”的判定比“是否有错”更不稳定 |

> 所有“人工复核”均由 GPT-5.6-terra 执行，输出按人工审计标准记录。详细审计记录见 `audit_outputs/`、`results/validation_real_errors.json`、`results/validation_false_positives.json`、`results/validation_cbu_injection.json`。

关键发现：
1. **真实答错题首错步定位显著改善**：精确命中率从旧版约 7% 提升至 **51.85%**，±1 步命中率 **55.56%**，得益于 `solution_parser` 步骤索引规范化与依赖图验证。
2. **答案正确样本误报率低**：规范批次 C 抽检 20 道漏判率 5.00%，扩展抽检 35 道漏判率 2.86%，合并 55 道约 3.64%；评估器对正样本的阴性判断基本可信。
3. **CBU 检出率 77.78%**：计算/定理/概念/幻觉类 CBU 可稳定捕获，但跳步推导与循环论证类仍依赖 judge 语义判断，后续可结合依赖图显式标注进行算法化检测。
4. **多 judge 一致性有限**：三裁判对“过程是否成立”的完全同意率仅 48.10%，首错步匹配率仅 2.60%，说明 LLM-as-judge 在复杂数学过程上存在显著主观差异；多 judge 投票可抑制个体差异，但错误类型/位置标签应以趋势参考为主。

FrontierMath v2 人工抽检记录见 `validation/frontiermath_spot_check.md`。

---

## 数据集

### 主库 146 题

| 层级 | 题数 | 主要来源 |
|---|---|---|
| L1 | 30 | GSM8K + Math23K |
| L2 | 35 | MATH Level 2-3 + AGIEval |
| L3 | 47 | MATH Level 4-5 + OlympiadBench + Omni-MATH + AMC12 |
| L4 | 34 | AIME + AMC/AIME-HF |

### FrontierMath v2 附录

12 道研究级公开样本，原始 tier 覆盖 Tier 1~4，本项目统一归为 L4。其中 3 道有公开答案，9 道标记为 `manual_check`。

### 数据污染风险说明

合并题集 `dataset/problems_merged.jsonl` 已为每题标注 `contamination_risk` 字段，按题源污染风险分为 **high / medium / low** 三级：

- **high**：GSM8K、Math23K、Ape210K、MATH、AGIEval 等常见预训练/微调数据集；
- **medium**：AMC、AIME、AMC/AIME-HF、OlympiadBench、Omni-MATH 等竞赛/考试题源；
- **low**：FrontierMath-v2、perturbation 变体、自构造题等研究级新题或扰动题。

该项目旨在区分“真实推理”与“记忆/背诵”表现：过程评估本身可暴露记忆型解答（答案对但过程缺失/模板化）。我们已通过 `dataset/perturb_problems.py` 对 16 道 high/medium 风险原题生成 32 条扰动变体（`surface_rewrite` + `add_noise`），对照实验显示扰动后答案正确率基本持平，但过程正确率从 62.50% 降至 56.25%，CBU 率从 0.00% 升至 9.38%，说明表面变化会诱使模型生成“答案对但过程不成立”的解答。

按风险等级分组的 Hy3 表现（单 judge = GPT-5.6-terra，已修正 L2 gold 标签）：

| 风险等级 | 题数 | 答案正确率 | 过程正确率 | 严格过程正确率 | CBU 率 |
|---|---|---|---|---|---|
| high | 77 | 94.81% | 84.42% | 80.52% | 14.29% |
| medium | 69 | 40.58% | 33.33% | 30.43% | 10.14% |
| low | 12 | 0.00% | 8.33% | 0.00% | 0.00% |

high 风险组（GSM8K/MATH 等常见数据集）答案正确率显著高于 medium 组，但外部 GPT 裁判下 high 组 CBU 率高达 14.29%，说明该组大量答对题目存在过程不严谨问题，提示污染/记忆风险可能被放大。medium 组（竞赛/考试题源）的过程正确率仍明显低于答案正确率。low 组（FrontierMath-v2）基本全部未答对，与研究级难度一致。

我们进一步对 16 道 high/medium 风险原题生成了 32 条扰动变体（`surface_rewrite` + `add_noise`）。对比发现：扰动后答案正确率基本持平，但**过程正确率从 62.50% 降至 56.25%，CBU 率从 0.00% 升至 9.38%**，说明表面变化会诱使模型产生“答案对但过程不成立”的解答。完整实验设计与结果见 [`PROJECT_REPORT.md`](PROJECT_REPORT.md) 的「扰动变体对照实验」小节与 `results/perturbation_analysis.md`。

### 扩展评测集 v2（386 题）

除原始 158 题合并题集外，我们还从 `dataset/math-data/math-data/new_expand/problems_v2.jsonl`（779 题）中清洗、去重、采样，生成了扩展评测集：

| 数据集 | 总题数 | L1 | L2 | L3 | L4 |
|---|---|---|---|---|---|
| `problems_merged.jsonl` | 158 | 30 | 35 | 47 | 46 |
| `problems_merged_v2.jsonl` | **386** | 90 | 100 | 93 | 103 |

扩展流程：

1. **去重**：剔除与现有 158 题题面完全重复的 9 道题；
2. **保留 GSM-Plus 变体簇**：20 个原题 + 数值替换 + 干扰插入三元组，共 60 题，用于扰动/鲁棒性分析；
3. **优先自动判分**：`exact_match` / `choice_match` / `symbolic_equivalence` 占 362 题，仅 L3/L4 自动判分题不足时纳入 24 道 `manual_check` 证明题；
4. **来源多样化**：新增题来自 AGIEval、MiniF2F、AIME-AMC12/train、2026-Gaokao、AIME-2025、MMLU-Pro/math、Omni-MATH 等。

扩展报告见 `results/dataset_expansion_report.md`，处理脚本见 `scripts/expand_dataset_v2.py`。

### 完整主实验集（418 题）

为获得更大规模、更多样的评测结果，我们将 386 题扩展集与 32 条扰动变体合并为 `dataset/problems_merged_full.jsonl`，共 **418 题**。

| 分组 | 题数 | 说明 |
|---|---|---|
| `original_158` | 158 | 原 158 题（含 146 道 L1-L4 + 12 道 FM-v2） |
| `ext_228` | 228 | 386 扩展集中新增题 |
| `perturbation_32` | 32 | 16 原题 × 2 种扰动变体（surface_rewrite / add_noise） |
| **总计** | **418** | |

每道题均增加了多维标签：

| 标签维度 | 取值 |
|---|---|
| `level` | L1 / L2 / L3 / L4 |
| `dataset_group` | original_158 / ext_228 / frontiermath_12 / perturbation_32 |
| `variant_type` | original / numerical_substitution / distraction_insertion / surface_rewrite / add_noise |
| `problem_form` | open / choice / proof / unknown |
| `verification_method_tag` | formal_proof / verifiable_answer / human_evaluation |
| `problem_type_tag` | elementary_math / college_math / competition_math / formal_math |
| `evaluation_goal_tags` | problem_solving_accuracy / proof_completion_rate / generalization / reasoning_depth / robustness |
| `contamination_risk` | high / medium / low |

多维分类统计见 `dataset/problems_merged_full_stats.md`，生成脚本见 `scripts/merge_full_dataset.py`。

---

## 注意事项

1. **API 模式优先**：已部署 vLLM 服务时，请通过 `.env` 配置 `HY3_API_BASE`，避免本地重复加载模型导致 GPU 内存不足。
2. **本地模型加载**：若未配置 API，默认从 `bifrost` 目录加载本地模型；请确认该路径模型已就绪且 GPU 显存充足。
3. **LLM judge 成本**：开启 `--use_llm` 会调用模型进行二次推理，耗时会增加。
4. **符号验证局限**：当前符号验证基于启发式提取等式，复杂 LaTeX 或自然语言表述可能无法完全覆盖，需配合 LLM judge 使用。
5. **`.env` 文件**：包含本地服务地址，请勿提交到公开仓库（已通过 `.gitignore` 忽略）。

---

## 实验进展与迭代记录

| 时间 | 改动 | 关键结果 |
|---|---|---|
| 初版 | 规则 + sympy + LLM-as-judge 单层评估 | 过程正确率约 62%，CBU 识别不足 |
| 迭代 1 | 新增输出截断/未完成检测器；L4 启用 Research 严格 judge prompt | 过程正确率 55.06%，CBU 10.74%；FM-v2-011 截断漏判被修复 |
| 迭代 2 | 新增多 judge 交叉投票框架；适配 内部 AI 网关 的 gpt-5.6-terra/gemini-3.5-flash | 三 judge 投票下过程正确率 51.90%，CBU 14.09% |
| 迭代 3 | 抑制 sympy 解析 set-like 表达式时产生的 SyntaxWarning | 评估日志不再刷屏 |
| 迭代 4（本次） | answer_checker 等价形式归一化；step_validator 保守化；修正 L2 gold 标签；judge prompt 加 few-shot 示例 | 158 题全量：答案正确率 67.09%，GPT 单裁判过程正确率 67.09%、CBU 12.66%；多 judge（149 道可判题）：答案正确率 67.79%、过程正确率 61.39%、CBU 5.37% |
| 迭代 5 | LLM-as-judge 默认改为 GPT-5.6-terra 外部裁判，避免 Hy3 自评 | 多 judge 结果文件（149 道可判题）：单 judge（GPT）过程正确率 56.33%、CBU 12.08%；三 judge 过程正确率 61.39%、CBU 5.37% |

### 单 judge vs 多 judge 对比（修复后）

> 本节数据来自 `results/evaluation_results_merged_multi_judge_fixed.json`，其中 149 道为可自动判分题（gradable），9 道 FrontierMath v2 标记为 `manual_check`，因此部分指标分母为 149、部分为 158。

| 指标 | 单 judge（GPT-5.6-terra） | 三 judge 投票（Hy3 + GPT + Gemini） |
|---|---|---|
| 最终答案准确率 | 67.79%（101/149） | 67.79%（101/149） |
| 过程正确率 | 56.33%（89/158） | 61.39%（97/158） |
| 严格过程正确率 | 55.70%（83/149） | 62.42%（93/149） |
| CBU 率 | 12.08%（18/149） | 5.37%（8/149） |
| 答案错误但过程被判正确 | 3.36%（5/149） | 2.68%（4/149） |

使用外部 GPT 裁判时，单 judge 比三 judge 投票更严格：过程正确率更低、CBU 率更高。这说明 Hy3 自审在多 judge 中拉低了整体严格度，若要真实刻画过程严谨性，优先使用外部强模型单裁判。裁判间一致性分析见 `results/judge_agreement_stats.json`：三 judge 对过程是否正确的完全同意率为 48.1%，两两 Cohen's κ 在 0.24 ~ 0.85 之间，说明不同裁判对“过程是否成立”的判定存在显著差异。

---

## 后续计划

- [x] 引入依赖图显式分步格式，增强跳步与循环论证检测
- [x] 构建可视化 Web 应用，便于非技术用户直接使用
- [ ] 完成 386 题扩展集的全量生成与三 Judge 评估（已就绪，按需启动）
- [ ] 探索反向验证器（Math-Shepherd 思想）与细粒度步骤奖励模型，进一步降低误报/漏判
