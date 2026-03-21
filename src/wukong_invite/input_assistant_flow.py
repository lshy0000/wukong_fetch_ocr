"""
可复用的「flow」鼠标键盘序列：供 ``input_assistant_client`` 或其它脚本 import。

依赖本机已运行 ``input_assistant_server``；仅支持 Windows 下虚拟屏坐标计算。
"""
from __future__ import annotations

import json
import os
import socket
import sys
import time
from pathlib import Path

# flow 锚点：水平居中，竖直为虚拟屏高度的该比例（距顶 60%，偏下）
FLOW_ANCHOR_Y_FRAC = 0.60
# 相对锚点再下移：虚拟屏高度的该比例（× vh；1080p 约 80px）
FLOW_DOWN_FRAC = 0.074

# flow 第 3 步：``unicode`` = SendInput 逐字 Unicode（部分 WebView/中文环境会失败）；
# ``clipboard_paste`` = Ctrl+V（须事先把内容放进剪贴板，run_test_01 已 ``set_text``）。
TEXT_DELIVERY_UNICODE = "unicode"
TEXT_DELIVERY_CLIPBOARD_PASTE = "clipboard_paste"


def _env_screen_y_offset() -> int:
    """与 ui_dingtalk 一致：WUKONG_SCREEN_Y_OFFSET 加到 flow 里所有绝对屏幕 Y。"""
    raw = (os.environ.get("WUKONG_SCREEN_Y_OFFSET") or "").strip()
    if not raw:
        return 0
    try:
        return int(raw)
    except ValueError:
        return 0


def virtual_screen_metrics() -> tuple[int, int, int, int]:
    """虚拟屏外接矩形 (vx, vy, vw, vh)，GetSystemMetrics 76–79。"""
    if sys.platform != "win32":
        raise RuntimeError("virtual_screen_metrics 仅适用于 Windows")
    import ctypes

    u = ctypes.windll.user32
    vx = int(u.GetSystemMetrics(76))
    vy = int(u.GetSystemMetrics(77))
    vw = max(0, int(u.GetSystemMetrics(78)))
    vh = max(0, int(u.GetSystemMetrics(79)))
    return vx, vy, vw, vh


def virtual_screen_center() -> tuple[int, int]:
    """虚拟桌面外接矩形的几何中心。"""
    vx, vy, vw, vh = virtual_screen_metrics()
    return vx + vw // 2, vy + vh // 2


def flow_anchor_point(
    *,
    anchor_y_frac: float = FLOW_ANCHOR_Y_FRAC,
) -> tuple[int, int, int]:
    """返回 (cx, cy, vh)；cx 水平中心，cy = 顶边 + vh×anchor_y_frac。"""
    vx, vy, vw, vh = virtual_screen_metrics()
    cx = vx + vw // 2
    cy = vy + int(round(vh * float(anchor_y_frac)))
    return cx, cy, vh


def build_flow_commands(
    text: str,
    *,
    anchor_y_frac: float = FLOW_ANCHOR_Y_FRAC,
    down_frac: float = FLOW_DOWN_FRAC,
    text_delivery: str = TEXT_DELIVERY_UNICODE,
) -> tuple[list[dict], dict]:
    """
    构造 flow 五步 JSON 指令列表。

    返回 ``(commands, meta)``，``meta`` 含 ``cx, cy, vh, delta_y, y_down`` 便于日志。
    ``text_delivery`` 为 ``unicode`` 或 ``clipboard_paste``（后者对应 ``Ctrl+V``）。
    """
    td = text_delivery if text_delivery in (TEXT_DELIVERY_UNICODE, TEXT_DELIVERY_CLIPBOARD_PASTE) else TEXT_DELIVERY_UNICODE
    cx, cy, vh = flow_anchor_point(anchor_y_frac=anchor_y_frac)
    df = float(down_frac)
    delta_y = int(round(vh * df))
    y_adj = _env_screen_y_offset()
    cy2 = cy + y_adj
    y_down = cy + delta_y + y_adj
    if td == TEXT_DELIVERY_CLIPBOARD_PASTE:
        mid: dict = {"cmd": "key_combo", "mods": ["ctrl"], "key": "v"}
    else:
        mid = {"cmd": "text", "text": text}
    cmds: list[dict] = [
        {"cmd": "mouse_move", "x": cx, "y": cy2},
        {"cmd": "mouse_click", "button": "left", "x": cx, "y": cy2},
        mid,
        {"cmd": "mouse_move", "x": cx, "y": y_down},
        {"cmd": "mouse_click", "button": "left", "x": cx, "y": y_down},
    ]
    meta = {
        "cx": cx,
        "cy": cy2,
        "vh": vh,
        "delta_y": delta_y,
        "y_down": y_down,
        "screen_y_offset": y_adj,
        "anchor_y_frac": float(anchor_y_frac),
        "down_frac": df,
        "text_delivery": td,
    }
    return cmds, meta


