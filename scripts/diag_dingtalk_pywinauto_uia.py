#!/usr/bin/env python3
"""
诊断：用 pywinauto UIA 连接 DingTalkReal.exe，枚举顶层窗口与控件树，查找可编辑区。

说明
----
- 连接方式与 ``run_test_02_wukong_window.py`` 一致：复用 ``connect_preferred_window``（PID+HWND，
  避免 ``connect(process=pid)`` 在受保护进程上失败）。
- 钉钉/悟空主界面大量为内嵌 Chromium：UIA 树里**可能没有**标准 ``Edit``，或仅有整块 ``Pane``；
  此时无法像示例那样 ``edit.set_text()``，仍需剪贴板+Ctrl+V 或坐标点击（见 ``ui_dingtalk.activate_and_type_text``）。
- ``type_keys`` / ``send_keys`` 本质是向系统注入键盘事件，**不是**纯 WM_CHAR 后台写控件；真正「免键盘注入」
  需控件暴露 UIA ValuePattern 且允许 SetValue。

用法
----
  python scripts/diag_dingtalk_pywinauto_uia.py
  python scripts/diag_dingtalk_pywinauto_uia.py --print-identifiers --depth 12
  python scripts/diag_dingtalk_pywinauto_uia.py --process DingTalkReal.exe --list-edit-like
  # 未找到 Edit-like 时会自动再打印一遍全部控件（扁平摘要），可用 --max-lines-all 放宽行数
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _resolve_uia_wrapper(window: object) -> object:
    if hasattr(window, "rectangle") and callable(getattr(window, "rectangle", None)):
        return window
    if hasattr(window, "wrapper_object"):
        try:
            wo = window.wrapper_object()
            if wo is not None:
                return wo
        except Exception:
            pass
        if hasattr(window, "wait"):
            try:
                window.wait("exists", timeout=10)
            except Exception:
                pass
            try:
                wo = window.wrapper_object()
                if wo is not None:
                    return wo
            except Exception:
                pass
    return window


def _ctrl_type_name(w: object) -> str:
    try:
        ei = getattr(w, "element_info", None)
        if ei is not None:
            ct = getattr(ei, "control_type", None)
            if ct is not None:
                return str(ct)
    except Exception:
        pass
    return "?"


def _brief_line(w: object, idx: int) -> str:
    try:
        ei = getattr(w, "element_info", None)
        name = (getattr(ei, "name", "") or "").replace("\n", " ")[:80]
        aid = (getattr(ei, "automation_id", "") or "")[:64]
        cls = (getattr(ei, "class_name", "") or "")[:48]
        rect = getattr(w, "rectangle", None)
        rtxt = ""
        if callable(rect):
            try:
                r = rect()
                rtxt = f" [{r.left},{r.top}-{r.right},{r.bottom}]"
            except Exception:
                rtxt = ""
        ct = _ctrl_type_name(w)
        h = 0
        try:
            h = int(getattr(ei, "handle", 0) or 0)
        except Exception:
            h = 0
        return (
            f"#{idx:4d} type={ct!r} name={name!r} auto_id={aid!r} class={cls!r} hwnd=0x{h:x}{rtxt}"
        )
    except Exception as e:
        return f"#{idx:4d} <error {e!r}>"


def _is_edit_like(w: object) -> bool:
    t = _ctrl_type_name(w).lower()
    if "edit" in t or "document" in t:
        return True
    try:
        ei = getattr(w, "element_info", None)
        name = (getattr(ei, "name", "") or "").lower()
        for k in ("输入", "消息", "说点什么", "compose", "editor"):
            if k.lower() in name:
                return True
    except Exception:
        pass
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description="DingTalkReal UIA 控件树诊断")
    ap.add_argument(
        "--process",
        default="DingTalkReal.exe",
        help="进程 exe 路径子串（默认 DingTalkReal.exe）",
    )
    ap.add_argument(
        "--title-re",
        default="",
        help="若按进程失败，可再试标题正则（与 run_test_02 --title-re 相同语义）",
    )
    ap.add_argument(
        "--print-identifiers",
        action="store_true",
        help="对主窗调用 print_control_identifiers（体量大，可配合重定向到文件）",
    )
    ap.add_argument(
        "--depth",
        type=int,
        default=None,
        help="传给 print_control_identifiers 的 depth（省略则由 pywinauto 默认）",
    )
    ap.add_argument(
        "--list-edit-like",
        action="store_true",
        help="扁平扫描 descendants，列出 Edit/Document 或名称含输入/消息 的控件",
    )
    ap.add_argument(
        "--max-lines",
        type=int,
        default=400,
        help="--list-edit-like 时最多打印条数（默认 400）",
    )
    ap.add_argument(
        "--max-scan",
        type=int,
        default=8000,
        help="descendants 最大遍历数量（防止极深树卡死，默认 8000）",
    )
    ap.add_argument(
        "--max-lines-all",
        type=int,
        default=5000,
        help="未找到 Edit-like 时「打印全部控件」最多输出行数（默认 5000）",
    )
    args = ap.parse_args()

    from wukong_invite.ui_dingtalk import connect_preferred_window

    title_patterns = [args.title_re] if str(args.title_re).strip() else None
    proc = (str(args.process).strip(),) if str(args.process).strip() else ()

    try:
        if proc:
            win, used = connect_preferred_window(
                title_patterns=title_patterns,
                process_paths=proc,
            )
        else:
            from wukong_invite.ui_dingtalk import connect_by_process_path_substring

            win, used = connect_by_process_path_substring(str(args.process).strip())
    except Exception as e:
        print("连接失败:", e, file=sys.stderr)
        print("请先启动钉钉/悟空，或执行:", file=sys.stderr)
        print("  python scripts/run_test_02_wukong_window.py --list-processes", file=sys.stderr)
        return 2

    wrap = _resolve_uia_wrapper(win)
    try:
        wtext = wrap.window_text()
    except Exception:
        wtext = "?"
    try:
        hwnd = int(getattr(wrap, "handle", 0) or 0)
    except Exception:
        hwnd = 0
    print("连接模式:", used)
    print("主窗标题:", repr(wtext))
    print("主窗 hwnd:", hex(hwnd) if hwnd else "(unknown)")
    try:
        r = wrap.rectangle()
        print("主窗矩形:", r.left, r.top, r.right, r.bottom)
    except Exception as e:
        print("主窗矩形: 无法读取", e)

    if args.print_identifiers:
        print("\n========== print_control_identifiers（开始）==========", flush=True)
        kw = {}
        if args.depth is not None:
            kw["depth"] = int(args.depth)
        try:
            wrap.print_control_identifiers(**kw)
        except TypeError:
            # 旧版 pywinauto 可能无 depth
            wrap.print_control_identifiers()
        print("========== print_control_identifiers（结束）==========", flush=True)

    if args.list_edit_like:
        print("\n========== Edit-like / 名称启发式 ==========", flush=True)
        try:
            desc = wrap.descendants()
        except Exception as e:
            print("descendants() 失败:", e, file=sys.stderr)
            return 1
        shown = 0
        lim = max(1, int(args.max_lines))
        scan_cap = max(100, int(args.max_scan))
        all_lim = max(1, int(args.max_lines_all))
        hit_scan_cap_edit_pass = False
        for i, c in enumerate(desc):
            if i >= scan_cap:
                hit_scan_cap_edit_pass = True
                break
            if _is_edit_like(c):
                print(_brief_line(c, i))
                shown += 1
                if shown >= lim:
                    print(f"... 已达 --max-lines={lim}")
                    break
        if hit_scan_cap_edit_pass and shown > 0:
            print(f"... 已截断（仅扫描前 {scan_cap} 个 descendant）")
        if shown == 0:
            print(
                "（未发现 Edit/Document 或名称匹配的控件；"
                "常见于 WebView 内嵌。下面打印本窗口下扁平的全部控件摘要供排查。）"
            )
            print("\n========== 全部控件（扁平摘要）==========", flush=True)
            printed = 0
            for i, c in enumerate(desc):
                if i >= scan_cap:
                    print(f"... 已截断（仅扫描前 {scan_cap} 个 descendant）")
                    break
                print(_brief_line(c, i))
                printed += 1
                if printed >= all_lim:
                    print(f"... 已达 --max-lines-all={all_lim}（增大该参数或 --max-scan 可继续看更多）")
                    break
            print(f"全部摘要: 本次打印 {printed} 行，descendants 总数 {len(desc)}，扫描上限 {scan_cap}")
        else:
            print(f"Edit-like 共列出 {shown} 条（扫描上限 {scan_cap}）")

    if not args.print_identifiers and not args.list_edit_like:
        print("\n提示: 加 --print-identifiers 打印完整树，或 --list-edit-like 只筛可编辑类控件。")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
