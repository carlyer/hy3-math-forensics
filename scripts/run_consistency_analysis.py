"""多采样一致性分析脚本.

用法示例:
    python scripts/run_consistency_analysis.py \
        --input dataset/problems_merged.jsonl \
        --output results/consistency_analysis.json \
        --n_samples 5 \
        --limit 20 \
        --temperature 0.8 \
        --top_p 0.95 \
        --max_tokens 3072
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tqdm import tqdm

from app.hy3_client import load_client_from_env
from app.multi_sample_generator import generate_multiple_solutions
from evaluator.consistency_analyzer import (
    analyze_answer_consistency,
    analyze_process_consistency,
    compute_self_consistency_metrics,
)


def load_problems(path: str) -> List[Dict[str, Any]]:
    """加载题库 JSONL."""
    problems: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                problems.append(json.loads(line))
    return problems


def _fmt_ratio(value: Any) -> str:
    """格式化比率，None 时返回 '-'."""
    if value is None:
        return "-"
    return f"{value:.2%}"


def generate_markdown_report(
    report_path: Path,
    results: List[Dict[str, Any]],
    metrics: Dict[str, Any],
    config: Dict[str, Any],
) -> None:
    """生成 Markdown 格式的简洁报告."""
    lines: List[str] = []
    lines.append("# 多采样一致性分析报告\n")

    lines.append("## 运行配置\n")
    lines.append(f"- 输入文件：`{config['input']}`")
    lines.append(f"- 输出文件：`{config['output']}`")
    lines.append(f"- 每题采样数：**{config['n_samples']}**")
    lines.append(f"- 处理题数：**{len(results)}**")
    lines.append(f"- temperature：{config['temperature']}")
    lines.append(f"- top_p：{config['top_p']}")
    lines.append(f"- max_tokens：{config['max_tokens']}\n")

    lines.append("## 整体指标\n")
    overall = metrics.get("overall", {})
    lines.append(
        "| 自一致率 | 答案一致率 | 过程一致率 | "
        "答案一致但过程不一致率 | 条件过程一致率 |"
    )
    lines.append("| --- | --- | --- | --- | --- |")
    lines.append(
        f"| {_fmt_ratio(overall.get('self_consistency_rate'))} "
        f"| {_fmt_ratio(overall.get('answer_consistency_rate'))} "
        f"| {_fmt_ratio(overall.get('process_consistency_rate'))} "
        f"| {_fmt_ratio(overall.get('answer_consistent_but_process_inconsistent_rate'))} "
        f"| {_fmt_ratio(overall.get('conditional_process_consistency_rate'))} |"
    )
    lines.append("")

    by_level = metrics.get("by_level", {})
    if by_level:
        lines.append("## 按难度层指标\n")
        lines.append(
            "| 难度 | 题数 | 自一致率 | 答案一致率 | 过程一致率 | "
            "答案一致但过程不一致率 | 条件过程一致率 |"
        )
        lines.append("| --- | --- | --- | --- | --- | --- | --- |")
        for level in sorted(by_level.keys()):
            s = by_level[level]
            lines.append(
                f"| {level} | {s.get('total', 0)} "
                f"| {_fmt_ratio(s.get('self_consistency_rate'))} "
                f"| {_fmt_ratio(s.get('answer_consistency_rate'))} "
                f"| {_fmt_ratio(s.get('process_consistency_rate'))} "
                f"| {_fmt_ratio(s.get('answer_consistent_but_process_inconsistent_rate'))} "
                f"| {_fmt_ratio(s.get('conditional_process_consistency_rate'))} |"
            )
        lines.append("")

    lines.append("## 逐题摘要\n")
    lines.append(
        "| 题号 | 难度 | 样本数 | 答案一致 | 多数答案 | 多数答案正确 | "
        "过程一致 | 过程发散分数 |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in results:
        aa = r.get("answer_analysis", {})
        pa = r.get("process_analysis", {})
        majority_answer = aa.get("majority_answer")
        if majority_answer is not None and len(str(majority_answer)) > 20:
            majority_answer = str(majority_answer)[:20] + "..."
        lines.append(
            f"| {r.get('problem_id', '')} "
            f"| {r.get('level', '') or '-'} "
            f"| {aa.get('total_samples', 0)} "
            f"| {'是' if aa.get('answer_consistent') else '否'} "
            f"| {majority_answer if majority_answer is not None else '-'} "
            f"| {'是' if aa.get('majority_answer_correct') else '否'} "
            f"| {'是' if pa.get('process_consistent') else '否'} "
            f"| {pa.get('process_divergence_score', 0.0):.3f} |"
        )
    lines.append("")

    with report_path.open("w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description="多采样一致性分析")
    parser.add_argument(
        "--input",
        type=str,
        default="dataset/problems_merged.jsonl",
        help="题目 JSONL 路径",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="results/consistency_analysis.json",
        help="详细结果 JSON 路径",
    )
    parser.add_argument(
        "--n_samples",
        type=int,
        default=5,
        help="每题采样次数",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="仅处理前 N 题（用于快速测试）",
    )
    parser.add_argument("--temperature", type=float, default=0.8)
    parser.add_argument("--top_p", type=float, default=0.95)
    parser.add_argument("--max_tokens", type=int, default=3072)
    args = parser.parse_args()

    problems = load_problems(args.input)
    if args.limit is not None:
        problems = problems[: args.limit]

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path = output_path.with_name(output_path.stem + "_report.md")

    print(f"加载题库：{args.input}，共 {len(problems)} 题")
    print("加载模型客户端...")
    client = load_client_from_env()

    results: List[Dict[str, Any]] = []
    for problem in tqdm(problems, desc="多采样一致性分析"):
        samples = generate_multiple_solutions(
            client,
            problem,
            n_samples=args.n_samples,
            temperature=args.temperature,
            top_p=args.top_p,
            max_tokens=args.max_tokens,
        )
        answer_analysis = analyze_answer_consistency(samples, problem)
        process_analysis = analyze_process_consistency(samples, problem)
        results.append(
            {
                "problem_id": problem.get("id"),
                "level": problem.get("level"),
                "problem": problem.get("problem"),
                "answer_analysis": answer_analysis,
                "process_analysis": process_analysis,
                "samples": samples,
            }
        )

    metrics = compute_self_consistency_metrics(results)

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "problems": results,
                "metrics": metrics,
                "config": vars(args),
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    generate_markdown_report(report_path, results, metrics, vars(args))

    print(f"\n详细结果保存至：{output_path}")
    print(f"报告保存至：{report_path}")
    print("\n整体指标：")
    overall = metrics.get("overall", {})
    print(f"  总题数：{overall.get('total', 0)}")
    print(
        f"  自一致率（多数答案正确率）："
        f"{_fmt_ratio(overall.get('self_consistency_rate'))}"
    )
    print(
        f"  答案一致率："
        f"{_fmt_ratio(overall.get('answer_consistency_rate'))}"
    )
    print(
        f"  过程一致率："
        f"{_fmt_ratio(overall.get('process_consistency_rate'))}"
    )
    print(
        f"  答案一致但过程不一致率："
        f"{_fmt_ratio(overall.get('answer_consistent_but_process_inconsistent_rate'))}"
    )


def self_check() -> None:
    """使用模拟客户端跑通完整链路，不调用真实 API."""

    class MockClient:
        def chat_generate(self, messages_list: List[List[Dict[str, Any]]], **kwargs: Any) -> List[Dict[str, Any]]:
            return [
                {
                    "text": (
                        "步骤 1：2 x 12 = 24。\ndepends_on: []\n"
                        "步骤 2：24 x 2 = 48。\ndepends_on: [1]\n"
                        "步骤 3：48 / 3 = 16。\ndepends_on: [2]\n"
                        "\\boxed{16}"
                    ),
                    "finish_reason": "stop",
                    "token_usage": {"prompt_tokens": 10, "completion_tokens": 30, "total_tokens": 40},
                }
                for _ in messages_list
            ]

    problem = {
        "id": "demo",
        "level": "L1",
        "problem": "Mimi picked up 2 dozen seashells...",
        "answer": "16",
        "verification": {"method": "exact_match"},
    }

    samples = generate_multiple_solutions(
        MockClient(), problem, n_samples=3, temperature=0.8
    )
    aa = analyze_answer_consistency(samples, problem)
    pa = analyze_process_consistency(samples, problem)
    results = [
        {"problem_id": problem["id"], "level": problem["level"], "answer_analysis": aa, "process_analysis": pa}
    ]
    metrics = compute_self_consistency_metrics(results)

    report_path = Path("results/_consistency_selfcheck_report.md")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    generate_markdown_report(
        report_path,
        results,
        metrics,
        {
            "input": "selfcheck",
            "output": "selfcheck.json",
            "n_samples": 3,
            "temperature": 0.8,
            "top_p": 0.95,
            "max_tokens": 3072,
        },
    )

    assert len(samples) == 3
    assert aa["answer_consistent"] is True
    assert pa["process_consistent"] is True
    print("\n多采样一致性分析脚本自检通过")
    print(f"自检报告：{report_path}")


if __name__ == "__main__":
    # 无参数时执行自检示例；有参数时执行正式 CLI.
    if len(sys.argv) == 1:
        self_check()
    else:
        main()
