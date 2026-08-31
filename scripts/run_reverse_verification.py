"""Math-Shepherd 风格反向验证批量运行脚本.

用法示例:
    python scripts/run_reverse_verification.py \
        --input results/solutions_merged_full.jsonl \
        --output results/reverse_verification_test.json \
        --n_samples 4 \
        --max_prefixes 6 \
        --batch_size 16 \
        --problem_ids L1-001 L2-001

    # 混合多个输入文件（如主解题集 + CBU 注入样本）
    python scripts/run_reverse_verification.py \
        --input results/solutions_merged_full.jsonl dataset/cbu_injection_samples.jsonl \
        --output results/reverse_verification_test.json
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 自动加载 .env，确保 HY3_API_BASE 等配置生效
env_path = ROOT / ".env"
if env_path.exists():
    try:
        from dotenv import load_dotenv

        load_dotenv(env_path, override=False)
    except ImportError:
        pass

from tqdm import tqdm

from app.hy3_client import load_client_from_env
from evaluator.reverse_verifier import ReverseVerifier, summarize


def setup_logging() -> Path:
    """配置日志：同时写控制台和 logs/ 下的文件."""
    log_dir = ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"reverse_verification_{time.strftime('%Y%m%d_%H%M%S')}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_path, encoding="utf-8"),
        ],
    )
    return log_path


def load_records(paths: List[str]) -> List[Dict]:
    """加载一个或多个 jsonl 解题文件."""
    records = []
    for path in paths:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    return records


def main():
    parser = argparse.ArgumentParser(
        description="Math-Shepherd 风格反向验证（推理时步骤级奖励评分）"
    )
    parser.add_argument(
        "--input",
        type=str,
        nargs="+",
        default=["results/solutions_merged_full.jsonl"],
        help="解题结果 jsonl 路径（可多个）",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="results/reverse_verification.json",
        help="输出结果 json 路径",
    )
    parser.add_argument(
        "--n_samples",
        type=int,
        default=4,
        help="每个前缀的续写采样次数 N",
    )
    parser.add_argument(
        "--max_prefixes",
        type=int,
        default=6,
        help="每题最多采样前缀数（首步+末步+中间均匀取点）",
    )
    parser.add_argument(
        "--batch_size",
        type=int,
        default=16,
        help="并发线程数（所有题的前缀×采样任务铺平并发）",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.7,
        help="续写采样温度",
    )
    parser.add_argument(
        "--max_tokens",
        type=int,
        default=1536,
        help="续写最大 token 数",
    )
    parser.add_argument(
        "--problem_ids",
        type=str,
        nargs="*",
        default=None,
        help="只评估指定 problem_id（不指定则全量）",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="最多评估条数（调试用）",
    )
    args = parser.parse_args()

    log_path = setup_logging()
    logger = logging.getLogger("run_reverse_verification")
    logger.info("日志文件: %s", log_path)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("加载解题结果: %s", args.input)
    records = load_records(args.input)
    if args.problem_ids:
        wanted = set(args.problem_ids)
        records = [r for r in records if r.get("problem_id") in wanted]
        missing = wanted - {r.get("problem_id") for r in records}
        if missing:
            logger.warning("以下 problem_id 未找到: %s", sorted(missing))
    if args.limit:
        records = records[: args.limit]
    logger.info("共 %d 条待评估", len(records))

    client = load_client_from_env()
    verifier = ReverseVerifier(
        client,
        n_samples=args.n_samples,
        max_prefixes=args.max_prefixes,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
    )

    total_calls = sum(len(verifier.plan_jobs(r)[0]) for r in records)
    logger.info("预计续写调用总量: %d", total_calls)

    start = time.time()
    with tqdm(total=total_calls, desc="ReverseVerify") as bar:
        results = verifier.verify_batch(
            records, max_workers=args.batch_size, progress=bar
        )
    elapsed = time.time() - start

    summary = summarize(results)
    summary["elapsed_seconds"] = round(elapsed, 1)
    summary["total_calls"] = total_calls

    output = {
        "config": {
            "input": args.input,
            "n_samples": args.n_samples,
            "max_prefixes": args.max_prefixes,
            "batch_size": args.batch_size,
            "temperature": args.temperature,
            "max_tokens": args.max_tokens,
            "drop_high": verifier.drop_high,
            "drop_low": verifier.drop_low,
            "process_threshold": verifier.process_threshold,
        },
        "summary": summary,
        "results": results,
    }
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    logger.info("评估完成，耗时 %.1fs，结果保存至: %s", elapsed, output_path)
    logger.info(
        "过程判对 %d / 判错 %d / 首错步定位 %d",
        summary["process_correct"],
        summary["process_wrong"],
        summary["first_error_located"],
    )
    logger.info(
        "平均 min 分 %.3f / 平均 mean 分 %.3f",
        summary["avg_min_score"],
        summary["avg_mean_score"],
    )


if __name__ == "__main__":
    main()
