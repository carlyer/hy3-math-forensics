"""生成 demo GIF 动画.

从缓存的 demo 输出中生成逐行显示的 GIF，模拟终端输出过程。

用法:
    python demo/generate_demo_gif.py \
        --input demo/demo_correct.txt \
        --output demo/demo_correct.gif
"""

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def create_text_gif(
    text: str,
    output_path: str,
    width: int = 900,
    line_height: int = 24,
    font_size: int = 16,
    bg_color: tuple = (30, 30, 30),
    text_color: tuple = (240, 240, 240),
    highlight_color: tuple = (100, 200, 100),
    warning_color: tuple = (255, 200, 100),
    fps: int = 10,
    pause_frames: int = 30,
):
    """将文本逐行/逐段渲染为 GIF."""
    lines = text.splitlines()

    # 估算高度
    max_lines_visible = len(lines) + 5
    height = max(400, min(1200, max_lines_visible * line_height + 40))

    font_paths = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    ]
    font = None
    for fp in font_paths:
        try:
            font = ImageFont.truetype(fp, font_size)
            break
        except Exception:
            continue
    if font is None:
        font = ImageFont.load_default()

    frames = []
    current_lines = []

    def render_frame():
        img = Image.new("RGB", (width, height), bg_color)
        draw = ImageDraw.Draw(img)
        y = 20
        for ln in current_lines:
            color = text_color
            if "✓" in ln or "正确" in ln or "过程是否正确：是" in ln:
                color = highlight_color
            elif "✗" in ln or "错误" in ln or "不成立" in ln:
                color = warning_color
            draw.text((20, y), ln, fill=color, font=font)
            y += line_height
        return img

    # 初始空帧
    frames.append(render_frame())

    # 逐行显示
    for ln in lines:
        current_lines.append(ln)
        frames.append(render_frame())

    # 结尾停留
    for _ in range(pause_frames):
        frames.append(render_frame())

    # 保存 GIF
    duration = int(1000 / fps)
    frames[0].save(
        output_path,
        save_all=True,
        append_images=frames[1:],
        duration=duration,
        loop=0,
        optimize=True,
    )
    print(f"GIF 已生成: {output_path}")
    print(f"  尺寸: {width}x{height}")
    print(f"  帧数: {len(frames)}")
    print(f"  时长: {len(frames) * duration / 1000:.1f} 秒")


def main():
    parser = argparse.ArgumentParser(description="Generate demo GIF")
    parser.add_argument("--input", type=str, default="demo/demo_correct.txt")
    parser.add_argument("--output", type=str, default="demo/demo_correct.gif")
    parser.add_argument("--fps", type=int, default=10)
    args = parser.parse_args()

    text = Path(args.input).read_text(encoding="utf-8")
    create_text_gif(text, args.output, fps=args.fps)


if __name__ == "__main__":
    main()
