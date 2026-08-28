"""录制/生成 demo 展示材料.

支持两种模式：
1. --live: 调用 Hy3 模型实时生成解题过程并展示
2. --cached: 使用本地缓存的示例输出，生成文本/HTML demo（无需模型）

用法:
    python demo/record_demo.py --problem_id L1-001 --live
    python demo/record_demo.py --problem_id L1-001 --cached
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.solution_parser import Step, parse_solution
from dataset.answer_checker import check_answer
from evaluator.process_evaluator import ProcessEvaluator


def load_problem(problem_id: str, problems_path: str) -> dict:
    with open(problems_path, "r", encoding="utf-8") as f:
        for line in f:
            p = json.loads(line)
            if p["id"] == problem_id:
                return p
    raise ValueError(f"未找到题目: {problem_id}")


def load_cached_solution(problem_id: str, cache_path: str, scenario: str = "correct") -> dict:
    candidates = []
    with open(cache_path, "r", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r.get("problem_id") == problem_id:
                candidates.append(r)
    if not candidates:
        raise ValueError(f"未找到缓存: {problem_id}")
    if scenario == "correct":
        for r in candidates:
            if r.get("error_type") == "无错误":
                return r
    else:
        for r in candidates:
            if r.get("error_type") != "无错误":
                return r
    return candidates[0]


def generate_live_solution(problem_id: str, problem_text: str) -> dict:
    """实时调用模型生成解题过程."""
    from app.hy3_client import load_client_from_env
    from app.prompt_templates import build_messages

    client = load_client_from_env()
    messages = build_messages(problem_text)
    outputs = client.chat_generate([messages], max_tokens=2048, temperature=0.6)
    raw_output = outputs[0]["text"]
    reasoning_content = outputs[0].get("reasoning_content")
    return {
        "raw_output": raw_output,
        "reasoning_content": reasoning_content,
    }


def render_text_demo(problem: dict, solution: dict, eval_result: dict) -> str:
    """渲染为文本形式的 demo."""
    lines = []
    lines.append("=" * 70)
    lines.append("Hy3 数学解题与过程评估 Demo")
    lines.append("=" * 70)
    lines.append(f"\n【题目】\n{problem['problem']}\n")
    lines.append(f"【标准答案】{problem['answer']}\n")

    lines.append("【解题过程】")
    for step in solution.get("steps", []):
        lines.append(f"\n步骤 {step['index']}:")
        lines.append(step["text"])
    lines.append(f"\n【模型最终答案】{solution.get('final_answer')}")

    answer_correct = solution.get("answer_correct", False)
    lines.append(f"【答案校验】{'✓ 正确' if answer_correct else '✗ 错误'}\n")

    lines.append("【过程评估结果】")
    lines.append(f"  过程是否正确：{'✓ 是' if eval_result['process_correct'] else '✗ 否'}")
    lines.append(f"  首个错误步骤：{eval_result['first_error_step']}")
    lines.append(f"  错误类型：{eval_result['error_type']}")
    if eval_result["error_detail"]:
        lines.append(f"  错误详情：{eval_result['error_detail']}")

    cbu = eval_result.get("correct_but_unjustified", {})
    if cbu.get("correct_but_unjustified"):
        lines.append("\n⚠️ 警告：结果正确但推理过程不成立！")

    lines.append("\n" + "=" * 70)
    return "\n".join(lines)


def render_html_demo(problem: dict, solution: dict, eval_result: dict) -> str:
    """渲染为 HTML demo 页面."""
    steps_html = "\n".join(
        f"<div class='step'><h3>步骤 {s['index']}</h3><pre>{s['text']}</pre></div>"
        for s in solution.get("steps", [])
    )

    answer_status = "correct" if solution.get("answer_correct") else "incorrect"
    process_status = "correct" if eval_result["process_correct"] else "incorrect"
    cbu = eval_result.get("correct_but_unjustified", {})
    cbu_flag = cbu.get("correct_but_unjustified", False)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>Hy3 数学解题与过程评估 Demo</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; max-width: 800px; margin: 40px auto; padding: 0 20px; line-height: 1.6; }}
h1 {{ color: #1a1a1a; }}
.problem {{ background: #f5f5f5; padding: 16px; border-radius: 8px; margin: 20px 0; }}
.step {{ background: #fff; border: 1px solid #e0e0e0; padding: 12px; margin: 12px 0; border-radius: 6px; }}
.step pre {{ white-space: pre-wrap; margin: 0; }}
.status {{ display: inline-block; padding: 4px 12px; border-radius: 4px; font-weight: bold; }}
.correct {{ background: #d4edda; color: #155724; }}
.incorrect {{ background: #f8d7da; color: #721c24; }}
.warning {{ background: #fff3cd; color: #856404; padding: 12px; border-radius: 6px; margin: 16px 0; }}
</style>
</head>
<body>
<h1>Hy3 数学解题与过程评估 Demo</h1>
<div class="problem">
  <h2>题目</h2>
  <p>{problem['problem']}</p>
  <p><strong>标准答案：</strong>{problem['answer']}</p>
</div>
<h2>解题过程</h2>
{steps_html}
<p><strong>模型最终答案：</strong>{solution.get('final_answer')}</p>
<p><strong>答案校验：</strong><span class="status {answer_status}">{'正确' if solution.get('answer_correct') else '错误'}</span></p>
<h2>过程评估</h2>
<p><strong>过程是否正确：</strong><span class="status {process_status}">{'是' if eval_result['process_correct'] else '否'}</span></p>
<p><strong>首个错误步骤：</strong>{eval_result['first_error_step']}</p>
<p><strong>错误类型：</strong>{eval_result['error_type']}</p>
<p><strong>错误详情：</strong>{eval_result.get('error_detail', '无')}</p>
{'<div class="warning">⚠️ 结果正确但推理过程不成立！</div>' if cbu_flag else ''}
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description="Record demo")
    parser.add_argument("--problem_id", type=str, default="L1-001")
    parser.add_argument("--problems", type=str, default="dataset/problems.jsonl")
    parser.add_argument("--mode", choices=["live", "cached"], default="cached")
    parser.add_argument("--cache", type=str, default="dataset/problems_labeled.jsonl")
    parser.add_argument("--scenario", choices=["correct", "error"], default="correct",
                        help="使用正确样本还是注入错误样本（仅 cached 模式）")
    parser.add_argument("--output_text", type=str, default="demo/demo_output.txt")
    parser.add_argument("--output_html", type=str, default="demo/demo_output.html")
    args = parser.parse_args()

    problem = load_problem(args.problem_id, args.problems)

    if args.mode == "live":
        raw = generate_live_solution(args.problem_id, problem["problem"])
        parsed = parse_solution(
            problem_id=args.problem_id,
            raw_output=raw["raw_output"],
            reasoning_content=raw.get("reasoning_content"),
        )
    else:
        cached = load_cached_solution(args.problem_id, args.cache, scenario=args.scenario)
        raw_output = "\n".join(s["text"] for s in cached["steps"]) + f"\n\\boxed{{{cached['final_answer']}}}"
        parsed = parse_solution(
            problem_id=args.problem_id,
            raw_output=raw_output,
        )
        # 强制使用缓存中的步骤，避免合并
        parsed.steps = [
            Step(index=s["index"], text=s["text"], latex_expressions=[])
            for s in cached["steps"]
        ]

    answer_correct, detail = check_answer(
        parsed.final_answer,
        problem["answer"],
        problem["verification"],
    )

    solution_record = {
        "problem_id": args.problem_id,
        "steps": [{"index": s.index, "text": s.text} for s in parsed.steps],
        "final_answer": parsed.final_answer,
        "answer_correct": answer_correct,
    }

    evaluator = ProcessEvaluator(llm_judge=None)
    eval_result = evaluator.evaluate(
        problem["problem"],
        solution_record["steps"],
        answer_correct=answer_correct,
        use_llm=False,
    )

    text_demo = render_text_demo(problem, solution_record, eval_result)
    html_demo = render_html_demo(problem, solution_record, eval_result)

    Path(args.output_text).write_text(text_demo, encoding="utf-8")
    Path(args.output_html).write_text(html_demo, encoding="utf-8")

    print(text_demo)
    print(f"\nDemo 输出已保存：")
    print(f"  文本：{args.output_text}")
    print(f"  HTML：{args.output_html}")


if __name__ == "__main__":
    main()
