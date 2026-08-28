"""为合并题集标注数据污染风险等级.

风险等级依据：
- high: 常见预训练/微调数据集（GSM8K、Math23K、Ape210K、MATH、AGIEval）
- medium: 竞赛/考试题源（AMC、AIME、AMC/AIME-HF、OlympiadBench、Omni-MATH）
- low: 研究级新题、自构造题、扰动变体（FrontierMath-v2、perturbation）
"""

import json
from pathlib import Path
from typing import Dict


def risk_level(source: str) -> str:
    """根据题源返回污染风险等级."""
    s = (source or "").lower()
    # 先判断低风险，避免被 high 里的 "math" 误匹配
    low = ["frontiermath", "perturbation", "self-constructed"]
    if any(l in s for l in low):
        return "low"
    high = ["gsm8k", "math23k", "ape210k", "agieval"]
    if s == "math" or any(h in s for h in high):
        return "high"
    medium = ["amc", "aime", "olympiadbench", "omni-math"]
    if any(m in s for m in medium):
        return "medium"
    return "medium"


def main():
    input_path = Path(__file__).parent / "problems_merged.jsonl"
    output_path = Path(__file__).parent / "problems_merged.jsonl"

    records: list[Dict] = []
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rec = json.loads(line)
                rec["contamination_risk"] = risk_level(rec.get("source", ""))
                records.append(rec)

    with open(output_path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    counts = {"high": 0, "medium": 0, "low": 0}
    for rec in records:
        counts[rec["contamination_risk"]] += 1
    print(f"已标注 {len(records)} 题")
    print(f"high: {counts['high']}, medium: {counts['medium']}, low: {counts['low']}")


if __name__ == "__main__":
    main()
