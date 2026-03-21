#!/usr/bin/env python3
"""
本机「鼠标键盘助手」客户端：向 input_assistant_server 发送一行 JSON。

用法示例::

  python scripts/input_assistant_client.py ping
  python scripts/input_assistant_client.py center
  python scripts/input_assistant_client.py move 100 200
  python scripts/input_assistant_client.py flow -t helloworld
  python scripts/input_assistant_client.py flow hello world
  python scripts/input_assistant_client.py --raw '{"cmd":"vk_tap","vk":13}'

其它脚本可调用::

  from wukong_invite.input_assistant_flow import run_input_assistant_flow
  run_input_assistant_flow("helloworld", secret="...")  # 或依赖内置默认密钥常量

flow 起点：水平居中、竖直=虚拟屏高度 60%；下移 = 屏高×0.074。

密钥：默认与 ``input_assistant_server`` 相同，为代码内置常量；``--secret`` 可覆盖（须与服务端一致）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wukong_invite.input_assistant_flow import (
    FLOW_ANCHOR_Y_FRAC,
    FLOW_DOWN_FRAC,
    TEXT_DELIVERY_CLIPBOARD_PASTE,
    TEXT_DELIVERY_UNICODE,
    build_flow_commands,
    resolve_default_assistant_secret,
    run_input_assistant_flow,
    send_input_assistant_command as send_one,
    virtual_screen_center,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="鼠标键盘助手客户端")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=47821)
    ap.add_argument("--timeout", type=float, default=5.0)
    ap.add_argument("--secret", default="", help="明文密钥（覆盖内置常量，须与服务端一致）")
    ap.add_argument(
        "-t",
        "--flow-text",
        default="",
        metavar="STR",
        help="与 flow 联用：要键入的文本；也可写在 flow 之后（空格拼接）",
    )
    ap.add_argument(
        "--move-delay",
        type=float,
        default=0.1,
        metavar="SEC",
        help="flow 中每次 mouse_move 执行完后再等待的秒数（默认 0.1 = 100ms）",
    )
    ap.add_argument(
        "--click-delay",
        type=float,
        default=0.1,
        metavar="SEC",
        help="flow 中每次 mouse_click 执行完后再等待的秒数（默认 0.1 = 100ms）",
    )
    ap.add_argument(
        "--flow-clipboard",
        action="store_true",
        help="flow 第 3 步改为 Ctrl+V（须事先把文本放进剪贴板；避免 SendInput 中文失败）",
    )
    ap.add_argument(
        "--raw",
        dest="raw_json",
        nargs=1,
        default=None,
        metavar="JSON",
        help='发送一行 JSON（勿与 REMAINDER 混用；整条命令里 --raw 只出现一次）',
    )
    # 不用 REMAINDER：否则「子命令在前、-t 在后」时 -t 会掉进 tail 当普通字串
    args, rest = ap.parse_known_args()
    sec = (str(args.secret or "").strip()) or None
    if not sec:
        sec = resolve_default_assistant_secret()

    def wrap(cmd: dict) -> dict:
        if sec:
            cmd = {**cmd, "secret": sec}
        return cmd

    cmd: dict | None = None
    pending_flow_text: str | None = None

    if args.raw_json is not None:
        try:
            raw = json.loads(args.raw_json[0])
        except json.JSONDecodeError as e:
            print("无法解析 --raw JSON:", e, file=sys.stderr)
            return 2
        if not isinstance(raw, dict):
            print("--raw 必须是 JSON 对象", file=sys.stderr)
            return 2
        cmd = raw
        if sec:
            cmd = {**cmd, "secret": sec}
    elif not rest:
        ap.print_help()
        return 2
    else:
        sub = rest[0].lower()
        tail = rest[1:]
        if sub == "flow":
            text_to_type = (str(args.flow_text or "").strip()) or " ".join(tail).strip()
            if not text_to_type:
                print(
                    "flow 需要 -t/--flow-text 或在 flow 后提供要输入的文本。",
                    file=sys.stderr,
                )
                return 2
            pending_flow_text = text_to_type
        elif sub == "ping":
            cmd = wrap({"cmd": "ping"})
        elif sub == "center":
            try:
                cx, cy = virtual_screen_center()
            except RuntimeError as e:
                print(e, file=sys.stderr)
                return 2
            cmd = wrap({"cmd": "mouse_move", "x": cx, "y": cy})
            print(f"目标: 虚拟屏幕中心 ({cx}, {cy})", file=sys.stderr)
        elif sub == "move" and len(tail) >= 2:
            cmd = wrap({"cmd": "mouse_move", "x": int(tail[0]), "y": int(tail[1])})
        elif sub == "click":
            btn = tail[0] if tail else "left"
            if len(tail) >= 3:
                cmd = wrap(
                    {"cmd": "mouse_click", "button": btn, "x": int(tail[1]), "y": int(tail[2])}
                )
            else:
                cmd = wrap({"cmd": "mouse_click", "button": btn})
        elif sub == "down" and tail:
            cmd = wrap({"cmd": "mouse_down", "button": tail[0]})
        elif sub == "up" and tail:
            cmd = wrap({"cmd": "mouse_up", "button": tail[0]})
        elif sub == "wheel" and tail:
            cmd = wrap({"cmd": "wheel", "delta": int(tail[0])})
        elif sub == "hwheel" and tail:
            cmd = wrap({"cmd": "hwheel", "delta": int(tail[0])})
        elif sub == "text":
            cmd = wrap({"cmd": "text", "text": " ".join(tail)})
        elif sub == "combo" and len(tail) >= 2:
            mods = tail[:-1]
            key = tail[-1]
            cmd = wrap({"cmd": "key_combo", "mods": mods, "key": key})
        elif sub == "vk_tap" and tail:
            cmd = wrap({"cmd": "vk_tap", "vk": int(tail[0])})
        else:
            print("未知子命令或参数不足。见 --help", file=sys.stderr)
            return 2

    try:
        if pending_flow_text is not None:
            text_to_type = pending_flow_text
            td = TEXT_DELIVERY_CLIPBOARD_PASTE if args.flow_clipboard else TEXT_DELIVERY_UNICODE
            _, meta = build_flow_commands(text_to_type, text_delivery=td)
            cx, cy = meta["cx"], meta["cy"]
            vh, delta_y, y_down = meta["vh"], meta["delta_y"], meta["y_down"]
            step3 = "Ctrl+V 粘贴剪贴板" if td == TEXT_DELIVERY_CLIPBOARD_PASTE else f"输入 {text_to_type!r}"
            print(
                f"flow: 锚点=({cx},{cy}) 竖直{vh}px×{FLOW_ANCHOR_Y_FRAC:.2f} → 左键 → "
                f"{step3} → 下移{delta_y}px (屏高×{FLOW_DOWN_FRAC}) → ({cx},{y_down}) 左键",
                file=sys.stderr,
            )
            try:
                outs = run_input_assistant_flow(
                    text_to_type,
                    host=args.host,
                    port=int(args.port),
                    timeout=float(args.timeout),
                    secret=sec,
                    use_default_secret=False,
                    move_delay=float(args.move_delay),
                    click_delay=float(args.click_delay),
                    text_delivery=td,
                )
            except RuntimeError as e:
                print("flow 失败:", e, file=sys.stderr)
                return 3
            print(json.dumps(outs, ensure_ascii=False, indent=2))
            return 0

        assert cmd is not None
        out = send_one(cmd, host=args.host, port=int(args.port), timeout=float(args.timeout))
    except Exception as e:
        print("请求失败:", e, file=sys.stderr)
        return 1
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if not out.get("ok"):
        err = out.get("error")
        if err == "unauthorized":
            print(
                "提示: unauthorized = 客户端与服务端密钥不一致。"
                "请确认两端均为同一版本构建；若任一侧使用了 --secret，另一侧须相同。",
                file=sys.stderr,
            )
    return 0 if out.get("ok") else 3


if __name__ == "__main__":
    raise SystemExit(main())
