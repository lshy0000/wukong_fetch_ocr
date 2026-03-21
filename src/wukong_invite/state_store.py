from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


class InviteState:
    """记录上次 img_url / 上次 OCR 文本，避免重复写剪贴板。"""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._data = load_json(path)

    @property
    def last_img_url(self) -> str | None:
        v = self._data.get("last_img_url")
        return v if isinstance(v, str) else None

    @property
    def last_code(self) -> str | None:
        v = self._data.get("last_code")
        return v if isinstance(v, str) else None

    @property
    def last_image_sha256(self) -> str | None:
        v = self._data.get("last_image_sha256")
        return v if isinstance(v, str) else None

    def update(
        self,
        *,
        img_url: str | None = None,
        code: str | None = None,
        image_sha256: str | None = None,
    ) -> None:
        if img_url is not None:
            self._data["last_img_url"] = img_url
        if code is not None:
            self._data["last_code"] = code
        if image_sha256 is not None:
            self._data["last_image_sha256"] = image_sha256
        save_json(self.path, self._data)
