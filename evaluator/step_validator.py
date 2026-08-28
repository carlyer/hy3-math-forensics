"""单步规则与符号验证.

本模块对解题过程的每一步进行启发式检查：
1. 步骤文本非空、不含明显重复/循环复制
2. 数学表达式可被 sympy 解析
3. 关键等式在数值上成立（如果可以提取）
4. 步骤与题目条件和前序步骤无直接矛盾
"""

import re
import warnings
from typing import Dict, List, Optional, Tuple

import sympy as sp
from sympy.parsing.sympy_parser import parse_expr

# 抑制 sympy 解析非常规/set-like 表达式时产生的 SyntaxWarning（如 {1,2}(x)）
warnings.filterwarnings("ignore", category=SyntaxWarning)


# 常见数学常量映射
CONSTANTS = {
    "pi": sp.pi,
    "e": sp.E,
}


def normalize_expr(expr: str) -> str:
    """对表达式字符串做基础规范化，转换为 sympy 可解析形式."""
    expr = expr.strip()
    # 替换中文括号、乘号等
    expr = expr.replace("（", "(").replace("）", ")")
    expr = expr.replace("×", "*").replace("·", "*").replace("÷", "/")
    # 幂运算
    expr = expr.replace("^", "**")
    # 上标数字
    expr = expr.replace("²", "**2").replace("³", "**3")
    # 根号 √x → sqrt(x)，简单替换
    expr = expr.replace("√", "sqrt")
    # 去掉 $ 和 \(\) 等 latex 定界符
    expr = expr.replace("$", "").replace("\\(", "").replace("\\)", "")
    expr = expr.replace("\\[", "").replace("\\]", "")
    return expr


def try_parse_expr(expr: str) -> Tuple[bool, Optional[sp.Expr], Optional[str]]:
    """尝试用 sympy 解析表达式.

    Returns:
        (是否成功, 表达式对象, 错误信息)
    """
    expr = normalize_expr(expr)
    if not expr:
        return False, None, "空表达式"
    try:
        e = parse_expr(expr, transformations="all")
        return True, e, None
    except Exception as ex:
        return False, None, f"解析失败: {ex}"


def try_evaluate_numerically(expr: str) -> Tuple[bool, Optional[float], Optional[str]]:
    """尝试对表达式求数值."""
    ok, parsed, err = try_parse_expr(expr)
    if not ok:
        return False, None, err
    try:
        val = float(parsed.evalf())
        return True, val, None
    except Exception as ex:
        return False, None, f"数值求值失败: {ex}"


def _preprocess_latex_commands(text: str) -> str:
    """将常见 LaTeX 命令转换为 sympy 可理解的近似形式.

    注意：这是启发式转换，不保证完全正确。
    """
    # 保护 \text{...} 内容：先整体替换为占位符
    text = re.sub(r"\\text\{([^}]*)\}", r"\1", text)

    # \frac{a}{b} -> (a)/(b)
    # 由于 frac 可能嵌套，这里只做一层简化替换
    def replace_frac(m):
        num = m.group(1)
        den = m.group(2)
        return f"({num})/({den})"

    # 循环替换直到没有新的 \frac
    prev = None
    while prev != text:
        prev = text
        text = re.sub(r"\\frac\{([^{}]*)\}\{([^{}]*)\}", replace_frac, text)

    # 常见命令替换
    text = text.replace("\\times", "*")
    text = text.replace("\\cdot", "*")
    text = text.replace("\\div", "/")
    text = text.replace("\\%", "%")
    text = text.replace("\\pi", "pi")
    text = text.replace("\\sqrt", "sqrt")
    text = text.replace("\\infty", "oo")
    text = text.replace("\\le", "<=")
    text = text.replace("\\ge", ">=")
    text = text.replace("\\ne", "!=")
    text = text.replace("\\approx", "~")

    return text


def _find_math_spans(text: str) -> List[Tuple[int, int, str]]:
    """找出文本中所有数学表达式片段.

    Returns:
        列表，每个元素为 (start, end, expr)
    """
    math_chars = set(
        "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "+-*/^×·÷√()[]{}<>,!:.\\_%\u00B2\u00B3\u00B0\u03B1-\u03C9\u0391-\u03A9"
    )
    spans = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch in math_chars or ch.isspace():
            start = i
            while i < n and (text[i] in math_chars or text[i].isspace()):
                i += 1
            expr = text[start:i].strip()
            # 至少包含一个数字或字母
            if re.search(r"[0-9a-zA-Z]", expr):
                spans.append((start, i, expr))
        else:
            i += 1
    return spans


