#!/usr/bin/env python3
"""
本机「鼠标键盘助手」服务端：监听 TCP，按行 JSON 执行输入。

重要（必读）
------------
- 默认只监听 **127.0.0.1**，避免局域网被远程控机。需要时可 ``--host``（自担风险）。
- 本仓库默认同目录助手与 exe 使用**同一内置密钥常量**（仅本机回环）；也可用 ``--secret`` 覆盖。
  客户端每条命令带同名 ``secret``。

协议：每行一个 UTF-8 JSON，回复一行 JSON。

示例命令（见 input_assistant_client.py）::

  {"cmd":"ping"}
  {"cmd":"mouse_move","x":100,"y":200}
  {"cmd":"mouse_click","button":"left","x":300,"y":400}
  {"cmd":"text","text":"你好"}
  {"cmd":"key_combo","mods":["ctrl"],"key":"v"}
  {"cmd":"vk_tap","vk":13}
  {"cmd":"wheel","delta":120}
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any


def _ensure_wukong_on_path() -> None:
    """支持仓库 ``scripts/`` 与 zip 解压目录（旁路带 ``wukong_invite`` 包）。"""
    here = Path(__file__).resolve().parent
    for base in (here, here.parent / "src"):
        if (base / "wukong_invite" / "__init__.py").is_file():
            root = str(base.resolve())
            if root not in sys.path:
                sys.path.insert(0, root)
            return
    print(
        "错误: 找不到 wukong_invite 包。请使用完整分发 zip（内含 wukong_invite 文件夹与本脚本同目录），"
        "或在已 pip install -e 的仓库中运行。",
        file=sys.stderr,
    )
    raise SystemExit(2)


_ensure_wukong_on_path()

MAX_LINE = 65536


def _normalize_client_cmd(cmd: dict[str, Any]) -> dict[str, Any]:
    """兼容部分脚本/工具使用 ``command``、``Secret`` 等大小写变体。"""
    c = cmd.get("cmd")
    if c is None or (isinstance(c, str) and not str(c).strip()):
        alt = cmd.get("command")
        if alt is None:
            alt = cmd.get("Command")
        if alt is not None:
            return {**cmd, "cmd": alt}
    return cmd


def _dispatch(cmd: dict[str, Any]) -> dict[str, Any]:
    name = str(cmd.get("cmd") or "").strip().lower()
    if name == "ping":
        return {"ok": True, "pong": True}
    from wukong_invite import input_assistant_win as low

    if name == "mouse_move":
        x, y = int(cmd["x"]), int(cmd["y"])
        ok = low.mouse_move(x, y)
        return {"ok": bool(ok)}
    if name == "mouse_click":
        btn = str(cmd.get("button") or "left")
        x = cmd.get("x")
        y = cmd.get("y")
        if x is not None and y is not None:
            ok = low.mouse_click(btn, x=int(x), y=int(y))
        else:
            ok = low.mouse_click(btn)
        return {"ok": bool(ok)}
    if name == "mouse_down":
        ok = low.mouse_down(str(cmd.get("button") or "left"))
        return {"ok": bool(ok)}
    if name == "mouse_up":
        ok = low.mouse_up(str(cmd.get("button") or "left"))
        return {"ok": bool(ok)}
    if name == "wheel":
        ok = low.mouse_wheel(int(cmd.get("delta") or 0))
        return {"ok": bool(ok)}
    if name == "hwheel":
        ok = low.mouse_hwheel(int(cmd.get("delta") or 0))
        return {"ok": bool(ok)}
    if name == "text":
        body = str(cmd.get("text") or "")
        ok = low.text_unicode(body)
        if ok:
            return {"ok": True}
        return {
            "ok": False,
            "error": "text_sendinput_failed",
            "hint": (
                "SendInput(KEYEVENTF_UNICODE) 未全部成功，常见于中文/WebView；"
                "若剪贴板已有文本可改用 key_combo Ctrl+V 或 run_test_01 的 clipboard 流程。"
            ),
        }
    if name == "vk_tap":
        ok = low.vk_tap(int(cmd["vk"]))
        return {"ok": bool(ok)}
    if name == "vk_down":
        ok = low.vk_down(int(cmd["vk"]))
        return {"ok": bool(ok)}
    if name == "vk_up":
        ok = low.vk_up(int(cmd["vk"]))
        return {"ok": bool(ok)}
    if name == "key_combo":
        mods = cmd.get("mods") or []
        if not isinstance(mods, list):
            return {"ok": False, "error": "mods must be a list"}
        key = str(cmd.get("key") or "")
        ok = low.key_combo([str(m) for m in mods], key)
        return {"ok": bool(ok)}
    return {"ok": False, "error": f"unknown cmd: {name!r}"}


def _check_secret(cmd: dict[str, Any], required: str | None) -> dict[str, Any] | None:
    if not required:
        return None
    raw = cmd.get("secret")
    if raw is None:
        raw = cmd.get("Secret")
    got = str(raw if raw is not None else "").strip()
    req = str(required).strip()
    if got != req:
        return {"ok": False, "error": "unauthorized"}
    return None


async def handle_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    secret: str | None,
) -> None:
    peer = writer.get_extra_info("peername")
    try:
        while True:
            line = await reader.readline()
            if not line:
                break
            if len(line) > MAX_LINE:
                writer.write(
                    (json.dumps({"ok": False, "error": "line too large"}, ensure_ascii=False) + "\n").encode(
                        "utf-8"
                    )
                )
                await writer.drain()
                break
            try:
                text = line.decode("utf-8").strip().lstrip("\ufeff")
                if not text:
                    continue
                cmd = json.loads(text)
            except Exception as e:
                writer.write(
                    (json.dumps({"ok": False, "error": f"bad json: {e!s}"}, ensure_ascii=False) + "\n").encode(
                        "utf-8"
                    )
                )
                await writer.drain()
                continue
            if not isinstance(cmd, dict):
                out = {"ok": False, "error": "payload must be object"}
            else:
                cmd = _normalize_client_cmd(cmd)
                bad = _check_secret(cmd, secret)
                out = bad if bad is not None else _dispatch(cmd)
            writer.write((json.dumps(out, ensure_ascii=False) + "\n").encode("utf-8"))
            await writer.drain()
    except (ConnectionResetError, BrokenPipeError, asyncio.CancelledError):
        pass
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass
        print("断开:", peer, flush=True)


async def main_async(host: str, port: int, secret: str | None) -> None:
    server = await asyncio.start_server(
        lambda r, w: handle_client(r, w, secret),
        host=host,
        port=port,
    )
    addrs = ", ".join(str(s.getsockname()) for s in server.sockets or [])
    print(f"input_assistant 监听 {addrs} secret={'on' if secret else 'off'}", flush=True)
    async with server:
        await server.serve_forever()


def main() -> int:
    ap = argparse.ArgumentParser(description="本机鼠标键盘助手 TCP 服务")
    ap.add_argument("--host", default="127.0.0.1", help="默认仅本机回环")
    ap.add_argument("--port", type=int, default=47821, help="TCP 端口（默认 47821）")
    ap.add_argument(
        "--secret",
        default="",
        help="可选；明文密钥，覆盖内置常量（须与客户端一致）",
    )
    ap.add_argument(
        "--secret-file",
        default="",
        help=argparse.SUPPRESS,
    )
    args = ap.parse_args()
    if str(getattr(args, "secret_file", "") or "").strip():
        print(
            "提示: --secret-file 已废弃（密钥改为内置常量）。请重新运行 register_input_assistant_task.ps1 更新计划任务。",
            file=sys.stderr,
        )
    sec = (str(args.secret or "").strip()) or None
    host_l = str(args.host or "").strip().lower()
    if not sec:
        if host_l in ("127.0.0.1", "::1", "localhost"):
            from wukong_invite.input_assistant_flow import resolve_default_assistant_secret

            sec = resolve_default_assistant_secret()
    if host_l not in ("127.0.0.1", "::1", "localhost") and not sec:
        print("错误: 非本机回环监听必须设置 --secret", file=sys.stderr)
        return 2
    try:
        asyncio.run(main_async(args.host, int(args.port), sec))
    except KeyboardInterrupt:
        print("退出", flush=True)
        return 0
    except OSError as e:
        print("启动失败:", e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
