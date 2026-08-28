"""回代验证器批量测试脚本.

读取已有的 solutions 文件，对每道题运行回代验证，输出统计结果，
并重点列出「答案被判错但回代通过」的疑似 answer_checker 等价性问题案例。
"""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from tqdm import tqdm

from evaluator.back_substitution import verify_by_substitution


def load_solutions(path: str) -> List[Dict]:
    """加载 solutions.jsonl 文件."""
    records: List[Dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def run_back_substitution_audit(
    records: List[Dict],
    output_path: Optional[str] = None,
) -> Dict:
    """对记录列表批量运行回代验证并返回统计信息."""
    total = len(records)
    verifiable = 0
    verified = 0
    suspected_equivalence = 0
    verified_and_answer_correct = 0
    suspected_cases: List[Dict] = []
    enriched: List[Dict] = []

    for rec in tqdm(records, desc="Back substitution"):
        sub = verify_by_substitution(
            rec.get("problem", ""),
            rec.get("final_answer"),
            expected_type="auto",
        )
        enriched_rec = {**rec, "back_substitution": sub}
        enriched.append(enriched_rec)

        if sub.get("verifiable"):
            verifiable += 1
        if sub.get("verified"):
            verified += 1
            if rec.get("answer_correct") is True:
                verified_and_answer_correct += 1
            elif rec.get("answer_correct") is False:
                suspected_equivalence += 1
                suspected_cases.append(
                    {
                        "problem_id": rec.get("problem_id"),
                        "level": rec.get("level"),
                        "problem": rec.get("problem"),
                        "final_answer": rec.get("final_answer"),
                        "gold_answer": rec.get("gold_answer"),
                        "answer_correct": rec.get("answer_correct"),
                        "back_substitution": sub,
                    }
                )

    stats = {
        "total": total,
        "verifiable": verifiable,
        "verified": verified,
        "verified_and_answer_correct": verified_and_answer_correct,
        "suspected_answer_equivalence": suspected_equivalence,
        "unverifiable": total - verifiable,
        "suspected_cases": suspected_cases,
    }

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as f:
            for rec in enriched:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    return stats, enriched


def print_stats(stats: Dict) -> None:
    """打印统计结果."""
    print("\n===== 回代验证统计 =====")
    print(f"总题数: {stats['total']}")
    print(f"可自动回代: {stats['verifiable']}")
    print(f"回代验证通过: {stats['verified']}")
    print(f"  - 其中答案也被判对: {stats['verified_and_answer_correct']}")
    print(f"  - 答案被判错但回代通过（疑似等价性）: {stats['suspected_answer_equivalence']}")
    print(f"无法自动回代: {stats['unverifiable']}")

    if stats["suspected_cases"]:
        print("\n----- 疑似 answer_checker 等价性问题案例 -----")
        for case in stats["suspected_cases"]:
            sub = case["back_substitution"]
            print(
                f"[{case['problem_id']}] level={case['level']}\n"
                f"  题目: {case['problem'][:120]}...\n"
                f"  模型答案: {case['final_answer']}\n"
                f"  标准答案: {case['gold_answer']}\n"
                f"  回代方法: {sub.get('method')} | 详情: {sub.get('detail')}\n"
            )
    else:
        print("\n未发现答案被判错但回代通过的案例。")


def main():
    parser = argparse.ArgumentParser(description="Back-substitution audit over solutions")
    parser.add_argument(
        "--input",
        type=str,
        default="results/solutions.jsonl",
        help="输入 solutions.jsonl 路径",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="results/back_substitution_audit.jsonl",
        help="输出带 back_substitution 字段的 jsonl 路径",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="仅处理前 N 条",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"输入文件不存在: {input_path}")
        return

    records = load_solutions(str(input_path))
    if args.limit:
        records = records[: args.limit]
    print(f"加载 {len(records)} 条记录: {input_path}")

    stats, _ = run_back_substitution_audit(records, output_path=args.output)
    print_stats(stats)
    print(f"\n已保存增强记录至: {args.output}")


if __name__ == "__main__":
    # 自检：构造临时 solutions 文件并运行审计
    sample_records = [
        {
            "problem_id": "demo_eq",
            "level": "L1",
            "problem": "解方程 2x - 1 = 7。",
            "final_answer": "4",
            "gold_answer": "4",
            "answer_correct": True,
        },
        {
            "problem_id": "demo_equiv",
            "level": "L1",
            "problem": "解方程 x + 2 = 5。",
            "final_answer": "x=3",
            "gold_answer": "3",
            "answer_correct": False,  # 模拟 answer_checker 漏判
        },
        {
            "problem_id": "demo_unknown",
            "level": "L1",
            "problem": "请说明勾股定理的几何意义。",
            "final_answer": "直角三角形两直角边平方和等于斜边平方",
            "gold_answer": "...",
            "answer_correct": False,
        },
    ]

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
    ) as tmp:
        for rec in sample_records:
            tmp.write(json.dumps(rec, ensure_ascii=False) + "\n")
        tmp_path = tmp.name

    records = load_solutions(tmp_path)
    stats, _ = run_back_substitution_audit(records, output_path=None)
    try:
        assert stats["total"] == 3
        assert stats["verified"] >= 2
        assert stats["suspected_answer_equivalence"] >= 1
    finally:
        os.unlink(tmp_path)
    print("\n自检通过：回代审计脚本可正常识别通过案例与疑似等价性问题。")

    # 默认执行主流程（如果用户直接运行脚本且有默认输入文件）
    if Path("results/solutions.jsonl").exists():
        main()
