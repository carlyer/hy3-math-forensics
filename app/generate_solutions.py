"""批量生成数学解题过程.

用法:
    python app/generate_solutions.py \
        --input dataset/problems.jsonl \
        --output results/solutions.jsonl \
        --max_tokens 2048 \
        --temperature 0.6
"""

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).parent.parent))

from tqdm import tqdm

from app.hy3_client import Hy3MathClient, load_client_from_env
from app.prompt_templates import build_messages
from app.solution_parser import parse_solution
from dataset.answer_checker import check_answer
from evaluator.back_substitution import verify_by_substitution


def load_problems(path: str) -> List[Dict]:
    """加载题库."""
    problems = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                problems.append(json.loads(line))
    return problems


def _generate_single(
    client: Hy3MathClient,
    prob: Dict,
    max_tokens: int,
    temperature: float,
    top_p: float,
) -> Dict:
    """为单道题生成解题过程（供线程池调用）。"""
    messages = build_messages(prob["problem"])
    out = client.chat_generate(
        [messages],
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p,
    )[0]

    parsed = parse_solution(
        problem_id=prob["id"],
        raw_output=out["text"],
        reasoning_content=out.get("reasoning_content"),
    )

    answer_correct, detail = check_answer(
        parsed.final_answer,
        prob["answer"],
        prob["verification"],
    )

    return {
        "problem_id": prob["id"],
        "problem": prob["problem"],
        "level": prob["level"],
        "gold_answer": prob["answer"],
        "verification": prob["verification"],
        "messages": out.get("messages"),
        "prompt": out.get("prompt"),
        "generation_params": {
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
        },
        "token_usage": out.get("token_usage"),
        "finish_reason": out.get("finish_reason"),
        "model_name": out.get("model_name"),
        "timestamp": out.get("timestamp"),
        "raw_output": parsed.raw_output,
        "reasoning_content": parsed.reasoning_content,
        "steps": [
            {"index": s.index, "text": s.text, "latex_expressions": s.latex_expressions, "depends_on": s.depends_on}
            for s in parsed.steps
        ],
        "final_answer": parsed.final_answer,
        "answer_correct": answer_correct,
        "answer_check_detail": detail,
        "back_substitution": verify_by_substitution(
            prob["problem"], parsed.final_answer, expected_type="auto"
        ),
    }


def generate_for_problems(
    client: Hy3MathClient,
    problems: List[Dict],
    max_tokens: int = 2048,
    temperature: float = 0.6,
    top_p: float = 0.9,
    batch_size: int = 8,
) -> List[Dict]:
    """批量为题目生成解题过程，batch_size 作为并发线程数."""
    all_results = [None] * len(problems)

    with ThreadPoolExecutor(max_workers=batch_size) as executor:
        futures = {
            executor.submit(
                _generate_single, client, prob, max_tokens, temperature, top_p
            ): idx
            for idx, prob in enumerate(problems)
        }
        for future in tqdm(as_completed(futures), total=len(futures), desc="Generating"):
            idx = futures[future]
            try:
                all_results[idx] = future.result()
            except Exception as e:
                all_results[idx] = {
                    "problem_id": problems[idx]["id"],
                    "error": str(e),
                }

    return all_results


def main():
    parser = argparse.ArgumentParser(description="Generate math solutions with Hy3")
    parser.add_argument(
        "--input",
        type=str,
        default="dataset/problems.jsonl",
        help="Path to problems jsonl",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="results/solutions.jsonl",
        help="Path to output solutions jsonl",
    )
    parser.add_argument("--max_tokens", type=int, default=2048)
    parser.add_argument("--temperature", type=float, default=0.6)
    parser.add_argument("--top_p", type=float, default=0.9)
    parser.add_argument("--batch_size", type=int, default=8)
    parser.add_argument("--limit", type=int, default=None, help="仅处理前 N 题")
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"加载题库: {args.input}")
    problems = load_problems(args.input)
    if args.limit:
        problems = problems[: args.limit]
    print(f"共 {len(problems)} 题")

    print("加载模型...")
    client = load_client_from_env()

    print("开始生成...")
    results = generate_for_problems(
        client,
        problems,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
        top_p=args.top_p,
        batch_size=args.batch_size,
    )

    with output_path.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # 简单统计（过滤掉无标准答案的题）
    total = len(results)
    gradable = [r for r in results if r["answer_correct"] is not None]
    correct = sum(1 for r in gradable if r["answer_correct"])
    print(f"\n生成完成，结果保存至: {output_path}")
    if gradable:
        print(f"可自动判题数: {len(gradable)}/{total}")
        print(f"答案正确率: {correct}/{len(gradable)} = {correct/len(gradable):.2%}")
    else:
        print(f"无可自动判题（共 {total} 题）")


if __name__ == "__main__":
    main()
