# 数学推理评测题集说明文档

## 1. 评测题集概述

本题集用于评估大语言模型在数学推理任务上的表现，共包含 **182 道题目**，按难度分为四个层级（L1~L4）。每道题均具备：

- 明确的题目文本（支持 LaTeX）
- 标准答案
- 可自动校验的判定方式
- 来源与构造方式说明

所有题目统一存储为 JSONL 格式，字段一致，便于接入评测流水线。

---

## 2. 数据结构与字段说明

每道题统一为以下 6 个字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 题目唯一标识 |
| `level` | string | 难度层级：`L1_Basic`、`L2_Medium`、`L3_Hard`、`L4_Expert` |
| `source` | string | 题目来源，例如 `GSM8K`、`MATH`、`AIME 2025 I` |
| `problem` | string | 题目文本 |
| `answer` | string | 标准答案 |
| `solution` | string / null | 逐步解答（部分数据集无此字段时为 null） |

---

## 3. 难度分层与覆盖区间

### L1 Basic（基础层）：30 题

**覆盖能力**：小学算术、基础应用题、简单方程。

**题目来源**：

- **GSM8K**（18 题）：OpenAI 发布的英文小学数学应用题，天然带分步解答与 `####` 分隔的最终答案。
- **Math23K**（12 题）：中文小学数学应用题，通过 GitHub 镜像获取原始 JSON 后随机采样。

**分层依据**：

- 题目仅涉及四则运算、简单比例、单位换算、基础方程。
- 答案多为整数或简单分数，可直接字符串匹配或数值比较。

**自动校验方式**：

- 对 `answer` 字段提取数值后与模型输出进行精确匹配。
- 支持对分数、小数进行等价归一化（如 `1/2` 与 `0.5` 视为等价）。

---

### L2 Medium（中等层）：35 题

**覆盖能力**：初中至高中代数、几何、数列、概率、函数。

**题目来源**：

- **MATH Levels 2-3**（20 题）：Hendrycks MATH 数据集中标注为 Level 2 与 Level 3 的竞赛题，含完整分步解答。
- **AGIEval**（15 题）：微软发布的评测数据集，包含中国高考、中考及 SAT 数学选择题，通过 `hails/agieval-aqua-rat` 与 `dmayhem93/agieval-gaokao-mathqa` 配置加载。

**分层依据**：

- MATH Level 2-3 对应初中至高中常规竞赛难度。
- AGIEval 覆盖高考、中考真实试题，符合中国中学数学教学大纲。

**自动校验方式**：

- MATH：从 `solution` 中提取 `\boxed{...}` 内容作为标准答案，与模型输出做 LaTeX 归一化后匹配。
- AGIEval：记录选项字母与选项文本，模型输出需匹配正确选项字母或对应文本。

---

### L3 Hard（较难关）：62 题

**覆盖能力**：高中竞赛、数学奥林匹克入门、组合几何、数论、不等式。

**题目来源**：

- **MATH Levels 4-5**（12 题）：MATH 数据集中较高难度题目。
- **OlympiadBench**（30 题）：
  - `lmms-lab/OlympiadBench`（15 题）：多模态奥林匹克数学题，取文本子集。
  - `Hothan/OlympiadBench`（15 题，`OE_TO_maths_en_COMP` 配置）：文本-only 奥林匹克数学题。
- **Omni-MATH**（10 题）：`KbsdJames/Omni-MATH`，覆盖多学科竞赛级问题。
- **AMC12 Hy3 Test**（10 题）：用户提供的 AMC 12 #23-25 级别高难度题目，带完整解答。

**分层依据**：

- MATH Level 4-5 对应 AIME 及国家集训队选拔入门级难度。
- OlympiadBench 与 Omni-MATH 按数据集自身难度标签筛选中高档题目。
- AMC12 Hy3 Test 题目位于 AMC 12 后段难题区间（#23-25）。

**自动校验方式**：

- 数值/表达式答案：采用符号归一化后精确匹配（去除空格、统一分数与小数表示）。
- AMC12 选择题：与选项值进行匹配，允许输出选项字母或对应数值。
- 对于无标准解析解的题目，`solution` 字段为 null，仅做最终答案校验。

---

### L4 Expert（高难度层）：55 题

**覆盖能力**：AIME、AMC 12 难题、IMO 短名单级别，作为能力天花板探测。

**题目来源**：