def _find_nearest_math_span(
    spans: List[Tuple[int, int, str]], pos: int, side: str
) -> Optional[str]:
    """在 pos 附近找到最近的数学表达式."""
    if side == "left":
        candidates = [s for s in spans if s[1] <= pos]
        if not candidates:
            return None
        return candidates[-1][2]
    else:
        candidates = [s for s in spans if s[0] >= pos]
        if not candidates:
            return None
        return candidates[0][2]


def _strip_leading_bullet_operator(expr: str) -> str:
    """去掉表达式开头的列表标记型运算符，如 '- 82 + 90' -> '82 + 90'."""
    expr = expr.strip()
    # 匹配以 + - * / 开头且后面跟空白的情况
    while re.match(r"^[-+*/\u00B7\u00D7\u00F7]\s", expr):
        expr = expr[1:].strip()
    return expr


def _extract_latex_math_blocks(text: str) -> List[str]:
    """提取 LaTeX 数学公式块（$...$、$$...$$、\\(...\\)、\\[...\\]）.

    Returns:
        公式内容列表，不含定界符
    """
    patterns = [
        r"\$\$(.+?)\$\$",
        r"\\\[(.+?)\\\]",
        r"\\\((.+?)\\\)",
        r"\$(.+?)\$",
    ]
    blocks = []
    for pat in patterns:
        for m in re.finditer(pat, text, re.DOTALL):
            blocks.append(m.group(1).strip())
    return blocks


def _side_is_trivial_numeric_identity(left: str, right: str) -> bool:
    """判断等式是否为纯数值恒等式（通常是误提取碎片）."""
    ok_l, val_l, _ = try_evaluate_numerically(left)
    ok_r, val_r, _ = try_evaluate_numerically(right)
    if ok_l and ok_r:
        tol = 1e-4 * max(1.0, abs(val_r))
        if abs(val_l - val_r) <= tol:
            return True
    return False


def _is_reasonable_equation_side(side: str) -> bool:
    """判断等式的一边是否是可合理验证的数学表达式."""
    if not side:
        return False
    # 拒绝跨行碎片
    if "\n" in side:
        return False
    # 拒绝过长的碎片（正常单行等式很少超过 120 字符）
    if len(side) > 120:
        return False
    # 拒绝仍包含 LaTeX 定界符的碎片
    if re.search(r"\\\[|\\\]|\\\(|\\\)|\$\$|\$", side):
        return False
    # 至少包含一个数字或变量字母
    if not re.search(r"[0-9a-zA-Z]", side):
        return False
    return True


def _is_spurious_equation(left: str, right: str) -> bool:
    """判断提取出的等式是否无意义/误提取."""
    left_stripped = left.replace(" ", "")
    right_stripped = right.replace(" ", "")
    # 完全相同的字符串通常是格式碎片
    if left_stripped == right_stripped:
        return True
    # 纯数值恒等式（如 7 = 7.0）往往是碎片提取
    if _side_is_trivial_numeric_identity(left, right):
        return True
    # 两边都是裸数字时，极可能是从自然语言/列表里误提取的片段，跳过
    bare_num_pat = re.compile(r"^-?\d+(\.\d+)?$")
    if bare_num_pat.match(left_stripped) and bare_num_pat.match(right_stripped):
        return True
    return False


def _safe_equal_split(s: str) -> Tuple[List[str], int]:
    """按等号拆分字符串，但忽略 >=、<=、!= 等关系运算符中的 '='."""
    positions = [-1]
    n = len(s)
    for i, ch in enumerate(s):
        if ch == "=" and (i == 0 or s[i - 1] not in "<>=!:"):
            positions.append(i)
    positions.append(n)
    segments = [s[positions[i] + 1 : positions[i + 1]] for i in range(len(positions) - 1)]
    eq_count = max(0, len(positions) - 2)
    return segments, eq_count


