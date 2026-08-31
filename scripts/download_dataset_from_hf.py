#!/usr/bin/env python3
"""从 Hugging Face Dataset 仓库下载题目数据集到本仓库 dataset/ 目录。

用法：
    python scripts/download_dataset_from_hf.py \
        --repo Carlyer/hy3-math-forensics-dataset --dest .

私有仓库需设置环境变量 HF_TOKEN。
"""
import argparse

from huggingface_hub import snapshot_download


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="Carlyer/hy3-math-forensics-dataset",
                        help="HF Dataset 仓库名（namespace/name）")
    parser.add_argument("--dest", default=".", help="下载目标目录（通常为仓库根目录）")
    args = parser.parse_args()

    path = snapshot_download(
        repo_id=args.repo,
        repo_type="dataset",
        local_dir=args.dest,
    )
    print(f"数据集已下载到: {path}")


if __name__ == "__main__":
    main()
