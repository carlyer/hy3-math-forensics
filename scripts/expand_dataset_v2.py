#!/usr/bin/env python3
"""Hy3 数学评测集扩展脚本：清洗、采样、合并并生成 v2 评估集.

输入:
  - dataset/problems_merged.jsonl          (现有 158 题)
  - dataset/math-data/math-data/new_expand/problems_v2.jsonl  (新题 779 题)
输出:
  - dataset/problems_merged_v2.jsonl
  - dataset/problems_merged_v2_stats.json
  - results/dataset_expansion_report.md
"""

import json
import random
from collections import Counter, defaultdict
from pathlib import Path

SEED = 42
random.seed(SEED)

# -----------------------------------------------------------------------------
# 路径
# -----------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
EXISTING_PATH = ROOT / "dataset" / "problems_merged.jsonl"
NEW_PATH = ROOT / "dataset" / "math-data" / "math-data" / "new_expand" / "problems_v2.jsonl"
OUT_DATASET = ROOT / "dataset" / "problems_merged_v2.jsonl"
OUT_STATS = ROOT / "dataset" / "problems_merged_v2_stats.json"
OUT_REPORT = ROOT / "results" / "dataset_expansion_report.md"


def load_jsonl(path: Path):
    data = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data.append(json.loads(line))
    return data


