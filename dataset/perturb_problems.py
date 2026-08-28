"""生成原题的扰动变体，用于污染/记忆对照实验.

支持的扰动类型：
- surface_rewrite: 规则化表面改写（人名、地名、常见物品、句式微调），
  严格保持数学条件与答案不变
- add_noise: 插入无关子句（GSM-NoOp 风格），答案不变

输出：
- dataset/problems_perturbed.jsonl
- dataset/perturbation_index.json
"""

import json
import random
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.hy3_client import load_client_from_env


NOISE_SENTENCES = [
    "（注意：题目中所有涉及的物体数量均为正整数。）",
    "（小华在旁边看到了整个过程，但他没有参与计算。）",
    "（值得一提的是，这些数字的单位都是统一的，不需要额外换算。）",
    "（老师提醒大家，计算时请忽略任何与现实生活经验不符的细节。）",
    "（该问题发生在一个理想化的数学环境中，不考虑空气阻力等因素。）",
    "（请只根据题目给出的条件作答，不要引入额外假设。）",
    "（已知所有参与者的年龄都是整数岁。）",
    "（题干中提到的所有价格都已经包含了税费，无需再计算附加费用。）",
]

# ---------- 规则化表面改写资源 ----------

# 中文人名/占位符替换池
CN_XIAO_NAMES = ["小明", "小红", "小强", "小华", "小军", "小芳", "小刚", "小丽", "小伟", "小敏", "小涛", "小静"]
CN_PLACEHOLDERS = ["甲", "乙", "丙", "丁", "戊", "己"]

# 英文人名替换池（使用性别中性名，避免替换后与人称代词不一致）
EN_NEUTRAL_NAMES = [
    "Alex", "Jordan", "Casey", "Taylor", "Morgan", "Jamie", "Riley", "Avery",
    "Quinn", "Skyler", "Dakota", "Reese", "Rowan", "Emerson", "Finley", "Sawyer",
    "Hayden", "Parker", "Kai", "Cameron", "Devin", "Ellis", "Harper", "Luca",
    "Micah", "Nico", "Owen", "Peyton", "Robin", "Shannon",
]

# 从题目中识别出的已知英文人名（取常见名，避免把 How/Let/Find 等句子首词当名字）
KNOWN_EN_NAMES = {
    "Mimi", "Kyle", "Leigh", "Julie", "Letitia", "Anton", "Frankie", "Emma",
    "Ezekiel", "James", "Don", "Pauly", "Thomas", "TreQuan", "Trace", "Gordon",
    "Nicky", "Niko", "Patricia", "Olaf", "Alex", "Bekah", "Sam", "Mc", "Gwire", "Sosa",
    "Lbar",
}

# 常见物品/场景同义词替换（仅替换整词，避免误伤数学术语）
CN_ITEM_SYNONYMS = {
    "衣服": "外套",
    "书包": "背包",
    "苹果": "橘子",
    "香蕉": "苹果",
    "鸡蛋": "鸭蛋",
    "铅笔": "钢笔",
    "汽车": "自行车",
    "房间": "教室",
    "花园": "公园",
    "河流": "小溪",
    "餐厅": "饭店",
    "学校": "图书馆",
    "商店": "超市",
    "糖果": "饼干",
    "玩具": "模型",
    "球": "积木",
}

EN_ITEM_SYNONYMS = {
    "seashells": "pebbles",
    "shells": "stones",
    "restaurant": "café",
    "dinner": "lunch",
    "toy cars": "model trains",
    "coins": "tokens",
    "blocks": "cubes",
    "socks": "gloves",
    "books": "magazines",
    "cards": "stickers",
    "omelets": "pancakes",
    "pets": "animals",
    "rocks": "stones",
    "pebbles": "rocks",
    "boulders": "rocks",
    "snakes": "lizards",
    "cats": "rabbits",
    "parrot": "canary",
    "dogs": "cats",
    "baseball": "basketball",
    "film": "video",
    "cryptocurrency": "tokens",
    "hike": "walk",
    "tin": "metal",
}

# 句式微调模板（只改动非数学表达，全局替换且安全）
CN_SYNTACTIC_VARIANTS = [
    (re.compile(r"求(.+?)是多少"), r"问\1等于多少"),
    (re.compile(r"问(.+?)等于多少"), r"求\1的值"),
    (re.compile(r"计算(.+?)"), r"求\1"),
    (re.compile(r"如果(.+?)，"), r"若\1，"),
    (re.compile(r"共有多少"), "总共有多少"),
]

EN_SYNTACTIC_VARIANTS = [
    (re.compile(r"\bCalculate\b"), "Determine"),
    (re.compile(r"\bFind the value of\b"), "Compute the value of"),
    (re.compile(r"\bFind the number of\b"), "Determine the number of"),
    (re.compile(r"\bFind\b"), "Determine"),
    (re.compile(r"\bAnswer Choices:\b"), "Options:"),
    (re.compile(r"\bAmong A through E\b"), "From A to E"),
    (re.compile(r"\bQ:\b"), "Question:"),
]