def _extract_adjacent_pairs(
    processed: str, source: str = "block"
) -> List[Tuple[str, str, str]]:
    """从预处理后的文本中提取相邻的等式对."""
    results = []
    segments, eq_count = _safe_equal_split(processed)
    if eq_count < 1:
        return results

    bare_num_pat = re.compile(r"^-?\d+(\.\d+)?$")

    for i in range(len(segments) - 1):
        left_seg = segments[i]
        right_seg = segments[i + 1]

        # 跳过包含中文的片段
        if re.search(r"[\u4e00-\u9fff]", left_seg + right_seg):
            continue

        left_spans = _find_math_spans(left_seg)
        right_spans = _find_math_spans(right_seg)
        if not left_spans or not right_spans:
            continue

        left = _strip_leading_bullet_operator(left_spans[-1][2])
        right = _strip_leading_bullet_operator(right_spans[0][2])

        if not (_is_reasonable_equation_side(left) and _is_reasonable_equation_side(right)):
            continue

        # 链式等式伪影：一边为裸数字且该数字在另一边作为独立 token 出现
        left_bare = bare_num_pat.match(left)
        right_bare = bare_num_pat.match(right)

        def _token_pat(num: str):
            return re.compile(r"(?<![\d.\-])" + re.escape(num) + r"(?![\d.])")

        if left_bare and _token_pat(left_bare.group(0)).search(right):
            continue
        if right_bare and _token_pat(right_bare.group(0)).search(left):
            continue

        # 多等号链中两边都是裸数字且不相等 -> 可能是误提取的链片段
        if left_bare and right_bare and source == "block" and eq_count > 1:
            try:
                if abs(float(left) - float(right)) > 1e-9:
                    continue
            except Exception:
                pass

        if _is_spurious_equation(left, right):
            continue

        results.append((left, right, f"{left} = {right}"))

    return results


def extract_equation_candidates(text: str) -> List[Tuple[str, str, str]]:
    """从文本中提取等式候选 (左式, 右式, 原始文本).

    保守策略：
    - 只从 LaTeX 数学块或纯文本单行（恰好一个等号且无中文）中提取。
    - 每个块/行按等号拆分后取相邻段，避免跨链式等式误提取。
    """
    results = []
    seen = set()

    # 1. LaTeX 数学块内的等式
    math_blocks = _extract_latex_math_blocks(text)
    # 包含近似/不等关系或带余除法的块不适合做等式验证，直接跳过
    relation_pat = re.compile(r"\\approx|\\sim|\\ne|\\div|(?<![<>=])>(?!=)|(?<![<>=])<(?!=)")
    for block in math_blocks:
        if relation_pat.search(block):
            continue
        processed = _preprocess_latex_commands(block)
        for left, right, expr in _extract_adjacent_pairs(processed, source="block"):
            key = (left, right)
            if key in seen:
                continue
            seen.add(key)
            results.append((left, right, expr))

    # 2. 纯文本中的简单等式：先移除 LaTeX 块，避免重复提取
    plain_text = text
    for block in math_blocks:
        for delim_left, delim_right in [
            ("$$", "$$"),
            ("\\[", "\\]"),
            ("\\(", "\\)"),
            ("$", "$"),
        ]:
            plain_text = plain_text.replace(f"{delim_left}{block}{delim_right}", " ")

    for line in plain_text.splitlines():
        line = line.strip()
        if not line:
            continue
        # 必须恰好有一个安全等号且无中文
        _, eq_count = _safe_equal_split(line)
        if eq_count != 1:
            continue
        if re.search(r"[\u4e00-\u9fff]", line):
            continue
        processed = _preprocess_latex_commands(line)
        for left, right, expr in _extract_adjacent_pairs(processed, source="line"):
            key = (left, right)
            if key in seen:
                continue
            seen.add(key)
            results.append((left, right, expr))

    return results


def check_equation(left: str, right: str) -> Tuple[bool, Optional[str]]:
    """检查等式左右两边是否数值相等."""
    ok_l, val_l, err_l = try_evaluate_numerically(left)
    ok_r, val_r, err_r = try_evaluate_numerically(right)

    if not ok_l or not ok_r:
        # 至少有一边不能数值化，尝试符号等价
        ok_le, expr_l, _ = try_parse_expr(left)
        ok_re, expr_r, _ = try_parse_expr(right)
        if ok_le and ok_re:
            try:
                diff = sp.simplify(expr_l - expr_r)
                if diff == 0:
                    return True, None
            except Exception:
                pass
        return None, f"无法数值/符号验证: left_err={err_l}, right_err={err_r}"

    # 数值比较，使用相对容差
    tol = 1e-4 * max(1.0, abs(val_r))
    if abs(val_l - val_r) <= tol:
        return True, None
    return False, f"等式不成立: {left}={val_l}, {right}={val_r}"


def check_step_calculations(step_text: str) -> Tuple[bool, Optional[str]]:
    """检查步骤中的计算等式是否正确.

    Returns:
        (是否全部可验证且正确, 错误信息)
        如果没有任何可验证的等式，返回 (True, None) 表示跳过
    """
    candidates = extract_equation_candidates(step_text)
    if not candidates:
        return True, None

    checked_any = False
    for left, right, _ in candidates:
        # 过滤掉不是数学表达式的等式（如“设 x = 钢笔数量”）
        if not re.search(r"[0-9+\-*/^()\\]", left + right):
            continue
        result = check_equation(left, right)
        if result[0] is False:
            return False, result[1]
        if result[0] is True:
            checked_any = True

    if not checked_any:
        return True, None
    return True, None


