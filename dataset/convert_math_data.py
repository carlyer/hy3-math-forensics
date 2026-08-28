"""将 math-data 外部数据集转换为项目统一题库格式.

用法:
    python dataset/convert_math_data.py

输出:
    - dataset/problems_converted.jsonl: 转换后的统一题库
    - dataset/convert_report.json: 转换统计与问题报告
"""

import json
import re
from pathlib import Path
from collections import defaultdict, Counter

BASE_DIR = Path(__file__).parent
MATH_DATA_DIR = BASE_DIR / "math-data" / "math-data"
OUTPUT_FILE = BASE_DIR / "problems_converted.jsonl"
REPORT_FILE = BASE_DIR / "convert_report.json"

# 数据源配置: (相对路径, 目标层级, 来源描述, 构造说明, 难度说明, 默认标签)
SOURCE_CONFIG = [
    (
        "L1_Basic/raw/gsm8k_sample.jsonl",
        "L1",
        "GSM8K",
        "从 openai/gsm8k 训练集按固定种子随机抽取 18 题",
        "小学应用题，只需四则运算或简单方程",
        ["arithmetic", "word-problem"],
    ),
    (
        "L1_Basic/raw/math23k_sample.jsonl",
        "L1",
        "Math23K",
        "从 Math23K 中文小学数学题中随机抽取 12 题",
        "中文小学算术应用题，直接列式计算",
        ["arithmetic", "word-problem", "chinese"],
    ),
    (
        "L2_Medium/raw/math_level2_3.jsonl",
        "L2",
        "MATH",
        "从 Hendrycks MATH 数据集 Level 2-3 抽取 20 题",
        "初高中竞赛题，涉及代数、几何、数列、组合",
        ["algebra", "geometry", "competition"],
    ),
    (
        "L2_Medium/raw/agieval_sample.jsonl",
        "L2",
        "AGIEval",
        "从 AGIEval 高考/SAT 风格选择题中抽取 15 题",
        "标准化选择题，考察初高中数学概念与计算",
        ["algebra", "choice", "standardized-test"],
    ),
    (
        "L3_Hard/raw/math_level4_5.jsonl",
        "L3",
        "MATH",
        "从 Hendrycks MATH 数据集 Level 4-5 抽取 12 题",
        "高中竞赛到 AIME 入门级难度",
        ["algebra", "geometry", "competition"],
    ),
    (
        "L3_Hard/raw/olympiadbench_sample.jsonl",
        "L3",
        "OlympiadBench",
        "从 OlympiadBench 文本子集中抽取 15 题",
        "奥林匹克数学入门题，涉及数论、组合、几何",
        ["number-theory", "combinatorics", "olympiad"],
    ),
    (
        "L3_Hard/raw/omnimath_l3_sample.jsonl",
        "L3",
        "Omni-MATH",
        "从 Omni-MATH 数据集中抽取 10 题",
        "多学科竞赛级问题",
        ["algebra", "combinatorics", "competition"],
    ),
    (
        "L3_Hard/raw/amc12_hard_problems_hy3_test.jsonl",
        "L3",
        "AMC12",
        "用户提供 AMC 12 后段难题（#23-25 级别）10 题",
        "AMC 12 高难度选择题/填空题",
        ["amc", "competition", "geometry", "number-theory"],
    ),
    (
        "L4_Expert/raw/AIME1.jsonl",
        "L4",
        "AIME",
        "用户提供 AIME 2015-2025 真题 25 题",
        "AIME 级别难题，答案为 0-999 整数",
        ["aime", "competition", "number-theory", "combinatorics"],
    ),
    (
        "L4_Expert/raw/aime_amc_sample.jsonl",
        "L4",
        "AMC/AIME-HF",
        "从 AI-MO/aimo-validation-amc 与 kaggle-aimo/amc_filtered 抽取 10 题",
        "AMC/AIME 风格竞赛题",
        ["amc", "aime", "competition"],
    ),
]

# 已知 problem 不完整的记录 ID，需要丢弃
DROP_IDS = {
    "2010_AMC_10B_Problems/Problem_25",  # 条件缺失
}