def _is_chinese(text: str) -> bool:
    """判断文本是否主要为中文."""
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def _extract_number_tokens(text: str) -> List[str]:
    """提取文本中所有数字/分数/百分数/小数/时间比标记，用于一致性校验."""
    tokens = []
    # 百分比
    for m in re.finditer(r"\d+\s*%", text):
        tokens.append(m.group().replace(" ", ""))
    # 分数 a/b（可能带括号）
    for m in re.finditer(r"\(?\d+\s*/\s*\d+\)?", text):
        tokens.append(m.group())
    # 比值 a:b（数字比）
    for m in re.finditer(r"\d+\s*:\s*\d+", text):
        tokens.append(m.group().replace(" ", ""))
    # 整数与小数
    for m in re.finditer(r"\d+(?:\.\d+)?", text):
        tokens.append(m.group())
    return sorted(tokens)


def _numbers_consistent(original: str, rewritten: str) -> bool:
    """检查改写后的数字标记集合是否与原题完全一致."""
    return _extract_number_tokens(original) == _extract_number_tokens(rewritten)


def _build_cn_name_mapping(names: List[str], rng: random.Random) -> Dict[str, str]:
    """为中文人名/占位符建立一对一映射."""
    pool = list(CN_XIAO_NAMES)
    rng.shuffle(pool)
    mapping = {}
    for name in names:
        if name in CN_PLACEHOLDERS:
            # 甲乙丙丁 -> 戊己庚辛...
            idx = CN_PLACEHOLDERS.index(name)
            mapping[name] = CN_PLACEHOLDERS[(idx + 2) % len(CN_PLACEHOLDERS)]
        elif name in CN_XIAO_NAMES:
            # 小X 之间轮换
            idx = CN_XIAO_NAMES.index(name)
            mapping[name] = CN_XIAO_NAMES[(idx + 3) % len(CN_XIAO_NAMES)]
        else:
            # 未知中文名，从池中取一个未被使用的
            candidate = pool.pop(0) if pool else name
            mapping[name] = candidate
    return mapping


def _build_en_name_mapping(names: List[str], rng: random.Random) -> Dict[str, str]:
    """为英文人名建立一对一映射，全部使用性别中性名，避免代词不一致."""
    pool = list(EN_NEUTRAL_NAMES)
    rng.shuffle(pool)
    mapping = {}
    for name in names:
        candidate = pool.pop(0) if pool else name
        mapping[name] = candidate
    return mapping


def _replace_names(text: str, mapping: Dict[str, str]) -> str:
    """按整词替换名字/占位符."""
    if not mapping:
        return text
    # 按名字长度降序，避免短名替换覆盖长名的一部分
    for name in sorted(mapping, key=len, reverse=True):
        replacement = mapping[name]
        # 使用 \b 做英文整词，中文名直接替换（中文无空格）
        if _is_chinese(name):
            text = text.replace(name, replacement)
        else:
            text = re.sub(rf"\b{re.escape(name)}\b", replacement, text)
    return text


def _replace_items(text: str, synonyms: Dict[str, str]) -> str:
    """按整词替换常见物品/场景词."""
    for word, repl in synonyms.items():
        if _is_chinese(word):
            text = text.replace(word, repl)
        else:
            text = re.sub(rf"\b{re.escape(word)}\b", repl, text)
    return text


def _apply_syntactic_variants(text: str, variants: List[Tuple[re.Pattern, str]]) -> str:
    """按固定顺序应用所有安全的句式微调（每个模板只替换首次匹配，避免级联误改）."""
    for pattern, repl in variants:
        text, _ = pattern.subn(repl, text, count=1)
    return text


def surface_rewrite(problem: str, rng: random.Random) -> str:
    """对题目进行规则化表面改写，严格保持数字和数学条件不变."""
    original = problem
    text = problem

    if _is_chinese(text):
        # 替换中文人名/占位符
        cn_names_found = []
        for name in CN_XIAO_NAMES:
            if name in text and name not in cn_names_found:
                cn_names_found.append(name)
        for ph in CN_PLACEHOLDERS:
            if ph in text and ph not in cn_names_found:
                cn_names_found.append(ph)
        name_mapping = _build_cn_name_mapping(cn_names_found, rng)
        text = _replace_names(text, name_mapping)

        # 替换常见物品/场景
        text = _replace_items(text, CN_ITEM_SYNONYMS)

        # 句式微调
        text = _apply_syntactic_variants(text, CN_SYNTACTIC_VARIANTS)

        # 若未发生明显改写，追加一个安全前缀
        if text == original:
            text = "请解答下面的问题：" + text
    else:
        # 替换英文人名
        words = set(re.findall(r"[A-Za-z']+", text))
        en_names_found = sorted(words & KNOWN_EN_NAMES)
        name_mapping = _build_en_name_mapping(en_names_found, rng)
        text = _replace_names(text, name_mapping)

        # 替换常见物品/场景
        text = _replace_items(text, EN_ITEM_SYNONYMS)

        # 句式微调
        text = _apply_syntactic_variants(text, EN_SYNTACTIC_VARIANTS)

        # 若未发生明显改写，追加一个安全前缀
        if text == original:
            text = "Please solve the following problem. " + text

    # 数字一致性校验：若数字集合改变，则回退到最保守改写（只加前缀）
    if not _numbers_consistent(original, text):
        if _is_chinese(original):
            text = "请解答下面的问题：" + original
        else:
            text = "Please solve the following problem. " + original
        # 仍不一致则直接返回原题（理论上不会发生）
        if not _numbers_consistent(original, text):
            text = original

    return text