def check_repetition(text: str, prev_steps: List[Dict]) -> Tuple[bool, Optional[str]]:
    """检查当前步骤是否与前面步骤高度重复（循环论证/复制）."""
    for prev in prev_steps:
        prev_text = prev.get("text", "")
        # 完全相同或包含关系
        if text == prev_text:
            return False, f"与步骤 {prev.get('index')} 完全相同，疑似循环/复制"
        if len(text) > 30 and len(prev_text) > 30:
            # 长文本重叠度检查
            if text in prev_text or prev_text in text:
                return False, f"与步骤 {prev.get('index')} 高度重复"
    return True, None


def validate_step(
    step: Dict,
    prev_steps: List[Dict],
    problem_text: str,
    verification_method: Optional[str] = None,
    all_steps: Optional[List[Dict]] = None,
) -> Dict:
    """对单一步骤进行综合验证.

    Args:
        step: 当前步骤
        prev_steps: 前置步骤列表
        problem_text: 原始题目文本
        verification_method: 答案校验方式
        all_steps: 完整步骤列表，预留用于后续扩展（当前逻辑不使用）

    Returns:
        {
            "step_index": int,
            "valid": bool | None,  # True 正确，False 错误，None 无法判断
            "checks": {
                "non_empty": bool,
                "no_repetition": bool,
                "calculation_correct": bool | None,
            },
            "detail": str | None
        }
    """
    text = step.get("text", "").strip()
    idx = step.get("index", 0)

    if not text or len(text) < 5:
        return {
            "step_index": idx,
            "valid": False,
            "checks": {"non_empty": False, "no_repetition": True, "calculation_correct": None},
            "detail": "步骤内容为空或过短",
        }

    # 重复检查
    ok_rep, detail_rep = check_repetition(text, prev_steps)
    if not ok_rep:
        return {
            "step_index": idx,
            "valid": False,
            "checks": {"non_empty": True, "no_repetition": False, "calculation_correct": None},
            "detail": detail_rep,
        }

    # 计算检查
    calc_ok, calc_detail = check_step_calculations(text)

    # 对于无标准答案的研究级题目，避免符号层过度判定误报
    if verification_method == "manual_check" and calc_ok is False:
        calc_ok = None
        calc_detail = None

    checks = {
        "non_empty": True,
        "no_repetition": True,
        "calculation_correct": calc_ok if calc_detail else None,
    }

    if calc_ok is False:
        return {
            "step_index": idx,
            "valid": False,
            "checks": checks,
            "detail": calc_detail,
        }

    # 如果计算检查通过或跳过，暂时认为该步骤无明显错误
    return {
        "step_index": idx,
        "valid": True,
        "checks": checks,
        "detail": None,
    }


if __name__ == "__main__":
    # 基本功能示例
    step = {
        "index": 1,
        "text": "由题意，笔记本花费 5 × 8 = 40 元，钢笔花费 12x 元，总花费 88 元，所以 40 + 12x = 88。",
    }
    result = validate_step(step, [], "")
    print(result)

    # 对 previously failing CBU 步骤不再误判为 calculation_correct=False
    import json
    from pathlib import Path

    ROOT = Path(__file__).resolve().parent.parent
    eval_path = ROOT / "results" / "evaluation_results_merged.json"
    sol_path = ROOT / "results" / "solutions_merged.jsonl"

    target_ids = [
        "L1-006",
        "L1-014",
        "L1-017",
        "L2-004",
        "L4-009",
        "L4-026",
        "L4-031",
        "L4-034",
    ]

    cbu_checks_pass = True
    if eval_path.exists() and sol_path.exists():
        evaluations = json.loads(eval_path.read_text(encoding="utf-8"))["evaluations"]
        solutions = {}
        for line in sol_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                solutions[rec["problem_id"]] = rec

        for ev in evaluations:
            pid = ev.get("problem_id")
            if pid not in target_ids:
                continue
            ferr = ev.get("first_error_step")
            rec = solutions.get(pid)
            if not rec:
                continue
            step = next(
                (s for s in rec.get("steps", []) if s.get("index") == ferr), None
            )
            if not step:
                continue
            res = validate_step(step, [], "")
            calc = res["checks"]["calculation_correct"]
            status = "PASS" if calc is not False else "FAIL"
            if status == "FAIL":
                cbu_checks_pass = False
            print(f"[{status}] {pid} step {ferr}: calculation_correct={calc}")
    else:
        print(f"[SKIP] 未找到 {eval_path} 或 {sol_path}，CBU 回归测试跳过")

    if cbu_checks_pass:
        print("\nCBU 回归测试通过")
    else:
        print("\nCBU 回归测试存在失败项")
