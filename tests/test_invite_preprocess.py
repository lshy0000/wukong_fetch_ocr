import os
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("cv2")

from PIL import Image

from wukong_invite.invite_image_preprocess import (
    iter_ocr_rgb_variants,
    pil_invite_to_rgb,
    preprocess_invite_banner,
    preprocess_invite_exact_white_to_black,
    preprocess_invite_invert_then_crop,
)


def test_preprocess_produces_rgb_same_mode() -> None:
    root = Path(__file__).resolve().parents[1]
    p = root / "fixtures" / "wukong_invite_sample.png"
    if not p.is_file():
        pytest.skip("fixtures 样例不存在")
    im = pil_invite_to_rgb(Image.open(p))
    out = preprocess_invite_banner(im)
    assert out.mode == "RGB"
    assert out.size[0] >= im.size[0] * 0.5  # ROI 放大后宽度合理


def test_iter_variants_count() -> None:
    root = Path(__file__).resolve().parents[1]
    p = root / "fixtures" / "wukong_invite_sample.png"
    if not p.is_file():
        pytest.skip("fixtures 样例不存在")
    im = pil_invite_to_rgb(Image.open(p))
    old = os.environ.pop("WUKONG_INVITE_OCR_VARIANTS", None)
    try:
        vs = iter_ocr_rgb_variants(im)
        assert len(vs) == 1
    finally:
        if old is not None:
            os.environ["WUKONG_INVITE_OCR_VARIANTS"] = old


def test_iter_variants_raw_and_crop_is_two() -> None:
    root = Path(__file__).resolve().parents[1]
    p = root / "fixtures" / "wukong_invite_sample.png"
    if not p.is_file():
        pytest.skip("fixtures 样例不存在")
    im = pil_invite_to_rgb(Image.open(p))
    old = os.environ.get("WUKONG_INVITE_OCR_VARIANTS")
    try:
        os.environ["WUKONG_INVITE_OCR_VARIANTS"] = "raw_and_crop"
        vs = iter_ocr_rgb_variants(im)
        assert len(vs) == 2
    finally:
        if old is None:
            os.environ.pop("WUKONG_INVITE_OCR_VARIANTS", None)
        else:
            os.environ["WUKONG_INVITE_OCR_VARIANTS"] = old


def test_exact_white_to_black_only_ffffff() -> None:
    """仅 #FFFFFF → #000000，其余（含抗锯齿近白）不变。"""
    arr = np.full((2, 3, 3), 200, dtype=np.uint8)
    arr[0, 0] = [255, 255, 255]
    arr[0, 1] = [254, 255, 255]
    im = Image.fromarray(arr, mode="RGB")
    out = preprocess_invite_exact_white_to_black(im)
    oa = np.asarray(out)
    assert tuple(oa[0, 0]) == (0, 0, 0)
    assert tuple(oa[0, 1]) == (254, 255, 255)
    assert int(oa[1, 2, 0]) == 200


def test_rgba_transparency_filled_with_red_by_default() -> None:
    """透明像素不应对齐成白底；默认用红底便于与纯白字区分。"""
    im = Image.new("RGBA", (3, 2), (0, 0, 0, 0))
    im.putpixel((0, 0), (10, 20, 30, 255))
    out = pil_invite_to_rgb(im)
    assert out.mode == "RGB"
    assert out.getpixel((2, 1)) == (255, 0, 0)
    assert out.getpixel((0, 0)) == (10, 20, 30)


def test_invert_then_crop_smaller_than_full() -> None:
    root = Path(__file__).resolve().parents[1]
    p = root / "fixtures" / "wukong_invite_sample.png"
    if not p.is_file():
        pytest.skip("fixtures 样例不存在")
    im = pil_invite_to_rgb(Image.open(p))
    w, h = im.size
    out = preprocess_invite_invert_then_crop(im)
    ow, oh = out.size
    assert ow <= int(w * 0.83) + 2
    assert oh <= int(h * 0.43) + 2
    assert out.mode == "RGB"
