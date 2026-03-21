"""
Windows 用户态合成鼠标/键盘（ctypes SendInput / SetCursorPos / mouse_event）。

供 ``input_assistant_server`` 调用。须在**已登录用户的交互会话**中运行；
以 SYSTEM 身份跑在 Session 0 的「服务」无法向用户桌面注入输入。
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

if sys.platform != "win32":
    raise RuntimeError("input_assistant_win 仅支持 Windows")

user32 = ctypes.windll.user32

ULONG_PTR = ctypes.c_ulonglong

KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x1000


class MOUSEINPUT(ctypes.Structure):
    _fields_ = (
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    )


class KEYBDINPUT(ctypes.Structure):
    _fields_ = (
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    )


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = (
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    )


class INPUT_UNION(ctypes.Union):
    _fields_ = (("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT))


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = (("type", wintypes.DWORD), ("u", INPUT_UNION))


INPUT_MOUSE = 0
INPUT_KEYBOARD = 1


def _send_input(inputs: list[INPUT]) -> int:
    n = len(inputs)
    if n == 0:
        return 0
    arr = (INPUT * n)(*inputs)
    return int(user32.SendInput(n, ctypes.byref(arr), ctypes.sizeof(INPUT)))


def _clip_vscreen(x: int, y: int) -> tuple[int, int]:
    vx = user32.GetSystemMetrics(76)
    vy = user32.GetSystemMetrics(77)
    vw = user32.GetSystemMetrics(78)
    vh = user32.GetSystemMetrics(79)
    if vw < 1 or vh < 1:
        return int(x), int(y)
    xmax = vx + vw - 1
    ymax = vy + vh - 1
    return max(vx, min(xmax, int(x))), max(vy, min(ymax, int(y)))


def mouse_move(x: int, y: int) -> bool:
    x, y = _clip_vscreen(x, y)
    try:
        import win32api  # type: ignore

        win32api.SetCursorPos((int(x), int(y)))
        return True
    except Exception:
        pass
    return bool(user32.SetCursorPos(int(x), int(y)))


def _mouse_flag_pair(button: str) -> tuple[int, int]:
    b = (button or "left").strip().lower()
    if b in ("right", "r"):
        return MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP
    if b in ("middle", "m", "mid"):
        return MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP
    return MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP


def mouse_click(button: str = "left", *, x: int | None = None, y: int | None = None) -> bool:
    if x is not None and y is not None:
        mouse_move(int(x), int(y))
    down_f, up_f = _mouse_flag_pair(button)
    user32.mouse_event(down_f, 0, 0, 0, 0)
    user32.mouse_event(up_f, 0, 0, 0, 0)
    return True


def mouse_down(button: str = "left") -> bool:
    down_f, _ = _mouse_flag_pair(button)
    user32.mouse_event(down_f, 0, 0, 0, 0)
    return True


def mouse_up(button: str = "left") -> bool:
    _, up_f = _mouse_flag_pair(button)
    user32.mouse_event(up_f, 0, 0, 0, 0)
    return True


def mouse_wheel(delta: int) -> bool:
    user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, int(delta) & 0xFFFFFFFF, 0)
    return True


def mouse_hwheel(delta: int) -> bool:
    user32.mouse_event(MOUSEEVENTF_HWHEEL, 0, 0, int(delta) & 0xFFFFFFFF, 0)
    return True


_VK_MAP: dict[str, int] = {
    "back": 0x08,
    "tab": 0x09,
    "enter": 0x0D,
    "return": 0x0D,
    "shift": 0x10,
    "ctrl": 0x11,
    "control": 0x11,
    "alt": 0x12,
    "pause": 0x13,
    "caps": 0x14,
    "esc": 0x1B,
    "escape": 0x1B,
    "space": 0x20,
    "pgup": 0x21,
    "pageup": 0x21,
    "pgdn": 0x22,
    "pagedown": 0x22,
    "end": 0x23,
    "home": 0x24,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "insert": 0x2D,
    "delete": 0x2E,
    "lwin": 0x5B,
    "rwin": 0x5C,
    "apps": 0x5D,
    "f1": 0x70,
    "f2": 0x71,
    "f3": 0x72,
    "f4": 0x73,
    "f5": 0x74,
    "f6": 0x75,
    "f7": 0x76,
    "f8": 0x77,
    "f9": 0x78,
    "f10": 0x79,
    "f11": 0x7A,
    "f12": 0x7B,
}


def vk_from_name(name: str) -> int | None:
    s = (name or "").strip().lower()
    if not s:
        return None
    if s in _VK_MAP:
        return _VK_MAP[s]
    if len(s) == 1:
        if "a" <= s <= "z":
            return ord(s.upper())
        if "0" <= s <= "9":
            return ord(s)
        c = s.upper()
        if "A" <= c <= "Z":
            return ord(c)
    return None


def vk_down(vk: int) -> bool:
    vk = int(vk) & 0xFFFF
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.ki = KEYBDINPUT(vk, 0, 0, 0, 0)
    return _send_input([inp]) == 1


def vk_up(vk: int) -> bool:
    vk = int(vk) & 0xFFFF
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.ki = KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP, 0, 0)
    return _send_input([inp]) == 1


def vk_tap(vk: int) -> bool:
    return vk_down(vk) and vk_up(vk)


def key_combo(mods: list[str], key: str) -> bool:
    """例如 mods=[\"ctrl\"], key=\"v\" """
    mod_vks: list[int] = []
    for m in mods or []:
        v = vk_from_name(str(m))
        if v is None:
            continue
        if v in (0x11, 0x12, 0x10, 0x5B, 0x5C):
            mod_vks.append(v)
    key_v = vk_from_name(key)
    if key_v is None:
        try:
            key_v = int(key)
        except ValueError:
            return False
    for v in mod_vks:
        vk_down(v)
    try:
        vk_down(key_v)
        vk_up(key_v)
    finally:
        for v in reversed(mod_vks):
            vk_up(v)
    return True


def text_unicode(s: str) -> bool:
    """用 Unicode 键事件输入文本（不依赖键盘布局）。"""
    if not s:
        return True
    batch: list[INPUT] = []
    for ch in s:
        cp = ord(ch)
        down = INPUT()
        down.type = INPUT_KEYBOARD
        down.ki = KEYBDINPUT(0, cp, KEYEVENTF_UNICODE, 0, 0)
        up = INPUT()
        up.type = INPUT_KEYBOARD
        up.ki = KEYBDINPUT(0, cp, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, 0)
        batch.extend([down, up])
        if len(batch) >= 40:
            if _send_input(batch) != len(batch):
                return False
            batch.clear()
    if batch:
        if _send_input(batch) != len(batch):
            return False
    return True
