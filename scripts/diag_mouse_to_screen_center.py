#!/usr/bin/env python3
"""
诊断：能否用 Win32 控制鼠标移到「主显示器」中心。

在仓库根目录执行:
  python scripts/diag_mouse_to_screen_center.py
  python scripts/diag_mouse_to_screen_center.py --hold 5

若指针不动，常见原因：远程桌面/虚拟机捕获鼠标、安全软件拦截、无图形会话等。

若本脚本正常而 ``run_test_02_wukong_window.py`` 里鼠标仍异常，在 PowerShell 先试：
  $env:WUKONG_DEBUG_MOUSE=1
  python scripts/run_test_02_wukong_window.py
终端会打印 ``[wukong mouse]`` 目标坐标与 ``GetCursorPos``，便于对照。
"""
from __future__ import annotations

import argparse
import sys
import time


def main() -> int:
    p = argparse.ArgumentParser(description="将鼠标移到主屏中心（诊断 SetCursorPos）")
    p.add_argument(
        "--hold",
        type=float,
        default=3.0,
        help="移到中心后保持几秒再退出（默认 3）",
    )
    args = p.parse_args()

    try:
        import win32api
        import win32con
        import win32gui
    except ImportError as e:
        print("错误: 需要 pywin32（随 pywinauto 通常会装上）:", e, file=sys.stderr)
        print("可尝试: pip install pywin32", file=sys.stderr)
        return 1

    cx = win32api.GetSystemMetrics(win32con.SM_CXSCREEN)
    cy = win32api.GetSystemMetrics(win32con.SM_CYSCREEN)
    mx = cx // 2
    my = cy // 2

    try:
        before = win32api.GetCursorPos()
    except Exception as e:
        print("GetCursorPos 失败:", e)
        before = None

    print(f"主屏像素: {cx} x {cy}，目标中心: ({mx}, {my})")
    if before is not None:
        print(f"移动前光标: {before}")

    try:
        win32api.SetCursorPos((mx, my))
    except Exception as e:
        print("SetCursorPos 失败:", e)
        return 2

    time.sleep(0.05)
    try:
        after = win32api.GetCursorPos()
        print(f"移动后光标: {after}")
        if after != (mx, my):
            print(
                "提示: 坐标与目标不一致，可能是 DPI 缩放、多显示器或驱动改写光标位置。"
            )
    except Exception as e:
        print("再次 GetCursorPos 失败:", e)

    hold = max(0.0, float(args.hold))
    if hold > 0:
        print(f"保持 {hold:g}s（请观察指针是否在主屏中心）…", flush=True)
        time.sleep(hold)

    print("结束。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
