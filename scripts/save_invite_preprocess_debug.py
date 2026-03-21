#!/usr/bin/env python3
"""从 fixtures 样例生成调试图（固定文件名，先删旧再写，与 run_test_01 --save-debug 一致）。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image  # noqa: E402

from wukong_invite.invite_image_preprocess import (  # noqa: E402
    pil_invite_to_rgb,
    save_invite_debug_snapshots,
)


def main() -> int:
    src = ROOT / "fixtures" / "wukong_invite_sample.png"
    out = ROOT / "fixtures"
    if not src.is_file():
        print("缺少样例:", src)
        return 1
    for legacy in (
        "wukong_invite_sample_preprocessed_a.png",
        "wukong_invite_sample_preprocessed_b.png",
        "last_pre_a.png",
        "last_pre_b.png",
        "last_pre_soft.png",
        "last_pre_fff.png",
    ):
        lp = out / legacy
        if lp.is_file():
            lp.unlink()
            print("已删除旧调试图:", lp)
    im = pil_invite_to_rgb(Image.open(src))
    # fixtures 里保留公开样例名，调试图仍用 last_*.png 覆盖策略
    paths = save_invite_debug_snapshots(im, out)
    for k, fp in paths.items():
        print(k, "→", fp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
