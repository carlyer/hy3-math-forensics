"""使用 GPT-5.6-terra 对解题过程进行人工式复核审计.

通过环境变量读取裁判配置：
  JUDGE_GPT_API_BASE
  JUDGE_GPT_API_KEY
  JUDGE_GPT_MODEL

用法：
  python scripts/gpt_audit.py \
      --input audit_inputs/cbu_audit.jsonl \
      --output audit_outputs/cbu_audit.jsonl \
      --mode cbu
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.hy3_client import Hy3MathClient


SYSTEM_PROMPT = """你是一位严格的数学解题过程审计专家。你需要仔细阅读题目和模型给出的分步解答，判断推理过程是否严谨、成立，并定位首个不成立的步骤。

请按以下 JSON 格式输出（不要输出任何其他内容）：
{
  "process_valid": true/false,
  "first_error_step": null 或 整数（从 1 开始计数）,
  "error_type": "无错误" | "题意误读" | "概念理解错误" | "定理/公式误用" | "计算错误" | "条件遗漏" | "跳步推导" | "循环论证" | "幻觉/无中生有" | "单位/格式不符" | "其他/无法归类",
  "error_detail": "具体说明，若无错误则为空",
  "comment": "对整体过程的简要评价"
}

审查原则：
1. 步骤必须能从题目条件和前面已证结论逻辑推出；
2. 不允许凭空引入未给出的条件或结论；
3. 关键步骤缺失视为跳步；
4. 用结论证明结论视为循环论证；
5. 计算错误包括符号、数值、等式不成立；
6. 仅因表述啰嗦但逻辑正确应判为 valid；
7. 只输出 JSON，不要输出 markdown 代码块或其他解释。"""


CBU_SYSTEM_PROMPT = """你是一位严格的数学解题过程审计专家。本题的最终答案与标准答案一致，但你需要判断模型给出的推理过程是否真正支撑该结论，还是靠猜测、数值巧合、模板化背诵或隐含错误恰好得到正确答案。

请按以下 JSON 格式输出（不要输出任何其他内容）：
{
  "process_valid": true/false,
  "first_error_step": null 或 整数（从 1 开始计数）,
  "error_type": "无错误" | "题意误读" | "概念理解错误" | "定理/公式误用" | "计算错误" | "条件遗漏" | "跳步推导" | "循环论证" | "幻觉/无中生有" | "单位/格式不符" | "其他/无法归类",
  "error_detail": "具体说明，若无错误则为空",
  "comment": "对整体过程的简要评价"
}

审查原则：
1. 答案正确不等于过程正确；
2. 跳步严重、缺少关键推导、直接写出结果都算过程不成立；
3. 出现题目未给定的中间值或固定模板可能提示记忆/背诵；
4. 计算链条中任何等式不成立都算错误；
5. 仅输出 JSON。"""


SPOT_SYSTEM_PROMPT = """你是一位严格的数学解题过程审计专家。请对以下题目和模型解答进行抽检，判断过程是否严谨成立。

请按以下 JSON 格式输出（不要输出任何其他内容）：
{
  "process_valid": true/false,
  "first_error_step": null 或 整数（从 1 开始计数）,
  "error_type": "无错误" | "题意误读" | "概念理解错误" | "定理/公式误用" | "计算错误" | "条件遗漏" | "跳步推导" | "循环论证" | "幻觉/无中生有" | "单位/格式不符" | "其他/无法归类",
  "error_detail": "具体说明，若无错误则为空",
  "comment": "简要评价"
}

