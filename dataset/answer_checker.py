"""标准答案自动校验模块.

支持:
- exact_match: 精确匹配(整数、字符串)
- numeric_tolerance: 数值容差匹配
- symbolic_equivalence: sympy 符号等价
- list_match: 列表/集合匹配
- contains: 关键词包含(用于证明题)
- regex: 正则提取后匹配
"""

import re
import warnings
from typing import Any, Dict, List, Optional, Tuple, Union

import sympy as sp
from sympy.parsing.latex import parse_latex
from sympy.parsing.sympy_parser import parse_expr

# 抑制 sympy 解析非常规/set-like 表达式时产生的 SyntaxWarning
warnings.filterwarnings("ignore", category=SyntaxWarning)


class AnswerCheckError(Exception):
    """校验过程中出现的错误."""

    pass


def normalize_answer(text: Union[str, float, int]) -> str:
    """对答案文本做基础规范化.

    注意：不要破坏 LaTeX 结构（如 \\frac、{}），否则 sympy 无法解析。
    """
    if text is None:
        return ""
    s = str(text).strip()
    # 去除 display/inline math 包装符
    s = s.replace("$", "").replace("\\(", "").replace("\\)", "")
    s = s.replace("\\[", "").replace("\\]", "")
    # 仅去除 \\text{...} 的包装，保留内部文本
    s = re.sub(r"\\text\{(.*?)\}", r"\1", s)
    # 将 LaTeX 转义的百分号、美元符统一为普通字符
    s = s.replace("\\%", "%")
    s = s.replace("\\$", "$")
    # 去除 LaTeX 显式空格 \ 后接空白
    s = re.sub(r"\\\s+", " ", s)
    # 去除多余空白（但保留 LaTeX 命令中的空格需求）
    s = " ".join(s.split())
    return s


def canonicalize_answer(text: Union[str, float, int]) -> str:
    """对答案文本做进一步规范化，使等价形式更易匹配.

    在 normalize_answer 基础上：
    - 去除常见的答案前缀/ affixes（如 x=、answer is、答案是等）
    - 去除末尾标点
    - 处理千分位逗号、百分号、末尾单位字母
    """
    s = normalize_answer(text)

    # 1. 去除答案前缀/ affixes（大小写不敏感，冒号/空白可选）
    prefix_pat = re.compile(
        r"^\s*(?:"
        r"x\s*=\s*|"
        r"answer\s*is\s*[:\uff1a]?\s*|"
        r"answer\s*[:\uff1a]\s*|"
        r"ans\s*[:\uff1a]\s*|"
        r"答案是\s*[:\uff1a]?\s*|"
        r"答案为\s*[:\uff1a]?\s*|"
        r"答案\s*[:\uff1a]\s*|"
        r"最终答案\s*[:\uff1a]?\s*"
        r")",
        re.IGNORECASE,
    )
    s = prefix_pat.sub("", s)

    # 2. 去除末尾标点
    s = re.sub(r"[\u3002\uff0c.,;:!?]+$", "", s)

    # 3. 去除千分位逗号（仅保留形如 1,000,000 的合法千分位）
    s = re.sub(r"(?<=\d),(?=(?:\d{3})+(?!\d))", "", s)

    # 4. 百分号转换为小数
    percent_match = re.fullmatch(r"(-?\d+(?:\.\d+)?)\s*%", s)
    if percent_match:
        s = str(float(percent_match.group(1)) / 100)

    # 5. 去除末尾单位字母（如 126km -> 126）
    unit_match = re.fullmatch(r"(-?\d+(?:\.\d+)?)\s*[a-zA-Z]+", s)
    if unit_match:
        s = unit_match.group(1)

    # 5b. 去除末尾多个英文单词单位（如 4\text{ dollars each} -> 4；2\sqrt{3} cm -> 2\sqrt{3}）
    s = re.sub(r"(?<=[\d\)\}])\s+[a-zA-Z][a-zA-Z\s]*$", "", s)

    # 6. 去除末尾中文字符单位（如 7 米 -> 7，保留“星期五”等非数字答案）
    cn_unit_match = re.fullmatch(r"(-?\d+(?:\.\d+)?)\s*[\u4e00-\u9fff]+", s)
    if cn_unit_match:
        s = cn_unit_match.group(1)

    # 6b. 去除末尾多个中文词单位（如 7 平方米 -> 7）
    s = re.sub(r"(?<=[\d\)\}])\s+[\u4e00-\u9fff][\u4e00-\u9fff\s]*$", "", s)

    s = s.strip()
    return s


def _is_latex(s: str) -> bool:
    """判断字符串是否包含 LaTeX 命令."""
    return bool(re.search(r"\\[a-zA-Z]+", s))


