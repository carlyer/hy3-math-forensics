#!/usr/bin/env python3
"""
合并 386 题扩展集与 32 条扰动变体，生成带多维度标签的 418 题主实验集。

输出：
- dataset/problems_merged_full.jsonl
- dataset/problems_merged_full_stats.md
"""

import json
import os
import re
from collections import Counter, defaultdict

DATASET_DIR = os.path.join(os.path.dirname(__file__), "..", "dataset")


def load_jsonl(path):
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def save_jsonl(path, records):
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def infer_problem_form(r):
    """根据 source / verification / problem 推断 problem_form。"""
    if r.get("problem_form") and r.get("problem_form") != "unknown":
        return r["problem_form"]

    src = r.get("source", "")
    vm = r.get("verification", {}).get("method", "")
    prob = r.get("problem", "")

    if "MiniF2F" in src or "ProofNet" in src or "Mathlib" in src:
        return "proof"
    if vm == "choice_match" or "(A)" in prob or "(B)" in prob or "(C)" in prob or "(D)" in prob:
        return "choice"
    if vm == "manual_check" and ("证明" in prob or "prove" in prob.lower() or "theorem" in prob.lower()):
        return "proof"
    if "证明" in prob or "prove" in prob.lower() or "theorem" in prob.lower():
        return "proof"
    return "open"


def classify_verification_method(r):
    """按验证方式分类。"""
    src = r.get("source", "")
    vm = r.get("verification", {}).get("method", "")
    prob = r.get("problem", "")

    # 形式化证明：必须来自形式数学数据集，或题目明显是 Lean/Coq 定理声明
    if (
        "MiniF2F" in src
        or "ProofNet" in src
        or "Mathlib" in src
        or "Lean" in src
        or "Coq" in src
        or re.search(r"^\s*theorem\s+\w+\s*\(", prob, re.IGNORECASE)
    ):
        return "formal_proof"

    if vm == "manual_check":
        return "human_evaluation"

    if vm in ("exact_match", "choice_match", "symbolic_equivalence", "numeric_tolerance", "list_match"):
        return "verifiable_answer"

    return "human_evaluation"


def classify_problem_type(r):
    """按问题类型分类。"""
    src = r.get("source", "")

    # 形式数学最高优先级
    if any(s in src for s in ["MiniF2F", "ProofNet", "Mathlib", "Lean", "Coq"]):
        return "formal_math"

    # 竞赛数学
    if any(s in src for s in [
        "AIME", "AMC", "IMO", "Olympiad", "Omni-MATH", "Putnam",
        "FrontierMath", "MATH/Level 4", "MATH/Level 5", "MATH/Level 3"
    ]):
        return "competition_math"

    # 高等数学
    if any(s in src for s in ["MMLU-Pro", "College", "Calculus", "Linear Algebra", "Probability"]):
        return "college_math"

    # 初等数学兜底
    return "elementary_math"


def classify_evaluation_goals(r):
    """按评测目标打标签（可多选）。"""
    goals = []
    vmt = r.get("verification_method_tag", "")
    ptype = r.get("problem_type_tag", "")
    level = r.get("level", "")
    variant = r.get("variant_type", "original")

    if vmt == "formal_proof":
        goals.append("proof_completion_rate")
    if vmt == "verifiable_answer":
        goals.append("problem_solving_accuracy")
    if variant != "original":
        goals.append("generalization")
        goals.append("robustness")
    if level in ("L3", "L4") or ptype == "formal_math":
        goals.append("reasoning_depth")

    return list(set(goals))


def build_full_dataset():
    ext = load_jsonl(os.path.join(DATASET_DIR, "problems_merged_v2.jsonl"))
    perturbed = load_jsonl(os.path.join(DATASET_DIR, "problems_perturbed.jsonl"))

    # 给 386 题加 group 标签和推断 form
    # 386 中 158 道为原题（146 道 L1-L4 ID + 12 道 FM-v2 ID），228 道为 EXT 新题
    for r in ext:
        if r["id"].startswith("EXT-"):
            r["dataset_group"] = "ext_228"
        else:
            r["dataset_group"] = "original_158"
        r["problem_form"] = infer_problem_form(r)
        r["variant_type"] = "original"
        r["source_id"] = r["id"]
        if not r.get("cluster_id"):
            r["cluster_id"] = None

    # 给 32 条扰动变体规范化
    for r in perturbed:
        oid = r.get("original_id", "")
        ptype = r.get("perturbation_type", "")
        # 统一新 ID，避免和 386 中同名原题混淆
        new_id = f"PERT-{oid}-{ptype.replace('_rewrite', '').replace('_noise', '')}"
        r["id"] = new_id
        r["dataset_group"] = "perturbation_32"
        r["variant_type"] = ptype
        r["source_id"] = oid
        r["cluster_id"] = f"perturb-{oid}"
        r["problem_form"] = infer_problem_form(r)
        # 扰动变体的污染风险应标为 low（因为是改造后的新题）
        r["contamination_risk"] = "low"
        if "tags" not in r:
            r["tags"] = []
        r["tags"] = list(set(r["tags"] + ["perturbation", ptype]))

    # 合并
    all_records = ext + perturbed

    # 打分类标签
    for r in all_records:
        r["verification_method_tag"] = classify_verification_method(r)
        r["problem_type_tag"] = classify_problem_type(r)
        r["evaluation_goal_tags"] = classify_evaluation_goals(r)

    return all_records


