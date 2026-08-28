// 内置演示题：2026 年高考数学新课标卷（低污染题源，contamination_risk: low）
export interface DemoProblem {
  id: string; level: string; domain: string; form: 'choice' | 'fill' | 'open';
  title: string; problem: string; answer: string;
}

export const DEMO_PROBLEMS: DemoProblem[] = [
  { id: 'GK26-01', level: 'L2', domain: '统计', form: 'choice', title: '中位数',
    problem: '样本数据 6，8，4，5，12 的中位数为\n(A) 5　(B) 6　(C) 8　(D) 9', answer: 'B' },
  { id: 'GK26-04', level: 'L2', domain: '导数', form: 'choice', title: '切线方程',
    problem: '曲线 y = 5x + 8ln x 在点 (1, 5) 处的切线方程为\n(A) y=3x+2　(B) y=5x　(C) y=8x−3　(D) y=13x−8', answer: 'D' },
  { id: 'GK26-05', level: 'L2', domain: '圆锥曲线', form: 'choice', title: '抛物线焦点距离',
    problem: '已知抛物线 C₁: y²=2p₁x (p₁>0) 和 C₂: x²=2p₂y (p₂>0) 均经过点 (4,8)，则 C₁ 的焦点与 C₂ 的焦点之间的距离为\n(A) 12　(B) 4√5　(C) 6　(D) √65/2', answer: 'D' },
  { id: 'GK26-08', level: 'L3', domain: '概率期望', form: 'choice', title: '点集期望',
    problem: '设 U={(x₁,x₂,x₃) | xᵢ∈{−2,−1,1,2}, i=1,2,3} 为空间中 64 个点构成的集合，点 P(1,1,1)，记样本空间 Ω=U∖{P}。从 Ω 中随机取一个点 A(x₁,x₂,x₃)，令 X(A)=x₁+x₂+x₃，则 X 的数学期望为\n(A) −1/21　(B) −1/63　(C) 0　(D) 1/7', answer: 'A' },
  { id: 'GK26-12', level: 'L2', domain: '圆锥曲线', form: 'fill', title: '双曲线离心率',
    problem: '双曲线 5x² − 6y² = 1 的离心率为 ______。', answer: '√66/6' },
  { id: 'GK26-13', level: 'L3', domain: '三角函数', form: 'fill', title: '偶函数与单调性',
    problem: '已知 f(x)=2sin(ωx+θ)（ω∈Z，0≤θ<2π）是偶函数，f(x) 在区间 (0, π/2) 单调递增，则 θ=______，f(2π/3)=______。', answer: 'θ=3π/2，f(2π/3)=1' },
  { id: 'GK26-16', level: 'L2', domain: '解三角形', form: 'open', title: '解三角形综合',
    problem: '已知在△ABC 中，AB=3，BC=2√3，cos B=√3/3。\n(1) 求 cos A；\n(2) 设 D、E 两点满足：D 在 BA 的延长线上，DE//BC，AE⊥AC。若 DE=√6，求 CE。', answer: '(1) cos A=1/3；(2) CE=3√5' },
  { id: 'GK26-17', level: 'L3', domain: '概率', form: 'open', title: '投篮停止规则',
    problem: '设整数 N≥2。某同学投篮练习，至多投篮 N 次，当且仅当投中 1 次时或 N 次均未投中时停止。每次投中概率为 p (0<p<1)，各次独立。记 X 为停止时的投篮次数。\n(1) 当 N=4，p=1/3 时，求 X 的分布列；\n(2) 设 k,m 均为自然数。(ⅰ) 当 k≤N−1 时，求 P(X>k)；(ⅱ) 当 k+m≤N−1 时，证明：P(X>k+m | X>k)=P(X>m)。', answer: '(1) P(X=1)=1/3, P(X=2)=2/9, P(X=3)=4/27, P(X=4)=8/27；(2)(ⅰ) (1−p)^k' },
  { id: 'GK26-18', level: 'L3', domain: '圆锥曲线', form: 'open', title: '椭圆与动直线',
    problem: '已知椭圆 C: x²/a²+y²/b²=1 (a>b>0) 的左焦点为 F(−1,0)，离心率为 1/2。\n(1) 求 C 的方程；\n(2) 设 O 为坐标原点，过 F 且斜率大于 0 的动直线 l 与 C 交于 P、Q 两点，Q 在第三象限，直线 PO 与 C 的另一个交点为 R。(ⅰ) 若△PQR 的面积是△PFO 面积的 3 倍，求 l 的方程；(ⅱ) 求 tan∠PQR 的最小值。', answer: '(1) x²/4+y²/3=1；(2)(ⅰ) √5 x−2y+√5=0；(ⅱ) 4√3' },
  { id: 'GK26-19', level: 'L4', domain: '抽象函数', form: 'open', title: '集合 D(x₀) 证明',
    problem: '已知函数 f(x) 的定义域为 R，且当 x<0 时 f(x)=2ˣ。对任意 x₀∈R，定义集合 D(x₀)={d∈R | f(x₀+d)>f(x₀)}。\n(1) 若当 x≥0 时 f(x)=1−x，求 D(−1)；\n(2) 若 f(x) 是奇函数，f(x₁)≤f(x₂)，且 x₁x₂≠0，证明：D(x₂)⊆D(x₁)；\n(3) 设 f(x) 满足：① 若 f(x₁)≤f(x₂)，则 D(x₂)⊆D(x₁)；② 当 0<x<1 时，f(x)<f(0)。(ⅰ) 证明：f(0)≥1；(ⅱ) 证明：f(x) 在区间 (0,+∞) 单调递增。', answer: '(1) D(−1)={d | 0<d<3/2}；(2)(3) 证明见官方评分细则' },
];
