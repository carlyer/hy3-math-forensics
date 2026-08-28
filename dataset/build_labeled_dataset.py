"""构建带注入错误的验证集.

用于验证过程评估器的定位准确率与误报率。
每道题包含：
- 原始题目
- 标准答案
- 正确解题过程（reference_solution）
- 一个或多个注入错误的变体（mutations）
"""

import json
from pathlib import Path
from typing import Dict, List


# 正确解题过程示例（手写，供注入错误使用）
REFERENCE_SOLUTIONS = {
    "L1-001": {
        "steps": [
            {"index": 1, "text": "设小明买了 x 支钢笔。"},
            {"index": 2, "text": "5 本笔记本花费 5 × 8 = 40 元。"},
            {"index": 3, "text": "钢笔花费 88 - 40 = 48 元，即 12x = 48。"},
            {"index": 4, "text": "解得 x = 48 / 12 = 4。"},
        ],
        "final_answer": "4",
    },
    "L1-002": {
        "steps": [
            {"index": 1, "text": "路程 = 速度 × 时间。"},
            {"index": 2, "text": "代入数据：路程 = 60 × 3.5 = 210 千米。"},
        ],
        "final_answer": "210",
    },
    "L2-003": {
        "steps": [
            {"index": 1, "text": "由勾股定理，斜边 AB = √(AC² + BC²) = √(6² + 8²) = √100 = 10。"},
            {"index": 2, "text": "三角形面积 = (1/2) × AC × BC = (1/2) × 6 × 8 = 24。"},
            {"index": 3, "text": "面积也可表示为 (1/2) × AB × CD = (1/2) × 10 × CD = 5 × CD。"},
            {"index": 4, "text": "因此 5 × CD = 24，解得 CD = 24/5。"},
        ],
        "final_answer": "24/5",
    },
    "L2-008": {
        "steps": [
            {"index": 1, "text": "f(x) = x² - 6x + 10。"},
            {"index": 2, "text": "配方得 f(x) = (x - 3)² + 1。"},
            {"index": 3, "text": "因为 (x - 3)² ≥ 0，所以 f(x) ≥ 1，最小值为 1。"},
        ],
        "final_answer": "1",
    },
    "L3-004": {
        "steps": [
            {"index": 1, "text": "递推式 a_{n+1} = 2a_n + 1 可变形为 a_{n+1} + 1 = 2(a_n + 1)。"},
            {"index": 2, "text": "因此 {a_n + 1} 是首项为 a_1 + 1 = 2、公比为 2 的等比数列。"},
            {"index": 3, "text": "所以 a_n + 1 = 2 × 2^{n-1} = 2^n，即 a_n = 2^n - 1。"},
            {"index": 4, "text": "当 n = 10 时，a_10 = 2^10 - 1 = 1024 - 1 = 1023。"},
        ],
        "final_answer": "1023",
    },
}


# 错误注入模板
MUTATIONS = {
    "calculation_error": {
        "description": "计算错误：将某一步的正确数值改为错误数值",
        "operations": [
            {
                "step_index": 3,
                "original": "钢笔花费 88 - 40 = 48 元，即 12x = 48。",
                "mutated": "钢笔花费 88 - 40 = 52 元，即 12x = 52。",
                "expected_first_error_step": 3,
            },
            {
                "step_index": 2,
                "original": "代入数据：路程 = 60 × 3.5 = 210 千米。",
                "mutated": "代入数据：路程 = 60 × 3.5 = 200 千米。",
                "expected_first_error_step": 2,
            },
        ],
    },
    "theorem_misuse": {
        "description": "定理误用：用错误的定理或公式",
        "operations": [
            {
                "step_index": 1,
                "original": "由勾股定理，斜边 AB = √(AC² + BC²) = √(6² + 8²) = √100 = 10。",
                "mutated": "由勾股定理，斜边 AB = AC + BC = 6 + 8 = 14。",
                "expected_first_error_step": 1,
            },
        ],
    },
    "missing_condition": {
        "description": "条件遗漏：跳过或使用未给出的条件",
        "operations": [
            {
                "step_index": 2,
                "original": "配方得 f(x) = (x - 3)² + 1。",
                "mutated": "因为平方项非负，所以 f(x) ≥ 1，最小值为 1。",
                "expected_first_error_step": 2,
            },
        ],
    },
    "skipped_step": {
        "description": "跳步推导：直接给出没有中间过程的结论",
        "operations": [
            {
                "step_index": 3,
                "original": "所以 a_n + 1 = 2 × 2^{n-1} = 2^n，即 a_n = 2^n - 1。",
                "mutated": "所以 a_n = 2^n - 1。",
                "expected_first_error_step": 3,
            },
        ],
    },
}


def load_problems(path: str) -> Dict[str, Dict]:
    """加载题库并转为 id -> problem 映射."""
    problems = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            p = json.loads(line)
            problems[p["id"]] = p
    return problems


def inject_errors(problem_id: str, solution: Dict) -> List[Dict]:
    """为某道题的正确解题过程注入错误，生成多个变体."""
    mutations = []
    for error_type, config in MUTATIONS.items():
        for op in config["operations"]:
            if op["original"] not in [s["text"] for s in solution["steps"]]:
                continue

            new_steps = []
            for s in solution["steps"]:
                if s["text"] == op["original"]:
                    new_steps.append({
                        "index": s["index"],
                        "text": op["mutated"],
                    })
                else:
                    new_steps.append(dict(s))

            mutations.append({
                "mutation_id": f"{problem_id}-{error_type}-{op['step_index']}",
                "problem_id": problem_id,
                "error_type": error_type,
                "injected_step_index": op["step_index"],
                "expected_first_error_step": op["expected_first_error_step"],
                "steps": new_steps,
                "final_answer": solution["final_answer"],
                "answer_correct": True,  # 答案仍标记为正确（用于测试过程识别）
                "description": config["description"],
            })
    return mutations


def build_labeled_dataset(problems_path: str, output_path: str) -> None:
    """构建带标签的验证集."""
    problems = load_problems(problems_path)
    records = []

    # 1) 正确答案样本（用于误报率验证）
    for pid, solution in REFERENCE_SOLUTIONS.items():
        if pid not in problems:
            continue
        records.append({
            "mutation_id": f"{pid}-correct",
            "problem_id": pid,
            "error_type": "无错误",
            "injected_step_index": None,
            "expected_first_error_step": None,
            "steps": solution["steps"],
            "final_answer": solution["final_answer"],
            "answer_correct": True,
            "description": "正确答案样本，用于测试误报率",
        })

    # 2) 注入错误的样本（用于定位准确率验证）
    for pid, solution in REFERENCE_SOLUTIONS.items():
        if pid not in problems:
            continue
        mutations = inject_errors(pid, solution)
        records.extend(mutations)

    with open(output_path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"已生成标注验证集: {output_path}")
    print(f"总样本数: {len(records)}")

    correct_count = sum(1 for r in records if r["error_type"] == "无错误")
    error_count = len(records) - correct_count
    print(f"  正确样本: {correct_count}")
    print(f"  注入错误样本: {error_count}")


if __name__ == "__main__":
    root = Path(__file__).parent
    build_labeled_dataset(
        problems_path=str(root / "problems.jsonl"),
        output_path=str(root / "problems_labeled.jsonl"),
    )