def clean_answer(answer):
    """清洗答案文本."""
    if answer is None:
        return ""
    s = str(answer).strip()
    # 去除 LaTeX display math 包装
    s = re.sub(r"^\\\[\s*|\s*\\\]$", "", s)
    s = re.sub(r"^\\\(\s*|\s*\\\)$", "", s)
    # 去除 $ 包装
    s = s.strip("$").strip()
    # 去除 "Answer:" 等前缀
    s = re.sub(r"(?i)^answer\s*[:=]\s*", "", s)
    return s.strip()


def clean_solution(sol):
    """统一 solution 为字符串或 null."""
    if sol is None or sol == "":
        return None
    if isinstance(sol, list):
        # 列表类型直接拼接
        return "\n\n".join(str(x).strip() for x in sol if str(x).strip())
    return str(sol).strip()


def infer_answer_type(answer):
    """根据答案文本推断答案类型与校验方式."""
    a = answer.strip()
    if not a:
        return "unknown", {"method": "exact_match"}

    # 选择题
    if re.match(r"^\([A-E]\)", a):
        return "choice", {"method": "choice_match"}

    # 列表 / 元组格式，如 [0]、(4,1,4,0)
    if re.match(r"^\[[^\]]+\]$", a) or re.match(r"^\([^)]+\)$", a):
        return "list", {"method": "list_match", "ordered": True}

    # 纯整数（含负数）
    if re.match(r"^-?\d+$", a):
        return "integer", {"method": "exact_match"}

    # 明显分数形式 x/y
    if re.match(r"^-?\d+\s*/\s*\d+$", a):
        return "rational", {"method": "symbolic_equivalence"}

    # LaTeX 分数
    if r"\frac" in a:
        return "rational", {"method": "symbolic_equivalence"}

    # 小数：若数值上为整数则按整数处理
    if re.match(r"^-?\d+\.\d+$", a):
        try:
            if float(a).is_integer():
                return "integer", {"method": "exact_match"}
        except ValueError:
            pass
        return "float", {"method": "numeric_tolerance", "tolerance": 1e-4}

    # 含根号、pi 等符号的表达式
    if any(sym in a for sym in [r"\sqrt", r"\pi", "^", "sqrt", "pi"]):
        return "expression", {"method": "symbolic_equivalence"}

    # 列表 / 元组
    if "," in a and not re.search(r"[a-zA-Z]", a):
        return "list", {"method": "list_match", "ordered": True}

    # 默认表达式级匹配
    return "expression", {"method": "symbolic_equivalence"}


def infer_tags(problem, answer, base_tags):
    """基于题目文本补充标签."""
    tags = set(base_tags)
    p_lower = problem.lower()
    if any(k in p_lower for k in ["triangle", "angle", "circle", "polygon", "side", "area", "\triangle", "\angle"]):
        tags.add("geometry")
    if any(k in p_lower for k in ["prime", "mod", "divisible", "gcd", "remainder", "integer"]):
        tags.add("number-theory")
    if any(k in p_lower for k in ["subset", "arrangement", "choose", "permutation", "combination"]):
        tags.add("combinatorics")
    if any(k in p_lower for k in ["probability", "random", "expected"]):
        tags.add("probability")
    if any(k in p_lower for k in ["function", "polynomial", "equation", "solve"]):
        tags.add("algebra")
    if re.match(r"^\([A-E]\)", answer):
        tags.add("choice")
    return sorted(tags)


