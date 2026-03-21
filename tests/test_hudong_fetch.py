import httpx
import pytest

from wukong_invite.hudong_fetch import (
    InviteImagePayload,
    fetch_invite_payload,
    parse_jsonp_body,
    payload_from_parsed,
)


def test_parse_jsonp_body() -> None:
    raw = 'img_url({"img_url":"https://gw.alicdn.com/x.png"})'
    d = parse_jsonp_body(raw)
    assert d["img_url"] == "https://gw.alicdn.com/x.png"


def test_payload_from_parsed() -> None:
    assert payload_from_parsed({}) is None
    p = payload_from_parsed({"img_url": "https://a/b.png"})
    assert isinstance(p, InviteImagePayload)
    assert p.img_url == "https://a/b.png"


def test_fetch_invite_payload_mock() -> None:
    body = 'img_url({"img_url":"https://example.com/code.png"})'

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body)

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        p = fetch_invite_payload(client=client)
    assert p is not None
    assert p.img_url == "https://example.com/code.png"
