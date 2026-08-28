r"""回代验证器.

把模型输出的最终答案代回原题的数学约束，做纯符号/数值验证：
- 方程/等式：验证左右两边是否相等；
- 不等式/约束：验证是否满足所有不等式；
- 最值/优化：至少验证答案满足约束或在临界点；
- 多解/计数：给出启发式提示，标记为需人工确认；
- 无法自动处理时优雅降级，返回 verifiable=false。

整个模块不调用 LLM，仅使用 sympy 做确定性计算。
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import warnings
from typing import Any, Dict, List, Optional, Tuple, Union

import sympy as sp
from sympy.logic.boolalg import BooleanFalse, BooleanTrue
from sympy.parsing.latex import parse_latex

from dataset.answer_checker import _is_latex, _to_sympy, normalize_answer

warnings.filterwarnings("ignore", category=SyntaxWarning)

# 题型关键词
_OPTIMIZATION_MAX_KWS = ["最大值", "最大", "极大值", "极大", "maximize", "maximum", "max"]
_OPTIMIZATION_MIN_KWS = ["最小值", "最小", "极小值", "极小", "minimize", "minimum", "min"]
_MULTI_SOLUTION_KWS = [
    "所有解",
    "全部解",
    "解的个数",
    "有多少个",
    "有多少",
    "个数",
    "正整数解",
    "整数解",
    "解集",
]

_TOLERANCE = 1e-4


def _preprocess_plain_expr(expr_str: str) -> str:
    """对纯文本数学表达式做简单规范化，便于 sympy 解析.

    - 将 ^ 替换为 **
    - 补上隐式乘法：2x -> 2*x, 3(x+1) -> 3*(x+1)
    """
    s = expr_str.replace("^", "**")
    # 数字/右括号 后面跟 字母/左括号
    s = re.sub(r"(\d|[a-zA-Z)])([(a-zA-Z])", r"\1*\2", s)
    return s


def _safe_to_sympy(expr_str: str) -> Optional[sp.Expr]:
    """尝试把字符串解析为 sympy 表达式，先按 LaTeX 再按普通表达式."""
    if not expr_str:
        return None
    if _is_latex(expr_str):
        try:
            return parse_latex(expr_str)
        except Exception:
            pass
    return _to_sympy(_preprocess_plain_expr(expr_str))


def _parse_relation(segment: str) -> Optional[Union[sp.Rel, sp.Equality]]:
    """把一段文本解析成 sympy 关系对象（等式或不等式）."""
    segment = normalize_answer(segment).strip()
    if not segment:
        return None

    # 去除题目中的中文字符，保留数学符号与表达式
    segment = re.sub(r"[\u4e00-\u9fff]+", "", segment).strip()
    if not segment:
        return None

    # 优先尝试 LaTeX 整体解析（可处理 \leq、\geq、\frac 等）
    if _is_latex(segment):
        try:
            rel = parse_latex(segment)
            if isinstance(rel, (sp.Rel, sp.Equality)):
                return rel
        except Exception:
            pass

    # 普通文本：统一不等号并去除多余标点/空白
    s = segment.replace("≤", "<=").replace("≥", ">=")
    s = s.replace("＜", "<").replace("＞", ">")
    s = re.sub(r"[^0-9a-zA-Z+\-*/=<>().^]+", "", s)
    if not s:
        return None

    ops = [
        ("<=", sp.Le),
        (">=", sp.Ge),
        ("!=", sp.Ne),
        ("<", sp.Lt),
        (">", sp.Gt),
        ("=", sp.Eq),
    ]

    for op, cls in ops:
        if op in s:
            lhs_str, rhs_str = s.split(op, 1)
            lhs = _safe_to_sympy(lhs_str)
            rhs = _safe_to_sympy(rhs_str)
            if lhs is None or rhs is None:
                continue
            try:
                return cls(lhs, rhs)
            except Exception:
                continue
    return None


def _extract_math_segments(text: str) -> List[str]:
    r"""从题目文本中提取可能包含数学关系的片段.

    优先提取 $...$、\(...\)、\[...\] 中的内容，再对剩余文本按句切分。
    """
    text = normalize_answer(text)
    segments: List[str] = []

    # LaTeX / markdown 数学环境
    math_patterns = [
        r"\$\$(.+?)\$\$",
        r"\$(.+?)\$",
        r"\\\[(.+?)\\\]",
        r"\\\((.+?)\\\)",
    ]
    for pat in math_patterns:
        for m in re.finditer(pat, text, re.DOTALL):
            seg = m.group(1).strip()
            if seg:
                segments.append(seg)

    # 按中文标点与换行切分剩余文本
    for seg in re.split(r"[。；;\n]", text):
        seg = seg.strip()
        if not seg:
            continue
        # 包含关系运算符或 LaTeX 不等号命令
        if re.search(
            r"(?<![<>=!])=(?![<>=])|[<>≤≥]|\\leq|\\geq|\\le|\\ge|\\neq",
            seg,
        ):
            segments.append(seg)

    return segments


def _extract_constraints(problem_text: str) -> List[Union[sp.Rel, sp.Equality]]:
    """提取题目中的全部可解析约束."""
    constraints: List[Union[sp.Rel, sp.Equality]] = []
    seen: set = set()
    for seg in _extract_math_segments(problem_text):
        # 一个片段中可能包含多个等式/不等式（用逗号/分号分隔）
        for sub in re.split(r"[，,；;]", seg):
            rel = _parse_relation(sub)
            if rel is None:
                continue
            key = str(rel)
            if key not in seen:
                seen.add(key)
                constraints.append(rel)
    return constraints


def _free_symbols_of_constraints(
    constraints: List[Union[sp.Rel, sp.Equality]],
) -> List[sp.Symbol]:
    """返回约束中所有自由符号的有序列表."""
    symbols: set = set()
    for c in constraints:
        try:
            symbols.update(c.free_symbols)
        except Exception:
            pass
    return sorted(symbols, key=lambda x: str(x))


def _extract_boxed_answer(text: str) -> Optional[str]:
    """提取 \\boxed{...} 中的答案，支持嵌套大括号."""
    if not text:
        return None
    idx = text.rfind("\\boxed{")
    if idx == -1:
        return None
    start = idx + len("\\boxed{")
    depth = 1
    end = start
    while end < len(text) and depth > 0:
        if text[end] == "{":
            depth += 1
        elif text[end] == "}":
            depth -= 1
        end += 1
    if depth == 0:
        return text[start : end - 1].strip()
    return None


def _strip_answer_wrappers(answer: str) -> str:
    r"""去除答案外的 \boxed{}、单位、末尾标点等包装."""
    if not answer:
        return ""
    boxed = _extract_boxed_answer(answer)
    if boxed is not None:
        s = boxed
    else:
        s = normalize_answer(answer)
    # 去掉末尾常见标点
    s = re.sub(r"[。，,;；！!？?]+$", "", s).strip()
    return s


def _parse_substitutions(
    answer: str, expected_symbols: List[sp.Symbol]
) -> Dict[sp.Symbol, sp.Expr]:
    """从最终答案中提取变量赋值.

    支持：x=5、(x,y)=(2,3)、\frac{a}{b}=...、裸数值（单变量时自动对应）等。
    """
    s = _strip_answer_wrappers(answer)
    if not s:
        return {}

    subs: Dict[sp.Symbol, sp.Expr] = {}

    # 1. (x, y) = (2, 3) 形式
    tuple_match = re.search(
        r"[\(（]\s*([a-zA-Z][a-zA-Z0-9]*(?:\s*,\s*[a-zA-Z][a-zA-Z0-9]*)*)\s*[\)）]\s*=\s*[\(（]([^\)）]+)[\)）]",
        s,
    )
    if tuple_match:
        vars_ = [v.strip() for v in tuple_match.group(1).split(",")]
        vals = [v.strip() for v in tuple_match.group(2).split(",")]
        for var_name, val_str in zip(vars_, vals):
            val = _safe_to_sympy(val_str)
            if val is not None:
                subs[sp.Symbol(var_name)] = val
        return subs

    # 2. 多个 x=...、y=... 赋值
    for m in re.finditer(r"([a-zA-Z][a-zA-Z0-9]*)\s*=\s*([^,;，。]+)", s):
        var_name = m.group(1)
        val_str = m.group(2).strip()
        val = _safe_to_sympy(val_str)
        if val is not None:
            subs[sp.Symbol(var_name)] = val
    if subs:
        return subs

    # 3. 裸数值/表达式：单变量直接对应，多变量尝试按逗号拆分
    expr = _safe_to_sympy(s)
    if expr is not None:
        if isinstance(expr, sp.Tuple):
            for sym, val in zip(expected_symbols, expr):
                subs[sym] = val
        elif len(expected_symbols) == 1:
            subs[expected_symbols[0]] = expr
        else:
            parts = [p.strip() for p in re.split(r"[,，、]", s) if p.strip()]
            if len(parts) == len(expected_symbols):
                for sym, part in zip(expected_symbols, parts):
                    val = _safe_to_sympy(part)
                    if val is not None:
                        subs[sym] = val
    return subs


def _evaluate_substituted_constraint(
    constraint: Union[sp.Rel, sp.Equality], subs: Dict[sp.Symbol, sp.Expr]
) -> Tuple[bool, bool]:
    """把约束代入后判断真假.

    Returns:
        (可判断, 为真)
    """
    try:
        substituted = constraint.subs(subs)
        if isinstance(substituted, (BooleanTrue, BooleanFalse)):
            return True, bool(substituted)

        simplified = sp.simplify(substituted)
        if isinstance(simplified, (BooleanTrue, BooleanFalse)):
            return True, bool(simplified)

        # 对数值关系做容差判断
        if isinstance(constraint, sp.Eq):
            diff = (constraint.lhs - constraint.rhs).subs(subs)
            diff_simpl = sp.simplify(diff)
            if diff_simpl.is_number:
                return True, bool(abs(complex(diff_simpl.evalf())) < _TOLERANCE)
            return False, False

        # 不等式：尝试数值化
        if hasattr(constraint, "lhs") and hasattr(constraint, "rhs"):
            diff = (constraint.lhs - constraint.rhs).subs(subs)
            diff_simpl = sp.simplify(diff)
            if diff_simpl.is_number:
                val = float(diff_simpl.evalf())
                if isinstance(constraint, (sp.Lt, sp.Le)):
                    return True, val < _TOLERANCE
                if isinstance(constraint, (sp.Gt, sp.Ge)):
                    return True, val > -_TOLERANCE
                if isinstance(constraint, sp.Ne):
                    return True, abs(val) > _TOLERANCE
        return False, False
    except Exception:
        return False, False


def _detect_problem_type(problem_text: str) -> str:
    """根据题目文本启发式判断题型."""
    t = problem_text
    if any(kw in t for kw in _MULTI_SOLUTION_KWS):
        return "multi_solution"
    if any(kw in t for kw in _OPTIMIZATION_MAX_KWS + _OPTIMIZATION_MIN_KWS):
        return "optimization"

    tmp = t.replace("≤", "<=").replace("≥", ">=")
    if re.search(r"(?<![<>=!])>(?![=])|(?<![<>=!])<(?![=])|<=|>=", tmp):
        return "inequality"

    if "=" in tmp:
        return "equation"

    return "unknown"


def _extract_objective(text: str) -> Optional[sp.Expr]:
    """尝试从 '求 ... 的最大值/最小值' 中提取目标函数."""
    t = normalize_answer(text)
    marker_positions: List[Tuple[int, str]] = []
    for kw in _OPTIMIZATION_MAX_KWS + _OPTIMIZATION_MIN_KWS:
        idx = t.find(kw)
        if idx != -1:
            marker_positions.append((idx, kw))
    if not marker_positions:
        return None
    marker_positions.sort(key=lambda x: x[0])
    end = marker_positions[0][0]
    candidate = t[:end]
    # 去除前导中文/非数学字符
    candidate = re.sub(r"^[^0-9a-zA-Z\(\)\[\]\{\}\\\-\+\*/\^\.]+", "", candidate)
    # 去除剩余中文字符，保留数学表达式
    candidate = re.sub(r"[\u4e00-\u9fff]+", "", candidate).strip()
    if not candidate:
        return None

    expr = _safe_to_sympy(candidate)
    if expr is not None and not isinstance(expr, (sp.Rel, sp.Equality)):
        return expr

    # 形如 f(x)=x^2 时，等号右侧才是真正的目标函数
    if "=" in candidate:
        rhs = candidate.split("=", 1)[1].strip()
        expr = _safe_to_sympy(rhs)
        if expr is not None and not isinstance(expr, (sp.Rel, sp.Equality)):
            return expr
    return None


def _is_maximization(text: str) -> bool:
    """判断是否为求最大值."""
    return any(kw in text for kw in _OPTIMIZATION_MAX_KWS)


def _build_result(
    verifiable: bool,
    verified: Optional[bool],
    method: str,
    detail: str,
    constraints: List[Union[sp.Rel, sp.Equality]],
    subs: Dict[sp.Symbol, sp.Expr],
) -> Dict[str, Any]:
    return {
        "verifiable": verifiable,
        "verified": verified,
        "method": method,
        "detail": detail,
        "extracted_constraints": [str(c) for c in constraints],
        "substituted_values": {str(k): str(v) for k, v in subs.items()},
    }


def verify_by_substitution(
    problem_text: str,
    final_answer: Optional[str],
    expected_type: str = "auto",
) -> Dict[str, Any]:
    """把最终答案代回原题约束做确定性验证.

    Args:
        problem_text: 原始题目文本.
        final_answer: 模型输出的最终答案.
        expected_type: 期望题型（auto/equation/inequality/optimization/multi_solution/unknown）.

    Returns:
        统一结构的验证结果字典.
    """
    if not problem_text or not final_answer:
        return _build_result(
            False,
            None,
            "none",
            "题目或答案为空，无法回代验证",
            [],
            {},
        )

    if expected_type == "auto":
        expected_type = _detect_problem_type(problem_text)

    constraints = _extract_constraints(problem_text)
    symbols = _free_symbols_of_constraints(constraints)
    subs = _parse_substitutions(str(final_answer), symbols)

    # 方程/等式验证
    if expected_type == "equation":
        equations = [c for c in constraints if isinstance(c, sp.Eq)]
        if not equations:
            return _build_result(
                False,
                None,
                "equation",
                "未能从题目中提取到可解析的等式",
                constraints,
                subs,
            )

        evaluated = 0
        true_count = 0
        false_count = 0
        details: List[str] = []
        for eq in equations:
            decidable, holds = _evaluate_substituted_constraint(eq, subs)
            if not decidable:
                details.append(f"{eq}: 代入后仍含自由变量，无法判定")
                continue
            evaluated += 1
            if holds:
                true_count += 1
                details.append(f"{eq}: 成立")
            else:
                false_count += 1
                details.append(f"{eq}: 不成立")

        if false_count > 0:
            return _build_result(
                True,
                False,
                "equation",
                "；".join(details),
                equations,
                subs,
            )
        if evaluated > 0 and true_count == evaluated:
            return _build_result(
                True,
                True,
                "equation",
                "所有提取到的等式在答案处均成立",
                equations,
                subs,
            )
        return _build_result(
            False,
            None,
            "equation",
            "提取到等式，但代入后无法数值/符号判定；".join(details),
            equations,
            subs,
        )

    # 不等式/约束验证
    if expected_type == "inequality":
        inequalities = [c for c in constraints if not isinstance(c, sp.Eq)]
        if not inequalities:
            inequalities = constraints
        if not inequalities:
            return _build_result(
                False,
                None,
                "inequality",
                "未能从题目中提取到可解析的不等式约束",
                constraints,
                subs,
            )

        evaluated = 0
        true_count = 0
        false_count = 0
        details: List[str] = []
        for ineq in inequalities:
            decidable, holds = _evaluate_substituted_constraint(ineq, subs)
            if not decidable:
                details.append(f"{ineq}: 代入后仍含自由变量，无法判定")
                continue
            evaluated += 1
            if holds:
                true_count += 1
                details.append(f"{ineq}: 满足")
            else:
                false_count += 1
                details.append(f"{ineq}: 不满足")

        if false_count > 0:
            return _build_result(
                True,
                False,
                "inequality",
                "；".join(details),
                inequalities,
                subs,
            )
        if evaluated > 0 and true_count == evaluated:
            return _build_result(
                True,
                True,
                "inequality",
                "所有提取到的不等式约束在答案处均满足",
                inequalities,
                subs,
            )
        return _build_result(
            False,
            None,
            "inequality",
            "代入后无法完全判定不等式约束；".join(details),
            inequalities,
            subs,
        )

    # 最值/优化验证：至少验证约束满足或临界点
    if expected_type == "optimization":
        objective = _extract_objective(problem_text)
        is_max = _is_maximization(problem_text)

        evaluated = 0
        true_count = 0
        false_count = 0
        for c in constraints:
            decidable, holds = _evaluate_substituted_constraint(c, subs)
            if not decidable:
                continue
            evaluated += 1
            if holds:
                true_count += 1
            else:
                false_count += 1

        constraints_ok = evaluated > 0 and false_count == 0
        detail_parts: List[str] = []
        if evaluated:
            detail_parts.append(f"约束满足 {true_count}/{evaluated}")
        else:
            detail_parts.append("未提取到可判定的约束")

        critical = False
        if objective is not None and subs:
            try:
                free_vars = list(objective.free_symbols)
                # 只处理单变量目标函数，避免高维优化误报
                if len(free_vars) == 1:
                    var = free_vars[0]
                    val = subs.get(var)
                    if val is not None and val.is_number:
                        derivative = sp.diff(objective, var)
                        df_val = sp.simplify(derivative.subs(subs)).evalf()
                        if df_val.is_number and abs(complex(df_val)) < _TOLERANCE:
                            critical = True
                            detail_parts.append(
                                f"目标函数 {objective} 在 {var}={val} 处导数为 0（临界点）"
                            )
                        else:
                            obj_val = sp.simplify(objective.subs(subs)).evalf()
                            detail_parts.append(
                                f"目标函数 {objective} 在答案处取值为 {obj_val}"
                            )
            except Exception:
                pass

        if false_count > 0:
            return _build_result(
                True,
                False,
                "optimization",
                "；".join(detail_parts),
                constraints,
                subs,
            )

        # 只要有约束满足或存在临界点，就认为通过基础验证
        verified = constraints_ok or critical
        return _build_result(
            True,
            verified,
            "optimization",
            "；".join(detail_parts)
            + (
                "。注意：此验证不保证全局最优性，仅确认约束/临界点。"
                if verified
                else ""
            ),
            constraints,
            subs,
        )

    # 多解/计数题：目前仅给出启发式提示
    if expected_type == "multi_solution":
        return _build_result(
            False,
            None,
            "multi_solution_heuristic",
            "多解/计数题暂不支持自动回代验证，建议人工核对解的个数/范围",
            constraints,
            subs,
        )

    # 未知 / 无法自动处理
    return _build_result(
        False,
        None,
        "unknown",
        "未能识别可自动回代验证的数学结构",
        constraints,
        subs,
    )


if __name__ == "__main__":
    # 自检示例
    test_cases = [
        # (problem_text, final_answer, expected_type, expected_verified)
        ("若 x+2=5，求 x。", "x=3", "auto", True),
        ("解方程 2x-1=7。", "4", "auto", True),
        ("解方程 x^2-5x+6=0。", "x=2", "auto", True),
        ("已知 x+y=5，x-y=1，求 x,y。", "(x,y)=(3,2)", "auto", True),
        ("若 x>1，判断 x=2 是否满足。", "2", "inequality", True),
        ("求函数 f(x)=x^2 的最小值。", "x=0", "optimization", True),
        ("求所有满足 x^2=4 的整数解。", "x=2", "multi_solution", None),
        ("三角形内角和是多少度？", "180", "auto", None),  # 无数学约束，无法自动验证
    ]

    all_pass = True
    for problem, answer, exp_type, expected in test_cases:
        result = verify_by_substitution(problem, answer, expected_type=exp_type)
        verified = result.get("verified")
        status = "PASS" if verified == expected else "FAIL"
        if status == "FAIL":
            all_pass = False
        print(
            f"[{status}] type={exp_type}, verified={verified}, expected={expected}, "
            f"detail={result['detail']}"
        )

    if all_pass:
        print("\n所有自检通过")
    else:
        print("\n自检存在失败项")