审查原则：
1. 逻辑正确但表述不完美的应判 valid；
2. 明显跳步、误用定理、计算错误、条件遗漏才判 invalid；
3. 仅输出 JSON。"""


def build_user_prompt(item: Dict, mode: str) -> str:
    problem = item.get("problem", "")
    steps = item.get("steps", [])
    gold = item.get("gold_answer", "")
    pred = item.get("final_answer", "")
    steps_text = "\n\n".join(
        f"步骤 {s.get('index', i+1)}：\n{s.get('text', '')}" for i, s in enumerate(steps)
    )
    extra = ""
    if mode == "cbu":
        extra = f"\n注意：模型给出的最终答案 {pred!r} 与标准答案 {gold!r} 一致，请重点审查推理是否真正成立。"
    elif mode in ("l2", "wrong"):
        extra = f"\n注意：模型给出的最终答案 {pred!r} 与标准答案 {gold!r} 不一致，请判断推理过程是否也存在错误，并定位首个错误步骤。"
    else:
        extra = f"\n标准答案：{gold!r}，模型答案：{pred!r}。"

    return f"题目：\n{problem}\n\n解题过程：\n{steps_text}{extra}\n\n请给出 JSON 审计结果。"


def parse_json_output(text: str) -> Dict[str, Any]:
    text = text.strip()
    # 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 尝试从 markdown 代码块提取
    blocks = re.findall(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    for block in blocks:
        try:
            return json.loads(block.strip())
        except json.JSONDecodeError:
            continue
    # 兜底
    return {
        "process_valid": None,
        "first_error_step": None,
        "error_type": "其他/无法归类",
        "error_detail": f"无法解析 JSON: {text[:200]}",
        "comment": "",
    }


def load_client() -> Hy3MathClient:
    base = os.environ.get("JUDGE_GPT_API_BASE")
    key = os.environ.get("JUDGE_GPT_API_KEY")
    model = os.environ.get("JUDGE_GPT_MODEL", "gpt-5.6-terra")
    if not base or not key:
        raise RuntimeError("请设置 JUDGE_GPT_API_BASE 与 JUDGE_GPT_API_KEY 环境变量")
    return Hy3MathClient(api_base=base, api_key=key, model_name=model)


def main():
    parser = argparse.ArgumentParser(description="GPT audit of solution processes")
    parser.add_argument("--input", required=True, help="输入 jsonl，每行一个待审计样本")
    parser.add_argument("--output", required=True, help="输出 jsonl")
    parser.add_argument(
        "--mode",
        required=True,
        choices=["cbu", "spot", "l2", "wrong"],
        help="审计模式：cbu=答案对过程可疑，spot=抽检正确样本，l2/wrong=答案错样本定位",
    )
    parser.add_argument("--batch_size", type=int, default=4)
    parser.add_argument("--resume", action="store_true", help="从已有输出中断点续审")
    args = parser.parse_args()

    system = {
        "cbu": CBU_SYSTEM_PROMPT,
        "spot": SPOT_SYSTEM_PROMPT,
        "l2": SYSTEM_PROMPT,
        "wrong": SYSTEM_PROMPT,
    }[args.mode]

    client = load_client()

    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    items = []
    with input_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))

    done_ids = set()
    if args.resume and output_path.exists():
        with output_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rec = json.loads(line)
                    done_ids.add(rec.get("problem_id"))
        print(f"已存在输出，跳过 {len(done_ids)} 条已审计样本")

    pending = [it for it in items if it.get("problem_id") not in done_ids]
    print(f"待审计：{len(pending)} / {len(items)}")

    out_f = output_path.open("a" if args.resume else "w", encoding="utf-8")

    batch_messages = []
    batch_items = []

    def flush_batch():
        nonlocal batch_messages, batch_items
        if not batch_messages:
            return
        try:
            results = client.chat_generate(batch_messages, max_tokens=1024, temperature=0.2)
        except Exception as e:
            print(f"批次调用失败：{e}")
            # 写入失败标记
            for item in batch_items:
                item["audit"] = {
                    "process_valid": None,
                    "first_error_step": None,
                    "error_type": "其他/无法归类",
                    "error_detail": f"API 调用失败: {e}",
                    "comment": "",
                }
                out_f.write(json.dumps(item, ensure_ascii=False) + "\n")
            out_f.flush()
            batch_messages = []
            batch_items = []
            return

        for item, res in zip(batch_items, results):
            audit = parse_json_output(res.get("text", ""))
            item["audit"] = audit
            out_f.write(json.dumps(item, ensure_ascii=False) + "\n")
        out_f.flush()
        print(f"完成 {len(batch_items)} 条")
        batch_messages = []
        batch_items = []

    for item in pending:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": build_user_prompt(item, args.mode)},
        ]
        batch_messages.append(messages)
        batch_items.append(item)
        if len(batch_messages) >= args.batch_size:
            flush_batch()
            time.sleep(0.2)

    flush_batch()
    out_f.close()
    print(f"审计完成，结果保存至：{output_path}")


if __name__ == "__main__":
    main()