def _to_sympy(expr_str: str) -> Optional[sp.Expr]:
    """尝试将字符串解析为 sympy 表达式."""
    expr_str = normalize_answer(expr_str)
    if not expr_str:
        return None

    # LaTeX 表达式优先用 parse_latex
    if _is_latex(expr_str):
        try:
            return parse_latex(expr_str)
        except Exception:
            pass
        # 清理逗号分隔符（如 20,\!000）后再试
        try:
            cleaned = expr_str.replace(",\\!", "").replace(",", "")
            return parse_latex(cleaned)
        except Exception:
            pass

    # 非 LaTeX：先尝试 sympy 自带解析
    try:
        return parse_expr(expr_str, evaluate=True)
    except Exception:
        pass

    # 处理 Math23K 风格分数表示 ((2)/(35)) -> 2/35
    try:
        m = re.match(r"^\(\((\d+)\)/\((\d+)\)\)$", expr_str)
        if m:
            return sp.Rational(int(m.group(1)), int(m.group(2)))
    except Exception:
        pass

    # 处理常见分数表示如 3/10
    try:
        if "/" in expr_str and not any(c in expr_str for c in "+-*()"):
            num, den = expr_str.split("/", 1)
            return sp.Rational(int(num), int(den))
    except Exception:
        pass
    return None


def check_exact_match(pred: str, gold: str) -> Tuple[bool, Optional[str]]:
    """精确字符串匹配."""
    pred_norm = canonicalize_answer(pred)
    gold_norm = canonicalize_answer(gold)
    ok = pred_norm == gold_norm
    detail = None if ok else f"精确不匹配: pred='{pred_norm}', gold='{gold_norm}'"
    return ok, detail


def _strip_units(s: str) -> str:
    """去掉末尾的中文字符和单位，保留数值表达式."""
    s = canonicalize_answer(s)
    # 兜底：去掉末尾连续的中文字符
    s = re.sub(r"[\u4e00-\u9fff]+$", "", s)
    # 兜底：去掉末尾非数字、非变量、非运算符字符，但保留 LaTeX 命令所需的 \ 和 {}
    s = re.sub(r"[^0-9a-zA-Z+\-*/().^\\{}]+$", "", s)
    return s


def check_numeric_tolerance(
    pred: str, gold: str, tolerance: float = 1e-4
) -> Tuple[bool, Optional[str]]:
    """数值容差匹配."""
    pred_norm = _strip_units(pred)
    gold_norm = _strip_units(gold)
    if not pred_norm or not gold_norm:
        return False, "数值解析失败: 去除单位后为空"

    def _eval(s: str):
        try:
            return float(sp.N(parse_expr(s)))
        except Exception:
            if _is_latex(s):
                return float(sp.N(parse_latex(s)))
            raise

    try:
        pred_val = _eval(pred_norm)
        gold_val = _eval(gold_norm)
    except Exception as e:
        return False, f"数值解析失败: {e}"
    ok = abs(pred_val - gold_val) <= tolerance * max(1.0, abs(gold_val))
    detail = None if ok else f"数值不匹配: pred={pred_val}, gold={gold_val}"
    return ok, detail


def check_symbolic_equivalence(
    pred: str, gold: str
) -> Tuple[bool, Optional[str]]:
    """符号等价匹配."""
    pred_expr = _to_sympy(pred)
    gold_expr = _to_sympy(gold)
    if pred_expr is None or gold_expr is None:
        # 若符号解析失败, 回退到精确匹配
        return check_exact_match(pred, gold)
    try:
        diff = sp.simplify(pred_expr - gold_expr)
        ok = diff == 0
    except Exception as e:
        return False, f"符号化简失败: {e}"
    detail = None if ok else f"符号不等价: pred={pred_expr}, gold={gold_expr}"
    return ok, detail


def check_list_match(
    pred: str, gold: str, ordered: bool = True
) -> Tuple[bool, Optional[str]]:
    """列表/集合匹配."""
    pred_norm = normalize_answer(pred)
    gold_norm = normalize_answer(gold)

    def _parse_list(s: str) -> List[str]:
        # 支持逗号、空格、顿号分隔
        s = s.replace("，", ",").replace("、", ",")
        parts = re.split(r"[,;\s]+", s)
        return [p.strip() for p in parts if p.strip()]

    pred_list = _parse_list(pred_norm)
    gold_list = _parse_list(gold_norm)

    if ordered:
        ok = pred_list == gold_list
        detail = None if ok else f"顺序列表不匹配: pred={pred_list}, gold={gold_list}"
    else:
        ok = sorted(pred_list) == sorted(gold_list)
        detail = None if ok else f"集合不匹配: pred={pred_list}, gold={gold_list}"
    return ok, detail