def add_noise(problem: str, rng: random.Random) -> str:
    """在题目中随机位置插入一句无关信息."""
    sentences = [s.strip() for s in problem.split("。") if s.strip()]
    noise = rng.choice(NOISE_SENTENCES)
    if not sentences:
        return problem + noise
    # 在倒数第二句之后插入，既显眼又不破坏结尾问句
    insert_pos = max(0, len(sentences) - 1)
    sentences.insert(insert_pos, noise)
    return "。".join(sentences) + "。"


def select_problems(records: List[Dict], per_level: int = 4) -> List[Dict]:
    """为每个难度层选择最多 per_level 道题（优先 2 high + 2 medium，不足则补同风险）."""
    rng = random.Random(42)
    selected = []
    levels = sorted({r["level"] for r in records})
    for lv in levels:
        high = [r for r in records if r["level"] == lv and r.get("contamination_risk") == "high"]
        medium = [r for r in records if r["level"] == lv and r.get("contamination_risk") == "medium"]
        rng.shuffle(high)
        rng.shuffle(medium)

        # 优先各取 2 道；若某一风险不足，用另一风险补齐到 per_level
        take_high = min(2, len(high))
        take_medium = min(2, len(medium))
        slot_left = per_level - take_high - take_medium
        if slot_left > 0:
            if len(high) > take_high:
                extra_high = min(slot_left, len(high) - take_high)
                take_high += extra_high
                slot_left -= extra_high
            if slot_left > 0 and len(medium) > take_medium:
                take_medium += min(slot_left, len(medium) - take_medium)

        selected.extend(high[:take_high])
        selected.extend(medium[:take_medium])
    return selected


def main():
    input_path = Path(__file__).parent / "problems_merged.jsonl"
    output_path = Path(__file__).parent / "problems_perturbed.jsonl"
    index_path = Path(__file__).parent / "perturbation_index.json"

    records = []
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    selected = select_problems(records, per_level=4)
    print(f"选中 {len(selected)} 道原题用于生成扰动变体")

    client = load_client_from_env()
    rng = random.Random(42)

    variants: List[Dict] = []
    index: Dict[str, List[str]] = {}

    for rec in selected:
        original_id = rec["id"]
        index[original_id] = []

        # surface_rewrite 变体（规则化同义改写）
        try:
            new_problem = surface_rewrite(rec["problem"], rng)
        except Exception as e:
            print(f"[surface_rewrite] {original_id} 失败: {e}")
            new_problem = rec["problem"]
        var_rewrite = {
            "id": f"{original_id}-surface_rewrite",
            "original_id": original_id,
            "level": rec["level"],
            "source": rec.get("source", ""),
            "contamination_risk": "low",
            "perturbation_type": "surface_rewrite",
            "perturbation_note": "规则化表面改写：人名、地名、常见物品、句式微调，数学条件与答案保持不变",
            "problem": new_problem,
            "answer": rec["answer"],
            "answer_type": rec.get("answer_type", ""),
            "verification": rec.get("verification", {}),
            "tags": rec.get("tags", []),
        }
        variants.append(var_rewrite)
        index[original_id].append(var_rewrite["id"])

        # add_noise 变体
        var_noise = {
            "id": f"{original_id}-add_noise",
            "original_id": original_id,
            "level": rec["level"],
            "source": rec.get("source", ""),
            "contamination_risk": "low",
            "perturbation_type": "add_noise",
            "perturbation_note": "插入无关子句（GSM-NoOp 风格），答案保持不变",
            "problem": add_noise(rec["problem"], rng),
            "answer": rec["answer"],
            "answer_type": rec.get("answer_type", ""),
            "verification": rec.get("verification", {}),
            "tags": rec.get("tags", []),
        }
        variants.append(var_noise)
        index[original_id].append(var_noise["id"])

    with open(output_path, "w", encoding="utf-8") as f:
        for v in variants:
            f.write(json.dumps(v, ensure_ascii=False) + "\n")

    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    print(f"已生成 {len(variants)} 条扰动变体，保存至 {output_path}")
    print(f"映射索引保存至 {index_path}")


if __name__ == "__main__":
    main()
