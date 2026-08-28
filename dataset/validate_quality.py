"""对转换后的题库做数据质量校验，生成 quality_report.json.

用法:
    python dataset/validate_quality.py
"""

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from answer_checker import check_answer, AnswerCheckError

BASE_DIR = Path(__file__).parent
DATA_FILE = BASE_DIR / "problems_converted.jsonl"
REPORT_FILE = BASE_DIR / "quality_report.json"

# 明显的不完整结尾标记（problem 以这些词结尾时很可能被截断）
INCOMPLETE_ENDINGS = [
    "such that",
    "find",
    "compute",
    "calculate",
    "determine",
    "where",
    "if",
    "given",
    "prove",
    "show",
]

# 被认为是“纯 LaTeX 命令”的正则：以反斜杠开头，主要由反斜杠/字母/空格组成
PURE_LATEX_RE = re.compile(r"^\\[a-zA-Z]+(\\[a-zA-Z]+|\s)*$")


def load_records(path: Path):
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def is_problem_incomplete(problem: str) -> tuple[bool, str]:
    """检查 problem 是否明显过短或不完整。"""
    p = problem.strip()
    if len(p) < 30:
        return True, f"problem 过短 ({len(p)} 字符)"
    lower = p.lower().rstrip(".:")
    for marker in INCOMPLETE_ENDINGS:
        if lower.endswith(marker):
            return True, f"problem 以不完整标记结尾: '{marker}'"
    return False, ""


def is_answer_anomaly(answer: str) -> tuple[bool, str]:
    """检查 answer 是否为空或存在明显异常。"""
    a = answer.strip()
    if not a:
        return True, "answer 为空"

    if PURE_LATEX_RE.match(a):
        return True, "answer 为纯 LaTeX 命令"

    # 未闭合括号检查（只考虑 {}, [], ()）
    counts = {c: a.count(c) for c in "{}[]()"}
    if counts["{"] != counts["}"]:
        return True, "answer 花括号未闭合"
    if counts["["] != counts["]"]:
        return True, "answer 方括号未闭合"
    if counts["("] != counts[")"]:
        return True, "answer 圆括号未闭合"

    return False, ""


def is_integer_answer(answer: str) -> bool:
    return bool(re.fullmatch(r"-?\d+", answer.strip()))


def is_choice_answer(answer: str) -> bool:
    return bool(re.match(r"^\([A-E]\)", answer.strip()))


def problem_has_options(problem: str) -> bool:
    """判断 problem 文本中是否包含常见选项标记。"""
    p = problem
    # (A) / (B) / (C) / (D) / (E)
    if re.search(r"\([A-E]\)", p):
        return True
    # A. B. C. D. E. 作为行首或空格后
    if re.search(r"(^|\s)[A-E]\.\s", p):
        return True
    # Option A / choice A 等
    if re.search(r"(?i)option\s+[A-E]", p):
        return True
    # \\textbf{(A)} 等 LaTeX 选项格式
    if re.search(r"\\\\textbf\{\([A-E]\)\}", p):
        return True
    return False


def is_mathematical_integer(answer: str) -> bool:
    """判断 answer 在数值上是否为整数（如 47.0, 4.00 等）。"""
    a = answer.strip()
    try:
        v = float(a)
        return v.is_integer()
    except (ValueError, TypeError):
        return False


def check_type_inference(rec) -> tuple[bool, str]:
    """检查 answer_type 推断是否合理。"""
    at = rec.get("answer_type", "unknown")
    ans = str(rec.get("answer", "")).strip()

    if at == "integer" and not is_integer_answer(ans):
        return True, f"answer_type=integer 但 answer 不是整数: {ans!r}"

    if at == "choice" and not problem_has_options(rec.get("problem", "")):
        return True, f"answer_type=choice 但 problem 未检测到选项"

    # 如果 answer 明显是整数但被标成其它类型（expression 等），需要复核
    if at != "integer" and is_integer_answer(ans):
        return True, f"answer 明显为整数但 answer_type={at}"

    # float 类型但数值上为整数（常见于 AIME/AMC 答案被错误保留小数）
    if at == "float" and is_mathematical_integer(ans):
        return True, f"answer_type=float 但 answer 数值上为整数: {ans!r}"

    # 如果 answer 明显是选择题但被标成其它类型
    if at != "choice" and is_choice_answer(ans):
        return True, f"answer 明显为选择题但 answer_type={at}"

    return False, ""