def check_contains(
    pred: str, gold: str, keywords: Optional[List[str]] = None
) -> Tuple[bool, Optional[str]]:
    """检查预测文本是否包含所有关键词(用于证明题)."""
    pred_norm = normalize_answer(pred).lower()
    if keywords is None:
        keywords = [normalize_answer(gold).lower()]
    missing = [kw for kw in keywords if normalize_answer(kw).lower() not in pred_norm]
    ok = len(missing) == 0
    detail = None if ok else f"缺少关键词: {missing}"
    return ok, detail


def check_regex(
    pred: str, gold: str, pattern: Optional[str] = None
) -> Tuple[bool, Optional[str]]:
    """正则提取后匹配."""
    pred_norm = normalize_answer(pred)
    if pattern is None:
        pattern = normalize_answer(gold)
    try:
        match = re.search(pattern, pred_norm)
    except re.error as e:
        return False, f"正则编译失败: {e}"
    ok = match is not None
    detail = None if ok else f"正则未匹配: pattern={pattern}"
    return ok, detail


def check_choice_match(pred: str, gold: str) -> Tuple[bool, Optional[str]]:
    """选择题选项匹配.

    支持:
    - 选项字母匹配(不区分大小写), 如 gold="(C)10" 时 pred="C" 或 "(C)"
    - 选项文本匹配, 如 gold="(C)10" 时 pred="10"
    - 完整选项匹配, 如 gold="(C)10" 时 pred="(C)10"
    """
    pred_norm = normalize_answer(pred).lower()
    gold_norm = normalize_answer(gold).lower()

    # 完全规范化后相同
    if pred_norm == gold_norm:
        return True, None

    # 尝试从 gold 中拆出选项字母和选项文本
    letter_match = re.match(r"^\(([a-z])\)(.*)$", gold_norm)
    if letter_match:
        letter = letter_match.group(1)
        text = letter_match.group(2).strip()

        # 仅选项字母: "C" 或 "(C)"
        if pred_norm == letter or pred_norm == f"({letter})":
            return True, None

        # 完整选项: "(C)10" 或 "C10"
        if pred_norm == f"({letter}){text}" or pred_norm == f"{letter}{text}":
            return True, None

        # 仅选项文本: "10" 或 "10km"(规范化后)
        if text and pred_norm == text:
            return True, None

    # gold 本身就是单个选项字母, 如 "C" 或 "(C)"
    simple_letter = re.match(r"^\(?([a-z])\)?$", gold_norm)
    if simple_letter:
        letter = simple_letter.group(1)
        if pred_norm == letter or pred_norm == f"({letter})":
            return True, None

    detail = f"选项不匹配: pred='{pred_norm}', gold='{gold_norm}'"
    return False, detail


def _looks_numeric(s: str) -> bool:
    """判断字符串是否主要包含数值表达式."""
    s = canonicalize_answer(s)
    # 去掉单位等Trailing中文
    s = re.sub(r"[\u4e00-\u9fff]+", "", s)
    if not s:
        return False
    try:
        float(sp.N(parse_expr(s)))
        return True
    except Exception:
        pass
    # LaTeX 表达式（如 2\sqrt{3}）尝试用 latex 解析
    if _is_latex(s):
        try:
            float(sp.N(parse_latex(s)))
            return True
        except Exception:
            pass
    return False


def check_manual(pred: str, gold: str) -> Tuple[Optional[bool], Optional[str]]:
    """无标准答案时跳过自动校验."""
    return None, "无标准答案，跳过自动校验"


def check_answer(
    pred: Union[str, float, int, None],
    gold: str,
    verification: Dict[str, Any],
) -> Tuple[Optional[bool], Optional[str]]:
    """统一的答案校验入口.

    Args:
        pred: 模型预测答案
        gold: 标准答案
        verification: 校验配置, 必须包含 method 字段

    Returns:
        (是否通过或 None, 失败原因或 None)
    """
    method = verification.get("method", "exact_match")

    if method == "manual_check":
        return check_manual(str(pred) if pred is not None else "", gold)

    if pred is None or str(pred).strip() == "":
        return False, "模型未输出答案"

    if method == "exact_match":
        ok, detail = check_exact_match(str(pred), gold)
        if ok:
            return ok, detail
        # 先尝试符号等价
        sym_ok, sym_detail = check_symbolic_equivalence(str(pred), gold)
        if sym_ok:
            return sym_ok, sym_detail
        # 若仍不匹配且两边都是数值，使用更宽松的数值容差
        if _looks_numeric(str(pred)) and _looks_numeric(gold):
            return check_numeric_tolerance(str(pred), gold, tolerance=1e-2)
        return ok, detail
    elif method == "numeric_tolerance":
        return check_numeric_tolerance(
            str(pred), gold, tolerance=verification.get("tolerance", 1e-4)
        )
    elif method == "symbolic_equivalence":
        return check_symbolic_equivalence(str(pred), gold)
    elif method == "list_match":
        return check_list_match(
            str(pred), gold, ordered=verification.get("ordered", True)
        )
    elif method == "contains":
        return check_contains(str(pred), gold, keywords=verification.get("keywords"))
    elif method == "regex":
        return check_regex(str(pred), gold, pattern=verification.get("pattern"))
    elif method == "choice_match":
        return check_choice_match(str(pred), gold)
    else:
        raise AnswerCheckError(f"未知的校验方法: {method}")


