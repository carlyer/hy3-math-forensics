"""交互式 demo：输入题目 -> 生成解题过程 -> 过程评估.

用法:
    python demo/demo.py --problem "题目文本"
    python demo/demo.py --problem_id L1-001
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.hy3_client import load_client_from_env
from app.prompt_templates import build_messages
from app.solution_parser import parse_solution
from dataset.answer_checker import check_answer
from evaluator.process_evaluator import ProcessEvaluator


def load_problem(problem_id: str, problems_path: str = "dataset/problems.jsonl") -> dict:
    with open(problems_path, "r", encoding="utf-8") as f:
        for line in f:
            p = json.loads(line)
            if p["id"] == problem_id:
                return p
    raise ValueError(f"未找到题目: {problem_id}")


def main():
    parser = argparse.ArgumentParser(description="Interactive math solution demo")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--problem", type=str, help="直接输入题目文本")
    group.add_argument("--problem_id", type=str, help="使用题库中的题目 ID")
    parser.add_argument("--problems", type=str, default="dataset/problems.jsonl")
    parser.add_argument("--max_tokens", type=int, default=2048)
    parser.add_argument("--temperature", type=float, default=0.6)
    args = parser.parse_args()

    if args.problem_id:
        problem = load_problem(args.problem_id, args.problems)
        problem_text = problem["problem"]
        gold_answer = problem.get("answer")
        verification = problem.get("verification")
    else:
        problem_text = args.problem
        gold_answer = None
        verification = {"method": "exact_match"}

    print("=" * 60)
    print("题目：")
    print(problem_text)
    print("=" * 60)

    print("\n[1/3] 正在加载模型...")
    client = load_client_from_env()

    print("\n[2/3] 正在生成解题过程...")
    messages = build_messages(problem_text)
    outputs = client.chat_generate(
        [messages],
        max_tokens=args.max_tokens,
        temperature=args.temperature,
    )
    raw_output = outputs[0]["text"]
    reasoning_content = outputs[0].get("reasoning_content")

    parsed = parse_solution(
        problem_id=args.problem_id or "custom",
        raw_output=raw_output,
        reasoning_content=reasoning_content,
    )

    print("\n解题过程：")
    for step in parsed.steps:
        print(f"\n步骤 {step.index}:")
        print(step.text)
    print(f"\n最终答案：{parsed.final_answer}")

    if gold_answer:
        answer_correct, detail = check_answer(parsed.final_answer, gold_answer, verification)
        print(f"\n答案校验：{'正确' if answer_correct else '错误'}")
        if detail:
            print(f"详情：{detail}")
    else:
        answer_correct = None

    print("\n[3/3] 正在评估解题过程...")
    evaluator = ProcessEvaluator(llm_judge=None)
    eval_result = evaluator.evaluate(
        problem_text,
        [{"index": s.index, "text": s.text} for s in parsed.steps],
        answer_correct=answer_correct if answer_correct is not None else False,
        use_llm=False,
    )

    print(f"\n过程评估结果：")
    print(f"  过程是否正确：{eval_result['process_correct']}")
    print(f"  首个错误步骤：{eval_result['first_error_step']}")
    print(f"  错误类型：{eval_result['error_type']}")
    if eval_result['error_detail']:
        print(f"  错误详情：{eval_result['error_detail']}")

    if answer_correct and not eval_result["process_correct"]:
        print("\n⚠️ 结果正确但过程不成立！")


if __name__ == "__main__":
    main()
