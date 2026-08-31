#!/usr/bin/env python3
"""将题目数据集上传到 Hugging Face Dataset 仓库。

用法：
    # 先登录：hf auth login（或设置环境变量 HF_TOKEN）
    python scripts/upload_dataset_to_hf.py \
        --repo yerr2/hy3-math-forensics-dataset \
        --src /path/to/hy3-dataset-staging \
        --private

仓库默认创建为 private（数据在 2026-09-11 前不公开）；
如需公开可去掉 --private 或之后在 HF 网页端切换可见性。
"""
import argparse
import os
import sys

from huggingface_hub import HfApi


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="yerr2/hy3-math-forensics-dataset",
                        help="HF Dataset 仓库名（namespace/name）")
    parser.add_argument("--src", required=True,
                        help="本地暂存目录（内含 dataset/ 相对路径结构）")
    parser.add_argument("--private", action="store_true", default=True,
                        help="创建为私有仓库（默认）")
    parser.add_argument("--public", dest="private", action="store_false",
                        help="创建为公开仓库")
    args = parser.parse_args()

    if not (os.environ.get("HF_TOKEN") or os.path.exists(os.path.expanduser("~/.cache/huggingface/token"))):
        sys.exit("未找到 HF 凭据：请先 `hf auth login` 或设置环境变量 HF_TOKEN")

    api = HfApi()
    api.create_repo(args.repo, repo_type="dataset", private=args.private, exist_ok=True)
    api.upload_folder(
        repo_id=args.repo,
        repo_type="dataset",
        folder_path=args.src,
        path_in_repo="",
        commit_message="上传 hy3-math-forensics 题目数据集（418 题主实验集及全部衍生集）",
    )
    print(f"上传完成: https://huggingface.co/datasets/{args.repo}")


if __name__ == "__main__":
    main()
