#!/usr/bin/env python3
"""
数据融合脚本：schema 对齐 → 去重 → 合并 → 冒烟测试
输入：扩展题集 + 4 个源文件
输出：problems_v2.jsonl
"""
import json
import re
import sys
from pathlib import Path
from difflib import SequenceMatcher
from collections import Counter

import pandas as pd

ROOT = Path(__file__).parent

# ---------- schema 模板 ----------

def make_record(**kwargs):
    """返回符合项目 schema 的记录。"""
    rec = {
        "id": kwargs["id"],
        "source": kwargs["source"],
        "level": kwargs.get("level", "L2"),
        "domain": kwargs.get("domain", "数学"),
        "problem_form": kwargs["problem_form"],
        "problem": kwargs["problem"],
        "answer": kwargs["answer"],
        "verification": {"method": kwargs["verification_method"]},
        "reference_steps": kwargs.get("reference_steps", []),
        "contamination_risk": kwargs.get("contamination_risk", "medium"),
        "cluster_id": kwargs.get("cluster_id", None),
        "is_adversarial": kwargs.get("is_adversarial", False),
    }
    return rec

# ---------- 归一化 / 查重 ----------

def norm(text: str) -> str:
    """去空格、转小写、去 LaTeX 反斜杠和大括号。"""
    return re.sub(r"[\s\\{}$]", "", str(text).lower())

def find_duplicates(new_records, existing_records, threshold=0.85):
    """返回 (new_id, existing_id, similarity) 的疑似重复列表。"""
    dups = []
    for n in new_records:
        n_norm = norm(n["problem"])
        if not n_norm:
            continue
        for e in existing_records:
            sim = SequenceMatcher(None, n_norm, norm(e["problem"])).ratio()
            if sim > threshold:
                dups.append((n["id"], e["id"], round(sim, 2)))
    return dups


def deduplicate_records(records, threshold_exact=1.0, threshold_report=0.85):
    """
    对 records 列表内部去重。
    - sim >= threshold_exact: 删除后出现的记录
    - threshold_report <= sim < threshold_exact: 报告疑似重复，保留
    返回 (去重后列表, 删除ID列表, 报告列表)。
    """
    removed_ids = []
    report = []
    keep = []
    # 为了稳定性按输入顺序处理；对每个记录与已保留记录比较
    for r in records:
        r_norm = norm(r["problem"])
        is_exact_dup = False
        for kept in keep:
            sim = SequenceMatcher(None, r_norm, norm(kept["problem"])).ratio()
            if sim >= threshold_exact:
                removed_ids.append((r["id"], kept["id"], round(sim, 2)))
                is_exact_dup = True
                break
            elif sim >= threshold_report:
                report.append((r["id"], kept["id"], round(sim, 2)))
        if not is_exact_dup:
            keep.append(r)
    return keep, removed_ids, report

# ---------- 解析器 ----------

def parse_gaokao_2026():
    """解析 2026 高考数学新课标卷 markdown。"""
    text = (ROOT / "2026高考数学新课标卷_试题与答案.md").read_text(encoding="utf-8")
    lines = text.splitlines()

    # 1) 题干区：按题号切分
    # 题型分段标记
    problem_blocks = {}
    current_no = None
    buffer = []

    # 简单状态机：遇到 **数字. 或 **数字.（ 开始新题
    # 只在前 90 行（题干区）扫描
    for line in lines[:90]:
        m = re.match(r"\*\*(\d+)\.(.*)", line)
        if m:
            if current_no is not None:
                problem_blocks[current_no] = "\n".join(buffer).strip()
            current_no = int(m.group(1))
            buffer = [m.group(2).strip()]
        elif current_no is not None:
            buffer.append(line)
    if current_no is not None:
        problem_blocks[current_no] = "\n".join(buffer).strip()

    # 答案映射
    single_choice_ans = {1:"B",2:"A",3:"C",4:"D",5:"D",6:"B",7:"B",8:"A"}
    multi_choice_ans = {9:"ACD",10:"BC",11:"BCD"}
    fill_ans = {
        12: "√66/6",
        13: "θ=3π/2; f(2π/3)=1",
        14: "(3/2)^(1/3)",
    }

    # 难度表
    level_map = {
        1:"L2",2:"L2",3:"L2",4:"L2",5:"L2",6:"L2",7:"L2",8:"L2",
        9:"L3",10:"L3",11:"L3",
        12:"L2",13:"L2",14:"L3",
        15:"L2",16:"L2",17:"L3",18:"L3",19:"L3",
    }
    # domain 映射（按题内容粗略）
    domain_map = {
        1:"统计",2:"向量",3:"集合",4:"导数",5:"圆锥曲线",6:"函数",7:"数列",8:"概率",
        9:"复数",10:"立体几何",11:"圆与直线",
        12:"圆锥曲线",13:"三角函数",14:"数列",
        15:"立体几何",16:"解三角形",17:"概率",18:"圆锥曲线",19:"函数与证明",
    }

    # 解答题答案：从参考答案区手动提取最终结论
    proof_ans = {
        15: "(1) 证明 DE // 平面 BCC₁B₁；(2) 直线 DE 到平面 BCC₁B₁ 的距离为 1",
        16: "(1) cos A = 1/3；(2) CE = 3√5",
        17: "(1) 分布列见参考；(2)(i) P(X>k)=(1-p)^k；(ii) 证明成立",
        18: "(1) x²/4 + y²/3 = 1；(2)(i) √5 x - 2y + √5 = 0；(ii) tan∠PQR 最小值 4√3",
        19: "(1) D(-1) = (0, 3/2)；(2)(3) 证明成立",
    }

    records = []
    for no in sorted(problem_blocks):
        text = problem_blocks[no]
        if no in single_choice_ans:
            problem_form = "choice"
            verification_method = "choice"
            answer = single_choice_ans[no]
        elif no in multi_choice_ans:
            problem_form = "choice"
            verification_method = "choice"
            answer = multi_choice_ans[no]
        elif no in fill_ans:
            problem_form = "open"
            verification_method = "numeric"
            answer = fill_ans[no]
        else:
            problem_form = "proof"
            verification_method = "manual_check"
            answer = proof_ans.get(no, "见参考答案")

        records.append(make_record(
            id=f"GK26-{no:03d}",
            source="2026-Gaokao",
            level=level_map.get(no, "L2"),
            domain=domain_map.get(no, "数学"),
            problem_form=problem_form,
            problem=text,
            answer=answer,
            verification_method=verification_method,
            contamination_risk="low",
        ))
    return records


