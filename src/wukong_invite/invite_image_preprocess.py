"""
邀请码 Banner 预处理。

**主路径（默认）**：本项目约定「反色」= **仅绝对 ``#FFFFFF`` → ``#000000``**，其余像素不变
（可用 ``WUKONG_INVITE_WHITE_MIN`` 放宽为 RGB 均 ≥ 阈值再变黑）；再按环境变量做 **ROI 精准裁剪**。
**禁止**默认放大、CLAHE、Otsu 等。

带 **Alpha** 的 PNG：转 RGB 时**不用白底**（避免透明区变 ``#FFFFFF`` 后被误判为字），默认用**纯红**
``(255,0,0)`` 填补透明像素；可用 ``WUKONG_INVITE_ALPHA_FILL_RGB`` 改为 ``R,G,B``。

调试输出顺序：1）原图（已压平透明）2）FF→黑整图 3）裁剪后图（仅为 2 的矩形裁切，无涂抹）。

``WUKONG_INVITE_ROI_BR_*`` 右下抹除 **仅** 用于 legacy A/B/C（灰度二值化链路），主路径裁剪**不使用**。
"""
from __future__ import annotations

import io
import os
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from PIL import Image


def _env_float(name: str, default: str) -> float:
    raw = os.environ.get(name, default).strip()
    try:
        return float(raw)
    except ValueError:
        return float(default)


# 默认：保留图高上方足够包住「当前邀请码」整行（过小会裁掉字下半截）；仍可调小以去底部文案
_DEFAULT_CROP_TOP = "0.43"
# 保留图宽左侧比例（在 0.64×1.2≈0.77 基础上略增至 0.83，减少把第五字（如「涧」）裁没导致 rec 缺字）
_DEFAULT_CROP_WIDTH = "0.83"
_DEFAULT_ROI_BR_MASK_X0 = "0.50"
_DEFAULT_ROI_BR_MASK_Y0 = "0.42"


def _parse_alpha_fill_rgb() -> tuple[int, int, int]:
    raw = (os.environ.get("WUKONG_INVITE_ALPHA_FILL_RGB") or "255,0,0").strip()
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) != 3:
        return (255, 0, 0)
    try:
        r, g, b = int(parts[0]), int(parts[1]), int(parts[2])
        return (max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b)))
    except ValueError:
        return (255, 0, 0)


def pil_invite_to_rgb(img: Image.Image) -> Image.Image:
    """
    邀请图统一转 RGB：透明区域用纯色填充（默认红），**避免** 直接 ``convert('RGB')``
    把透明当成白底导致整片 ``#FFFFFF``、后续「仅 FF→黑」把底误伤。
    """
    from PIL import Image

    fill = _parse_alpha_fill_rgb()
    if img.mode == "RGBA":
        bg = Image.new("RGB", img.size, fill)
        bg.paste(img, mask=img.split()[3])
        return bg
    if img.mode == "LA":
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, fill)
        bg.paste(img, mask=img.split()[3])
        return bg
    if img.mode == "P":
        if "transparency" in img.info:
            img = img.convert("RGBA")
            bg = Image.new("RGB", img.size, fill)
            bg.paste(img, mask=img.split()[3])
            return bg
    return img.convert("RGB")


def _pil_to_rgb(img: Image.Image) -> Image.Image:
    return pil_invite_to_rgb(img)


def preprocess_invite_exact_white_to_black(pil_rgb: Image.Image) -> Image.Image:
    """
    整图 RGB：**仅**将绝对 ``#FFFFFF`` (255,255,255) 改为 ``#000000``，其余像素不变。

    抗锯齿等近白像素默认**不**改；若需放宽，设 ``WUKONG_INVITE_WHITE_MIN``（例如 ``254`` 表示
    R、G、B **均 ≥ 该值** 的像素一律改为黑）。
    """
    from PIL import Image

    rgb = _pil_to_rgb(pil_rgb)
    arr = np.asarray(rgb, dtype=np.uint8)
    out = arr.copy()
    lo = int((os.environ.get("WUKONG_INVITE_WHITE_MIN") or "255").strip() or "255")
    lo = max(0, min(255, lo))
    if lo >= 255:
        mask = (out[:, :, 0] == 255) & (out[:, :, 1] == 255) & (out[:, :, 2] == 255)
    else:
        mask = (out[:, :, 0] >= lo) & (out[:, :, 1] >= lo) & (out[:, :, 2] >= lo)
    out[mask] = (0, 0, 0)
    return Image.fromarray(out, mode="RGB")