def load_records():
    """加载并清洗所有配置的数据源."""
    converted = []
    dropped = []
    source_stats = defaultdict(lambda: {"total": 0, "kept": 0, "dropped": 0})

    for rel_path, level, source, construction, difficulty, base_tags in SOURCE_CONFIG:
        file_path = MATH_DATA_DIR / rel_path
        if not file_path.exists():
            print(f"[WARN] 文件不存在: {file_path}")
            continue

        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError as e:
                    dropped.append({"file": rel_path, "reason": f"JSON error: {e}"})
                    source_stats[rel_path]["total"] += 1
                    source_stats[rel_path]["dropped"] += 1
                    continue

                source_stats[rel_path]["total"] += 1
                original_id = rec.get("id", "")

                # 丢弃已知不完整记录
                if original_id in DROP_IDS:
                    dropped.append({"file": rel_path, "id": original_id, "reason": "已知 problem 不完整"})
                    source_stats[rel_path]["dropped"] += 1
                    continue

                problem = str(rec.get("problem", "")).strip()
                answer_raw = rec.get("answer")
                answer = clean_answer(answer_raw)
                solution = clean_solution(rec.get("solution"))

                # 过滤空 problem / 空 answer
                if not problem or not answer:
                    reason = f"problem空={not problem}, answer空={not answer}"
                    dropped.append({"file": rel_path, "id": original_id, "reason": reason})
                    source_stats[rel_path]["dropped"] += 1
                    continue

                # 过滤过短题目（通常也是残缺的）
                if len(problem) < 20:
                    dropped.append({"file": rel_path, "id": original_id, "reason": f"problem 过短 ({len(problem)} chars)"})
                    source_stats[rel_path]["dropped"] += 1
                    continue

                answer_type, verification = infer_answer_type(answer)
                tags = infer_tags(problem, answer, base_tags)

                converted.append({
                    "id": None,  # 后续统一编号
                    "level": level,
                    "source": source,
                    "construction": construction,
                    "difficulty_rationale": difficulty,
                    "problem": problem,
                    "answer": answer,
                    "answer_type": answer_type,
                    "verification": verification,
                    "solution": solution,
                    "tags": tags,
                    "original_id": original_id,
                    "original_file": rel_path,
                })
                source_stats[rel_path]["kept"] += 1

    return converted, dropped, source_stats


def deduplicate(records):
    """按 problem 文本去重，保留第一个."""
    seen = set()
    unique = []
    duplicates = []
    for r in records:
        key = re.sub(r"\s+", " ", r["problem"].lower())
        if key in seen:
            duplicates.append({"id": r["original_id"], "file": r["original_file"], "problem": r["problem"][:100]})
            continue
        seen.add(key)
        unique.append(r)
    return unique, duplicates


def assign_ids(records):
    """按层级分配 L1-001 格式 ID."""
    counters = defaultdict(int)
    for r in records:
        counters[r["level"]] += 1
        r["id"] = f"{r['level']}-{counters[r['level']]:03d}"
    return records


def write_output(records):
    """写入最终 JSONL."""
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for r in records:
            out = {k: v for k, v in r.items() if k not in ("original_id", "original_file")}
            f.write(json.dumps(out, ensure_ascii=False) + "\n")


def main():
    print("[1/4] 加载并清洗外部数据源...")
    records, dropped, source_stats = load_records()
    print(f"      加载 {len(records) + len(dropped)} 条，保留 {len(records)} 条，丢弃 {len(dropped)} 条")

    print("[2/4] 按 problem 文本去重...")
    records, duplicates = deduplicate(records)
    print(f"      去重后保留 {len(records)} 条，重复 {len(duplicates)} 条")

    print("[3/4] 分配统一 ID...")
    records = assign_ids(records)

    print("[4/4] 写入输出文件...")
    write_output(records)

    # 生成统计
    level_counts = Counter(r["level"] for r in records)
    type_counts = Counter(r["answer_type"] for r in records)

    report = {
        "total_kept": len(records),
        "total_dropped": len(dropped),
        "by_level": dict(sorted(level_counts.items())),
        "by_answer_type": dict(type_counts),
        "by_source": dict(sorted(
            ((rel_path, {"total": s["total"], "kept": s["kept"], "dropped": s["dropped"]})
             for rel_path, s in source_stats.items()),
            key=lambda x: x[0],
        )),
        "dropped_samples": dropped[:50],
        "duplicate_samples": duplicates[:50],
    }

    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n转换完成:")
    print(f"  输出文件: {OUTPUT_FILE}")
    print(f"  报告文件: {REPORT_FILE}")
    print(f"  总计可用: {len(records)} 题")
    print(f"  分层统计: {dict(sorted(level_counts.items()))}")
    print(f"  答案类型: {dict(type_counts)}")


if __name__ == "__main__":
    main()
