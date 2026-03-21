from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx

from wukong_invite.config import DEFAULT_USER_AGENT, HUDONG_JSONP_BASE, JSONP_CALLBACK


@dataclass(frozen=True)
class InviteImagePayload:
    """互动接口返回的邀请码展示图信息（码本身在 PNG 内，需 OCR）。"""

    img_url: str


_JSONP_RE = re.compile(
    rf"{re.escape(JSONP_CALLBACK)}\s*\(\s*(\{{.*\}})\s*\)\s*;?\s*$",
    re.DOTALL,
)


def build_jsonp_url() -> str:
    t = int(time.time() * 1000)
    return f"{HUDONG_JSONP_BASE}?t={t}&callback={JSONP_CALLBACK}"


def parse_jsonp_body(text: str) -> dict[str, Any]:
    text = text.strip()
    m = _JSONP_RE.search(text)
    if not m:
        raise ValueError(f"无法解析 JSONP，期望 {JSONP_CALLBACK}({{...}}) 形式")
    return json.loads(m.group(1))


def payload_from_parsed(data: dict[str, Any]) -> InviteImagePayload | None:
    raw = data.get("img_url")
    if not raw or not isinstance(raw, str):
        return None
    url = raw.strip()
    if not url.startswith("http"):
        return None
    return InviteImagePayload(img_url=url)


def fetch_invite_payload(
    *,
    client: httpx.Client | None = None,
    timeout: float = 15.0,
) -> InviteImagePayload | None:
    """GET JSONP，解析出 img_url。"""
    url = build_jsonp_url()
    headers = {"User-Agent": DEFAULT_USER_AGENT}
    if client is None:
        with httpx.Client(headers=headers, timeout=timeout, follow_redirects=True) as c:
            r = c.get(url)
            r.raise_for_status()
            text = r.text
    else:
        r = client.get(url)
        r.raise_for_status()
        text = r.text
    data = parse_jsonp_body(text)
    return payload_from_parsed(data)


def download_image_bytes(img_url: str, *, client: httpx.Client | None = None, timeout: float = 30.0) -> bytes:
    headers = {"User-Agent": DEFAULT_USER_AGENT}
    if client is None:
        with httpx.Client(headers=headers, timeout=timeout, follow_redirects=True) as c:
            r = c.get(img_url)
            r.raise_for_status()
            return r.content
    r = client.get(img_url)
    r.raise_for_status()
    return r.content
