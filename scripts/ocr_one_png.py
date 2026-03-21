#!/usr/bin/env python3
"""
对单张 PNG 跑一次 PaddleOCR（不经多路预处理），用于对照调试图。

典型：先 ``python scripts/run_test_01_fetch_ocr.py --save-debug``，
再对本机 ``debug/invite_ocr/last_inv_crop.png`` 等跑本脚本，做单图 Paddle 对照。

用法（仓库根目录）:
  python scripts/ocr_one_png.py debug/invite_ocr/last_inv_crop.png
  python scripts/ocr_one_png.py fixtures/wukong_invite_sample.png
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    p = argparse.ArgumentParser(description="单图 PaddleOCR 调试（无 ROI 变体）")
    p.add_argument("png", type=Path, help="PNG 路径，如 debug/invite_ocr/last_inv_crop.png")
    args = p.parse_args()
    path = args.png.expanduser().resolve()
    if not path.is_file():
        print(f"错误：文件不存在 {path}", file=sys.stderr)
        return 1

    from wukong_invite.ocr_extract import collect_ocr_texts_from_png_path, pick_invite_candidate

    lines = collect_ocr_texts_from_png_path(path)
    print(f"文件: {path}")
    print(f"rec 行数: {len(lines)}")
    for i, x in enumerate(lines):
        print(f"  [{i}] {x!r}")
    trace: list[str] = []
    code = pick_invite_candidate(lines, trace=trace)
    print("pick_invite_candidate:", code)
    for t in trace:
        print(f"  · {t}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