def parse_agieval():
    """解析 AGIEval parquet（中文多选）。"""
    df = pd.read_parquet(ROOT / "test-00000-of-00001-31399d80475862e0.parquet")
    records = []
    for idx, row in df.iterrows():
        query = str(row["query"]).strip()
        choices = list(row["choices"])
        gold_arr = list(row["gold"]) if hasattr(row["gold"], "__iter__") and not isinstance(row["gold"], str) else [row["gold"]]
        gold_arr = [int(g) for g in gold_arr]
        # answer 取选项字母
        letters = [chr(ord("A") + i) for i in range(len(choices))]
        ans_letters = [letters[g] for g in gold_arr if 0 <= g < len(letters)]
        answer = "".join(ans_letters)
        # 题干中已含选项， cleaner 的 problem 用 query 即可
        records.append(make_record(
            id=f"AGV-{idx+1:03d}",
            source="AGIEval",
            level="L2",
            domain="数学",
            problem_form="choice",
            problem=query,
            answer=answer,
            verification_method="choice",
            contamination_risk="high",
        ))
    return records


def parse_minif2f():
    """解析 MiniF2F lean 文件，提取 theorem 语句。"""
    text = (ROOT / "test.lean").read_text(encoding="utf-8")
    # theorem 块：theorem <name> ... :=\nbegin ... end
    pattern = re.compile(r"theorem\s+(\S+)(.*?):=\s*\n\s*begin\s+(.*?)\nend", re.DOTALL)
    matches = pattern.findall(text)
    records = []
    for i, (name, decl, _body) in enumerate(matches, 1):
        # 定理陈述 = name + 变量/假设 + 结论
        decl_clean = " ".join(decl.split())
        problem_text = f"theorem {name}{decl_clean}"
        # 难度判断
        lower = name.lower()
        if "imo" in lower or "aime" in lower:
            level = "L4"
        elif "amc" in lower:
            level = "L3"
        else:
            level = "L3"
        records.append(make_record(
            id=f"MF2F-{i:03d}",
            source="MiniF2F",
            level=level,
            domain="数学/形式化证明",
            problem_form="proof",
            problem=problem_text,
            answer="形式化证明（Lean 定理）",
            verification_method="manual_check",
            contamination_risk="medium",
        ))
    return records


def parse_aimetrain():
    """解析 AIME/AMC train parquet。"""
    df = pd.read_parquet(ROOT / "train-00000-of-00001.parquet")
    records = []
    for idx, row in df.iterrows():
        records.append(make_record(
            id=f"AMC-TRAIN-{idx+1:03d}",
            source="AIME-AMC12/train",
            level="L4",
            domain="竞赛数学",
            problem_form="open",
            problem=str(row["problem"]).strip(),
            answer=str(row["answer"]).strip(),
            verification_method="numeric",
            contamination_risk="high",
        ))
    return records


