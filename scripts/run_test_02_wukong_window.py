#!/usr/bin/env python3
"""
测试 2：连接悟空前台窗口 → 置前（可选中心点击）→ 通过本机 input_assistant_server 执行与
``python scripts/input_assistant_client.py flow -t <文本>`` 相同的键鼠序列。

默认仅按进程 ``DingTalkReal.exe`` 连接；可选 ``--title-re``；``--no-process`` 时必须带 ``--title-re``。

用法:
  python scripts/run_test_02_wukong_window.py --list-processes
  python scripts/run_test_02_wukong_window.py --list-windows --filter "钉钉|悟空"
  python scripts/run_test_02_wukong_window.py -t helloworld
  python scripts/run_test_02_wukong_window.py --text "SMOKE_TEST_001"
  python scripts/run_test_02_wukong_window.py --no-center-click
  python scripts/run_test_02_wukong_window.py --process "DingTalkReal.exe"
  python scripts/run_test_02_wukong_window.py --no-process --title-re "(?i).*悟空.*" -t hello

密钥与 ``input_assistant_client`` 一致：``--secret`` / ``--secret-file`` / 环境变量 /
``%LOCALAPPDATA%\\wukong_input_assistant\\secret.txt``。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wukong_invite.input_assistant_flow import resolve_default_assistant_secret  # noqa: E402


def _resolve_assistant_secret(
    *,
    secret: str,
    secret_file: str,
) -> str:
    sec = (str(secret or "").strip()) or None
    if not sec:
        sf = (str(secret_file or "").strip()) or (
            os.environ.get("INPUT_ASSISTANT_SECRET_FILE") or ""
        ).strip()
        if sf:
            try:
                p = Path(sf).expanduser()
                if p.is_file():
                    line = p.read_text(encoding="utf-8").splitlines()[0].strip()
                    if line:
                        sec = line
            except OSError as e:
                print("无法读取 --secret-file:", e, file=sys.stderr)
                raise SystemExit(2) from e
    if sec:
        return sec
    return resolve_default_assistant_secret()


def main() -> int:
    ap = argparse.ArgumentParser(description="测试2：激活悟空窗口后通过 input_assistant 执行 flow 输入")
    ap.add_argument("--list-windows", action="store_true", help="仅列出匹配过滤的顶层窗口标题")
    ap.add_argument(
        "--filter",
        default="",
        help="与 --list-windows 联用：标题正则；省略则用内置宽匹配（钉钉/悟空/DingTalk 等）",
    )
    ap.add_argument(
        "-t",
        "--text",
        dest="text",
        default="helloworld",
        help="flow 要键入的文本（默认 helloworld）",
    )
    ap.add_argument(
        "--title-re",
        default="",
        help="指定后仅按该标题正则尝试（仍默认先 --process；与 --no-process 联用则只走标题）",
    )
    ap.add_argument(
        "--process",
        action="append",
        metavar="SUBSTR",
        help=(
            "可重复。按「进程可执行路径子串」连接（如 DingTalkReal.exe）；"
            "若给出本参数则只试列出的子串，不再用内置默认"
        ),
    )
    ap.add_argument(
        "--no-process",
        action="store_true",
        help="跳过按进程连接，仅用窗口标题（旧行为，易连错钉钉主窗）",
    )
    ap.add_argument(
        "--list-processes",
        action="store_true",
        help="列出路径名含 DingTalkReal/dingtalk 等的进程（pid、exe、命令行）",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="只解析参数并打印将使用的模式，不连接窗口",
    )
    ap.add_argument(
        "--focus-wait",
        type=float,
        default=1.0,
        help="连接成功后、置前/点击前额外等待秒数（便于你看清屏幕）",
    )
    ap.add_argument(
        "--no-center-click",
        action="store_true",
        help="不在窗口中心模拟鼠标左键（仅 set_focus；默认会中心点击以激活 WebView 内输入）",
    )
    ap.add_argument(
        "--center-hold",
        type=float,
        default=1.0,
        metavar="SEC",
        help="鼠标移到窗口中心后静止多少秒再左键单击（默认 1）",
    )
    ap.add_argument(
        "--center-move-duration",
        type=float,
        default=0.45,
        metavar="SEC",
        help="从当前光标位置滑向窗口中心所用秒数（SetCursorPos 插值，便于看见指针在动）",
    )
    ap.add_argument(
        "--center-move-steps",
        type=int,
        default=40,
        metavar="N",
        help="滑向中心的分段数（越大越平滑，默认 40）",
    )
    ap.add_argument(
        "--center-offset-y",
        type=int,
        default=None,
        metavar="PX",
        help=(
            "相对窗口几何中心向下偏移像素（默认 108；不设则用环境变量 "
            "WUKONG_CENTER_CLICK_OFFSET_Y 或内置 108）"
        ),
    )
    ap.add_argument(
        "--center-taps",
        type=int,
        default=2,
        metavar="N",
        help="目标点上连续点击次数（默认 2；与 --right-click 联用则为右键）",
    )
    ap.add_argument(
        "--right-click",
        action="store_true",
        help="中心序列使用右键；可配合 WUKONG_DEBUG_MOUSE=1 看是否弹出菜单",
    )
    ap.add_argument(
        "--click-delivery",
        choices=("mouse", "postmessage", "postmessage_then_mouse"),
        default=None,
        help=(
            "中心点击如何投递：mouse=物理光标（默认）；postmessage=WM_*BUTTON 不移动光标；"
            "postmessage_then_mouse=两者。也可设环境变量 WUKONG_CENTER_CLICK_DELIVERY"
        ),
    )
    ap.add_argument(
        "--mouse-after-focus-only",
        action="store_true",
        help="等价 WUKONG_SKIP_MOUSE_BEFORE_FOCUS=1：先置前窗口，再移动鼠标",
    )
    ap.add_argument("--host", default="127.0.0.1", help="input_assistant_server 地址")
    ap.add_argument("--port", type=int, default=47821, help="input_assistant_server 端口")
    ap.add_argument("--timeout", type=float, default=5.0, help="单条 TCP 请求超时（秒）")
    ap.add_argument("--secret", default="", help="明文密钥（优先）")
    ap.add_argument("--secret-file", default="", help="密钥文件首行")
    ap.add_argument(
        "--move-delay",
        type=float,
        default=0.1,
        metavar="SEC",
        help="flow 中每次 mouse_move 后的等待秒数（与 input_assistant_client 一致）",
    )
    ap.add_argument(
        "--click-delay",
        type=float,
        default=0.1,
        metavar="SEC",
        help="flow 中每次 mouse_click 后的等待秒数",
    )
    args = ap.parse_args()

    if args.no_process and not args.title_re.strip() and not args.list_windows and not args.list_processes:
        ap.error("--no-process 必须同时提供 --title-re（已取消自动标题回退，防止误连 Cursor 等）")

    if args.dry_run:
        print("dry-run: title_re =", args.title_re or "（不用；仅进程 DingTalkReal.exe）")
        print(
            "dry-run: process =",
            "跳过" if args.no_process else (args.process or "（内置 DingTalkReal.exe）"),
        )
        print("dry-run: flow text =", repr(args.text))
        print("dry-run: assistant =", f"{args.host}:{args.port}")
        return 0

    print("正在加载 pywinauto（首次在本机可能需数十秒）…", flush=True)
    from wukong_invite.input_assistant_flow import (  # noqa: E402
        FLOW_ANCHOR_Y_FRAC,
        FLOW_DOWN_FRAC,
        build_flow_commands,
        run_input_assistant_flow,
    )
    from wukong_invite.ui_dingtalk import (  # noqa: E402
        connect_preferred_window,
        list_process_modules_matching,
        list_visible_window_titles,
        prepare_window_for_input,
    )

    if args.list_processes:
        rows = list_process_modules_matching(("DingTalkReal", "dingtalk", "DingTalk", "钉钉"))
        print("========== 进程（exe 路径含 DingTalkReal / dingtalk 等）==========")
        if not rows:
            print("（无匹配；请打开悟空/钉钉后重试，或改大匹配子串）")
        for pid, name, cmdline in rows:
            cl = (cmdline or "").strip()
            if len(cl) > 120:
                cl = cl[:117] + "..."
            print(f"pid={pid}\n  exe={name}\n  cmd={cl or '（无）'}\n")
        print(f"共 {len(rows)} 个进程")
        return 0

    if args.list_windows:
        filt = args.filter.strip() or None
        titles = list_visible_window_titles(filter_re=filt)
        print("========== 顶层窗口标题（Win32 标题正则）==========")
        if not titles:
            print("（无匹配项；可去掉 --filter 或放宽正则）")
        for t in titles:
            print(t)
        print(f"\n共 {len(titles)} 个")
        return 0

    title_patterns = [args.title_re] if args.title_re.strip() else None
    if args.title_re.strip():
        re.compile(args.title_re)

    proc_paths: tuple[str, ...] | None
    if args.no_process:
        proc_paths = ()
    elif args.process:
        proc_paths = tuple(str(x).strip() for x in args.process if str(x).strip())
    else:
        proc_paths = None

    try:
        win, used = connect_preferred_window(
            title_patterns=title_patterns,
            process_paths=proc_paths,
        )
    except RuntimeError as e:
        print("失败:", e)
        print("提示: 先打开悟空客户端，再执行:")
        print("  python scripts/run_test_02_wukong_window.py --list-processes")
        print("  python scripts/run_test_02_wukong_window.py --list-windows --filter \"钉钉|悟空\"")
        return 2

    try:
        wtitle = win.window_text()
    except Exception:
        wtitle = "?"
    print(f"已连接窗口（模式 {used!r}），标题: {wtitle!r}")

    ch = max(0.0, args.center_hold)
    md = max(0.0, args.center_move_duration)
    ms = max(1, int(args.center_move_steps))
    coy = args.center_offset_y
    off_note = f"中心下移 {coy}px" if coy is not None else "中心下移（默认/环境变量）"
    taps = max(1, int(args.center_taps))
    btn_note = "右键" if args.right_click else "左键"
    cdel = (
        args.click_delivery
        or (os.environ.get("WUKONG_CENTER_CLICK_DELIVERY") or "").strip()
        or "mouse"
    )
    if args.mouse_after_focus_only:
        move_desc = "置前窗口 → "
    else:
        move_desc = f"置前窗口 → 鼠标约 {md:g}s 滑向目标（{ms} 段，{off_note}）→ "
    print(
        f"{args.focus_wait} 秒后将：{move_desc}"
        f"静止 {ch:g}s → {taps} 次{btn_note}（投递 {cdel}）→ "
        f"input_assistant flow 输入 {args.text!r}（{args.host}:{args.port}）",
        flush=True,
    )

    sec = _resolve_assistant_secret(secret=args.secret, secret_file=args.secret_file)
    _, meta = build_flow_commands(args.text)
    cx, cy = meta["cx"], meta["cy"]
    vh, delta_y, y_down = meta["vh"], meta["delta_y"], meta["y_down"]
    print(
        f"flow: 锚点=({cx},{cy}) 竖直{vh}px×{FLOW_ANCHOR_Y_FRAC:.2f} → 左键 → "
        f"输入 {args.text!r} → 下移{delta_y}px (屏高×{FLOW_DOWN_FRAC}) → ({cx},{y_down}) 左键",
        file=sys.stderr,
    )

    time.sleep(max(0.0, args.focus_wait))
    if args.mouse_after_focus_only:
        os.environ["WUKONG_SKIP_MOUSE_BEFORE_FOCUS"] = "1"
    cbtn = "right" if args.right_click else None
    wrap = prepare_window_for_input(
        win,
        pause_s=0.25,
        click_center=not args.no_center_click,
        center_click_hold_s=ch,
        center_move_duration_s=md,
        center_move_steps=ms,
        center_click_offset_y=coy,
        center_click_taps=taps,
        center_click_button=cbtn,
        center_click_delivery=args.click_delivery,
    )
    time.sleep(0.12)
    try:
        wrap.set_focus()
    except Exception:
        pass
    time.sleep(0.12)

    try:
        outs = run_input_assistant_flow(
            args.text,
            host=args.host,
            port=int(args.port),
            timeout=float(args.timeout),
            secret=sec,
            use_default_secret=False,
            move_delay=float(args.move_delay),
            click_delay=float(args.click_delay),
        )
    except RuntimeError as e:
        print("input_assistant flow 失败:", e, file=sys.stderr)
        return 3
    print(json.dumps(outs, ensure_ascii=False, indent=2))
    print("已发送 flow 输入。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
