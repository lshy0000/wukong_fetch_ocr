from __future__ import annotations

import io
import logging
import os
import re
import tempfile
import time
from typing import Any

from PIL import Image

logger = logging.getLogger(__name__)

# 单例：PaddleOCR 首次加载会下载/初始化模型，较慢
_paddle_engine: Any = None
_logged_paddle_predict_kw: bool = False


# 仅出现这类文案、且 OCR 行里无「当前邀请码」锚点时，多为无码/结束态 Banner；Tesseract 兜底几乎无效且慢
_UI_ONLY_SKIP_TESSERACT_PHRASES: tuple[str, ...] = (
    "已领完",
    "谢谢参与",
    "活动已结束",
    "名额已满",
    "敬请期待",
    "暂无邀请码",
    "感谢参与",
)


def _should_skip_tesseract_after_paddle_miss(texts: list[str]) -> bool:
    if (os.environ.get("WUKONG_OCR_FORCE_TESSERACT") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return False
    joined = "".join(re.sub(r"\s+", "", str(x)) for x in texts if str(x).strip())
    if not joined:
        return False
    if "当前邀请码" in joined:
        return False
    return any(p in joined for p in _UI_ONLY_SKIP_TESSERACT_PHRASES)


# 与「邀请码」文案区分的锚点（五字）
_INVITE_ANCHOR = "当前邀请码"

# 去掉空白、冒号、引号、破折/连字符等；汉字、字母、数字等保留，作为邀请码原文
_INVITE_STRIP_SYMBOLS_RE = re.compile(
    r'[\s\u3000:：;；＂＂""＇\'「」『』·_'
    r"\-\u2010\u2011\u2012\u2013\u2014\u2015\u2212\uFE58\uFE63\uFF0D]+"
)


def _strip_invite_symbols(s: str) -> str:
    return _INVITE_STRIP_SYMBOLS_RE.sub("", s)


def pick_invite_candidate(
    texts: list[str],
    *,
    trace: list[str] | None = None,
) -> str | None:
    """
    两种规则（合并去空白后的 ``merged_ns`` 上判断）：

    1. **无**子串「当前邀请码」：整段去掉符号后的内容即为邀请码。
    2. **有**「当前邀请码」：取其后的子串，去掉符号后的内容即为邀请码。
    """
    def _t(msg: str) -> None:
        if trace is not None:
            trace.append(msg)

    lines = [str(x).strip() for x in texts if str(x).strip()]
    if not lines:
        _t("解析:无OCR行")
        return None

    merged_raw = "".join(lines)
    merged_ns = re.sub(r"\s+", "", merged_raw)

    pos = merged_ns.find(_INVITE_ANCHOR)
    if pos != -1:
        tail = merged_ns[pos + len(_INVITE_ANCHOR) :]
        code = _strip_invite_symbols(tail)
        if code:
            _t(f"解析:有「当前邀请码」锚点，去符号 → {code!r}")
            return code
        _t("解析:有锚点但去符号后为空")
        return None

    code = _strip_invite_symbols(merged_ns)
    if code:
        _t(f"解析:无「当前邀请码」，全文去符号 → {code!r}")
        return code
    _t("解析:全文去符号后为空")
    return None


def _paddle_predict_kwargs() -> dict[str, Any]:
    """
    - ``text_det_limit_side_len``：较长边上限（默认 2560），**仅**在 ``limit_type=max`` 时把过大图缩小。
    - ``text_det_limit_type``：默认 ``max``。若用库默认 ``min``，会把**短边**拉到 limit_side_len，
      极宽横幅裁剪条会变成「16375×2560」一类尺寸，再触发 ``max_side_limit=4000`` 的告警与二次缩放。

    环境变量：``WUKONG_PADDLE_TEXT_DET_LIMIT_SIDE_LEN``、``WUKONG_PADDLE_TEXT_DET_LIMIT_TYPE``、
    ``WUKONG_PADDLE_TEXT_DET_THRESH``、``WUKONG_PADDLE_TEXT_DET_BOX_THRESH``、
    ``WUKONG_PADDLE_TEXT_REC_SCORE_THRESH``。
    """
    kw: dict[str, Any] = {}

    def _int(name: str, default: int) -> int:
        raw = (os.environ.get(name) or "").strip()
        if not raw:
            return default
        try:
            return int(raw)
        except ValueError:
            return default

    def _float(name: str, default: float | None) -> float | None:
        raw = (os.environ.get(name) or "").strip()
        if not raw:
            return default
        try:
            return float(raw)
        except ValueError:
            return default

    def _limit_type() -> str:
        raw = (os.environ.get("WUKONG_PADDLE_TEXT_DET_LIMIT_TYPE") or "max").strip().lower()
        if raw in ("max", "min", "resize_long"):
            return raw
        return "max"

    # 邀请码是窄条文本，默认把 det 输入边长压小以换速度（可环境变量覆盖）。
    kw["text_det_limit_side_len"] = _int("WUKONG_PADDLE_TEXT_DET_LIMIT_SIDE_LEN", 960)
    kw["text_det_limit_type"] = _limit_type()
    dt = _float("WUKONG_PADDLE_TEXT_DET_THRESH", None)
    if dt is not None:
        kw["text_det_thresh"] = dt
    bt = _float("WUKONG_PADDLE_TEXT_DET_BOX_THRESH", None)
    if bt is not None:
        kw["text_det_box_thresh"] = bt
    rs = _float("WUKONG_PADDLE_TEXT_REC_SCORE_THRESH", None)
    if rs is not None:
        kw["text_rec_score_thresh"] = rs
    return kw


def _make_paddle_ocr_engine() -> Any:
    """PaddleOCR 3.x 优先，失败则回退 2.x 构造参数。"""
    from paddleocr import PaddleOCR

    try:
        return PaddleOCR(
            # 速度优先：默认使用 mobile 检测/识别模型（可通过环境变量改回 server）。
            text_detection_model_name=(
                os.environ.get("WUKONG_PADDLE_DET_MODEL_NAME") or "PP-OCRv5_mobile_det"
            ),
            text_recognition_model_name=(
                os.environ.get("WUKONG_PADDLE_REC_MODEL_NAME") or "PP-OCRv5_mobile_rec"
            ),
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )
    except TypeError:
        logger.info("使用 PaddleOCR 2.x 风格初始化")
        # 2.x 下关闭 angle cls，避免额外开销。
        return PaddleOCR(use_angle_cls=False, lang="ch", show_log=False)


def _texts_from_paddle_output(output: Any) -> list[str]:
    texts: list[str] = []

    if not output:
        return texts

    # --- PaddleOCR 3.x：predict 返回可迭代结果，内含 rec_texts ---
    try:
        for item in output:
            j: dict[str, Any] | None = None
            if isinstance(item, dict):
                j = item
            else:
                for attr in ("json", "to_json"):
                    if hasattr(item, attr):
                        try:
                            raw = getattr(item, attr)
                            j = raw() if callable(raw) else raw
                        except Exception:
                            j = None
                        if isinstance(j, dict):
                            break
            if not isinstance(j, dict):
                continue
            res = j.get("res", j)
            if isinstance(res, dict):
                rt = res.get("rec_texts")
                if isinstance(rt, (list, tuple)):
                    texts.extend(str(x).strip() for x in rt if str(x).strip())
    except (TypeError, AttributeError):
        texts.clear()

    if texts:
        return texts

    # --- PaddleOCR 2.x：[[box, (text, score)], ...] ---
    if isinstance(output, list) and output:
        block = output[0]
        if isinstance(block, list):
            for line in block:
                if (
                    isinstance(line, (list, tuple))
                    and len(line) >= 2
                    and isinstance(line[1], (list, tuple))
                ):
                    texts.append(str(line[1][0]).strip())
                elif isinstance(line, (list, tuple)) and len(line) >= 2 and isinstance(line[1], str):
                    texts.append(line[1].strip())

    return [t for t in texts if t]


def _run_paddle_on_image(ocr: Any, image: Image.Image) -> list[str]:
    """
    直接以内存图像推理，避免每轮写入临时 PNG 文件。
    若当前 Paddle 版本不支持 ndarray 输入，再回退到临时文件路径。
    """
    import numpy as np

    arr = np.array(image)
    if hasattr(ocr, "predict"):
        global _logged_paddle_predict_kw
        kw = _paddle_predict_kwargs()
        logger.debug("Paddle predict kwargs: %s", kw)
        if not _logged_paddle_predict_kw:
            logger.info(
                "Paddle predict 参数（默认 limit_type=max；速度优先默认 limit_side_len=960，可用 WUKONG_PADDLE_* 覆盖）: %s",
                kw,
            )
            _logged_paddle_predict_kw = True
        try:
            out = ocr.predict(arr, **kw)
            return _texts_from_paddle_output(out)
        except TypeError:
            # 旧实现可能只接收路径；继续走临时文件回退。
            pass
        except Exception:
            logger.debug("Paddle ndarray 直推失败，回退临时文件路径", exc_info=True)

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        image.save(f, format="PNG")
        tmp = f.name
    try:
        return _run_paddle_on_png_path(ocr, tmp)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _run_paddle_on_png_path(ocr: Any, path: str) -> list[str]:
    if hasattr(ocr, "predict"):
        global _logged_paddle_predict_kw
        kw = _paddle_predict_kwargs()
        logger.debug("Paddle predict kwargs: %s", kw)
        if not _logged_paddle_predict_kw:
            logger.info(
                "Paddle predict 参数（默认 limit_type=max 避免窄条被暴力放大；可用 WUKONG_PADDLE_* 覆盖）: %s",
                kw,
            )
            _logged_paddle_predict_kw = True
        try:
            out = ocr.predict(path, **kw)
        except TypeError:
            out = ocr.predict(path)
        return _texts_from_paddle_output(out)
    import numpy as np

    from wukong_invite.invite_image_preprocess import pil_invite_to_rgb

    arr = np.array(pil_invite_to_rgb(Image.open(path)))
    out = ocr.ocr(arr, cls=False)
    return _texts_from_paddle_output(out)


def warmup_paddle_ocr() -> None:
    """
    预先创建 Paddle 引擎并对小图跑一次 infer，缩短后续首轮真实 OCR 的等待。
    未安装 Paddle 时静默跳过；infer 失败仍会保留已加载的引擎。
    """
    global _paddle_engine
    try:
        if _paddle_engine is None:
            logger.info(
                "Paddle: 正在创建 OCR 引擎（首次会加载 det/rec 模型，"
                "期间库可能向 stderr 输出大量日志，属正常现象）…"
            )
            t0 = time.monotonic()
            _paddle_engine = _make_paddle_ocr_engine()
            logger.info("Paddle: 引擎创建完毕，用时 %.1fs", time.monotonic() - t0)
    except ImportError:
        logger.warning("Paddle 未安装，跳过 OCR 预热")
        return
    im = Image.new("RGB", (64, 64), (128, 128, 128))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(buf.getvalue())
        tmp = f.name
    try:
        logger.info("Paddle: 预热 infer（64×64 占位图，触发首次推理编译/缓存）…")
        t1 = time.monotonic()
        _run_paddle_on_png_path(_paddle_engine, tmp)
        logger.info("Paddle: 预热 infer 结束，用时 %.1fs", time.monotonic() - t1)
    except Exception:
        logger.exception("OCR 预热 infer 失败（引擎若已加载仍可继续轮询）")
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    logger.info("Paddle OCR 预热完成（引擎已就绪）")
    return None


def collect_ocr_texts_from_png(
    png_bytes: bytes,
) -> tuple[list[str], list[tuple[str, list[str], tuple[int, int]]]]:
    """
    多路预处理 + PaddleOCR，合并各路的 rec_texts（未做邀请码解析）。

    返回 ``(合并列表, 各路明细)``。明细每项为 ``(变体名称, 该路 rec 文本行, (宽, 高))``，
    尺寸为送入 Paddle 前该路 RGB 图的像素大小。

    变体列表由 ``invite_image_preprocess.iter_ocr_rgb_variants_named`` 决定；
    可设环境变量 ``WUKONG_INVITE_OCR_VARIANTS=pre_b`` 等只跑预处理 B。
    """
    global _paddle_engine
    try:
        if _paddle_engine is None:
            _paddle_engine = _make_paddle_ocr_engine()
    except ImportError:
        return [], []

    from wukong_invite.invite_image_preprocess import iter_ocr_rgb_variants_named, pil_to_png_bytes

    pil = Image.open(io.BytesIO(png_bytes))
    iw, ih = pil.size
    logger.info("Paddle 识别输入: 解码后原图约 %s 字节，尺寸 %sx%s", len(png_bytes), iw, ih)
    ve = (os.environ.get("WUKONG_INVITE_OCR_VARIANTS") or "").strip()
    if ve:
        logger.info("Paddle 识别: 环境变量 WUKONG_INVITE_OCR_VARIANTS=%r（收窄/重排变体）", ve)

    variants = list(iter_ocr_rgb_variants_named(pil))
    total = len(variants)
    collected: list[str] = []
    per_variant: list[tuple[str, list[str], tuple[int, int]]] = []
    for idx, (label, var) in enumerate(variants, start=1):
        w, h = var.size
        data = pil_to_png_bytes(var)
        batch = _run_paddle_on_image(_paddle_engine, var)
        per_variant.append((label, batch, (w, h)))
        collected.extend(batch)
        if batch:
            joined = " | ".join(repr(x) for x in batch)
        else:
            joined = "（本路无 rec 行）"
        logger.info(
            "Paddle 变体 [%s/%s] «%s» → 送入图 %sx%s（PNG %s 字节）| 本路 rec %s 行，合并后累计 %s 段 | %s",
            idx,
            total,
            label,
            w,
            h,
            len(data),
            len(batch),
            len(collected),
            joined,
        )
    logger.info(
        "Paddle 多路合并完成: 顺序追加共 %s 段文本（各路可能重复，解析时一并交给 pick）",
        len(collected),
    )
    logger.debug("PaddleOCR 多路合并文本段: %s", collected)
    return collected, per_variant


def collect_ocr_texts_from_png_path(path: str | os.PathLike[str]) -> list[str]:
    """
    对磁盘上已有 PNG 单图跑一次 Paddle（**不再**做 ROI/预处理变体）。
    用于对照 ``--save-debug`` 写出的 ``last_inv_crop.png`` 等是否与线上一致。
    """
    global _paddle_engine
    p = os.fspath(path)
    try:
        if _paddle_engine is None:
            _paddle_engine = _make_paddle_ocr_engine()
    except ImportError:
        return []
    from wukong_invite.invite_image_preprocess import pil_invite_to_rgb

    im = pil_invite_to_rgb(Image.open(p))
    w, h = im.size
    lines = _run_paddle_on_png_path(_paddle_engine, p)
    logger.info(
        "Paddle 单文件识别: 路径 %r | 尺寸 %sx%s | rec %s 行: %s",
        p,
        w,
        h,
        len(lines),
        " | ".join(repr(x) for x in lines) if lines else "（无）",
    )
    return lines


def _try_import_pytesseract():
    try:
        import pytesseract  # noqa: WPS433

        return pytesseract
    except ImportError:
        return None


def _extract_with_pytesseract(png_bytes: bytes) -> str | None:
    pytesseract = _try_import_pytesseract()
    if pytesseract is None:
        return None
    from wukong_invite.invite_image_preprocess import iter_ocr_rgb_variants

    pil = Image.open(io.BytesIO(png_bytes))
    for var in iter_ocr_rgb_variants(pil):
        for lang in ("chi_sim+eng", "chi_sim", "eng"):
            try:
                raw = pytesseract.image_to_string(var, lang=lang)
            except Exception:
                continue
            got = pick_invite_candidate([raw])
            if got:
                return got
    return None


def extract_code_from_png_with_lines(
    png_bytes: bytes,
) -> tuple[str | None, list[str], list[str], list[tuple[str, list[str], tuple[int, int]]]]:
    """
    返回 ``(邀请码, Paddle 合并 rec 行, 解析路径留痕, Paddle 各路明细)``。

    各路明细每项为 ``(变体名称, 该路 rec 行, (宽, 高))``；非 Paddle 后端或未完成 Paddle 时为 ``[]``。
    """
    backend = (os.environ.get("WUKONG_OCR_BACKEND") or "paddle").lower().strip()
    pick_trace: list[str] = []
    variant_reports: list[tuple[str, list[str], tuple[int, int]]] = []
    if backend == "tesseract":
        logger.info("OCR 后端: Tesseract（环境变量 WUKONG_OCR_BACKEND）")
        code = _extract_with_pytesseract(png_bytes)
        if code:
            pick_trace.append("解析:Tesseract命中")
        return code, [], pick_trace, []

    texts: list[str] = []
    try:
        logger.info("OCR 后端: Paddle，原始 PNG 约 %s 字节", len(png_bytes))
        texts, variant_reports = collect_ocr_texts_from_png(png_bytes)
        for vlabel, vlines, (vw, vh) in variant_reports:
            vsub: list[str] = []
            code_v = pick_invite_candidate(vlines, trace=vsub)
            if code_v:
                pick_trace.append(f"解析:变体«{vlabel}»({vw}×{vh})单独命中")
                pick_trace.extend(vsub)
                logger.info("解析结果: 变体单独命中 → %r（%s）", code_v, vlabel)
                return code_v, texts, pick_trace, variant_reports
        code = pick_invite_candidate(texts, trace=pick_trace)
        if code:
            logger.info("解析结果: 已命中邀请码候选 → %r", code)
            return code, texts, pick_trace, variant_reports
        if _should_skip_tesseract_after_paddle_miss(texts):
            logger.info(
                "解析结果: 未命中邀请码；合并行疑似活动/致谢文案且无「当前邀请码」锚点，"
                "跳过 Tesseract 兜底。若仍要跑兜底可设 WUKONG_OCR_FORCE_TESSERACT=1；"
                "或设 WUKONG_INVITE_OCR_VARIANTS=raw_and_crop 增加原图一路 Paddle。"
            )
            pick_trace.append("解析:跳过Tesseract(活动/无码文案)")
            return None, texts, pick_trace, variant_reports
        logger.info("解析结果: 未命中邀请码；Paddle 合并行数=%s，将尝试 Tesseract 兜底", len(texts))
        logger.info("Paddle 未解析出邀请码，尝试 Tesseract 兜底")
    except ImportError:
        logger.warning("未安装 paddleocr/paddlepaddle，回退 Tesseract（若可用）")
    except Exception:
        logger.exception("PaddleOCR 识别异常，回退 Tesseract（若可用）")

    code = _extract_with_pytesseract(png_bytes)
    if code:
        pick_trace.append("解析:Tesseract兜底命中")
        logger.info("解析结果: Tesseract 兜底命中 → %r", code)
    else:
        pick_trace.append("解析:Tesseract兜底仍无结果")
        logger.info("解析结果: Tesseract 兜底仍无邀请码")
    return code, texts, pick_trace, variant_reports


def extract_code_from_png(png_bytes: bytes) -> str | None:
    """
    从邀请码 PNG 识别字符：默认 **飞桨 PaddleOCR**；未安装或失败时尝试 Tesseract。
    测试环境可设环境变量 ``WUKONG_OCR_BACKEND=tesseract`` 强制走 Tesseract。
    """
    code, _, _, _ = extract_code_from_png_with_lines(png_bytes)
    return code
