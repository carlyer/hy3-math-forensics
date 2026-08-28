#!/bin/bash
# 录制 demo 视频/GIF
# 需要预先安装 termtosvg 或 asciinema

set -e

cd /path/to/workspace/hy3-math-eval

PROBLEM_ID=${1:-L1-001}
DEMO_DIR=$(dirname "$0")

echo "录制题目: $PROBLEM_ID"

# 方案 1：使用 termtosvg（推荐，可直接生成 SVG/PNG/GIF）
if command -v termtosvg &> /dev/null; then
    echo "使用 termtosvg 录制..."
    termtosvg "$DEMO_DIR/demo_video.svg" -g 100x30 -c "python demo/demo.py --problem_id $PROBLEM_ID"
    echo "SVG 已保存: $DEMO_DIR/demo_video.svg"
    # 如需 GIF，可用 ImageMagick 转换（帧数较多，文件可能很大）
    # convert -delay 100 -loop 0 demo_video.svg demo_video.gif
    exit 0
fi

# 方案 2：使用 asciinema
if command -v asciinema &> /dev/null; then
    echo "使用 asciinema 录制..."
    asciinema rec -c "python demo/demo.py --problem_id $PROBLEM_ID" "$DEMO_DIR/demo_video.cast"
    echo "Cast 已保存: $DEMO_DIR/demo_video.cast"
    # 可用 asciinema-agg 转换为 GIF
    # agg demo_video.cast demo_video.gif
    exit 0
fi

# 兜底：仅保存文本输出
echo "未安装 termtosvg/asciinema，使用文本输出模式..."
python demo/demo.py --problem_id $PROBLEM_ID > "$DEMO_DIR/demo_video.txt"
echo "文本已保存: $DEMO_DIR/demo_video.txt"
