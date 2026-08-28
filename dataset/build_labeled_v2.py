#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
构造 problems_labeled_v2.jsonl：18 道人工注入错误的数学解题过程样本。
主要用于验证过程评估器定位首个错误步以及识别“答案对但过程错”的能力。
"""
import json
from collections import Counter

OUTPUT_JSONL = "dataset/problems_labeled_v2.jsonl"
OUTPUT_REPORT = "dataset/injection_report.json"

entries = [
    {
        "mutation_id": "L1-001-v2-calculation-3",
        "problem_id": "L1-001",
        "error_type": "计算错误",
        "injected_step_index": 3,
        "expected_first_error_step": 3,
        "steps": [
            {"index": 1, "text": "设小明买了 x 支钢笔。"},
            {"index": 2, "text": "5 本笔记本花费 5 × 8 = 40 元。"},
            {"index": 3, "text": "钢笔花费 88 - 40 = 52 元，即 12x = 52。"},
            {"index": 4, "text": "解得 x = 52 / 12 = 13/3。"},
        ],
        "final_answer": "13/3",
        "answer_correct": False,
        "description": "将 88 - 40 算错为 52，导致后续结果错误。",
    },
    {
        "mutation_id": "L1-001-v2-missing_condition-2",
        "problem_id": "L1-001",
        "error_type": "条件遗漏",
        "injected_step_index": 2,
        "expected_first_error_step": 2,
        "steps": [
            {"index": 1, "text": "设小明买了 x 支钢笔。"},
            {"index": 2, "text": "由题意，买钢笔花费 12x = 88 元。"},
            {"index": 3, "text": "解得 x = 88 / 12 = 22/3。"},
        ],
        "final_answer": "22/3",
        "answer_correct": False,
        "description": "忽略了小明还买了 5 本笔记本的条件，直接用总花费列方程。",
    },
    {
        "mutation_id": "L1-006-v2-misread-3",
        "problem_id": "L1-006",
        "error_type": "题意误读",
        "injected_step_index": 3,
        "expected_first_error_step": 3,
        "steps": [
            {"index": 1, "text": "设 x 年后父亲年龄是儿子年龄的 2 倍。"},
            {"index": 2, "text": "x 年后父亲为 35 + x 岁。"},
            {"index": 3, "text": "题意误读为父亲年龄是儿子现在年龄的 2 倍，即 35 + x = 2 × 8 = 16。"},
            {"index": 4, "text": "解得 x = -19。"},
        ],
        "final_answer": "-19",
        "answer_correct": False,
        "description": "未将儿子年龄也加上 x，错误使用儿子当前年龄建立等式。",
    },
    {
        "mutation_id": "L1-007-v2-theorem_misuse-3",
        "problem_id": "L1-007",
        "error_type": "误用定理/公式",
        "injected_step_index": 3,
        "expected_first_error_step": 3,
        "steps": [
            {"index": 1, "text": "设工程总量为 1。"},
            {"index": 2, "text": "甲每天完成 1/10，乙每天完成 1/15。"},
            {"index": 3, "text": "误用平均公式，认为合作效率为 ((1/10) + (1/15)) / 2 = 1/12。"},
            {"index": 4, "text": "合作需要 12 天。"},
        ],
        "final_answer": "12",
        "answer_correct": False,
        "description": "合作效率应为两人效率之和，而非算术平均。",
    },
    {
        "mutation_id": "L1-008-v2-skipped_step-3",
        "problem_id": "L1-008",
        "error_type": "跳步推导",
        "injected_step_index": 3,
        "expected_first_error_step": 3,
        "steps": [
            {"index": 1, "text": "设鸡有 x 只，兔有 y 只。"},
            {"index": 2, "text": "根据题意：x + y = 10，2x + 4y = 28。"},
            {"index": 3, "text": "直接断言 x = 5，y = 5。"},
            {"index": 4, "text": "因此鸡 5 只，兔 5 只。"},
        ],
        "final_answer": "5,5",
        "answer_correct": False,
        "description": "跳过解方程组的关键推导，直接给出未经验证的结论。",
    },
    {
        "mutation_id": "L1-011-v2-misread-2",
        "problem_id": "L1-011",
        "error_type": "题意误读",
        "injected_step_index": 2,
        "expected_first_error_step": 2,
        "steps": [
            {"index": 1, "text": "实际距离 = 图上距离 × 比例尺代表的实际长度。"},
            {"index": 2, "text": "误将比例尺 1:50000 读作 1:5000，计算得 4 × 5000 = 20000 厘米。"},
            {"index": 3, "text": "20000 厘米 = 0.2 千米。"},
        ],
        "final_answer": "0.2",
        "answer_correct": False,
        "description": "将比例尺少看一个 0，导致实际距离缩小为正确的 1/10。",
    },
    {
        "mutation_id": "L1-012-v2-calculation-2",
        "problem_id": "L1-012",
        "error_type": "计算错误",
        "injected_step_index": 2,
        "expected_first_error_step": 2,
        "steps": [
            {"index": 1, "text": "1 到 100 的整数和 S = n(n+1)/2，其中 n = 100。"},
            {"index": 2, "text": "计算 100 × 101 / 2 = 5000。"},
            {"index": 3, "text": "因此和为 5000。"},
        ],
        "final_answer": "5000",
        "answer_correct": False,
        "description": "套用等差数列求和公式时，100×101/2 算错为 5000。",
    },
    {
        "mutation_id": "L2-002-v2-missing_condition-2",
        "problem_id": "L2-002",
        "error_type": "条件遗漏",
        "injected_step_index": 2,
        "expected_first_error_step": 2,
        "steps": [
            {"index": 1, "text": "百位是奇数，可选 1、3、5；个位是偶数，可选 2、4。"},
            {"index": 2, "text": "忽略“没有重复数字”的限制，认为十位仍有 5 种选择。"},
            {"index": 3, "text": "总数为 3 × 5 × 2 = 30。"},
        ],
        "final_answer": "30",
        "answer_correct": False,
        "description": "遗漏“没有重复数字”条件，导致十位可选项被重复计算。",
    },
    {
        "mutation_id": "L2-006-v2-theorem_misuse-3",
        "problem_id": "L2-006",
        "error_type": "误用定理/公式",
        "injected_step_index": 3,
        "expected_first_error_step": 3,
        "steps": [
            {"index": 1, "text": "因为 PA 是切线，所以 OA ⊥ PA，三角形 OAP 为直角三角形。"},
            {"index": 2, "text": "由勾股定理，PA² + OA² = OP²。"},
            {"index": 3, "text": "误用公式，认为 PA = OP - OA = 10 - 6 = 4。"},
            {"index": 4, "text": "所以 PA = 4。"},
        ],
        "final_answer": "4",
        "answer_correct": False,
        "description": "用斜边减直角边求另一直角边，未正确使用勾股定理开方。",
    },
    {
        "mutation_id": "L2-005-v2-skipped_step-2",
        "problem_id": "L2-005",
        "error_type": "跳步推导",
        "injected_step_index": 2,
        "expected_first_error_step": 2,
        "steps": [
            {"index": 1, "text": "原不等式为 1 ≤ 2x - 1 ≤ 13。"},
            {"index": 2, "text": "直接断言该不等式等价于 1 ≤ x ≤ 7。"},
            {"index": 3, "text": "因此整数解为 1,2,3,4,5,6,7，共 7 个。"},
        ],
        "final_answer": "7",
        "answer_correct": True,
        "description": "跳过了不等式两端同时加 1 与除以 2 的推导过程，但结果正确。",
    },
    {
        "mutation_id": "L2-007-v2-calculation-3",
        "problem_id": "L2-007",
        "error_type": "计算错误",
        "injected_step_index": 3,
        "expected_first_error_step": 3,
        "steps": [
            {"index": 1, "text": "等比数列和公式 S = 2^{n+1} - 1，其中 n = 10。"},
            {"index": 2, "text": "计算 2^{11} = 2048。"},
            {"index": 3, "text": "再减 1 时算错：2048 - 1 = 2046。"},
            {"index": 4, "text": "所以和为 2046。"},
        ],
        "final_answer": "2046",
        "answer_correct": False,
        "description": "最后一步减法计算错误，2048 - 1 被写成 2046。",
    },
    {
        "mutation_id": "L2-011-v2-calculation-3",
        "problem_id": "L2-011",
        "error_type": "计算错误",
        "injected_step_index": 3,
        "expected_first_error_step": 3,
        "steps": [
            {"index": 1, "text": "2^n 除以 7 的余数周期为 3：2, 4, 1。"},
            {"index": 2, "text": "100 = 3 × 33 + 2，对应周期中的第 2 项。"},
            {"index": 3, "text": "周期中第 2 项被误记为 1，因此 2^{100} ≡ 1 (mod 7)。"},
            {"index": 4, "text": "所以余数为 1。"},
        ],
        "final_answer": "1",
        "answer_correct": False,
        "description": "周期内第 2 项实际为 4，误记为 1，导致余数错误。",
    },
    {
        "mutation_id": "L2-012-v2-missing_condition-2",
        "problem_id": "L2-012",
        "error_type": "条件遗漏",
        "injected_step_index": 2,
        "expected_first_error_step": 2,
        "steps": [
            {"index": 1, "text": "由韦达定理，两根之和 = -b = 5，两根之积 = c = 6。"},
            {"index": 2, "text": "遗漏负号条件，直接得到 b = 5。"},
            {"index": 3, "text": "于是 b + c = 5 + 6 = 11。"},
        ],
        "final_answer": "11",
        "answer_correct": False,
        "description": "遗漏韦达定理中一次项系数 b 前的负号，导致 b 的符号错误。",
    },
    {
        "mutation_id": "L3-003-v2-misread-3",
        "problem_id": "L3-003",
        "error_type": "题意误读",
        "injected_step_index": 3,
        "expected_first_error_step": 3,
        "steps": [
            {"index": 1, "text": "已知 sin x + cos x = 7/5。"},
            {"index": 2, "text": "两边平方得 sin² x + 2 sin x cos x + cos² x = 49/25。"},
            {"index": 3, "text": "误将题目要求的 sin x · cos x 看成 sin x + cos x，直接输出 7/5。"},
        ],
        "final_answer": "7/5",
        "answer_correct": False,
        "description": "没有看清所求量，把已知条件直接当作答案。",
    },
    {
        "mutation_id": "L3-002-v2-calculation-3",
        "problem_id": "L3-002",
        "error_type": "计算错误",
        "injected_step_index": 3,
        "expected_first_error_step": 3,
        "steps": [
            {"index": 1, "text": "n² + n = n(n+1)，且 n 与 n+1 互质，因数个数 d(n(n+1)) = d(n)d(n+1)。"},
            {"index": 2, "text": "检验 n = 14：14 × 15 = 210 = 2 × 3 × 5 × 7。"},
            {"index": 3, "text": "漏算质因子 7，错误算得 d(210) = (1+1)(1+1)(1+1) = 8。"},
            {"index": 4, "text": "因此继续寻找，最终给出 n = 15。"},
        ],
        "final_answer": "15",
        "answer_correct": False,
        "description": "在 n = 14 处漏算一个质因子，导致因数个数算错，错过真正的最小值。",
    },
    {
        "mutation_id": "L3-007-v2-theorem_misuse-2",
        "problem_id": "L3-007",
        "error_type": "误用定理/公式",
        "injected_step_index": 2,
        "expected_first_error_step": 2,
        "steps": [
            {"index": 1, "text": "展开 (1+√2)^5 + (1-√2)^5，奇次根号项抵消，只留偶次项。"},
            {"index": 2, "text": "误用二项式系数，算成 2[1 + 5·2 + 10·4] = 122。"},
            {"index": 3, "text": "所以原式的值为 122。"},
        ],
        "final_answer": "122",
        "answer_correct": False,
        "description": "二项式展开时混淆了组合系数，导致偶次项系数求和错误。",
    },
    {
        "mutation_id": "L4-006-v2-circular-3",
        "problem_id": "L4-006",
        "error_type": "循环论证",
        "injected_step_index": 3,
        "expected_first_error_step": 3,
        "steps": [
            {"index": 1, "text": "当 n = 1 时，左边 = 1，右边 = 1·2·3/6 = 1，成立。"},
            {"index": 2, "text": "假设 n = k 时等式成立。"},
            {"index": 3, "text": "证明 n = k+1 时，直接写“由等式成立可知 1²+...+k²+(k+1)² = (k+1)(k+2)(2k+3)/6”，没有实际推导。"},
            {"index": 4, "text": "因此等式对所有正整数 n 成立。"},
        ],
        "final_answer": "n(n+1)(2n+1)/6",
        "answer_correct": True,
        "description": "在数学归纳法的递推步骤中直接引用待证结论，构成循环论证，但答案形式正确。",
    },
    {
        "mutation_id": "L4-005-v2-circular-3",
        "problem_id": "L4-005",
        "error_type": "循环论证",
        "injected_step_index": 3,
        "expected_first_error_step": 3,
        "steps": [
            {"index": 1, "text": "将 1,2,...,20 分成 10 对 {1,20},{2,19},...,{10,11}。"},
            {"index": 2, "text": "每对中至多取一个数，因此子集大小至多为 10。"},
            {"index": 3, "text": "在证明 10 可以达到时，直接断言“因为答案就是 10，所以存在这样的子集”，循环使用了待证结论。"},
            {"index": 4, "text": "因此最大大小为 10。"},
        ],
        "final_answer": "10",
        "answer_correct": True,
        "description": "证明可达性时直接引用结论本身，构成循环论证，但答案正确。",
    },
]


def write_jsonl(path, records):
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def build_report(records):
    type_counter = Counter(r["error_type"] for r in records)
    correct_counter = Counter(r["answer_correct"] for r in records)
    return {
        "total_mutations": len(records),
        "error_type_distribution": dict(type_counter),
        "answer_correct_distribution": {
            "correct": correct_counter.get(True, 0),
            "incorrect": correct_counter.get(False, 0),
        },
        "answer_correct_but_process_wrong": sum(
            1 for r in records if r["answer_correct"] and r["expected_first_error_step"] is not None
        ),
        "notes": [
            "answer_correct_but_process_wrong 统计的是最终答案与标准答案一致，但过程被注入错误的样本数。",
            "answer_correct_distribution.correct 包含无错误样本；本文件中所有样本均含注入错误，因此 correct 全部为答案对过程错。",
        ],
    }


def main():
    write_jsonl(OUTPUT_JSONL, entries)
    report = build_report(entries)
    with open(OUTPUT_REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"已生成 {OUTPUT_JSONL}，共 {len(entries)} 条。")
    print(f"已生成 {OUTPUT_REPORT}。")


if __name__ == "__main__":
    main()