- **AIME 2015-2025**（25 题）：用户提供的 AIME 真题集合（`AIME1.txt`），含完整解答。
- **AIME 1983-2024**（15 题）：`di-zhang-fdu/AIME_1983_2024`，历年 AIME 题目。
- **AMC / AIMO**（10 题）：`AI-MO/aimo-validation-amc` 与 `kaggle-aimo/amc_filtered`。
- **IMO**（5 题）：`dots-studio/IMO-AnswerBench-Verified`，IMO 短名单验证题。

**分层依据**：

- AIME 答案为 0-999 整数，天然适合自动校验。
- IMO 题目为国际数学奥林匹克级别，难度最高。
- AMC 12 难题与 AIME 共同构成高难度区间。

**自动校验方式**：

- AIME：严格匹配 0-999 整数。
- AMC / AIMO：数值或选项匹配。
- IMO：表达式级匹配，必要时使用 sympy 进行符号等价判定。

---

## 4. 自动校验实现建议

推荐实现一个统一的 `AnswerNormalizer` 与 `AnswerJudge`：

```python
class AnswerNormalizer:
    def normalize(self, text: str) -> str:
        # 1. 去除多余空白与标点
        # 2. 统一 LaTeX 表示（如 \\frac -> 分数）
        # 3. 统一小数与分数（可选）
        # 4. 转小写
        return cleaned

class ExactMatchJudge:
    def judge(self, pred: str, ref: str) -> bool:
        return normalize(pred) == normalize(ref)

class SymbolicJudge:
    # 适用于表达式答案，使用 sympy 判断等价
    def judge(self, pred: str, ref: str) -> bool:
        # 尝试将 pred 与 ref 解析为 sympy 表达式并比较
        ...
```

### 各层级推荐校验策略

| 层级 | 主要校验方式 | 备注 |
|------|--------------|------|
| L1 | 精确数值匹配 | 支持分数/小数归一化 |
| L2 | 数值/表达式匹配 + 选择题匹配 | MATH 提取 `\boxed{}` |
| L3 | 表达式归一化匹配 | AMC12 选择题允许字母或数值 |
| L4 | AIME 整数精确匹配；IMO 符号等价 | 复杂表达式使用 sympy |

---

## 5. 题目构造方式说明

### 公开数据集抽样

- 所有 HF 数据集均通过 `datasets` 库加载。
- 抽样固定随机种子 `42`，保证可复现。
- 样本量按用户要求控制：L1 15-20 题、L2 15-20 题、L3 10-20 题、L4 10-15 题每来源。

### 用户构造/补充题目

- **AMC12 Hy3 Test**：用户提供 10 题中文 AMC 12 难题，已统一为 JSONL。
- **AIME1**：用户提供 25 题 AIME 真题 Python 脚本，已执行并提取为 JSONL。

### 答案提取

- GSM8K：从 `answer` 字段按 `####` 分割提取最终答案。
- MATH：从 `solution` 中提取 `\boxed{...}`。
- AIME：直接取 `answer` 字段（0-999 整数）。
- AGIEval：将选项字母映射为选项文本。

---

## 6. 项目文件说明

```
.
├── L1_Basic/raw/              # 基础层 JSONL
├── L2_Medium/raw/             # 中等层 JSONL
├── L3_Hard/raw/               # 较难关 JSONL
├── L4_Expert/raw/             # 高难度层 JSONL
├── L*/metadata/               # 部分来源的原始元数据/脚本
├── all_problems.jsonl         # 全部 182 题合并文件
├── dataset_index.json         # 各文件题数索引
├── download_summary.json      # 按层级/来源统计
├── README.md                  # 项目说明
└── EVALUATION_GUIDE.md        # 本文件
```

---

## 7. 迁移与复现

### 环境依赖

- Python 3.10+
- `datasets`, `huggingface_hub`

### 打包迁移

项目已通过压缩包形式打包。`.venv` 未包含在压缩包中，目标机器解压后请重新创建虚拟环境并安装依赖：

```bash
cd math-data
python -m venv .venv
source .venv/bin/activate
pip install datasets huggingface_hub
```

### 校验示例

```bash
wc -l L*/raw/*.jsonl
python -c "import json; print(sum(1 for _ in open('all_problems.jsonl')))"
```

---

## 8. 已知限制

- 部分来源（AGIEval、OlympiadBench、AMC/AIME from HF）未提供逐步解答，`solution` 为 `null`。
- OlympiadBench 原为多模态数据，本题集仅保留文本部分。
- 复杂表达式答案建议配合 sympy 进行符号等价判定，避免纯字符串匹配漏判。
