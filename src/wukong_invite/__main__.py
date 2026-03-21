from __future__ import annotations

import argparse
import logging
from pathlib import Path

from wukong_invite.orchestrator import poll_loop, process_once
from wukong_invite.state_store import InviteState
from wukong_invite.ui_dingtalk import run_paste_flow


def _default_state_path() -> Path:
    return Path.home() / ".wukong_invite_state.json"


def main(argv: list[str] | None = None) -> int:
    """argv 为 None 时使用 sys.argv（兼容 setuptools 入口）。"""
    parser = argparse.ArgumentParser(description="悟空官网邀请码轮询与剪贴板工具")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_once = sub.add_parser("once", help="拉取一次，若有新变化则更新剪贴板")
    p_once.add_argument("--state", type=Path, default=_default_state_path())
    p_once.add_argument(
        "--skip-ocr",
        action="store_true",
        help="跳过 PaddleOCR/Tesseract，URL 变化时仅把图片 URL 写入剪贴板",
    )

    p_poll = sub.add_parser("poll", help="按间隔轮询（Ctrl+C 结束）")
    p_poll.add_argument("--state", type=Path, default=_default_state_path())
    p_poll.add_argument("--interval", type=float, default=0.5, help="秒，建议 0.3～2")
    p_poll.add_argument("--skip-ocr", action="store_true", help="同 once：跳过 OCR")
    p_poll.add_argument(
        "--paste-ui",
        action="store_true",
        help="每次剪贴板更新后尝试激活钉钉窗口并 Ctrl+V（需本机已开钉钉且标题能匹配）",
    )
    p_poll.add_argument(
        "--window-title-re",
        default=".*钉钉.*",
        help="pywinauto 连接窗口用的标题正则",
    )

    p_paste = sub.add_parser("paste-ui", help="仅执行：激活钉钉 + Ctrl+V（使用当前剪贴板）")
    p_paste.add_argument("--window-title-re", default=".*钉钉.*")

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.cmd == "once":
        st = InviteState(args.state)
        process_once(state=st, skip_ocr=args.skip_ocr)
        return 0

    if args.cmd == "poll":

        def maybe_paste(_code: str) -> None:
            if args.paste_ui:
                logging.getLogger(__name__).info("触发 UI 粘贴…")
                run_paste_flow(title_pattern=args.window_title_re)

        poll_loop(
            state_path=args.state,
            interval_s=args.interval,
            skip_ocr=args.skip_ocr,
            on_update_code=maybe_paste if args.paste_ui else None,
        )
        return 0

    if args.cmd == "paste-ui":
        run_paste_flow(title_pattern=args.window_title_re)
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
