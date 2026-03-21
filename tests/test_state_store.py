import json
from pathlib import Path

from wukong_invite.state_store import InviteState


def test_invite_state_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "s.json"
    s = InviteState(p)
    assert s.last_img_url is None
    s.update(img_url="https://a/1.png", code="ABC123", image_sha256="deadbeef")
    s2 = InviteState(p)
    assert s2.last_img_url == "https://a/1.png"
    assert s2.last_code == "ABC123"
    assert s2.last_image_sha256 == "deadbeef"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["last_img_url"] == "https://a/1.png"
    assert data["last_image_sha256"] == "deadbeef"