def invert_invite_rgb_full(pil_rgb: Image.Image) -> Image.Image:
    """
    整图「反色」（本项目定义）：**不是** ``255−RGB``，而是 **仅 ``#FFFFFF`` → ``#000000``**，
    与 ``preprocess_invite_exact_white_to_black`` 相同。
    """
    return preprocess_invite_exact_white_to_black(pil_rgb)


def _rgb_roi_crop_geometry_only(arr_rgb: np.ndarray) -> np.ndarray:
    """
    在 **已是 RGB** 的数组上：仅按 ``WUKONG_INVITE_CROP_TOP`` / ``WUKONG_INVITE_CROP_WIDTH``
    做矩形裁剪 ``[0:y2, 0:x2]``，**不**对 ROI 内做任何涂抹/填色（避免误盖住邀请码）。
    """
    h, w = arr_rgb.shape[:2]
    top = _env_float("WUKONG_INVITE_CROP_TOP", _DEFAULT_CROP_TOP)
    wid = _env_float("WUKONG_INVITE_CROP_WIDTH", _DEFAULT_CROP_WIDTH)
    y2 = max(1, int(h * top))
    x2 = max(1, int(w * wid))
    return arr_rgb[0:y2, 0:x2].copy()


def preprocess_invite_invert_then_crop(pil_rgb: Image.Image) -> Image.Image:
    """
    主预处理：先得到与 ``last_inv_full`` 相同的 **FF→黑整图**，再 **仅几何裁剪**，
    不做右下抹除等任何额外像素操作。
    """
    from PIL import Image

    w2b = preprocess_invite_exact_white_to_black(pil_rgb)
    arr = np.asarray(w2b, dtype=np.uint8)
    roi = _rgb_roi_crop_geometry_only(arr)
    return Image.fromarray(roi, mode="RGB")


