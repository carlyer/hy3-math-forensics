"""从 ModelScope 下载 Hy3-GPTQ-Int4 模型.

用法:
    python scripts/download_model_from_modelscope.py --output ./models/hy3-gptq-int4
"""

import argparse
from pathlib import Path

from modelscope import snapshot_download


def main():
    parser = argparse.ArgumentParser(description="Download Hy3-GPTQ-Int4 from ModelScope")
    parser.add_argument(
        "--model_id",
        type=str,
        default="AngelSlim/Hy3-GPTQ-Int4",
        help="ModelScope model ID",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="./models/hy3-gptq-int4",
        help="Output directory",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Number of parallel download workers (modelscope snapshot_download)",
    )
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.parent.mkdir(parents=True, exist_ok=True)

    print(f"开始从 ModelScope 下载 {args.model_id} ...")
    print(f"目标目录: {output_dir}")
    print(f"并行线程数: {args.workers}")

    snapshot_download(
        model_id=args.model_id,
        local_dir=str(output_dir),
        local_dir_use_symlinks=False,
        max_workers=args.workers,
    )

    print(f"下载完成: {output_dir}")


if __name__ == "__main__":
    main()
