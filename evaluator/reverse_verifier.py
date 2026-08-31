"""Math-Shepherd 风格反向验证器（推理时步骤级奖励评分，无需训练）.

核心思想（Wang et al. 2023, Math-Shepherd）：
一个步骤的"好坏"不由裁判主观判断，而由**该步骤之后的推理到达正确答案的经验概率**决定。

对一条解答的步骤序列 s1..sn：
1. 选取若干前缀采样点（首步、中间均匀取点、末步，最多 max_prefixes 个）；
2. 对每个前缀 (s1..si)，把"题目 + 已有步骤（声称为正确步骤）"作为上下文，
   让 Hy3 以 temperature≈0.7 续写采样 N 次后续推理；
3. 每次续写提取最终答案，用 dataset/answer_checker 与 gold_answer 比对，
   步骤 i 的奖励分 = N 次续写中到达正确答案的比例（hard estimation）；
4. 若前缀已包含全部步骤（末步），不再采样，直接比对该解答自己的 final_answer；
5. 聚合：
   - min/mean 分；
   - 首错步定位 = 分数骤降（从前缀分 >= drop_high 跌到 < drop_low）的第一个步骤；
   - 过程判错 = min 分低于 process_threshold。

用法:
    from app.hy3_client import load_client_from_env
    from evaluator.reverse_verifier import ReverseVerifier

    verifier = ReverseVerifier(load_client_from_env())
    result = verifier.verify_solution(record)
"""

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

from dataset.answer_checker import check_answer, extract_final_answer

logger = logging.getLogger(__name__)


def _extract_boxed_nested(text: str) -> Optional[str]:
    """提取 \\boxed{...} 内容（支持任意层花括号嵌套）.

    answer_checker.extract_boxed_answer 的 `[^}]*` 正则无法处理嵌套
    （如 \\boxed{\\frac{1}{2}} 会被截断为 \\frac{1），这里用括号计数实现，
    仅用于续写输出的答案提取，不改动 answer_checker 的既有行为。
    """
    if not text:
        return None
    result = None
    for m in re.finditer(r"\\boxed\{", text):
        depth = 1
        i = m.end()
        while i < len(text) and depth > 0:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        if depth == 0:
            result = text[m.end() : i - 1].strip()
    return result


def extract_continuation_answer(text: str) -> Optional[str]:
    """从续写输出中提取最终答案：优先嵌套感知的 boxed，其次通用提取."""
    boxed = _extract_boxed_nested(text)
    if boxed:
        return boxed
    return extract_final_answer(text)


# 续写 prompt：声明已有步骤为"正确步骤"，要求从下一步继续
CONTINUATION_SYSTEM_PROMPT = """你是一位极其严谨的数学解题专家。用户会给你一道数学题目和本题已有的若干正确解题步骤。你的任务是信任这些已有步骤，从下一步开始继续完成剩余解题过程。

要求：
1. 不要重复已有步骤的内容，直接从下一步继续推导；
2. 每一步推导必须写明依据（定义、公理、定理、公式或前一步结论）；
3. 中间计算必须准确，注意符号、单位和边界条件；
4. 最后必须用 \\boxed{...} 给出最终答案。

请用中文输出完整解题过程。"""


def select_prefix_indices(n_steps: int, max_prefixes: int) -> List[int]:
    """选取前缀采样点：首步、末步 + 中间均匀取点.

    Args:
        n_steps: 解答总步数
        max_prefixes: 最多采样前缀数（控制每题调用量 = 前缀数 × N）

    Returns:
        升序的步骤编号列表（1-based），最后一个元素恒为 n_steps
    """
    if n_steps <= 0:
        return []
    if n_steps <= max_prefixes:
        return list(range(1, n_steps + 1))
    # 在 [1, n_steps] 上均匀取 max_prefixes 个点，去重后保持升序
    idxs = sorted(
        {round(1 + i * (n_steps - 1) / (max_prefixes - 1)) for i in range(max_prefixes)}
    )
    # 去重可能导致点数不足，从缺口处补齐
    if len(idxs) < max_prefixes:
        for cand in range(1, n_steps + 1):
            if len(idxs) >= max_prefixes:
                break
            if cand not in idxs:
                idxs.append(cand)
        idxs.sort()
    return idxs


