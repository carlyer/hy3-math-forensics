"""清洗并转换 FrontierMath v2 样本到项目格式.

用法:
    python dataset/convert_frontiermath.py

输出:
    - dataset/frontiermath_v2_converted.jsonl
    - dataset/frontiermath_v2_convert_report.json
"""

import json
import re
from pathlib import Path
from typing import Dict, List

SRC_FILE = Path(__file__).parent / "frontiermath_v2_sample_12_problems.json"
OUTPUT_FILE = Path(__file__).parent / "frontiermath_v2_converted.jsonl"
REPORT_FILE = Path(__file__).parent / "frontiermath_v2_convert_report.json"


def infer_answer_type(answer: str) -> str:
    """根据答案推断类型."""
    if not answer or answer == "(待计算)":
        return "unknown"
    # 整数
    if re.match(r"^-?\d+$", answer):
        return "integer"
    # 浮点数
    if re.match(r"^-?\d+\.\d+$", answer):
        return "float"
    # 分数
    if "/" in answer and not re.search(r"[a-zA-Z]", answer):
        return "rational"
    return "expression"


def build_verification(answer_type: str) -> Dict:
    """构建校验配置."""
    if answer_type == "integer":
        return {"method": "exact_match"}
    if answer_type == "float":
        return {"method": "numeric_tolerance", "tolerance": 1e-4}
    if answer_type == "rational":
        return {"method": "symbolic_equivalence"}
    if answer_type == "expression":
        return {"method": "symbolic_equivalence"}
    return {"method": "manual_check"}


def extract_tags(subject: str, technique: str) -> List[str]:
    """从 subject 和 technique 提取标签."""
    text = f"{subject} {technique}".lower()
    tags = ["frontiermath", "research-level"]
    
    keywords = {
        "number theory": "number-theory",
        "algebraic geometry": "algebraic-geometry",
        "group theory": "group-theory",
        "combinatorics": "combinatorics",
        "analysis": "analysis",
        "linear algebra": "linear-algebra",
        "recurrence": "recurrence",
        "galois theory": "galois-theory",
        "finite fields": "finite-fields",
        "banach spaces": "functional-analysis",
        "elliptic curves": "elliptic-curves",
        "modular forms": "modular-forms",
        "coxeter groups": "coxeter-groups",
        "prime number theorem": "prime-number-theorem",
        "riemann hypothesis": "riemann-hypothesis",
        "inclusion-exclusion": "inclusion-exclusion",
        "linearity of expectation": "linearity-of-expectation",
    }
    
    for kw, tag in keywords.items():
        if kw in text:
            tags.append(tag)
    
    return sorted(set(tags))


def tier_to_level(tier: str) -> str:
    """FrontierMath tier 映射到项目 level."""
    # FrontierMath 全部为难/研究级，统一归为 L4
    return "L4"


def convert():
    with open(SRC_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    problems = data.get("problems", [])
    converted = []
    
    for p in problems:
        raw_answer = p.get("answer", "")
        has_gold = raw_answer and raw_answer != "(待计算)"
        answer = raw_answer if has_gold else None
        answer_type = infer_answer_type(answer) if has_gold else "unknown"
        verification = build_verification(answer_type) if has_gold else {"method": "manual_check"}
        
        record = {
            "id": f"FM-v2-{p['id']:03d}",
            "level": tier_to_level(p["tier"]),
            "source": "FrontierMath-v2",
            "construction": f"从 FrontierMath v2 公开样本第 {p['id']} 题转换，原始 tier={p['tier']}",
            "difficulty_rationale": f"FrontierMath {p['tier']}，难度标注为 {p.get('difficulty', 'Unknown')}，属于研究级数学问题",
            "problem": p["problem"],
            "answer": answer,
            "answer_type": answer_type if has_gold else None,
            "verification": verification,
            "tags": extract_tags(p.get("subject", ""), p.get("technique", "")),
            "has_gold_answer": has_gold,
            "frontiermath_tier": p.get("tier"),
            "frontiermath_difficulty": p.get("difficulty"),
            "frontiermath_subject": p.get("subject"),
            "frontiermath_technique": p.get("technique"),
            "msc_classification": p.get("msc_classification"),
        }
        converted.append(record)
    
    OUTPUT_FILE.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in converted) + "\n",
        encoding="utf-8",
    )
    
    report = {
        "total": len(converted),
        "has_gold_answer": sum(1 for r in converted if r["has_gold_answer"]),
        "no_gold_answer": sum(1 for r in converted if not r["has_gold_answer"]),
        "by_tier": {},
        "records": [{"id": r["id"], "has_gold_answer": r["has_gold_answer"], "answer": r["answer"]} for r in converted],
    }
    
    for r in converted:
        tier = r["frontiermath_tier"]
        report["by_tier"][tier] = report["by_tier"].get(tier, 0) + 1
    
    REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    
    print(f"转换完成: {OUTPUT_FILE}")
    print(f"  总计: {report['total']}")
    print(f"  有标准答案: {report['has_gold_answer']}")
    print(f"  无标准答案: {report['no_gold_answer']}")
    print(f"  按 tier 分布: {report['by_tier']}")


if __name__ == "__main__":
    convert()