def extract_boxed_answer(text: str) -> Optional[str]:
    """从文本中提取 \\boxed{...} 内的内容.

    支持嵌套括号, 返回最外层匹配.
    """
    if not text:
        return None
    # 匹配 \boxed{...}, 支持一层嵌套
    pattern = r"\\boxed\{([^}]*)\}"
    matches = re.findall(pattern, text)
    if matches:
        return matches[-1].strip()
    return None


def extract_final_answer(text: str) -> Optional[str]:
    """尝试多种策略提取最终答案."""
    if not text:
        return None
    # 优先 \boxed
    boxed = extract_boxed_answer(text)
    if boxed:
        return boxed
    # 其次找 "最终答案"、"答案是" 等标记
    markers = ["最终答案", "答案是", "答案为", "answer is", "答案是:", "答案:"]
    for marker in markers:
        idx = text.rfind(marker)
        if idx != -1:
            tail = text[idx + len(marker) :].strip()
            # 取第一行或第一个句号前的内容
            line = tail.split("\n")[0].split("。")[0].strip()
            if line:
                return line
    # 兜底: 取最后一行非空内容
    lines = [ln.strip() for ln in text.strip().split("\n") if ln.strip()]
    if lines:
        return lines[-1]
    return text.strip()


if __name__ == "__main__":
    # 自检: 验证所有内置样例
    test_cases = [
        ("4", "4", {"method": "exact_match"}, True),
        ("210", "210", {"method": "exact_match"}, True),
        ("86.6", "86.6", {"method": "numeric_tolerance", "tolerance": 1e-4}, True),
        ("3/10", "0.3", {"method": "symbolic_equivalence"}, True),
        ("24/5", "4.8", {"method": "numeric_tolerance"}, True),
        ("6,4", "6,4", {"method": "list_match", "ordered": True}, True),
        ("4,6", "6,4", {"method": "list_match", "ordered": False}, True),
        (
            "等号当 a=b=c=1/3 时成立",
            "等号当 a=b=c=1/3 时成立",
            {"method": "contains", "keywords": ["1/3", "a=b=c"]},
            True,
        ),
        # choice_match 自检
        ("C", "(C)10", {"method": "choice_match"}, True),
        ("(C)", "(C)10", {"method": "choice_match"}, True),
        ("10", "(C)10", {"method": "choice_match"}, True),
        ("(C)10", "(C)10", {"method": "choice_match"}, True),
        ("126km", "(A)126km", {"method": "choice_match"}, True),
        ("A", "(A)126km", {"method": "choice_match"}, True),
        ("B", "(C)10", {"method": "choice_match"}, False),
        ("11", "(C)10", {"method": "choice_match"}, False),
        # 更鲁棒的等价形式匹配
        ("27/128", "0.2109", {"method": "exact_match"}, True),
        ("2\\sqrt{3}", "3.46", {"method": "exact_match"}, True),
        ("x=5", "5", {"method": "exact_match"}, True),
        ("5%", "0.05", {"method": "exact_match"}, True),
        ("144\\text{km}", "(A)126km", {"method": "choice_match"}, False),
        # 多词单位归一化
        ("4\\text{ dollars each}", "4", {"method": "exact_match"}, True),
        ("7 平方米", "7", {"method": "exact_match"}, True),
        ("2\\sqrt{3} \\text{ cm}", "2\\sqrt{3}", {"method": "exact_match"}, True),
    ]

    all_pass = True
    for pred, gold, verif, expected in test_cases:
        ok, detail = check_answer(pred, gold, verif)
        status = "PASS" if ok == expected else "FAIL"
        if status == "FAIL":
            all_pass = False
        print(f"[{status}] pred={pred!r}, gold={gold!r}, method={verif['method']}, detail={detail}")

    if all_pass:
        print("\n所有自检通过")
    else:
        print("\n自检存在失败项")