def send_input_assistant_command(
    obj: dict,
    *,
    host: str = "127.0.0.1",
    port: int = 47821,
    timeout: float = 5.0,
) -> dict:
    """发送一行 JSON，返回解析后的响应 dict。"""
    data = (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")
    with socket.create_connection((host, port), timeout=timeout) as s:
        s.sendall(data)
        buf = bytearray()
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            buf.extend(chunk)
            if b"\n" in buf:
                line, _, _ = buf.partition(b"\n")
                return json.loads(line.decode("utf-8"))
    raise RuntimeError("no response from input assistant server")


def resolve_default_assistant_secret() -> str:
    """与 ``input_assistant_server`` 共用的默认密钥：内置常量 ``BUNDLED_INPUT_ASSISTANT_SECRET``。"""
    from wukong_invite.input_assistant_defaults import BUNDLED_INPUT_ASSISTANT_SECRET

    return BUNDLED_INPUT_ASSISTANT_SECRET


def _wrap_secret(cmd: dict, secret: str | None) -> dict:
    if secret:
        return {**cmd, "secret": secret}
    return cmd


def run_input_assistant_flow(
    text: str,
    *,
    host: str = "127.0.0.1",
    port: int = 47821,
    timeout: float = 5.0,
    secret: str | None = None,
    move_delay: float = 0.1,
    click_delay: float = 0.1,
    anchor_y_frac: float = FLOW_ANCHOR_Y_FRAC,
    down_frac: float = FLOW_DOWN_FRAC,
    text_delivery: str = TEXT_DELIVERY_UNICODE,
    use_default_secret: bool = True,
) -> list[dict]:
    """
    执行完整 flow：移动 → 点击 → 输入 ``text`` → 下移 → 再点击。

    - ``text_delivery``：``unicode`` 为逐字 SendInput；``clipboard_paste`` 为 Ctrl+V（剪贴板须已有内容）。
    - ``secret``：若非空则每条命令附带；若为空且 ``use_default_secret`` 为 True，则调用
      ``resolve_default_assistant_secret()``。
    - 任一步响应 ``ok`` 不为 True 时抛出 ``RuntimeError``。
    - 返回每步服务端响应列表。
    """
    t = (text or "").strip()
    if not t:
        raise ValueError("run_input_assistant_flow: text 不能为空")

    sec = secret
    if sec is None and use_default_secret:
        sec = resolve_default_assistant_secret()

    commands, _meta = build_flow_commands(
        t,
        anchor_y_frac=anchor_y_frac,
        down_frac=down_frac,
        text_delivery=text_delivery,
    )
    move_wait = max(0.0, float(move_delay))
    click_wait = max(0.0, float(click_delay))
    outs: list[dict] = []

    for i, c in enumerate(commands):
        o = send_input_assistant_command(
            _wrap_secret(c, sec),
            host=host,
            port=port,
            timeout=timeout,
        )
        outs.append(o)
        if not o.get("ok"):
            raise RuntimeError(
                f"input assistant flow failed at step {i + 1}: {c!r} -> {o!r}"
            )
        name = str(c.get("cmd") or "")
        if name == "mouse_move" and move_wait > 0:
            time.sleep(move_wait)
        elif name == "mouse_click" and click_wait > 0:
            time.sleep(click_wait)
        elif name == "key_combo" and click_wait > 0:
            time.sleep(click_wait)

    return outs
