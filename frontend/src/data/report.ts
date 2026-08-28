// 内置评测数据：来自 158 题合并题集的实跑结果（单 judge 与三 judge 两版）
export interface LevelRow {
  level: string; label: string; total: number;
  answerAcc: number; processAcc: number; strictAcc: number; cbu: number; ansWrongProcRight: number | null;
}

export const OVERALL = {
  totalProblems: 158,
  autoCheckable: 149,
  single: { answerAcc: 67.09, processAcc: 67.09, strictAcc: 67.09, cbu: 12.66, ansWrongProcRight: 0.00 },
  multi: { processAcc: 61.39, strictAcc: 62.42, cbu: 5.37 },
  validation: { locAcc: 86.96, locN: 23, falsePos: 0.0, fpN: 35 },
};

export const LEVEL_SINGLE: LevelRow[] = [
  { level: 'L1', label: '基础 · 小学/初中应用题', total: 30, answerAcc: 93.33, processAcc: 90.00, strictAcc: 83.33, cbu: 10.00, ansWrongProcRight: 3.33 },
  { level: 'L2', label: '中等 · 中考/高一', total: 35, answerAcc: 94.29, processAcc: 94.29, strictAcc: 88.58, cbu: 5.71, ansWrongProcRight: 0.00 },
  { level: 'L3', label: '较难 · 高考压轴/竞赛入门', total: 47, answerAcc: 61.70, processAcc: 61.70, strictAcc: 42.55, cbu: 19.15, ansWrongProcRight: 0.00 },
  { level: 'L4', label: '高难度 · AIME/研究级', total: 46, answerAcc: 34.78, processAcc: 36.96, strictAcc: 21.74, cbu: 13.04, ansWrongProcRight: 2.18 },
];

export const LEVEL_MULTI: LevelRow[] = [
  { level: 'L1', label: '基础', total: 30, answerAcc: 93.33, processAcc: 90.00, strictAcc: 83.33, cbu: 10.00, ansWrongProcRight: null },
  { level: 'L2', label: '中等', total: 35, answerAcc: 94.29, processAcc: 94.29, strictAcc: 88.58, cbu: 5.71, ansWrongProcRight: null },
  { level: 'L3', label: '较难', total: 47, answerAcc: 61.70, processAcc: 55.32, strictAcc: 48.94, cbu: 12.77, ansWrongProcRight: null },
  { level: 'L4', label: '高难度', total: 46, answerAcc: 34.78, processAcc: 30.43, strictAcc: 28.26, cbu: 6.52, ansWrongProcRight: null },
];

export const ERROR_DIST = [
  { type: '无错误', count: 106, note: '过程完全成立' },
  { type: '跳步推导', count: 12, note: '中间结论缺乏依据' },
  { type: '计算错误', count: 11, note: '符号层可确定性检出' },
  { type: '条件遗漏', count: 9, note: '关键限制未使用' },
  { type: '概念理解错误', count: 8, note: '概念/定义使用不当' },
  { type: '其他/无法归类', count: 6, note: '' },
  { type: '定理/公式误用', count: 4, note: '' },
  { type: '题意误读', count: 1, note: '' },
  { type: '循环论证', count: 1, note: '依赖图显式检出' },
];

export interface CBUCase {
  id: string; answer: string; gold: string; errStep: number; errType: string; detail: string;
}
export const CBU_CASES: CBUCase[] = [
  { id: 'L1-006', answer: '50', gold: '50', errStep: 4, errType: '计算错误', detail: '中间步骤等式变形有误，但最终答案侥幸命中标准答案' },
  { id: 'L1-014', answer: '2', gold: '2', errStep: 6, errType: '计算错误', detail: '末段验证等式不成立，答案与过程脱节' },
  { id: 'L1-017', answer: '150', gold: '150', errStep: 2, errType: '计算错误', detail: '比例式列错，(2/5)×400=160 ≠ 所列等式，结果却巧合正确' },
  { id: 'L2-004', answer: '27/128', gold: '27/128', errStep: 3, errType: '计算错误', detail: '3×3×3=27 与 27·4³=1728 混排比较，推导链条断裂但答案正确' },
  { id: 'L3-003', answer: '1/2', gold: '1/2', errStep: 2, errType: '计算错误', detail: '把含 π 的表达式与纯数值等式混写，过程不成立' },
];

export const DATASET_COMPOSITION = [
  { level: 'L1', count: 30, sources: 'GSM8K、Math23K', purpose: '误报率基准（正样本池）' },
  { level: 'L2', count: 35, sources: 'MATH L2-3、AGIEval 高考/中考', purpose: '过程问题开始暴露' },
  { level: 'L3', count: 47, sources: 'MATH L4-5、OlympiadBench、Omni-MATH、AMC12', purpose: '「答案对过程错」高发区' },
  { level: 'L4', count: 46, sources: 'AIME、AMC-HF、FrontierMath v2', purpose: '能力天花板探测' },
];

export const ERROR_TAXONOMY = [
  '题意误读', '概念理解错误', '定理/公式误用', '计算错误', '条件遗漏',
  '跳步推导', '循环论证', '幻觉/无中生有', '单位/格式不符', '其他/无法归类',
];

export const PIPELINE_LAYERS = [
  { id: 'L0', name: '答案层', method: '与标准答案比对（exact / numeric / sympy 等价）', detects: '最终答案错误', color: 'cyan' },
  { id: 'L1', name: '结构层', method: '非空检查、重复/循环检测', detects: '空过程、循环复制', color: 'cyan' },
  { id: 'L2', name: '符号验证层', method: 'SymPy 解析与数值验证等式两边', detects: '计算错误、等式不成立', color: 'mint' },
  { id: 'L3', name: '语义审查层', method: 'LLM-as-judge（普通 / Research 双 prompt）', detects: '题意误读、定理误用、条件遗漏、跳步、循环论证、幻觉', color: 'amber' },
  { id: 'L4', name: '截断/完整性层', method: 'finish_reason、末尾字符、\\boxed{}、token 用量', detects: '输出截断、未完成推理', color: 'red' },
];