def generate_stats(records):
    lines = []
    lines.append("# 418 题主实验集统计\n")
    lines.append(f"总题数：{len(records)}\n")

    # 1. 按难度
    lines.append("\n## 1. 按 L1-L4 难度分布\n")
    lines.append("| 难度 | 题数 | 占比 |\n|---|---|---|\n")
    for lv in ["L1", "L2", "L3", "L4"]:
        cnt = sum(1 for r in records if r["level"] == lv)
        lines.append(f"| {lv} | {cnt} | {cnt/len(records)*100:.2f}% |\n")

    # 2. 按验证方式
    lines.append("\n## 2. 按验证方式分类\n")
    lines.append("| 类别 | 题数 | 占比 | 说明 |\n|---|---|---|---|\n")
    desc = {
        "formal_proof": "形式化证明，需 Lean/Coq 验证",
        "verifiable_answer": "可计算答案，自动验证",
        "human_evaluation": "需人工/LLM 判分",
    }
    for tag in ["formal_proof", "verifiable_answer", "human_evaluation"]:
        cnt = sum(1 for r in records if r["verification_method_tag"] == tag)
        lines.append(f"| {tag} | {cnt} | {cnt/len(records)*100:.2f}% | {desc[tag]} |\n")

    # 3. 按问题类型
    lines.append("\n## 3. 按问题类型分类\n")
    lines.append("| 类别 | 题数 | 占比 |\n|---|---|---|\n")
    for tag in ["elementary_math", "college_math", "competition_math", "formal_math"]:
        cnt = sum(1 for r in records if r["problem_type_tag"] == tag)
        lines.append(f"| {tag} | {cnt} | {cnt/len(records)*100:.2f}% |\n")

    # 4. 按评测目标
    lines.append("\n## 4. 按评测目标分类（可多选）\n")
    lines.append("| 目标 | 题数 | 占比 |\n|---|---|---|\n")
    all_goals = ["problem_solving_accuracy", "proof_completion_rate", "generalization", "reasoning_depth", "robustness"]
    for tag in all_goals:
        cnt = sum(1 for r in records if tag in r["evaluation_goal_tags"])
        lines.append(f"| {tag} | {cnt} | {cnt/len(records)*100:.2f}% |\n")

    # 5. 按数据集来源分组
    lines.append("\n## 5. 按数据集来源分组\n")
    lines.append("| 分组 | 题数 | 占比 | 说明 |\n|---|---|---|---|\n")
    group_desc = {
        "original_158": "原 158 题（含 146 道 L1-L4 + 12 道 FM-v2）",
        "ext_228": "386 扩展集中新增题",
        "perturbation_32": "16 原题 × 2 种扰动变体",
    }
    for grp in ["original_158", "ext_228", "perturbation_32"]:
        cnt = sum(1 for r in records if r["dataset_group"] == grp)
        lines.append(f"| {grp} | {cnt} | {cnt/len(records)*100:.2f}% | {group_desc[grp]} |\n")

    # 6. 按污染风险
    lines.append("\n## 6. 按污染风险分布\n")
    lines.append("| 风险 | 题数 | 占比 |\n|---|---|---|\n")
    for risk in ["high", "medium", "low"]:
        cnt = sum(1 for r in records if r.get("contamination_risk") == risk)
        lines.append(f"| {risk} | {cnt} | {cnt/len(records)*100:.2f}% |\n")

    # 7. 交叉：难度 × 问题类型
    lines.append("\n## 7. 难度 × 问题类型 交叉分布\n")
    lines.append("| 难度 | elementary_math | college_math | competition_math | formal_math |\n|---|---|---|---|---|\n")
    for lv in ["L1", "L2", "L3", "L4"]:
        row = [lv]
        for tag in ["elementary_math", "college_math", "competition_math", "formal_math"]:
            cnt = sum(1 for r in records if r["level"] == lv and r["problem_type_tag"] == tag)
            row.append(str(cnt))
        lines.append("| " + " | ".join(row) + " |\n")

    # 8. 扰动簇统计
    lines.append("\n## 8. 扰动/变体簇统计\n")
    clusters = defaultdict(list)
    for r in records:
        cid = r.get("cluster_id")
        if cid:
            clusters[cid].append(r)
    lines.append(f"总簇数：{len(clusters)}\n")
    lines.append(f"参与簇的题数：{sum(len(v) for v in clusters.values())}\n")
    lines.append("\n| 簇类型 | 簇数 | 题数 |\n|---|---|---|\n")
    gsm_clusters = {k: v for k, v in clusters.items() if k.startswith("gsm8k")}
    pert_clusters = {k: v for k, v in clusters.items() if k.startswith("perturb-")}
    lines.append(f"| GSM-Plus 变体簇 | {len(gsm_clusters)} | {sum(len(v) for v in gsm_clusters.values())} |\n")
    lines.append(f"| surface_rewrite/add_noise 簇 | {len(pert_clusters)} | {sum(len(v) for v in pert_clusters.values())} |\n")

    return "".join(lines)


def main():
    records = build_full_dataset()
    out_path = os.path.join(DATASET_DIR, "problems_merged_full.jsonl")
    save_jsonl(out_path, records)
    print(f"已生成：{out_path}，共 {len(records)} 题")

    stats_md = generate_stats(records)
    stats_path = os.path.join(DATASET_DIR, "problems_merged_full_stats.md")
    with open(stats_path, "w", encoding="utf-8") as f:
        f.write(stats_md)
    print(f"已生成统计报告：{stats_path}")


if __name__ == "__main__":
    main()
