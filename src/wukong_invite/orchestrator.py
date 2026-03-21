from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Callable
from pathlib import Path

import httpx

from wukong_invite.config import DEFAULT_USER_AGENT
from wukong_invite.clipboard_util import set_text
from wukong_invite.hudong_fetch import download_image_bytes, fetch_invite_payload
from wukong_invite.ocr_extract import extract_code_from_png
from wukong_invite.state_store import InviteState

logger = logging.getLogger(__name__)


def process_once(
    *,
    state: InviteState,
    client: httpx.Client | None = None,
    skip_ocr: bool = False,
) -> str | None:
    """
    拉取一次 JSONP；若 img_url 变化则下载图、尝试 OCR、写剪贴板并更新 state。
    返回本次写入剪贴板的邀请码/文本；无更新返回 None。
    """
    payload = fetch_invite_payload(client=client)
    if payload is None:
        logger.warning("接口未返回有效 img_url")
        return None
    if payload.img_url == state.last_img_url:
        return None

    logger.info("检测到邀请图 URL 变化: %s", payload.img_url)
    png = download_image_bytes(payload.img_url, client=client)
    digest = hashlib.sha256(png).hexdigest()
    code: str | None = None
    if not skip_ocr:
        code = extract_code_from_png(png)
    if code:
        set_text(code)
        state.update(img_url=payload.img_url, code=code, image_sha256=digest)
        logger.info("已 OCR 并写入剪贴板: %s", code)
        return code
    set_text(payload.img_url)
    state.update(img_url=payload.img_url, image_sha256=digest)
    logger.warning(
        "OCR 未得到邀请码，已将图片 URL 写入剪贴板；请安装飞桨 paddlepaddle + pip install -e \".[paddle]\"，或设置 WUKONG_OCR_BACKEND=tesseract 并安装 Tesseract",
    )
    return payload.img_url


def poll_loop(
    *,
    state_path: Path,
    interval_s: float = 0.5,
    skip_ocr: bool = False,
    on_update_code: Callable[[str], None] | None = None,
) -> None:
    state = InviteState(state_path)
    headers = {"User-Agent": DEFAULT_USER_AGENT}
    with httpx.Client(headers=headers, timeout=20.0, follow_redirects=True) as client:
        while True:
            try:
                got = process_once(state=state, client=client, skip_ocr=skip_ocr)
                if got and on_update_code:
                    on_update_code(got)
            except Exception:
                logger.exception("本轮轮询失败")
            time.sleep(interval_s)