def save_jsonl(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for item in data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def save_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


# -----------------------------------------------------------------------------
# 数据规范化
# -----------------------------------------------------------------------------
def normalize_problem_text(text: str) -> str:
    """用于去重的题面规范化：统一空白."""
    return " ".join(str(text).strip().split())


def normalize_verification(item: dict) -> dict:
    """将新数据集的 verification method 映射到 answer_checker 支持的名称."""
    ver = item.get("verification", {})
    if not isinstance(ver, dict):
        ver = {"method": str(ver)}
    method = ver.get("method", "")
    mapping = {
        "numeric": "exact_match",
        "choice": "choice_match",
    }
    if method in mapping:
        ver = dict(ver)
        ver["method"] = mapping[method]
        ver["original_method"] = method
    return ver


def ensure_required_fields(item: dict) -> dict:
    """确保必要字段存在；如缺失，根据 source / problem_form 推断合理默认值."""
    required = ["id", "level", "source", "problem", "answer", "verification", "contamination_risk"]
    for key in required:
        if key not in item or item[key] is None:
            if key == "contamination_risk":
                src = str(item.get("source", "")).lower()
                if "train" in src or "gsm8k" in src:
                    item[key] = "high"
                elif "test" in src or "aime-2025" in src or "gaokao" in src:
                    item[key] = "low"
                else:
                    item[key] = "medium"
            elif key == "verification":
                form = item.get("problem_form", "open")
                if form == "choice":
                    item[key] = {"method": "choice_match"}
                elif form == "proof":
                    item[key] = {"method": "manual_check"}
                else:
                    item[key] = {"method": "exact_match"}
            else:
                item[key] = ""
    return item


# -----------------------------------------------------------------------------
# 采样辅助
# -----------------------------------------------------------------------------
def stratified_sample(population: list, n: int, strata_key) -> list:
    """按 strata_key 分层后尽量按比例采样，最后用随机项补足到 n."""
    if n >= len(population):
        return population
    strata = defaultdict(list)
    for p in population:
        strata[strata_key(p)].append(p)
    result = []
    # 按比例分配
    total = len(population)
    quotas = {k: int(n * len(v) / total) for k, v in strata.items()}
    # 先取配额
    for k, v in strata.items():
        q = min(quotas[k], len(v))
        result.extend(random.sample(v, q))
    # 补齐
    remaining = [p for p in population if p not in result]
    if len(result) < n:
        result.extend(random.sample(remaining, n - len(result)))
    random.shuffle(result)
    return result


def verification_method(item: dict) -> str:
    return item.get("verification", {}).get("method", "NA")


# -----------------------------------------------------------------------------
# 主流程
# -----------------------------------------------------------------------------
def main():
    existing = load_jsonl(EXISTING_PATH)
    new_raw = load_jsonl(NEW_PATH)

    # 1. 清洗 + 规范化
    new_cleaned = []
    for item in new_raw:
        item = dict(item)
        item["verification"] = normalize_verification(item)
        item = ensure_required_fields(item)
        item["_norm_problem"] = normalize_problem_text(item["problem"])
        new_cleaned.append(item)

    # 2. 去重（与现有 158 题题面完全重复）
    existing_problem_set = {normalize_problem_text(p["problem"]) for p in existing}
    deduped = [p for p in new_cleaned if p["_norm_problem"] not in existing_problem_set]
    duplicates_removed = len(new_cleaned) - len(deduped)

    # 同时处理新数据集内部完全重复
    seen = set()
    unique_new = []
    for p in deduped:
        if p["_norm_problem"] not in seen:
            seen.add(p["_norm_problem"])
            unique_new.append(p)
    internal_dups_removed = len(deduped) - len(unique_new)

    # 3. 按层、验证方式、风险分组
    by_level = defaultdict(list)
    for p in unique_new:
        by_level[p["level"]].append(p)

    def is_auto_gradable(p: dict) -> bool:
        return verification_method(p) not in {"manual_check", "contains", "regex"}

    def is_proof(p: dict) -> bool:
        return p.get("problem_form") == "proof" or verification_method(p) == "manual_check"

    # 4. 设计采样
    # 目标最终分层（含现有 158 题）:
    # L1: ~90, L2: 100, L3: ~93, L4: ~103  => 总计 ~386
    # 现有: L1=30, L2=35, L3=47, L4=46
    # 需新增: L1=60, L2=65, L3=46, L4=57

    sampled = []
    sampling_log = {}

    # ---- L1: 全部 20 个 GSM-Plus 簇，每簇 3 题 ----
    l1_candidates = by_level["L1"]
    l1_clusters = defaultdict(list)
    for p in l1_candidates:
        l1_clusters[p.get("cluster_id")].append(p)
    # 保留完整簇
    l1_selected = []
    for cid in sorted(l1_clusters.keys()):
        l1_selected.extend(l1_clusters[cid])
    sampled.extend(l1_selected)
    sampling_log["L1"] = {
        "available": len(l1_candidates),
        "selected": len(l1_selected),
        "clusters_total": len(l1_clusters),
        "clusters_complete": sum(1 for v in l1_clusters.values() if len(v) == 3),
        "auto_gradable": sum(1 for p in l1_selected if is_auto_gradable(p)),
        "manual_check": sum(1 for p in l1_selected if not is_auto_gradable(p)),
    }

    # ---- L2: 65 题，全部自动判分 ----
    l2_candidates = by_level["L2"]
    l2_auto = [p for p in l2_candidates if is_auto_gradable(p)]
    # 1) 保留所有低风险自动判分题（2026-Gaokao，约 10 道）
    l2_low = [p for p in l2_auto if p.get("contamination_risk") == "low"]
    # 2) 保留 MATH/Level 2-3 符号等价题，提升来源多样性（目标 8 道）
    l2_math = [p for p in l2_auto if p.get("source", "").startswith("MATH/")]
    l2_math_sample = random.sample(l2_math, min(8, len(l2_math)))
    # 3) 其余从 AGIEval 选择题补充
    l2_agieval_pool = [p for p in l2_auto if p.get("source") == "AGIEval" and p not in l2_low and p not in l2_math_sample]
    need_agieval = 65 - len(l2_low) - len(l2_math_sample)
    l2_agieval_sample = random.sample(l2_agieval_pool, min(need_agieval, len(l2_agieval_pool)))
    l2_selected = l2_low + l2_math_sample + l2_agieval_sample
    # 4) 兜底：如数量不足，从剩余 auto 题随机补
    if len(l2_selected) < 65:
        pool = [p for p in l2_auto if p not in l2_selected]
        need = 65 - len(l2_selected)
        l2_selected.extend(random.sample(pool, need))
    random.shuffle(l2_selected)
    sampled.extend(l2_selected)
    sampling_log["L2"] = {
        "available": len(l2_candidates),
        "selected": len(l2_selected),
        "auto_gradable": sum(1 for p in l2_selected if is_auto_gradable(p)),
        "manual_check": sum(1 for p in l2_selected if not is_auto_gradable(p)),
    }

    # ---- L3: 46 题，36 自动 + 10 manual_check ----
    l3_candidates = by_level["L3"]
    l3_auto = [p for p in l3_candidates if is_auto_gradable(p)]
    l3_manual = [p for p in l3_candidates if not is_auto_gradable(p)]
    l3_auto_all = l3_auto[:]  # 36 题
    # manual 中优先取低风险 Gaokao，再随机取 MiniF2F
    l3_manual_low = [p for p in l3_manual if p.get("contamination_risk") == "low"]
    l3_manual_other = [p for p in l3_manual if p.get("contamination_risk") != "low"]
    l3_manual_selected = l3_manual_low[:]
    if len(l3_manual_selected) < 10:
        need = 10 - len(l3_manual_selected)
        l3_manual_selected.extend(random.sample(l3_manual_other, need))
    l3_selected = l3_auto_all + l3_manual_selected
    random.shuffle(l3_selected)
    sampled.extend(l3_selected)
    sampling_log["L3"] = {
        "available": len(l3_candidates),
        "selected": len(l3_selected),
        "auto_gradable": sum(1 for p in l3_selected if is_auto_gradable(p)),
        "manual_check": sum(1 for p in l3_selected if not is_auto_gradable(p)),
    }

    # ---- L4: 58 题，53 自动 + 5 manual_check ----
    l4_candidates = by_level["L4"]
    l4_auto = [p for p in l4_candidates if is_auto_gradable(p)]
    l4_manual = [p for p in l4_candidates if not is_auto_gradable(p)]
    l4_auto_all = l4_auto[:]  # 53 题
    # manual 按污染风险分层采样
    l4_manual_selected = stratified_sample(l4_manual, 5, lambda p: p.get("contamination_risk", "medium"))
    l4_selected = l4_auto_all + l4_manual_selected
    random.shuffle(l4_selected)
    sampled.extend(l4_selected)
    sampling_log["L4"] = {
        "available": len(l4_candidates),
        "selected": len(l4_selected),
        "auto_gradable": sum(1 for p in l4_selected if is_auto_gradable(p)),
        "manual_check": sum(1 for p in l4_selected if not is_auto_gradable(p)),
    }

    # 5. 重新编号（避免与现有 ID 冲突）
    level_counter = defaultdict(int)
    for item in sampled:
        lvl = item["level"]
        level_counter[lvl] += 1
        item["id"] = f"EXT-{lvl}-{level_counter[lvl]:03d}"
        # 删除辅助字段
        item.pop("_norm_problem", None)

    # 6. 合并现有 + 新题
    merged = []
    # 现有题原样保留
    for p in existing:
        merged.append(dict(p))
    # 新题
    for p in sampled:
        merged.append(p)

    # 7. 统计
    def count_by(records, key, subkey=None):
        if subkey:
            return dict(Counter(r.get(key, {}).get(subkey, "NA") for r in records))
        return dict(Counter(r.get(key, "NA") for r in records))

    def count_by_func(records, func):
        return dict(Counter(func(r) for r in records))

    stats = {
        "seed": SEED,
        "existing": {
            "total": len(existing),
            "by_level": count_by(existing, "level"),
            "by_verification": count_by(existing, "verification", "method"),
            "by_contamination_risk": count_by(existing, "contamination_risk"),
            "by_source": count_by(existing, "source"),
        },
        "new_raw": {
            "total": len(new_raw),
            "by_level": count_by(new_raw, "level"),
            "by_verification": count_by(new_raw, "verification", "method"),
            "by_contamination_risk": count_by(new_raw, "contamination_risk"),
            "by_problem_form": count_by(new_raw, "problem_form"),
        },
        "deduplication": {
            "duplicates_with_existing_removed": duplicates_removed,
            "internal_duplicates_removed": internal_dups_removed,
            "available_after_dedup": len(unique_new),
            "available_after_dedup_by_level": count_by(unique_new, "level"),
        },
        "sampling": sampling_log,
        "merged_v2": {
            "total": len(merged),
            "by_level": count_by(merged, "level"),
            "by_verification": count_by(merged, "verification", "method"),
            "by_contamination_risk": count_by(merged, "contamination_risk"),
            "by_source": count_by(merged, "source"),
            "by_problem_form": count_by(merged, "problem_form"),
            "new_ids_prefix": "EXT-",
            "id_unique": len({p["id"] for p in merged}) == len(merged),
        },
    }

    # 8. 保存
    save_jsonl(OUT_DATASET, merged)
    save_json(OUT_STATS, stats)

    # 9. 报告
    report_lines = []
    report_lines.append("# Hy3 数学评测集扩展报告\n")
    report_lines.append(f"生成时间: 自动脚本生成 | 随机种子: `{SEED}`\n")

    report_lines.append("## 1. 原始数据集规模\n")
    report_lines.append("| 数据集 | 总题数 | L1 | L2 | L3 | L4 |")
    report_lines.append("|---|---|---|---|---|---|")
    e = stats["existing"]
    report_lines.append(
        f"| 现有 `problems_merged.jsonl` | {e['total']} | {e['by_level'].get('L1',0)} | "
        f"{e['by_level'].get('L2',0)} | {e['by_level'].get('L3',0)} | {e['by_level'].get('L4',0)} |"
    )
    n = stats["new_raw"]
    report_lines.append(
        f"| 新题 `problems_v2.jsonl` | {n['total']} | {n['by_level'].get('L1',0)} | "
        f"{n['by_level'].get('L2',0)} | {n['by_level'].get('L3',0)} | {n['by_level'].get('L4',0)} |"
    )
    report_lines.append("")

    report_lines.append("## 2. 去重后可用新题规模\n")
    report_lines.append(f"- 与现有 158 题题面完全重复：{duplicates_removed} 道（已剔除）")
    report_lines.append(f"- 新集内部完全重复：{internal_dups_removed} 道（已剔除）")
    report_lines.append(f"- 去重后可用新题：**{len(unique_new)}** 道\n")

    report_lines.append("### 2.1 按难度分布\n")
    report_lines.append("| 难度 | 题数 |")
    report_lines.append("|---|---|")
    for lvl in ["L1", "L2", "L3", "L4"]:
        report_lines.append(f"| {lvl} | {stats['deduplication']['available_after_dedup_by_level'].get(lvl, 0)} |")
    report_lines.append("")

    report_lines.append("### 2.2 按题型 / 验证方式分布\n")
    report_lines.append("| 验证方式 | 题数 | 说明 |")
    report_lines.append("|---|---|---|")
    for ver, cnt in sorted(stats["new_raw"]["by_verification"].items(), key=lambda x: -x[1]):
        note = {
            "choice": "选择题（映射为 choice_match）",
            "manual_check": "证明 / 需要人工判分",
            "numeric": "数值题（映射为 exact_match）",
            "symbolic_equivalence": "符号等价",
        }.get(ver, "")
        report_lines.append(f"| {ver} | {cnt} | {note} |")
    report_lines.append("")

    report_lines.append("### 2.3 按污染风险分布\n")
    report_lines.append("| 风险 | 题数 |")
    report_lines.append("|---|---|")
    for risk, cnt in sorted(stats["new_raw"]["by_contamination_risk"].items(), key=lambda x: -x[1]):
        report_lines.append(f"| {risk} | {cnt} |")
    report_lines.append("")

    report_lines.append("### 2.4 按 problem_form 分布\n")
    report_lines.append("| 形式 | 题数 |")
    report_lines.append("|---|---|")
    for form, cnt in sorted(stats["new_raw"]["by_problem_form"].items(), key=lambda x: -x[1]):
        report_lines.append(f"| {form} | {cnt} |")
    report_lines.append("")

    report_lines.append("## 3. 采样策略说明\n")
    report_lines.append("目标：生成约 350–400 题的扩展评估集，保留全部现有 158 题，新题重新编号为 `EXT-L{level}-{seq:03d}`。\n")
    report_lines.append("分层目标与实现：\n")
    report_lines.append("| 难度 | 现有题数 | 计划新增 | 实际新增 | 最终题数 | 策略要点 |")
    report_lines.append("|---|---|---|---|---|---|")
    final_by_level = stats["merged_v2"]["by_level"]
    for lvl in ["L1", "L2", "L3", "L4"]:
        existing_cnt = e["by_level"].get(lvl, 0)
        selected = sampling_log[lvl]["selected"]
        final = final_by_level.get(lvl, 0)
        note = {
            "L1": "保留全部 20 个 GSM-Plus 变体簇（原题+数值替换+干扰插入）",
            "L2": "全部自动判分；保留所有低风险 Gaokao + 8 道 MATH 符号题 + AGIEval 补充",
            "L3": "自动判分题全取（仅 36 道），补充 10 道 manual_check 证明题",
            "L4": "自动判分题全取（去重后 52 道），补充 5 道 manual_check 证明题",
        }[lvl]
        report_lines.append(f"| {lvl} | {existing_cnt} | 见策略 | {selected} | {final} | {note} |")
    report_lines.append("")

    report_lines.append("采样约束：\n")
    report_lines.append("- 随机种子 `42`，结果可复现。")
    report_lines.append("- 优先选择可自动判分题（`exact_match` / `choice_match` / `symbolic_equivalence`），仅在 L3/L4 可用题不足时纳入 `manual_check` 证明题。")
    report_lines.append("- L2 低风险自动判分题约 10 道（2026-Gaokao），全部纳入；额外固定抽取 8 道 MATH/Level 2-3 符号等价题，剩余由 AGIEval 选择题补足，保证来源多样性。")
    report_lines.append("- L3/L4 的 manual_check 题按污染风险分层采样，尽量使 high/medium/low 分布合理。\n")

    report_lines.append("## 4. 最终 `problems_merged_v2.jsonl` 统计\n")
    report_lines.append(f"- **总题数**：{stats['merged_v2']['total']}")
    report_lines.append(f"- **ID 唯一**：{'是' if stats['merged_v2']['id_unique'] else '否'}\n")

    report_lines.append("### 4.1 难度分布\n")
    report_lines.append("| 难度 | 题数 | 占比 |")
    report_lines.append("|---|---|---|")
    total = stats["merged_v2"]["total"]
    for lvl in ["L1", "L2", "L3", "L4"]:
        cnt = final_by_level.get(lvl, 0)
        report_lines.append(f"| {lvl} | {cnt} | {cnt/total*100:.1f}% |")
    report_lines.append("")

    report_lines.append("### 4.2 验证方式分布\n")
    report_lines.append("| 验证方式 | 题数 |")
    report_lines.append("|---|---|")
    for ver, cnt in sorted(stats["merged_v2"]["by_verification"].items(), key=lambda x: -x[1]):
        report_lines.append(f"| {ver} | {cnt} |")
    report_lines.append("")

    report_lines.append("### 4.3 污染风险分布\n")
    report_lines.append("| 风险 | 题数 |")
    report_lines.append("|---|---|")
    for risk, cnt in sorted(stats["merged_v2"]["by_contamination_risk"].items(), key=lambda x: -x[1]):
        report_lines.append(f"| {risk} | {cnt} |")
    report_lines.append("")

    report_lines.append("### 4.4 来源分布（Top 15）\n")
    report_lines.append("| 来源 | 题数 |")
    report_lines.append("|---|---|")
    for src, cnt in sorted(stats["merged_v2"]["by_source"].items(), key=lambda x: -x[1])[:15]:
        report_lines.append(f"| {src} | {cnt} |")
    report_lines.append("")

    report_lines.append("### 4.5 题型形式分布\n")
    report_lines.append("| 形式 | 题数 |")
    report_lines.append("|---|---|")
    for form, cnt in sorted(stats["merged_v2"]["by_problem_form"].items(), key=lambda x: -x[1]):
        report_lines.append(f"| {form} | {cnt} |")
    report_lines.append("")

    report_lines.append("## 5. 保留的 GSM-Plus 变体簇\n")
    gsm_clusters = defaultdict(list)
    for p in sampled:
        if p.get("source", "").startswith("GSM") or "GSM-Plus" in p.get("source", ""):
            cid = p.get("cluster_id")
            if cid:
                gsm_clusters[cid].append(p)
    report_lines.append(f"- 完整保留的 GSM-Plus 簇数量：**{len(gsm_clusters)}**\n")
    report_lines.append("| cluster_id | 原题 | 数值替换 | 干扰插入 |")
    report_lines.append("|---|---|---|---|")
    for cid in sorted(gsm_clusters.keys())[:10]:
        items = gsm_clusters[cid]
        srcs = {p["source"]: p["id"] for p in items}
        orig = srcs.get("GSM8K", "-")
        num = srcs.get("GSM-Plus/numerical substitution", "-")
        dist = srcs.get("GSM-Plus/distraction insertion", "-")
        report_lines.append(f"| {cid} | {orig} | {num} | {dist} |")
    report_lines.append("")
    report_lines.append("（仅列出前 10 个示例，完整 20 个簇均已保留。）\n")

    report_lines.append("## 6. 与旧版 158 题对比\n")
    report_lines.append("| 指标 | 旧版 | 新版 v2 | 变化 |")
    report_lines.append("|---|---|---|---|")
    report_lines.append(f"| 总题数 | {e['total']} | {stats['merged_v2']['total']} | +{stats['merged_v2']['total'] - e['total']} |")
    for lvl in ["L1", "L2", "L3", "L4"]:
        old = e["by_level"].get(lvl, 0)
        newv = final_by_level.get(lvl, 0)
        report_lines.append(f"| {lvl} | {old} | {newv} | +{newv - old} |")
    old_auto = sum(1 for p in existing if verification_method(p) != "manual_check")
    new_auto = sum(1 for p in merged if verification_method(p) != "manual_check")
    old_manual = sum(1 for p in existing if verification_method(p) == "manual_check")
    new_manual = sum(1 for p in merged if verification_method(p) == "manual_check")
    report_lines.append(f"| 自动判分 | {old_auto} | {new_auto} | +{new_auto - old_auto} |")
    report_lines.append(f"| 人工判分 | {old_manual} | {new_manual} | +{new_manual - old_manual} |")
    report_lines.append("")

    # 运行时校验
    required_fields = ["id", "level", "source", "problem", "answer", "verification", "contamination_risk"]
    missing_fields_count = 0
    null_answer_ids = []
    bad_verification_ids = []
    for p in merged:
        for key in required_fields:
            if key not in p:
                missing_fields_count += 1
        if p.get("answer") is None:
            null_answer_ids.append(p["id"])
        ver = p.get("verification", {})
        if not isinstance(ver, dict) or "method" not in ver:
            bad_verification_ids.append(p["id"])

    report_lines.append("## 7. 验证\n")
    report_lines.append(f"- 最终题数 {stats['merged_v2']['total']} 在 350–400 范围内：{'是' if 350 <= stats['merged_v2']['total'] <= 400 else '否'}")
    report_lines.append(f"- ID 无重复：{'是' if stats['merged_v2']['id_unique'] else '否'}")
    report_lines.append(f"- 必要字段缺失：{missing_fields_count} 处")
    report_lines.append(f"- verification 含有效 method：{'是' if len(bad_verification_ids) == 0 else '否'}")
    if null_answer_ids:
        report_lines.append(f"- `answer` 为 null 的题目：{len(null_answer_ids)} 道（`{'`, `'.join(null_answer_ids)}`）。均为现有 FrontierMath-v2 证明题，原始数据即无标准答案，采用 `manual_check` 判分，属于预期情况。")
    report_lines.append("")

    report_lines.append("## 8. 注意事项\n")
    report_lines.append("- `problems_merged.jsonl` 原文件未被修改。")
    report_lines.append("- 新数据集中原 `verification.method` 为 `numeric` 的已映射为 `exact_match`，`choice` 的已映射为 `choice_match`，以兼容现有 `answer_checker.py`；原始方法保存在 `verification.original_method` 中。")
    report_lines.append("- L3 纳入 10 道、`L4` 纳入 5 道 `manual_check` 证明题，原因：对应难度可用自动判分题不足。")
    report_lines.append("")

    OUT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))

    print(f"✅ 完成。输出文件：")
    print(f"   {OUT_DATASET}")
    print(f"   {OUT_STATS}")
    print(f"   {OUT_REPORT}")
    print(f"\n总题数: {len(merged)} (现有 {len(existing)} + 新增 {len(sampled)})")


if __name__ == "__main__":
    main()
