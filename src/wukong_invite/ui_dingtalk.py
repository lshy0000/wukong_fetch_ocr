from __future__ import annotations

import os
import re
import sys
import time
from typing import Iterable


def _mouse_debug_enabled() -> bool:
    v = (os.environ.get("WUKONG_DEBUG_MOUSE") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _mouse_debug_print(*args: object) -> None:
    if _mouse_debug_enabled():
        print("[wukong mouse]", *args, flush=True)

# 通过「进程模块路径」子串连接（pywinauto path= 与 tasklist 中映像名匹配，大小写不敏感）
# 钉钉/悟空前台：按本机确认为 DingTalkReal.exe（不再默认尝试 wukong.exe）
DEFAULT_PROCESS_PATH_SUBSTRINGS: tuple[str, ...] = ("DingTalkReal.exe",)

# 相对窗口几何中心：点击目标纵向下移像素（屏幕 Y 向下为正）。可用 WUKONG_CENTER_CLICK_OFFSET_Y 或参数覆盖。
DEFAULT_CENTER_CLICK_OFFSET_Y = 108


def _env_screen_y_offset() -> int:
    """本机若整体「点高了」，设 WUKONG_SCREEN_Y_OFFSET 为正数（像素）把绝对 Y 下移。"""
    raw = (os.environ.get("WUKONG_SCREEN_Y_OFFSET") or "").strip()
    if not raw:
        return 0
    try:
        return int(raw)
    except ValueError:
        return 0

def activate_window_title_match(title_pattern: str, *, timeout: float = 8.0) -> object:
    """
    通过窗口标题正则连接前台应用（默认 UIA 后端）。
    返回 pywinauto 主窗口对象；失败抛异常。
    """
    from pywinauto import Application

    app = Application(backend="uia").connect(title_re=title_pattern, timeout=timeout)
    return app.top_window()


def list_process_modules_matching(
    substrings: Iterable[str] | None = None,
    *,
    max_rows: int = 80,
) -> list[tuple[int, str, str | None]]:
    """
    列出当前进程中，可执行文件路径包含任一子串的项。

    返回 ``(pid, exe_path, cmdline_or_None)``，便于确认本机映像名（如 DingTalkReal.exe）。
    """
    from pywinauto.application import process_get_modules

    subs = tuple(
        s.strip() for s in (substrings or ("DingTalkReal", "dingtalk")) if s and str(s).strip()
    )
    if not subs:
        return []
    out: list[tuple[int, str, str | None]] = []
    for pid, name, cmdline in process_get_modules():
        if not name:
            continue
        nl = name.lower()
        if any(s.lower() in nl for s in subs):
            out.append((pid, name, cmdline))
            if len(out) >= max_rows:
                break
    return out


def _pids_matching_exe_path_substring(sub: str) -> list[int]:
    """
    用与 ``list_process_modules_matching`` 相同的 ``process_get_modules()`` 枚举 PID。

    pywinauto 的 ``connect(path=…)`` 优先走 WMI，可能漏进程；``connect(process=pid)``
    依赖 ``OpenProcess(PROCESS_QUERY_INFORMATION)``，对 DingTalkReal 等常失败。
    上层应改用本函数得到 PID 后走 ``EnumWindows`` + ``connect(handle=…)``。
    """
    from pywinauto.application import process_get_modules

    needle = sub.strip().lower()
    if not needle:
        return []
    # (score, pid)； basename 完全等于子串（如 dingtalkreal.exe）优先于路径中仅包含片段
    best: list[tuple[int, int]] = []
    for pid, exe_path, _cmd in process_get_modules():
        if not exe_path:
            continue
        pl = exe_path.lower()
        if needle not in pl:
            continue
        base = os.path.basename(pl)
        score = 2 if base == needle else 1
        best.append((score, pid))
    if not best:
        return []
    top = max(s for s, _ in best)
    pids = [p for s, p in best if s == top]
    return pids


def _top_level_visible_hwnds_for_pid(pid: int) -> list[int]:
    """枚举某 PID 下可见的顶层 HWND（不 OpenProcess，避免受保护进程上 QUERY_INFORMATION 失败）。"""
    try:
        import win32gui
        import win32process

        out: list[int] = []

        def cb(hwnd: int, _ctx: object) -> bool:
            if not win32gui.IsWindowVisible(hwnd):
                return True
            try:
                if win32gui.GetParent(hwnd) != 0:
                    return True
            except Exception:
                return True
            try:
                _, wp = win32process.GetWindowThreadProcessId(hwnd)
            except Exception:
                return True
            if wp == pid:
                out.append(int(hwnd))
            return True

        win32gui.EnumWindows(cb, None)
        return out
    except ImportError:
        return _top_level_visible_hwnds_for_pid_ctypes(pid)


def _top_level_visible_hwnds_for_pid_ctypes(pid: int) -> list[int]:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    found: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def enum_proc(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        if user32.GetParent(hwnd) != 0:
            return True
        cpid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(cpid))
        if int(cpid.value) == pid:
            found.append(int(hwnd))
        return True

    user32.EnumWindows(enum_proc, 0)
    return found


def _pick_largest_hwnd(hwnds: list[int]) -> int:
    """同 PID 多顶层窗时取屏幕面积最大者（通常为主窗）。"""
    if len(hwnds) == 1:
        return hwnds[0]
    try:
        import win32gui

        best, best_a = hwnds[0], -1
        for h in hwnds:
            try:
                l, t, r, b = win32gui.GetWindowRect(h)
                a = max(0, r - l) * max(0, b - t)
            except Exception:
                a = 0
            if a > best_a:
                best_a, best = a, h
        return best
    except ImportError:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        rect = wintypes.RECT()
        best, best_a = hwnds[0], -1
        for h in hwnds:
            if user32.GetWindowRect(h, ctypes.byref(rect)):
                a = max(0, rect.right - rect.left) * max(0, rect.bottom - rect.top)
            else:
                a = 0
            if a > best_a:
                best_a, best = a, h
        return best


def connect_by_process_path_substring(
    path_substring: str,
    *,
    timeout: float = 8.0,
    backend: str = "uia",
) -> tuple[object, str]:
    """
    按正在运行的进程可执行路径子串连接。

    1. ``process_get_modules`` 匹配路径得到 PID；
    2. ``EnumWindows`` 找该 PID 的可见顶层 HWND，取面积最大窗；
    3. ``connect(handle=hwnd)`` — 避免 ``connect(process=pid)`` 内对目标进程 ``OpenProcess``
       使用 ``PROCESS_QUERY_INFORMATION``，在 DingTalkReal 等进程上常失败（误报 PID 不存在）。
    4. 若无 PID 匹配，再退回 ``connect(path=…)``。
    """
    from pywinauto import Application
    from pywinauto.application import ProcessNotFoundError

    ps = path_substring.strip()
    if not ps:
        raise ValueError("path_substring 不能为空")

    pids = _pids_matching_exe_path_substring(ps)
    if pids:
        pid = pids[-1]
        hwnds = _top_level_visible_hwnds_for_pid(pid)
        if hwnds:
            hwnd = _pick_largest_hwnd(hwnds)
            app = Application(backend=backend).connect(handle=hwnd)
            w = app.window(handle=hwnd)
            return w, f"process(pid={pid}, hwnd=0x{hwnd:x}, match={ps!r})"
        raise ProcessNotFoundError(
            f"已解析 PID={pid}（{ps!r}），但该进程无可见顶层窗口（若最小化请还原后再试）"
        )

    app = Application(backend=backend).connect(path=ps, timeout=timeout)
    w = app.top_window()
    return w, f"process(path={ps!r})"


def list_visible_window_titles(
    *,
    filter_re: str | None = None,
    max_titles: int = 200,
) -> list[str]:
    """
    枚举可见顶层窗口标题（Win32 句柄 + 标题正则），比遍历 UIA Desktop 快得多。
    filter_re 为空时使用「钉钉|悟空|DingTalk|dingtalk」宽匹配（不含裸 ``wukong``，减少 IDE 误匹配）。
    """
    from pywinauto import findwindows
    from pywinauto.win32functions import GetWindowText

    if filter_re and str(filter_re).strip():
        pat_str = str(filter_re).strip()
    else:
        # 默认不含裸子串 wukong：避免匹配到 Cursor 等标题里的「…wukong_window.py」
        pat_str = r"(?i).*(钉钉|悟空|DingTalk|dingtalk)"
    re.compile(pat_str)
    handles = findwindows.find_windows(title_re=pat_str, visible_only=True)
    out: list[str] = []
    seen: set[str] = set()
    for h in handles:
        try:
            t = (GetWindowText(h) or "").strip()
            if not t or t in seen:
                continue
            seen.add(t)
            out.append(t)
            if len(out) >= max_titles:
                break
        except Exception:
            continue
    return sorted(out, key=len)


def connect_preferred_window(
    title_patterns: Iterable[str] | None = None,
    *,
    process_paths: Iterable[str] | None = None,
    timeout_process: float = 8.0,
    timeout_per_pattern: float = 2.5,
) -> tuple[object, str]:
    """
    连接钉钉/悟空对应前台窗口（默认按进程，不做标题模糊回退）。

    1. 按 **进程模块路径子串** 连接（``process_paths=None`` 时仅 ``DingTalkReal.exe``）。
    2. **不会**自动用含 ``wukong`` 的泛标题正则（易误连 IDE 里打开的脚本路径）。
       仅当调用方传入非空 ``title_patterns`` 时，在进程阶段失败（或 ``process_paths=()``）后才按标题试。

    - ``process_paths=None``：使用内置子串列表。
    - ``process_paths=()``：不连接进程，只试 ``title_patterns``（须非空）。
    - ``title_patterns``：显式标题正则；省略则进程全失败即报错。
    """
    errs: list[str] = []

    if process_paths is None:
        pseq = DEFAULT_PROCESS_PATH_SUBSTRINGS
    else:
        pseq = tuple(process_paths)

    for sub in pseq:
        if not str(sub).strip():
            continue
        try:
            return connect_by_process_path_substring(
                str(sub).strip(),
                timeout=timeout_process,
            )
        except Exception as e:
            errs.append(f"process {sub!r}: {e}")
            continue

    seq = tuple(p for p in (title_patterns or ()) if p and str(p).strip())
    for pat in seq:
        re.compile(pat)
        try:
            w = activate_window_title_match(pat, timeout=timeout_per_pattern)
            return w, pat
        except Exception as e:
            errs.append(f"title {pat!r}: {e}")
            continue
    raise RuntimeError(
        "未找到 DingTalkReal.exe 进程或其顶层窗口。"
        " 默认只按进程定位，避免标题里的「wukong」误连 IDE。\n"
        " 请先启动钉钉/悟空，或执行:\n"
        "  python scripts/run_test_02_wukong_window.py --list-processes\n"
        " 可用 --process 指定本机实际映像子串。\n"
        "若必须按标题连接，请显式传入 title_patterns（脚本中 --title-re）。\n"
        + "\n".join(errs)
    )


def _resolve_uia_wrapper(window: object) -> object:
    """把 WindowSpecification 等解析成带 rectangle / handle 的 UIA 包装对象。"""
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


def _hwnd_from_wrapper(wrap: object) -> int:
    """从 UIA/Hwnd 包装器取顶层 HWND（供 ScreenToClient / click_input）。"""
    try:
        h = int(getattr(wrap, "handle", 0) or 0)
        if h and h != -1:
            return h
    except Exception:
        pass
    try:
        ei = getattr(wrap, "element_info", None)
        if ei is not None:
            h = int(getattr(ei, "handle", 0) or 0)
            if h and h != -1:
                return h
    except Exception:
        pass
    return 0


def _normalize_center_click_button(name: str | None) -> str:
    """返回 ``left`` 或 ``right``（供中心点击序列使用）。"""
    v = (name or "left").strip().lower()
    if v in ("right", "r", "secondary"):
        return "right"
    return "left"


def _center_click_button_effective(explicit: str | None) -> str:
    """显式参数优先，否则读环境变量 ``WUKONG_CENTER_CLICK_BUTTON``。"""
    if explicit is not None and str(explicit).strip():
        return _normalize_center_click_button(explicit)
    e = (os.environ.get("WUKONG_CENTER_CLICK_BUTTON") or "").strip().lower()
    if e in ("right", "r", "secondary"):
        return "right"
    return "left"


def _center_click_delivery_effective(explicit: str | None) -> str:
    """
    中心点击如何投递到窗口。

    - ``mouse``：``click_input`` / ``mouse_event``（依赖系统光标，受 UIPI 影响大）
    - ``postmessage``：``PostMessage(WM_*BUTTON*)``，**不移动**系统光标；Chromium 内可能仍无响应
    - ``postmessage_then_mouse``：先 PostMessage 再尝试物理路径
    """
    if explicit is not None and str(explicit).strip():
        v = str(explicit).strip().lower()
    else:
        v = (os.environ.get("WUKONG_CENTER_CLICK_DELIVERY") or "mouse").strip().lower()
    if v in ("postmessage", "pm", "message"):
        return "postmessage"
    if v in ("postmessage_then_mouse", "both", "pm+mouse"):
        return "postmessage_then_mouse"
    return "mouse"


def _skip_mouse_before_focus() -> bool:
    """环境变量 ``WUKONG_SKIP_MOUSE_BEFORE_FOCUS=1``：不在置前窗口前移动鼠标（仅置后再移/或仅 PostMessage）。"""
    v = (os.environ.get("WUKONG_SKIP_MOUSE_BEFORE_FOCUS") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _is_user_an_admin() -> bool:
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _pid_token_is_elevated(pid: int) -> bool | None:
    """
    若可打开进程令牌则返回该 PID 是否「提升」；无法查询时返回 None。

    用于判断 UIPI 场景：前台为提升进程、本脚本未提升时常导致 SetCursorPos/SendInput 无效。
    """
    try:
        import ctypes
        from ctypes import wintypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        TOKEN_QUERY = 0x0008
        TokenElevation = 20

        class TOKEN_ELEVATION(ctypes.Structure):
            _fields_ = [("TokenIsElevated", wintypes.DWORD)]

        kernel32 = ctypes.windll.kernel32
        advapi32 = ctypes.windll.advapi32
        hproc = kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, wintypes.DWORD(int(pid))
        )
        if not hproc:
            return None
        try:
            token = wintypes.HANDLE()
            if not advapi32.OpenProcessToken(hproc, TOKEN_QUERY, ctypes.byref(token)):
                return None
            try:
                te = TOKEN_ELEVATION()
                ret_len = wintypes.DWORD(0)
                if not advapi32.GetTokenInformation(
                    token,
                    TokenElevation,
                    ctypes.byref(te),
                    ctypes.sizeof(TOKEN_ELEVATION),
                    ctypes.byref(ret_len),
                ):
                    return None
                return bool(te.TokenIsElevated)
            finally:
                kernel32.CloseHandle(token)
        finally:
            kernel32.CloseHandle(hproc)
    except Exception:
        return None


def _warn_if_synthetic_input_likely_blocked(target_hwnd: int) -> None:
    """目标已提升、本进程未提升时打印一次 stderr 提示（与常见 SetCursorPos 失效现象一致）。"""
    if not target_hwnd:
        return
    try:
        import win32process

        r = win32process.GetWindowThreadProcessId(int(target_hwnd))
        if isinstance(r, tuple) and len(r) >= 2:
            pid = int(r[1])
        else:
            return
    except Exception:
        return
    elevated = _pid_token_is_elevated(int(pid))
    if elevated is not True:
        return
    if _is_user_an_admin():
        return
    print(
        "[wukong] 目标窗口进程以管理员/提升身份运行，而当前 Python 未提升："
        "Windows（UIPI）常会拦截 SetCursorPos/SendInput。"
        "请以管理员身份运行终端后重试；或试 WUKONG_CENTER_CLICK_DELIVERY=postmessage。"
        "参考: https://stackoverflow.com/questions/65691101",
        file=sys.stderr,
    )


def _post_message_button_click_client(
    hwnd: int,
    client_x: int,
    client_y: int,
    *,
    button: str = "left",
) -> bool:
    """向 HWND 客户区投递左/右键按下抬起（不移动系统光标）。失败返回 False。"""
    try:
        import win32api
        import win32con
        import win32gui

        btn = _normalize_center_click_button(button)
        if btn == "right":
            down, up, mk = (
                win32con.WM_RBUTTONDOWN,
                win32con.WM_RBUTTONUP,
                win32con.MK_RBUTTON,
            )
        else:
            down, up, mk = (
                win32con.WM_LBUTTONDOWN,
                win32con.WM_LBUTTONUP,
                win32con.MK_LBUTTON,
            )
        x, y = int(client_x), int(client_y)
        try:
            ch = win32gui.ChildWindowFromPoint(hwnd, (x, y))
            if ch and ch != hwnd:
                sx, sy = win32gui.ClientToScreen(hwnd, (x, y))
                x, y = win32gui.ScreenToClient(ch, (sx, sy))
                hwnd = int(ch)
        except Exception:
            pass
        lp = win32api.MAKELONG(x & 0xFFFF, y & 0xFFFF)
        win32gui.PostMessage(hwnd, down, mk, lp)
        time.sleep(0.03)
        win32gui.PostMessage(hwnd, up, 0, lp)
        return True
    except Exception as e:
        _mouse_debug_print("PostMessage 点击失败:", e)
        return False


def _click_client_input_at_screen(
    wrap: object,
    screen_x: int,
    screen_y: int,
    *,
    button: str = "left",
) -> bool:
    """
    用包装器 ``click_input`` + 客户区坐标点击，相对裸 ``mouse_event`` 更易把焦点交给内嵌 WebView。
    ``button`` 为 ``left`` / ``right``（与 pywinauto 一致）。
    """
    try:
        import win32gui

        hwnd = _hwnd_from_wrapper(wrap)
        if not hwnd:
            return False
        cx, cy = win32gui.ScreenToClient(hwnd, (int(screen_x), int(screen_y)))
        ci = getattr(wrap, "click_input", None)
        if not callable(ci):
            return False
        btn = _normalize_center_click_button(button)
        ci(coords=(int(cx), int(cy)), button=btn)
        return True
    except Exception as e:
        _mouse_debug_print("click_input 失败:", e)
        return False


def _force_foreground_win32(hwnd: int) -> None:
    """
    尽量把 HWND 抢到系统前台。Win10/11 对 SetForegroundWindow 有限制，需组合：

    - 与当前前台线程 ``AttachThreadInput`` 再 SetForegroundWindow；
    - 轻按 Alt 松手，打断前台锁（常见自动化手段）；
    - 可选 ``SwitchToThisWindow``（未公开 API，失败则忽略）。
    """
    if not hwnd:
        return
    try:
        import ctypes
        import win32api
        import win32con
        import win32gui
        import win32process
    except Exception:
        return

    if not win32gui.IsWindow(hwnd):
        return

    try:
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
    except Exception:
        pass

    fg = 0
    try:
        fg = int(win32gui.GetForegroundWindow() or 0)
    except Exception:
        fg = 0

    fg_tid = 0
    if fg:
        try:
            fg_tid = win32process.GetWindowThreadProcessId(fg)[0]
        except Exception:
            fg_tid = 0

    cur_tid = 0
    try:
        cur_tid = win32api.GetCurrentThreadId()
    except Exception:
        return

    attached = False
    if fg_tid and fg_tid != cur_tid:
        try:
            win32process.AttachThreadInput(cur_tid, fg_tid, True)
            attached = True
        except Exception:
            pass

    try:
        try:
            win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
            time.sleep(0.03)
            win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
            time.sleep(0.03)
        except Exception:
            pass
        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass
        try:
            win32gui.BringWindowToTop(hwnd)
        except Exception:
            pass
        try:
            win32gui.SetActiveWindow(hwnd)
        except Exception:
            pass
        try:
            win32gui.SetFocus(hwnd)
        except Exception:
            pass
        try:
            win32gui.SetWindowPos(
                hwnd,
                win32con.HWND_TOPMOST,
                0,
                0,
                0,
                0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW,
            )
            time.sleep(0.08)
            win32gui.SetWindowPos(
                hwnd,
                win32con.HWND_NOTOPMOST,
                0,
                0,
                0,
                0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE,
            )
        except Exception:
            pass
        try:
            ctypes.windll.user32.SwitchToThisWindow(hwnd, True)
        except Exception:
            pass
    finally:
        if attached:
            try:
                win32process.AttachThreadInput(cur_tid, fg_tid, False)
            except Exception:
                pass


def _bring_window_to_front(wrapper: object) -> None:
    """还原、Show，并调用强前台逻辑 + UIA set_focus。"""
    hwnd = 0
    try:
        hwnd = int(getattr(wrapper, "handle", 0) or 0)
    except Exception:
        hwnd = 0
    if hwnd:
        _force_foreground_win32(hwnd)
    try:
        wrapper.set_focus()
    except Exception:
        pass


def _window_center_screen_coords(wrapper: object) -> tuple[int, int]:
    """窗口在屏幕上的外接矩形中心。优先 ``GetWindowRect(hwnd)``，与 ``SetCursorPos`` 同一套坐标。"""
    hwnd = 0
    try:
        hwnd = int(getattr(wrapper, "handle", 0) or 0)
    except Exception:
        hwnd = 0
    if hwnd:
        try:
            import win32gui

            L, T, R, B = win32gui.GetWindowRect(hwnd)
            return (L + R) // 2, (T + B) // 2
        except Exception:
            pass
    r = wrapper.rectangle()
    return (int(r.left) + int(r.right)) // 2, (int(r.top) + int(r.bottom)) // 2


def _effective_center_click_offset_y(explicit: int | None) -> int:
    if explicit is not None:
        return int(explicit)
    raw = (os.environ.get("WUKONG_CENTER_CLICK_OFFSET_Y") or "").strip()
    if raw:
        try:
            return int(raw)
        except ValueError:
            pass
    return DEFAULT_CENTER_CLICK_OFFSET_Y


def _window_click_point_screen(
    wrapper: object,
    *,
    offset_y: int | None = None,
) -> tuple[int, int]:
    """几何中心 + 纵向偏移（默认下移 ``DEFAULT_CENTER_CLICK_OFFSET_Y``）。"""
    cx, cy = _window_center_screen_coords(wrapper)
    oy = _effective_center_click_offset_y(offset_y)
    return cx, cy + oy + _env_screen_y_offset()


def _clip_point_to_virtual_screen(x: int, y: int) -> tuple[int, int]:
    """把坐标限制在虚拟桌面范围内，非法坐标会导致 SetCursorPos 异常。"""
    try:
        import win32api
        import win32con

        vx = win32api.GetSystemMetrics(win32con.SM_XVIRTUALSCREEN)
        vy = win32api.GetSystemMetrics(win32con.SM_YVIRTUALSCREEN)
        vw = win32api.GetSystemMetrics(win32con.SM_CXVIRTUALSCREEN)
        vh = win32api.GetSystemMetrics(win32con.SM_CYVIRTUALSCREEN)
    except Exception:
        return int(x), int(y)
    if vw < 1 or vh < 1:
        return int(x), int(y)
    xmax = vx + vw - 1
    ymax = vy + vh - 1
    return max(vx, min(xmax, int(x))), max(vy, min(ymax, int(y)))


def _set_cursor_sendinput_virtual_desk(x: int, y: int) -> bool:
    """
    用 ``SendInput`` + ``MOUSEEVENTF_ABSOLUTE|MOUSEEVENTF_VIRTUALDESK`` 定位光标。
    在部分环境下 ``SetCursorPos`` 抢前台后会失败，此路径可作兜底。
    """
    import ctypes
    from ctypes import wintypes

    x, y = _clip_point_to_virtual_screen(x, y)
    user32 = ctypes.windll.user32
    vx = user32.GetSystemMetrics(76)
    vy = user32.GetSystemMetrics(77)
    vw = user32.GetSystemMetrics(78)
    vh = user32.GetSystemMetrics(79)
    if vw < 2 or vh < 2:
        return False
    nx = int((x - vx) * 65535 / (vw - 1))
    ny = int((y - vy) * 65535 / (vh - 1))
    nx = max(0, min(65535, nx))
    ny = max(0, min(65535, ny))

    ULONG_PTR = ctypes.c_ulonglong
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
    MOUSEEVENTF_MOVE = 0x0001
    MOUSEEVENTF_ABSOLUTE = 0x8000
    MOUSEEVENTF_VIRTUALDESK = 0x4000
    flags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK

    inp = INPUT()
    inp.type = INPUT_MOUSE
    inp.mi = MOUSEINPUT(nx, ny, 0, flags, 0, 0)
    n_sent = user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
    return n_sent == 1


def _set_cursor_pos_robust(x: int, y: int) -> bool:
    """依次尝试 win32api / ctypes SetCursorPos / SendInput，任一成功即 True。"""
    x, y = _clip_point_to_virtual_screen(x, y)
    try:
        import win32api

        win32api.SetCursorPos((x, y))
        _mouse_debug_print("SetCursorPos(win32api) ok →", x, y)
        return True
    except Exception as e:
        _mouse_debug_print("SetCursorPos(win32api) fail:", e)

    try:
        import ctypes

        if ctypes.windll.user32.SetCursorPos(int(x), int(y)):
            _mouse_debug_print("SetCursorPos(ctypes) ok →", x, y)
            return True
    except Exception as e:
        _mouse_debug_print("SetCursorPos(ctypes) fail:", e)

    if _set_cursor_sendinput_virtual_desk(x, y):
        _mouse_debug_print("SendInput(VIRTUALDESK) ok →", x, y)
        return True
    _mouse_debug_print("所有鼠标定位方式均失败 →", x, y)
    return False


def _move_mouse_linear_visibly(
    target_x: int,
    target_y: int,
    *,
    duration_s: float = 0.45,
    steps: int = 40,
) -> None:
    """
    从当前位置线性插值到目标，便于肉眼看到指针移动。
    每步使用 ``_set_cursor_pos_robust``（置前失败后仍可能逐步成功）。
    """
    try:
        import win32api

        cx, cy = win32api.GetCursorPos()
    except Exception:
        cx, cy = target_x, target_y
    tx, ty = _clip_point_to_virtual_screen(target_x, target_y)
    n = max(1, int(steps))
    total = max(0.0, float(duration_s))
    dt = total / n if total > 0 else 0.0
    for i in range(1, n + 1):
        t = i / n
        nx = int(cx + (tx - cx) * t)
        ny = int(cy + (ty - cy) * t)
        _set_cursor_pos_robust(nx, ny)
        if dt > 0:
            time.sleep(dt)


def _click_at_cursor(*, button: str = "left") -> None:
    """在当前光标位置单击（先 ``SetCursorPos`` 再调用本函数）。``button``: ``left`` / ``right``。"""
    import win32api
    import win32con

    btn = _normalize_center_click_button(button)
    if btn == "right":
        down, up = win32con.MOUSEEVENTF_RIGHTDOWN, win32con.MOUSEEVENTF_RIGHTUP
    else:
        down, up = win32con.MOUSEEVENTF_LEFTDOWN, win32con.MOUSEEVENTF_LEFTUP
    win32api.mouse_event(down, 0, 0, 0, 0)
    time.sleep(0.04)
    win32api.mouse_event(up, 0, 0, 0, 0)


def _perform_one_center_tap(
    wrap: object,
    screen_x: int,
    screen_y: int,
    *,
    button: str,
    delivery: str,
) -> None:
    """按投递策略执行一次中心点击（PostMessage / 物理鼠标 / 两者）。"""
    if delivery in ("postmessage", "postmessage_then_mouse"):
        hwnd = _hwnd_from_wrapper(wrap)
        if hwnd:
            try:
                import win32gui

                clx, cly = win32gui.ScreenToClient(hwnd, (int(screen_x), int(screen_y)))
                _post_message_button_click_client(hwnd, clx, cly, button=button)
            except Exception as e:
                _mouse_debug_print("PostMessage 路径异常:", e)
        time.sleep(0.05)
    if delivery in ("mouse", "postmessage_then_mouse"):
        if not _click_client_input_at_screen(wrap, screen_x, screen_y, button=button):
            _click_at_cursor(button=button)


def prepare_window_for_input(
    window: object,
    *,
    pause_s: float = 0.2,
    click_center: bool = True,
    center_click_hold_s: float = 1.0,
    center_move_duration_s: float = 0.45,
    center_move_steps: int = 40,
    center_click_offset_y: int | None = None,
    center_click_taps: int = 2,
    center_click_button: str | None = None,
    center_click_delivery: str | None = None,
) -> object:
    """
    置前目标窗体：还原、强前台（AttachThreadInput + Alt 松键 + TOPMOST 闪顶）、
    可选移到「几何中心 + 纵向偏移」点并静止 ``center_click_hold_s`` 秒后再单击，返回解析后的 wrapper。

    若仍无法压过当前前台，请先**点一下运行脚本的终端/IDE**再执行，或关闭「专注助手」等抢焦点软件。

    鼠标分两阶段：默认先在**仍为终端/Cursor 前台**时把指针移到目标窗中心（避免先 ``SetForegroundWindow``
    后 ``SetCursorPos`` 在本机报错）；设 ``WUKONG_SKIP_MOUSE_BEFORE_FOCUS=1`` 则**仅在置前之后**再尝试移动光标。

    置后连续点击 ``center_click_taps`` 次。投递方式由 ``center_click_delivery`` 或环境变量
    ``WUKONG_CENTER_CLICK_DELIVERY`` 控制：``mouse`` / ``postmessage`` / ``postmessage_then_mouse``。

    **注意**：当前台为**已提升（管理员）**进程、而本 Python 未提升时，Windows（UIPI）常拦截
    ``SetCursorPos``/``SendInput``；与「悟空到最前后再也控不了鼠标」现象一致，对策见 README「合成输入限制」。

    ``center_click_button`` 为 ``left`` / ``right``；省略时读环境变量 ``WUKONG_CENTER_CLICK_BUTTON``（如 ``right``）。
    """
    time.sleep(pause_s)
    wrap = _resolve_uia_wrapper(window)
    cbtn = _center_click_button_effective(center_click_button)
    delivery = _center_click_delivery_effective(center_click_delivery)
    _mouse_debug_print("中心点击键:", cbtn, "投递:", delivery)

    if click_center and not _skip_mouse_before_focus():
        try:
            cx, cy = _clip_point_to_virtual_screen(
                *_window_click_point_screen(wrap, offset_y=center_click_offset_y)
            )
            _mouse_debug_print("阶段1（置前窗口前）目标点 (中心+偏移Y):", cx, cy)
            _move_mouse_linear_visibly(
                cx,
                cy,
                duration_s=center_move_duration_s,
                steps=center_move_steps,
            )
            _set_cursor_pos_robust(cx, cy)
        except Exception as e:
            _mouse_debug_print("阶段1 异常:", e)

    _bring_window_to_front(wrap)
    _warn_if_synthetic_input_likely_blocked(_hwnd_from_wrapper(wrap))
    time.sleep(max(pause_s, 0.15))

    if click_center:
        try:
            cx, cy = _clip_point_to_virtual_screen(
                *_window_click_point_screen(wrap, offset_y=center_click_offset_y)
            )
            _mouse_debug_print("阶段2（置后对齐）目标点 (中心+偏移Y):", cx, cy)
            need_cursor = delivery in ("mouse", "postmessage_then_mouse")
            if need_cursor:
                cursor_ok = _set_cursor_pos_robust(cx, cy)
                if not cursor_ok:
                    _mouse_debug_print("置后 SetCursorPos/SendInput 失败")
                    if delivery == "mouse":
                        raise OSError(
                            "SetCursorPos/SendInput 无法定位光标。"
                            " 若仅当悟空在前台后失败，多为 Windows UIPI：请以管理员运行本终端，"
                            "或设置 WUKONG_CENTER_CLICK_DELIVERY=postmessage 再试。"
                            " 诊断: WUKONG_DEBUG_MOUSE=1、scripts/diag_mouse_to_screen_center.py"
                        )
                try:
                    import win32api

                    _mouse_debug_print("对齐后 GetCursorPos:", win32api.GetCursorPos())
                except Exception as e:
                    _mouse_debug_print("GetCursorPos:", e)
            else:
                _mouse_debug_print("投递为 postmessage，不要求置后移动系统光标")

            time.sleep(max(0.0, center_click_hold_s))
            taps = max(1, int(center_click_taps))
            for t in range(taps):
                _perform_one_center_tap(
                    wrap,
                    cx,
                    cy,
                    button=cbtn,
                    delivery=delivery,
                )
                if t + 1 < taps:
                    time.sleep(0.12)
        except Exception as e:
            print(
                "警告: 窗口中心鼠标序列失败（独立诊断: scripts/diag_mouse_to_screen_center.py；"
                "详单: WUKONG_DEBUG_MOUSE=1）:",
                e,
                file=sys.stderr,
            )
        time.sleep(max(pause_s, 0.15))
    try:
        wrap.set_focus()
    except Exception:
        pass
    time.sleep(max(pause_s, 0.1))
    return wrap


def send_paste_shortcut(window: object, *, pause_s: float = 0.15) -> None:
    """对给定窗口置前、中心点击后发送 Ctrl+V。"""
    wrap = prepare_window_for_input(window, pause_s=pause_s, click_center=True)
    wrap.type_keys("^v")


def activate_and_type_text(
    window: object,
    text: str,
    *,
    pause_s: float = 0.25,
    click_center: bool = True,
    center_click_hold_s: float = 1.0,
    center_move_duration_s: float = 0.45,
    center_move_steps: int = 40,
    center_click_offset_y: int | None = None,
    center_click_taps: int = 2,
    center_click_button: str | None = None,
    center_click_delivery: str | None = None,
    use_clipboard_paste: bool = True,
) -> None:
    """
    置前窗口（还原 + 前台 + 可选可见移动鼠标到「中心+纵向偏移」静止后再点击）再填入文本。

    默认 **剪贴板 + Ctrl+V**（Electron/WebView 上通常比直接向顶层 ``type_keys`` 可靠）。
    设 ``use_clipboard_paste=False`` 或环境变量 ``WUKONG_INPUT_USE_CLIPBOARD=0`` 则退回 ``type_keys``。
    """
    wrap = prepare_window_for_input(
        window,
        pause_s=pause_s,
        click_center=click_center,
        center_click_hold_s=center_click_hold_s,
        center_move_duration_s=center_move_duration_s,
        center_move_steps=center_move_steps,
        center_click_offset_y=center_click_offset_y,
        center_click_taps=center_click_taps,
        center_click_button=center_click_button,
        center_click_delivery=center_click_delivery,
    )
    time.sleep(max(pause_s, 0.1))
    try:
        wrap.set_focus()
    except Exception:
        pass
    time.sleep(0.12)

    use_clip = use_clipboard_paste
    v = (os.environ.get("WUKONG_INPUT_USE_CLIPBOARD") or "").strip().lower()
    if v in ("0", "false", "no", "off", "keys"):
        use_clip = False

    if use_clip and text:
        try:
            import pyperclip

            old: str | None = None
            try:
                old = pyperclip.paste()
            except Exception:
                pass
            pyperclip.copy(text)
            time.sleep(0.06)
            try:
                wrap.type_keys("^v", pause=0.05)
            except Exception:
                from pywinauto.keyboard import send_keys

                send_keys("^v", pause=50, with_spaces=True)
            time.sleep(0.08)
            if old is not None:
                try:
                    pyperclip.copy(old)
                except Exception:
                    pass
        except Exception as e:
            print("警告: 剪贴板粘贴失败，改用 type_keys:", e, file=sys.stderr)
            wrap.type_keys(text, with_spaces=True, pause=0.02)
    else:
        wrap.type_keys(text, with_spaces=True, pause=0.02)


def run_paste_flow(title_pattern: str = ".*钉钉.*") -> None:
    """集成：激活钉钉主窗 + 粘贴剪贴板。"""
    if not title_pattern:
        raise ValueError("title_pattern 不能为空")
    re.compile(title_pattern)
    w = activate_window_title_match(title_pattern)
    send_paste_shortcut(w)