def _invite_gray_roi(
    pil_rgb: Image.Image,
    *,
    crop_top_ratio: float | None = None,
    crop_width_ratio: float | None = None,
    roi_br_mask_x0: float | None = None,
    roi_br_mask_y0: float | None = None,
) -> np.ndarray:
    """
    灰度 ROI（供旧版 A/B 等 **legacy** 链路使用）。
    """
    import cv2

    top = crop_top_ratio if crop_top_ratio is not None else _env_float("WUKONG_INVITE_CROP_TOP", _DEFAULT_CROP_TOP)
    wid = crop_width_ratio if crop_width_ratio is not None else _env_float("WUKONG_INVITE_CROP_WIDTH", _DEFAULT_CROP_WIDTH)
    mx0 = roi_br_mask_x0 if roi_br_mask_x0 is not None else _env_float("WUKONG_INVITE_ROI_BR_X0", _DEFAULT_ROI_BR_MASK_X0)
    my0 = roi_br_mask_y0 if roi_br_mask_y0 is not None else _env_float("WUKONG_INVITE_ROI_BR_Y0", _DEFAULT_ROI_BR_MASK_Y0)

    rgb = _pil_to_rgb(pil_rgb)
    arr = np.asarray(rgb, dtype=np.uint8)
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    h, w = gray.shape[:2]
    y2 = max(1, int(h * top))
    x2 = max(1, int(w * wid))
    roi = gray[0:y2, 0:x2].copy()

    rh, rw = roi.shape[:2]
    ref = roi[0 : max(1, rh // 3), 0 : max(1, rw // 2)]
    bg = int(np.median(ref)) if ref.size > 0 else 245
    x0i = int(rw * mx0)
    y0i = int(rh * my0)
    roi[y0i:rh, x0i:rw] = bg
    return roi


def preprocess_invite_banner(
    pil_rgb: Image.Image,
    *,
    crop_top_ratio: float | None = None,
    crop_width_ratio: float | None = None,
    upscale: float = 2.0,
    clahe_clip: float = 3.0,
) -> Image.Image:
    """
    **Legacy**：CLAHE + 反色 + Otsu + 可选放大。默认 OCR 已不用；仅 ``legacy_chain`` 等模式需要。
    """
    import cv2
    from PIL import Image

    roi = _invite_gray_roi(
        pil_rgb,
        crop_top_ratio=crop_top_ratio,
        crop_width_ratio=crop_width_ratio,
    )

    clahe = cv2.createCLAHE(clipLimit=clahe_clip, tileGridSize=(8, 8))
    eq = clahe.apply(roi)
    inv = cv2.bitwise_not(eq)
    _, binary = cv2.threshold(inv, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, k, iterations=1)

    if upscale and upscale != 1.0:
        binary = cv2.resize(
            binary,
            None,
            fx=upscale,
            fy=upscale,
            interpolation=cv2.INTER_CUBIC,
        )

    rgb_out = cv2.cvtColor(binary, cv2.COLOR_GRAY2RGB)
    return Image.fromarray(rgb_out, mode="RGB")


def upscale_invite_rgb(pil_rgb: Image.Image, scale: float = 2.0) -> Image.Image:
    """**Legacy**：整图放大。"""
    import cv2
    from PIL import Image

    if scale <= 1.0001:
        return _pil_to_rgb(pil_rgb)
    arr = np.asarray(_pil_to_rgb(pil_rgb), dtype=np.uint8)
    h, w = arr.shape[:2]
    nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
    out = cv2.resize(arr, (nw, nh), interpolation=cv2.INTER_LANCZOS4)
    return Image.fromarray(out, mode="RGB")


def preprocess_invite_banner_soft(pil_rgb: Image.Image) -> Image.Image:
    """**Legacy**：ROI CLAHE + 放大。"""
    import cv2
    from PIL import Image

    roi = _invite_gray_roi(pil_rgb)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    eq = clahe.apply(roi)
    up = cv2.resize(eq, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    rgb_out = cv2.cvtColor(up, cv2.COLOR_GRAY2RGB)
    return Image.fromarray(rgb_out, mode="RGB")


def preprocess_invite_banner_variant_b(pil_rgb: Image.Image) -> Image.Image:
    """**Legacy**：自适应阈值 + 放大。"""
    import cv2
    from PIL import Image

    roi = _invite_gray_roi(pil_rgb)
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    eq = clahe.apply(roi)
    th = cv2.adaptiveThreshold(
        eq,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        35,
        7,
    )
    th = cv2.resize(th, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    rgb_out = cv2.cvtColor(th, cv2.COLOR_GRAY2RGB)
    return Image.fromarray(rgb_out, mode="RGB")


def _variant_map_for_base(base: Image.Image) -> dict[str, tuple[str, Image.Image]]:
    scale = _env_float("WUKONG_INVITE_RAW_UPSCALE", "2.0")
    raw_2x_label = "原图2倍放大" if abs(scale - 2.0) < 0.05 else f"原图×{scale:g}放大"
    w2b_full = preprocess_invite_exact_white_to_black(base)
    inv_crop = preprocess_invite_invert_then_crop(base)
    return {
        "raw": ("原图", base),
        "inv_full": ("反色_FF→黑_整图", w2b_full),
        "inv_crop": ("反色+ROI裁剪", inv_crop),
        "fff_black": ("legacy_FFFFFF→黑", w2b_full),
        "raw_2x": (raw_2x_label, upscale_invite_rgb(base, scale)),
        "pre_a": ("legacy_A_CLAHE反色Otsu", preprocess_invite_banner(base)),
        "pre_b": ("legacy_B_自适应阈值", preprocess_invite_banner_variant_b(base)),
        "soft": ("legacy_C_ROI_CLAHE", preprocess_invite_banner_soft(base)),
    }


def iter_ocr_rgb_variants_named(pil_rgb: Image.Image) -> list[tuple[str, Image.Image]]:
    """
    (名称, RGB 图) 供 OCR。

    **默认（``all``）**：**仅** ``反色+ROI裁剪`` 一路 OCR（最快）；原图不再默认跑。

    ``WUKONG_INVITE_OCR_VARIANTS``（不区分大小写）示例：

    - ``raw``：仅原图
    - ``raw_and_crop`` / ``dual``：原图 + 反色+裁剪（旧默认、兜底）
    - ``inv_crop`` / ``pre`` / ``invert_crop`` / ``crop``：同默认，仅裁剪图
    - ``inv_full``：仅反色整图（较宽，一般只作对照）
    - ``legacy3``：旧 原图 + legacy A + B
    - ``legacy_chain``：旧全套（含与主路径相同的 FF→黑整图、放大、A、B、C），仅排查用
    """
    base = _pil_to_rgb(pil_rgb)
    m = _variant_map_for_base(base)

    mode = (os.environ.get("WUKONG_INVITE_OCR_VARIANTS") or "all").strip().lower()
    if mode in ("legacy3", "old3", "3"):
        return [m["raw"], m["pre_a"], m["pre_b"]]
    if mode in ("legacy_chain", "rich", "oldchain", "experimental"):
        return [
            m["raw"],
            m["fff_black"],
            m["raw_2x"],
            m["pre_a"],
            m["pre_b"],
            m["soft"],
        ]
    if mode in ("", "all", "default"):
        return [m["inv_crop"]]
    if mode == "raw":
        return [m["raw"]]
    if mode in ("raw_and_crop", "dual", "both"):
        return [m["raw"], m["inv_crop"]]
    if mode in ("inv_crop", "pre", "invert_crop", "crop"):
        return [m["inv_crop"]]
    if mode in ("inv_full", "invert_full"):
        return [m["inv_full"]]
    if mode in ("fff_black", "fff", "white2black", "d", "pre_d"):
        return [m["fff_black"]]
    if mode in ("raw_2x", "2x", "upscale"):
        return [m["raw_2x"]]
    if mode in ("pre_a", "a"):
        return [m["pre_a"]]
    if mode in ("pre_b", "b"):
        return [m["pre_b"]]
    if mode in ("soft", "pre_c", "c"):
        return [m["soft"]]
    if mode in ("pre_ab", "ab"):
        return [m["pre_a"], m["pre_b"], m["soft"]]
    if mode in ("pre_b_first", "b_first", "bfirst"):
        return [m["pre_b"], m["raw"], m["inv_crop"], m["raw_2x"], m["pre_a"], m["soft"]]
    return [m["inv_crop"]]


def iter_ocr_rgb_variants(pil_rgb: Image.Image) -> list[Image.Image]:
    """与 ``iter_ocr_rgb_variants_named`` 同序的 RGB 图列表。"""
    return [img for _, img in iter_ocr_rgb_variants_named(pil_rgb)]


INVITE_DEBUG_FILENAMES = ("last_raw.png", "last_inv_full.png", "last_inv_crop.png")


def clear_invite_debug_snapshots(out_dir: Path) -> None:
    if not out_dir.is_dir():
        return
    for name in INVITE_DEBUG_FILENAMES:
        p = out_dir / name
        if p.is_file():
            p.unlink()


def save_invite_debug_snapshots(pil_rgb: Image.Image, out_dir: Path) -> dict[str, Path]:
    """
    按序保存：1）原图 2）FF→黑整图（反色定义）3）裁剪后图。
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    clear_invite_debug_snapshots(out_dir)
    base = _pil_to_rgb(pil_rgb)
    paths = {
        "last_raw": out_dir / "last_raw.png",
        "last_inv_full": out_dir / "last_inv_full.png",
        "last_inv_crop": out_dir / "last_inv_crop.png",
    }
    base.save(paths["last_raw"], optimize=True)
    invert_invite_rgb_full(base).save(paths["last_inv_full"], optimize=True)
    preprocess_invite_invert_then_crop(base).save(paths["last_inv_crop"], optimize=True)
    return paths


def pil_to_png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