def load_existing():
    """加载扩展题集作为已有数据。"""
    path = ROOT / "扩展题集_合并.jsonl"
    if not path.exists():
        return []
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def smoke_test(records):
    """字段完整性校验。"""
    required = {"id", "source", "level", "domain", "problem_form", "problem",
                "answer", "verification", "contamination_risk", "cluster_id", "is_adversarial"}
    errors = []
    method_counts = Counter()
    form_counts = Counter()
    for r in records:
        missing = required - set(r.keys())
        if missing:
            errors.append(f"{r.get('id','?')} 缺失字段: {missing}")
            continue
        if not r.get("answer"):
            errors.append(f"{r['id']} answer 为空")
        vm = r.get("verification", {}).get("method")
        if vm not in {"numeric", "symbolic_equivalence", "choice", "manual_check"}:
            errors.append(f"{r['id']} 非法 verification.method: {vm}")
        if r["problem_form"] == "proof" and vm != "manual_check":
            errors.append(f"{r['id']} proof 题 method 应为 manual_check，实际 {vm}")
        method_counts[vm] += 1
        form_counts[r["problem_form"]] += 1
    return errors, method_counts, form_counts


def main():
    print("=" * 50)
    print("1. Schema 对齐")
    print("=" * 50)
    gaokao = parse_gaokao_2026()
    agieval = parse_agieval()
    minif2f = parse_minif2f()
    aimetrain = parse_aimetrain()

    print(f"2026 高考: {len(gaokao)} 题")
    print(f"AGIEval:   {len(agieval)} 题")
    print(f"MiniF2F:   {len(minif2f)} 题")
    print(f"AIME train:{len(aimetrain)} 题")

    # 单独写出中间文件
    def write_jsonl(records, filename):
        with open(ROOT / filename, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    write_jsonl(gaokao, "gaokao2026_math.jsonl")
    write_jsonl(agieval, "agieval_new.jsonl")
    write_jsonl(minif2f, "minif2f_new.jsonl")
    write_jsonl(aimetrain, "aimetrain_new.jsonl")

    print("\n" + "=" * 50)
    print("2. 去重")
    print("=" * 50)
    existing = load_existing()
    print(f"已有扩展题集: {len(existing)} 题")

    all_new = gaokao + agieval + minif2f + aimetrain
    print(f"新题原始总数: {len(all_new)} 题")

    # 各批次内部去重（删除完全重复）
    gaokao, gk_removed, gk_report = deduplicate_records(gaokao, threshold_exact=0.97)
    agieval, ag_removed, ag_report = deduplicate_records(agieval, threshold_exact=0.97)
    minif2f, mf_removed, mf_report = deduplicate_records(minif2f, threshold_exact=0.97)
    aimetrain, am_removed, am_report = deduplicate_records(aimetrain, threshold_exact=0.97)

    removed_all = gk_removed + ag_removed + mf_removed + am_removed
    report_all = gk_report + ag_report + mf_report + am_report
    print(f"  自动删除完全重复: {len(removed_all)} 条")
    for a, b, s in removed_all[:10]:
        print(f"    {a} 与 {b} 相似度 {s}")
    if len(removed_all) > 10:
        print(f"    ... 还有 {len(removed_all)-10} 条")

    print(f"  疑似重复（保留，待人工审阅）: {len(report_all)} 对")
    for a, b, s in report_all[:10]:
        print(f"    {a} vs {b} 相似度 {s}")
    if len(report_all) > 10:
        print(f"    ... 还有 {len(report_all)-10} 对")

    all_new = gaokao + agieval + minif2f + aimetrain
    print(f"去重后新题总数: {len(all_new)} 题")

    # 与已有扩展题集交叉查重
    cross_dups = find_duplicates(all_new, existing, threshold=0.85)
    print(f"与扩展题集疑似重复: {len(cross_dups)} 对")
    for a, b, s in cross_dups[:10]:
        print(f"  {a} vs {b} 相似度 {s}")
    if len(cross_dups) > 10:
        print(f"  ... 还有 {len(cross_dups)-10} 对")

    # 合并
    merged = existing + all_new

    print("\n" + "=" * 50)
    print("3. 合并并写出 problems_v2.jsonl")
    print("=" * 50)
    write_jsonl(merged, "problems_v2.jsonl")
    print(f"合并后总数: {len(merged)} 题")

    print("\n" + "=" * 50)
    print("4. 冒烟测试")
    print("=" * 50)
    errors, method_counts, form_counts = smoke_test(merged)
    if errors:
        print(f"发现 {len(errors)} 处错误:")
        for e in errors[:20]:
            print("  -", e)
        if len(errors) > 20:
            print(f"  ... 还有 {len(errors)-20} 处")
        sys.exit(1)
    else:
        print("字段完整性校验通过。")
        print("verification.method 分布:", dict(method_counts))
        print("problem_form 分布:", dict(form_counts))
        print("level 分布:", Counter(r["level"] for r in merged))
        print("contamination_risk 分布:", Counter(r["contamination_risk"] for r in merged))


if __name__ == "__main__":
    main()