def build_continuation_messages(
    problem: str, steps: List[Dict], upto: int
) -> List[Dict]:
    """构建续写 prompt 的 chat messages.

    Args:
        problem: 题目文本
        steps: 全部步骤（含 index/text 字段）
        upto: 前缀截止步骤编号（1-based，含）
    """
    prefix = [s for s in steps if s.get("index", 0) <= upto]
    # 若步骤没有 index 字段，则按顺序取前 upto 个
    if not prefix:
        prefix = steps[:upto]
    prefix_text = "\n\n".join(
        f"步骤 {s.get('index', i + 1)}：{s.get('text', '')}"
        for i, s in enumerate(prefix)
    )
    next_idx = prefix[-1].get("index", len(prefix)) + 1
    user = (
        f"题目：\n{problem}\n\n"
        f"以下是本题已有的正确解题步骤：\n{prefix_text}\n\n"
        f"请从步骤 {next_idx} 开始继续完成剩余解题过程，"
        f"最后必须用 \\boxed{{}} 给出最终答案。"
    )
    return [
        {"role": "system", "content": CONTINUATION_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


class ReverseVerifier:
    """Math-Shepherd 风格反向验证器."""

    def __init__(
        self,
        client,
        n_samples: int = 4,
        max_prefixes: int = 6,
        temperature: float = 0.7,
        top_p: float = 0.9,
        max_tokens: int = 1536,
        drop_high: float = 0.5,
        drop_low: float = 0.25,
        process_threshold: float = 0.25,
        max_retries: int = 2,
    ):
        """初始化.

        Args:
            client: Hy3MathClient 实例（复用 app/hy3_client）
            n_samples: 每个前缀的续写采样次数 N
            max_prefixes: 每题最多采样前缀数（首步+末步+中间均匀取点）
            temperature: 续写采样温度
            top_p: 续写采样 top_p
            max_tokens: 续写最大 token 数
            drop_high: 分数骤降判定的高水位（此前缀分 >= 该值）
            drop_low: 分数骤降判定的低水位（跌到 < 该值视为首错步）
            process_threshold: 过程判错阈值（min 分 < 该值判过程错误）
            max_retries: 单次调用失败重试次数
        """
        self.client = client
        self.n_samples = n_samples
        self.max_prefixes = max_prefixes
        self.temperature = temperature
        self.top_p = top_p
        self.max_tokens = max_tokens
        self.drop_high = drop_high
        self.drop_low = drop_low
        self.process_threshold = process_threshold
        self.max_retries = max_retries

    # ------------------------------------------------------------------
    # 单次续写采样
    # ------------------------------------------------------------------
    def _run_continuation_job(self, job: Dict) -> Dict:
        """执行一次续写采样并与 gold 比对.

        job 字段: problem_id, problem, steps, upto, sample_idx, gold_answer, verification
        """
        upto = job["upto"]
        gold = job["gold_answer"]
        verification = job.get("verification") or {"method": "exact_match"}
        messages = build_continuation_messages(job["problem"], job["steps"], upto)

        last_err = None
        for attempt in range(self.max_retries + 1):
            try:
                results = self.client.chat_generate(
                    [messages],
                    temperature=self.temperature,
                    top_p=self.top_p,
                    max_tokens=self.max_tokens,
                )
                text = results[0].get("text", "")
                pred = extract_continuation_answer(text)
                ok, detail = check_answer(pred, gold, verification)
                return {
                    "problem_id": job["problem_id"],
                    "upto": upto,
                    "sample_idx": job["sample_idx"],
                    "pred_answer": pred,
                    "correct": bool(ok),
                    "check_detail": detail,
                    "finish_reason": results[0].get("finish_reason"),
                }
            except Exception as e:  # noqa: BLE001 - 采样失败重试
                last_err = e
                logger.warning(
                    "[%s] prefix=%s sample=%s 第 %d 次调用失败: %s",
                    job["problem_id"], upto, job["sample_idx"], attempt + 1, e,
                )
                time.sleep(1.0)
        return {
            "problem_id": job["problem_id"],
            "upto": upto,
            "sample_idx": job["sample_idx"],
            "pred_answer": None,
            "correct": False,
            "check_detail": f"续写调用失败: {last_err}",
            "finish_reason": None,
        }

    # ------------------------------------------------------------------
    # 聚合
    # ------------------------------------------------------------------
    def _aggregate(
        self, record: Dict, prefix_indices: List[int], job_results: List[Dict]
    ) -> Dict:
        """按前缀聚合并给出判定."""
        gold = record.get("gold_answer", "")
        verification = record.get("verification") or {"method": "exact_match"}
        steps = record.get("steps", [])
        n_steps = len(steps)

        by_prefix: Dict[int, List[Dict]] = {i: [] for i in prefix_indices}
        for r in job_results:
            by_prefix.setdefault(r["upto"], []).append(r)

        prefix_scores = []
        for idx in prefix_indices:
            if idx >= n_steps:
                # 末步前缀已包含完整解答（含最终答案），直接比对，不再采样
                pred = record.get("final_answer")
                ok, detail = check_answer(pred, gold, verification)
                prefix_scores.append(
                    {
                        "step": idx,
                        "score": 1.0 if ok else 0.0,
                        "n_samples": 0,
                        "n_correct": int(bool(ok)),
                        "direct_check": True,
                        "sampled_answers": [pred],
                        "check_detail": detail,
                    }
                )
                continue
            samples = sorted(by_prefix.get(idx, []), key=lambda x: x["sample_idx"])
            n_correct = sum(1 for s in samples if s["correct"])
            n = len(samples)
            prefix_scores.append(
                {
                    "step": idx,
                    "score": n_correct / n if n else None,
                    "n_samples": n,
                    "n_correct": n_correct,
                    "direct_check": False,
                    "sampled_answers": [s["pred_answer"] for s in samples],
                }
            )

        scored = [p for p in prefix_scores if p["score"] is not None]
        scores = [p["score"] for p in scored]
        min_score = min(scores) if scores else None
        mean_score = sum(scores) / len(scores) if scores else None

        # 首错步定位：第一个从前缀分 >= drop_high 跌到 < drop_low 的步骤；
        # 若首个采样点 already < drop_low，则首错步不晚于该采样点
        first_error_step = None
        prev_score = None
        for p in scored:
            s = p["score"]
            if prev_score is None:
                if s < self.drop_low:
                    first_error_step = p["step"]
                    break
            else:
                if prev_score >= self.drop_high and s < self.drop_low:
                    first_error_step = p["step"]
                    break
            prev_score = s

        # 过程判错：min 分低于阈值
        process_correct = (
            min_score is not None and min_score >= self.process_threshold
        )
        if min_score is None:
            verdict_reason = "无有效采样结果"
        elif process_correct:
            verdict_reason = (
                f"所有采样前缀分 >= {self.process_threshold}，过程可信"
            )
        else:
            verdict_reason = (
                f"min 前缀分 {min_score:.2f} < {self.process_threshold}，"
                f"首错步定位于步骤 {first_error_step}"
            )

        return {
            "problem_id": record.get("problem_id"),
            "level": record.get("level"),
            "gold_answer": gold,
            "final_answer": record.get("final_answer"),
            "answer_correct": record.get("answer_correct"),
            "n_steps": n_steps,
            "sampled_prefixes": prefix_indices,
            "prefix_scores": prefix_scores,
            "min_score": min_score,
            "mean_score": mean_score,
            "first_error_step": first_error_step,
            "process_correct": process_correct,
            "verdict_reason": verdict_reason,
        }

    # ------------------------------------------------------------------
    # 对外接口
    # ------------------------------------------------------------------
    def plan_jobs(self, record: Dict) -> List[Dict]:
        """为一条解答生成全部续写采样任务（末步前缀不采样）."""
        steps = record.get("steps", [])
        n_steps = len(steps)
        prefix_indices = select_prefix_indices(n_steps, self.max_prefixes)
        jobs = []
        for idx in prefix_indices:
            if idx >= n_steps:
                continue  # 末步直接比对，不采样
            for j in range(self.n_samples):
                jobs.append(
                    {
                        "problem_id": record.get("problem_id"),
                        "problem": record.get("problem", ""),
                        "steps": steps,
                        "upto": idx,
                        "sample_idx": j,
                        "gold_answer": record.get("gold_answer", ""),
                        "verification": record.get("verification"),
                    }
                )
        return jobs, prefix_indices

    def verify_batch(
        self, records: List[Dict], max_workers: int = 16, progress=None
    ) -> List[Dict]:
        """批量反向验证：把所有记录的 (前缀 × 采样) 任务铺平到一个线程池.

        Args:
            records: 解答记录列表
            max_workers: 并发线程数
            progress: 可选 tqdm 进度条对象（按任务粒度更新）
        """
        all_jobs: List[Dict] = []
        plans: Dict[str, Dict] = {}
        for rec in records:
            jobs, prefix_indices = self.plan_jobs(rec)
            all_jobs.extend(jobs)
            plans[rec.get("problem_id")] = {
                "record": rec,
                "prefix_indices": prefix_indices,
                "results": [],
            }

        logger.info(
            "反向验证: %d 条解答, 共 %d 次续写调用, 并发 %d",
            len(records), len(all_jobs), max_workers,
        )

        if all_jobs:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(self._run_continuation_job, job): job
                    for job in all_jobs
                }
                for future in as_completed(futures):
                    job = futures[future]
                    try:
                        res = future.result()
                    except Exception as e:  # noqa: BLE001 - 兜底，不应发生
                        res = {
                            "problem_id": job["problem_id"],
                            "upto": job["upto"],
                            "sample_idx": job["sample_idx"],
                            "pred_answer": None,
                            "correct": False,
                            "check_detail": f"任务异常: {e}",
                            "finish_reason": None,
                        }
                    plans[job["problem_id"]]["results"].append(res)
                    if progress is not None:
                        progress.update(1)

        results = []
        for rec in records:
            pid = rec.get("problem_id")
            plan = plans[pid]
            results.append(
                self._aggregate(rec, plan["prefix_indices"], plan["results"])
            )
            logger.info(
                "[%s] min=%s mean=%s first_err=%s process_correct=%s",
                pid,
                f"{results[-1]['min_score']:.2f}" if results[-1]["min_score"] is not None else "NA",
                f"{results[-1]['mean_score']:.2f}" if results[-1]["mean_score"] is not None else "NA",
                results[-1]["first_error_step"],
                results[-1]["process_correct"],
            )
        return results

    def verify_solution(self, record: Dict, max_workers: int = 16) -> Dict:
        """单条解答的反向验证."""
        return self.verify_batch([record], max_workers=max_workers)[0]


def summarize(results: List[Dict]) -> Dict:
    """汇总统计."""
    total = len(results)
    judged_wrong = [r for r in results if not r["process_correct"]]
    located = [r for r in judged_wrong if r["first_error_step"] is not None]
    return {
        "total": total,
        "process_correct": total - len(judged_wrong),
        "process_wrong": len(judged_wrong),
        "first_error_located": len(located),
        "avg_min_score": (
            sum(r["min_score"] for r in results if r["min_score"] is not None)
            / max(1, sum(1 for r in results if r["min_score"] is not None))
        ),
        "avg_mean_score": (
            sum(r["mean_score"] for r in results if r["mean_score"] is not None)
            / max(1, sum(1 for r in results if r["mean_score"] is not None))
        ),
    }


if __name__ == "__main__":
    # 自检：前缀取点逻辑
    assert select_prefix_indices(4, 6) == [1, 2, 3, 4]
    assert select_prefix_indices(10, 6)[0] == 1
    assert select_prefix_indices(10, 6)[-1] == 10
    assert len(select_prefix_indices(10, 6)) == 6
    assert select_prefix_indices(1, 6) == [1]
    print("select_prefix_indices 自检通过")
    for n in (5, 8, 20, 32):
        print(f"n_steps={n} -> {select_prefix_indices(n, 6)}")

    # 自检：嵌套 boxed 提取
    assert _extract_boxed_nested(r"答案为 \boxed{\frac{1}{2}}。") == r"\frac{1}{2}"
    assert _extract_boxed_nested(r"\boxed{-\frac{3}{2}}") == r"-\frac{3}{2}"
    assert _extract_boxed_nested(r"\boxed{16}") == "16"
    assert _extract_boxed_nested("没有 boxed") is None
    print("_extract_boxed_nested 自检通过")
