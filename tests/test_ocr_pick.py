from wukong_invite.ocr_extract import _texts_from_paddle_output, pick_invite_candidate


def test_pick_full_text_when_no_anchor() -> None:
    """无「当前邀请码」五字锚点：全文去符号即码。"""
    assert pick_invite_candidate(["邀请码", "X", "AB12CD34EF"]) == "邀请码XAB12CD34EF"


def test_pick_from_invite_anchor() -> None:
    assert pick_invite_candidate(["当前邀请码：火云炼大圣", "限量10000个"]) == "火云炼大圣限量10000个"


def test_pick_from_invite_anchor_compact() -> None:
    assert pick_invite_candidate(["当前邀请码：火云炼大圣限量10000个已领完"]) == "火云炼大圣限量10000个已领完"


def test_pick_from_invite_no_colon_between_label_and_code() -> None:
    """OCR 漏识冒号时，「当前邀请码」与码紧挨在同一合并串里。"""
    assert pick_invite_candidate(["当前邀请码火云炼大圣", "限量"]) == "火云炼大圣限量"


def test_pick_anchor_tail_four_chars() -> None:
    """锚点后仅四字 + 符号：去符号后整段为码。"""
    assert pick_invite_candidate(["当前 邀请码", "白龙辞深", "-"]) == "白龙辞深"


def test_pick_anchor_tail_five_after_strip() -> None:
    assert pick_invite_candidate(["当前 邀请码", "白龙辞深涧"]) == "白龙辞深涧"


def test_pick_full_text_five_han_without_anchor() -> None:
    assert pick_invite_candidate(["甲乙丙丁戊"]) == "甲乙丙丁戊"


def test_pick_full_text_alnum_strip_hyphens() -> None:
    assert pick_invite_candidate(["code: AB-12-CD-34"]) == "codeAB12CD34"


def test_pick_full_text_digits_and_han() -> None:
    assert pick_invite_candidate(["10000", "限量"]) == "10000限量"


def test_paddle_v2_style_output() -> None:
    out = [[([0, 0], ("HELLO99", 0.99))]]
    texts = _texts_from_paddle_output(out)
    assert "HELLO99" in texts


def test_paddle_v3_style_dict() -> None:
    out = [{"res": {"rec_texts": ["foo", "INVITE99ZZ"]}}]
    texts = _texts_from_paddle_output(out)
    assert "INVITE99ZZ" in texts
