"""让 GPT 判断 L2 错题中 gold 标签是否错误."""

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.hy3_client import Hy3MathClient

SYSTEM = """你正在审查一道数学选择题的标准答案。请仔细阅读题目和模型给出的解题过程，判断：
1. 模型的最终答案是否正确；
2. 数据集提供的标准答案（gold）是否正确；
3. 如果两者都不对，请给出你认为的正确答案。

请仅输出以下 JSON 格式，不要输出其他内容：
{
  "model_answer_correct": true/false,
  "gold_answer_correct": true/false,
  "correct_answer": "你认定的正确答案或选项",
  "explanation": "简要说明"
}"""


def parse_json(text):
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        blocks = re.findall(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        for b in blocks:
            try:
                return json.loads(b.strip())
            except Exception:
                pass
    return {"model_answer_correct": None, "gold_answer_correct": None, "correct_answer": "", "explanation": "解析失败"}


def main():
    client = Hy3MathClient(
        api_base=os.environ["JUDGE_GPT_API_BASE"],
        api_key=os.environ["JUDGE_GPT_API_KEY"],
        model_name=os.environ.get("JUDGE_GPT_MODEL", "gpt-5.6-terra"),
    )
    with open("audit_inputs/l2_gold_verify.jsonl") as f:
        items = [json.loads(l) for l in f if l.strip()]
    out = open("audit_outputs/l2_gold_verify.jsonl", "w")
    for it in items:
        steps_text = "\n\n".join(
            f"步骤 {s.get('index', i+1)}：\n{s.get('text', '')}" for i, s in enumerate(it["steps"])
        )
        user = f"题目：\n{it['problem']}\n\n模型解题过程：\n{steps_text}\n\n模型最终答案：{it['model_answer']!r}\n数据集标准答案（gold）：{it['gold_answer']!r}\n\n请判断模型答案与 gold 哪个正确，输出 JSON。"
        res = client.chat_generate([[{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]], max_tokens=1024, temperature=0.2)
        audit = parse_json(res[0]["text"])
        it["audit"] = audit
        out.write(json.dumps(it, ensure_ascii=False) + "\n")
        print(it["problem_id"], "model_correct=", audit["model_answer_correct"], "gold_correct=", audit["gold_answer_correct"], "correct=", audit["correct_answer"])
    out.close()


if __name__ == "__main__":
    main()