def self_check_answer(rec) -> tuple[bool, str]:
    """使用 answer_checker 自校验 gold=answer, pred=answer."""
    try:
        ok, detail = check_answer(
            pred=rec["answer"],
            gold=rec["answer"],
            verification=rec.get("verification", {"method": "exact_match"}),
        )
        return ok, detail or ""
    except AnswerCheckError as e:
        return False, f"checker 不支持: {e}"
    except Exception as e:
        return False, f"checker 异常: {type(e).__name__}: {e}"


def main():
    print(f"[1/4] 读取 {DATA_FILE.name}...")
    records = load_records(DATA_FILE)
    total = len(records)
    print(f"      共 {total} 题")

    print("[2/4] 统计分布...")
    by_level = Counter(r["level"] for r in records)
    by_source = Counter(r["source"] for r in records)
    by_type = Counter(r["answer_type"] for r in records)

    print("[3/4] 逐题质检与自校验...")
    suspicious = []
    self_failures = []

    for rec in records:
        reasons = []

        # problem 完整性
        bad, reason = is_problem_incomplete(rec.get("problem", ""))
        if bad:
            reasons.append(reason)

        # answer 异常
        bad, reason = is_answer_anomaly(str(rec.get("answer", "")))
        if bad:
            reasons.append(reason)

        # 类型推断
        bad, reason = check_type_inference(rec)
        if bad:
            reasons.append(reason)

        # answer_checker 自校验
        ok, detail = self_check_answer(rec)
        if not ok:
            self_failures.append({
                "id": rec.get("id"),
                "source": rec.get("source"),
                "answer": rec.get("answer"),
                "answer_type": rec.get("answer_type"),
                "verification": rec.get("verification"),
                "detail": detail,
            })
            reasons.append(f"checker 自校验失败: {detail}")

        if reasons:
            suspicious.append({
                "id": rec.get("id"),
                "source": rec.get("source"),
                "level": rec.get("level"),
                "answer_type": rec.get("answer_type"),
                "problem_preview": rec.get("problem", "")[:120],
                "answer_preview": str(rec.get("answer", ""))[:80],
                "reasons": reasons,
            })

    print("[4/4] 整理示例...")
    type_examples = defaultdict(list)
    for rec in records:
        at = rec.get("answer_type", "unknown")
        if len(type_examples[at]) < 3:
            type_examples[at].append({
                "id": rec.get("id"),
                "source": rec.get("source"),
                "answer": rec.get("answer"),
                "verification": rec.get("verification"),
            })

    report = {
        "total": total,
        "by_level": dict(sorted(by_level.items())),
        "by_source": dict(sorted(by_source.items())),
        "by_answer_type": dict(sorted(by_type.items())),
        "self_check_failures": {
            "count": len(self_failures),
            "samples": self_failures[:20],
        },
        "suspicious_records": {
            "count": len(suspicious),
            "records": suspicious,
        },
        "answer_type_examples": dict(sorted(type_examples.items())),
    }

    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n质量报告已写入: {REPORT_FILE}")
    print(f"  总题数: {total}")
    print(f"  分层统计: {dict(sorted(by_level.items()))}")
    print(f"  来源统计: {dict(sorted(by_source.items()))}")
    print(f"  答案类型: {dict(sorted(by_type.items()))}")
    print(f"  自校验失败: {len(self_failures)} 题")
    print(f"  可疑记录: {len(suspicious)} 题")


if __name__ == "__main__":
    main()
