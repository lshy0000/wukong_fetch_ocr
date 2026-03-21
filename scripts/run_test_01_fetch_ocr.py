#!/usr/bin/env python3
"""
悟空邀请码：专用集成脚本；**除可选 ``--save-debug`` 外无其它命令行参数**。

流程：轮询互动 JSONP → 下图 → 与本地 state 比对；建立基线后，若识别到**新的**邀请码则
复制 → 置前钉钉/悟空窗 → 经本机 ``input_assistant_server`` 执行与 ``input_assistant_client.py flow`` 相同的键鼠序列，
打印邀请码并退出。

**仅在脚本启动时检查一次**（轮询循环内不再复检）：

- **Paddle**：缺失则自动 ``pip`` 安装（Windows 用飞桨官方 CPU 源）；打包 exe 无法自动安装时会打印说明并退出。
- **input_assistant_server**：须已监听 ``127.0.0.1:47821`` 且 ``ping`` 成功；否则打印安装/启动说明并退出。

其它可调行为请用环境变量（如 ``WUKONG_INVITE_OCR_VARIANTS`` 等），见 README。

用法::

  python scripts/run_test_01_fetch_ocr.py
  python scripts/run_test_01_fetch_ocr.py --save-debug
  python scripts/run_test_01_fetch_ocr.py --save-debug D:\\tmp\\invite_dbg
  wukong_fetch_ocr.exe --save-debug
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

# PyInstaller 冻结后：工作目录用 exe 所在目录（state / debug 与 exe 同放）；源码运行仍用仓库根。
if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).resolve().parent
else:
    ROOT = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(ROOT / "src"))

# 本脚本为固定场景；轮询参数改这里，调试图用 ``--save-debug``。
STATE_FILE = ROOT / ".wukong_test_state.json"
DEFAULT_DEBUG_INVITE_DIR = ROOT / "debug" / "invite_ocr"
POLL_INTERVAL_S = 0.1
WATCH_TIMEOUT_S = 0.0  # 0 表示不限制总时长
FOCUS_WAIT_S = 0.2
IA_HOST = "127.0.0.1"
IA_PORT = 47821
IA_TIMEOUT_S = 5.0
IA_MOVE_DELAY_S = 0.1
IA_CLICK_DELAY_S = 0.1
LOG_LEVEL = "INFO"


def _paddle_import_ok() -> bool:
    try:
        import paddle  # noqa: F401
        import paddleocr  # noqa: F401
    except ImportError:
        return False
    return True


def _print_paddle_install_instructions() -> None:
    root = str(ROOT)
    print(
        "\n========== 缺少 Paddle（paddlepaddle / paddleocr）==========\n"
        "自动安装失败。请在本机当前 Python 环境中手动安装：\n\n"
        "Windows CPU 示例（版本以 https://www.paddlepaddle.org.cn/install/quick 为准）:\n"
        f"  cd {root}\n"
        "  python -m pip install --upgrade pip\n"
        "  python -m pip install paddlepaddle -i https://www.paddlepaddle.org.cn/packages/stable/cpu/\n"
        '  python -m pip install "paddleocr>=3.0.0"\n'
        "或从仓库安装可选依赖:\n"
        f"  pip install -e \".[paddle]\"\n"
        "（若仍缺 paddlepaddle，请再执行上面的飞桨官方 pip 行。）\n"
        "文档: README.md「飞桨 OCR（必装，主路径）」\n",
        file=sys.stderr,
    )


def _ensure_paddle_dependencies() -> None:
    if _paddle_import_ok():
        return
    if getattr(sys, "frozen", False):
        print(
            "当前为打包 exe，无法在运行时自动安装 Paddle；请使用带 Paddle 的完整目录发行包或从源码环境运行。",
            file=sys.stderr,
        )
        _print_paddle_install_instructions()
        raise SystemExit(2)
    exe = sys.executable
    print(
        "未检测到 paddlepaddle/paddleocr，正在尝试自动安装（首次可能较慢）…",
        file=sys.stderr,
        flush=True,
    )
    pre = subprocess.run([exe, "-m", "pip", "install", "--upgrade", "pip"], cwd=str(ROOT))
    if pre.returncode != 0:
        print("警告: pip 自升级失败，继续尝试安装 Paddle", file=sys.stderr)
    if sys.platform == "win32":
        r1 = subprocess.run(
            [
                exe,
                "-m",
                "pip",
                "install",
                "paddlepaddle",
                "-i",
                "https://www.paddlepaddle.org.cn/packages/stable/cpu/",
            ],
            cwd=str(ROOT),
        )
        if r1.returncode != 0:
            _print_paddle_install_instructions()
            raise SystemExit(2)
        r2 = subprocess.run(
            [exe, "-m", "pip", "install", "paddleocr>=3.0.0"],
            cwd=str(ROOT),
        )
    else:
        r2 = subprocess.run(
            [exe, "-m", "pip", "install", "paddlepaddle", "paddleocr>=3.0.0"],
            cwd=str(ROOT),
        )
    if r2.returncode != 0:
        _print_paddle_install_instructions()
        raise SystemExit(2)
    if not _paddle_import_ok():
        print("自动安装后仍无法 import paddle / paddleocr，请按下列说明手动排查。", file=sys.stderr)
        _print_paddle_install_instructions()
        raise SystemExit(2)
    print("Paddle 依赖已就绪。", file=sys.stderr, flush=True)


def _print_input_assistant_instructions(host: str, port: int) -> None:
    root = str(ROOT)
    if getattr(sys, "frozen", False):
        print(
            "\n========== 未检测到 input_assistant_server ==========\n"
            f"本程序需要向 {host}:{port} 发送键鼠指令，但当前连不上服务。\n\n"
            "**请在本 zip 解压目录内**（与 wukong_fetch_ocr.exe 同一文件夹）操作：\n\n"
            "1) 推荐：右键「以管理员身份运行 PowerShell」，执行：\n"
            f"   cd \"{root}\"\n"
            "   .\\register_input_assistant_task.ps1\n"
            "   （仅首次注册；助手使用与主程序相同的内置密钥，无需密钥文件或环境变量。）\n\n"
            "2) 或临时调试：在同一目录打开终端，执行：\n"
            f"   cd \"{root}\"\n"
            "   python input_assistant_server.py\n\n"
            "验证：\n"
            f"   python input_assistant_client.py ping\n"
            "（需本机已安装 Python 且能 import wukong_invite，开发与 zip 内脚本路径一致即可。）\n",
            file=sys.stderr,
        )
        return
    print(
        "\n========== 未检测到 input_assistant_server ==========\n"
        f"轮询到新邀请码后需要向 {host}:{port} 发送键鼠指令，但当前无法连通或服务未响应 ping。\n\n"
        "请先在本机**已登录桌面的会话**中启动助手服务（不要用 Session 0 系统服务），任选其一：\n\n"
        "1) 临时调试：\n"
        f"   cd {root}\n"
        "   python scripts/input_assistant_server.py\n\n"
        "2) 推荐（仓库内）：管理员 PowerShell 执行\n"
        f"   cd {root}\n"
        f"   .\\scripts\\register_input_assistant_task.ps1\n\n"
        "若使用 zip 分发包，请运行**解压目录内**的 register_input_assistant_task.ps1（勿用其他路径副本）。\n"
        "验证：python scripts/input_assistant_client.py ping\n",
        file=sys.stderr,
    )


def _input_assistant_ping_ok(host: str, port: int, timeout: float) -> bool:
    from wukong_invite.input_assistant_flow import (
        resolve_default_assistant_secret,
        send_input_assistant_command,
    )

    sec = resolve_default_assistant_secret()
    cmd = {"cmd": "ping", "secret": sec}
    try:
        out = send_input_assistant_command(cmd, host=host, port=port, timeout=timeout)
        return bool(out.get("ok") and out.get("pong"))
    except OSError as e:
        print(f"input_assistant 探测失败: {e}", file=sys.stderr)
    except RuntimeError as e:
        print(f"input_assistant 探测失败: {e}", file=sys.stderr)
    except Exception as e:
        print(f"input_assistant 探测失败: {e}", file=sys.stderr)
    return False


def _ensure_input_assistant_reachable(*, host: str, port: int, timeout: float) -> None:
    if _input_assistant_ping_ok(host, port, timeout):
        return
    _print_input_assistant_instructions(host, port)
    raise SystemExit(2)


from wukong_invite.config import DEFAULT_USER_AGENT  # noqa: E402
from wukong_invite.hudong_fetch import (  # noqa: E402
    build_jsonp_url,
    download_image_bytes,
    fetch_invite_payload,
)
from wukong_invite.invite_image_preprocess import (  # noqa: E402
    pil_invite_to_rgb,
    save_invite_debug_snapshots,
)
from wukong_invite.ocr_extract import (  # noqa: E402
    extract_code_from_png_with_lines,
    warmup_paddle_ocr,
)

_LOG = logging.getLogger("wukong.run_test_01")
_UI_CONNECT = None
_UI_PREPARE = None


def _save_invite_debug_snapshots_from_png(png: bytes, out_dir: Path) -> None:
    """写入 last_raw / last_inv_full / last_inv_crop（与历史行为一致）。"""
    from PIL import Image

    out_dir = out_dir.expanduser().resolve()
    pil = pil_invite_to_rgb(Image.open(io.BytesIO(png)))
    paths = save_invite_debug_snapshots(pil, out_dir)
    for k, fp in paths.items():
        _LOG.info("调试图 %s → %s", k, fp)


def _preload_ui_automation() -> None:
    """预加载 UI 自动化依赖，避免抓到新码后首次导入产生明显等待。"""
    global _UI_CONNECT, _UI_PREPARE
    if _UI_CONNECT is not None and _UI_PREPARE is not None:
        return
    from wukong_invite.ui_dingtalk import connect_preferred_window, prepare_window_for_input

    _UI_CONNECT = connect_preferred_window
    _UI_PREPARE = prepare_window_for_input


def _copy_and_focus_on_change(code: str) -> None:
    """邀请码变化后：复制剪贴板 → 置前 DingTalkReal → 中心点击 → 经 input_assistant 执行 flow 键入该码。"""
    from wukong_invite.clipboard_util import set_text
    from wukong_invite.input_assistant_flow import (
        resolve_default_assistant_secret,
        run_input_assistant_flow,
    )

    set_text(code)
    _LOG.info("已复制邀请码到剪贴板: %r", code)

    assert _UI_CONNECT is not None and _UI_PREPARE is not None

    os.environ["WUKONG_SKIP_MOUSE_BEFORE_FOCUS"] = "1"
    win, used = _UI_CONNECT(process_paths=None)
    _LOG.info("已连接窗口（模式 %r）", used)
    time.sleep(max(0.0, float(FOCUS_WAIT_S)))
    wrap = _UI_PREPARE(
        win,
        pause_s=0.15,
        click_center=True,
        center_click_hold_s=0.15,
        center_move_duration_s=0.35,
        center_move_steps=28,
        center_click_offset_y=None,
        center_click_taps=1,
    )
    time.sleep(0.12)
    try:
        wrap.set_focus()
    except Exception:
        pass
    time.sleep(0.12)

    sec = resolve_default_assistant_secret()
    _LOG.info(
        "通过 input_assistant 执行 flow（%s:%s）键入邀请码…",
        IA_HOST,
        IA_PORT,
    )
    run_input_assistant_flow(
        code,
        host=IA_HOST,
        port=int(IA_PORT),
        timeout=float(IA_TIMEOUT_S),
        secret=sec,
        use_default_secret=False,
        move_delay=float(IA_MOVE_DELAY_S),
        click_delay=float(IA_CLICK_DELAY_S),
    )
    _LOG.info("置前、中心点击与 input_assistant flow 已完成")


def _setup_logging(level: str) -> None:
    lv = getattr(logging, level.upper(), logging.INFO)
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    root = logging.getLogger()
    root.setLevel(lv)
    root.handlers.clear()
    rh = logging.StreamHandler()
    rh.setLevel(lv)
    rh.setFormatter(fmt)
    root.addHandler(rh)
    # Paddle 初始化后可能清理 root handlers；给业务 logger 单独挂 handler 防止“无日志假死”。
    for name in ("wukong_invite", "wukong.run_test_01"):
        lg = logging.getLogger(name)
        lg.setLevel(lv)
        lg.handlers.clear()
        lg.propagate = False
        h = logging.StreamHandler()
        h.setLevel(lv)
        h.setFormatter(fmt)
        lg.addHandler(h)
    logging.getLogger("httpx").setLevel(max(logging.WARNING, lv))
    logging.getLogger("httpcore").setLevel(max(logging.WARNING, lv))
    logging.getLogger("paddle").setLevel(max(logging.WARNING, lv))


def _configure_paddle_startup_env() -> None:
    """
    默认关闭 PaddleX 的模型源连通性检查，避免启动阶段长时间阻塞误判为“卡死”。
    用户若已显式设置环境变量，则尊重用户值。
    """
    if os.environ.get("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK") is None:
        os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"


def main() -> int:
    ap = argparse.ArgumentParser(description="悟空邀请码：轮询 OCR + 置前 + input_assistant flow")
    ap.add_argument(
        "--save-debug",
        nargs="?",
        const=str(DEFAULT_DEBUG_INVITE_DIR),
        default=None,
        metavar="DIR",
        help=(
            "每次建立基线或检测到图片变化并跑 OCR 时，保存 last_raw / last_inv_full / last_inv_crop；"
            f"省略目录则默认 {DEFAULT_DEBUG_INVITE_DIR}"
        ),
    )
    args = ap.parse_args()
    dbg_dir: Path | None = (
        Path(args.save_debug).expanduser().resolve() if args.save_debug else None
    )
    if dbg_dir is not None:
        print(f"已启用 --save-debug → {dbg_dir}", flush=True)

    # 环境自检仅在启动时执行一次，轮询循环内不再检查 Paddle / input_assistant。
    _ensure_paddle_dependencies()
    _configure_paddle_startup_env()
    _setup_logging(LOG_LEVEL)
    _ensure_input_assistant_reachable(host=IA_HOST, port=IA_PORT, timeout=IA_TIMEOUT_S)
    _LOG.info("input_assistant 已在 %s:%s 响应 ping", IA_HOST, IA_PORT)
    if dbg_dir is not None:
        _LOG.info("save-debug: 每次基线/OCR 前写入 %s", dbg_dir)

    _LOG.info("工作目录: %s", ROOT)
    _LOG.info("读取 state: %s", STATE_FILE.resolve())
    _LOG.info(
        "Paddle 环境: PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=%s",
        os.environ.get("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"),
    )
    _LOG.info("正在预热 Paddle OCR（首次会加载模型，可能较慢）…")
    warmup_paddle_ocr()
    _setup_logging(LOG_LEVEL)
    _LOG.info("Paddle OCR 预热完成")
    _LOG.info("正在加载 pywinauto（首次在本机可能需数十秒）…")
    _preload_ui_automation()
    _LOG.info("pywinauto 预加载完成（检测到新邀请码后可立即置前窗口）")

    prev: dict = {}
    if STATE_FILE.is_file():
        try:
            prev = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            _LOG.info("已加载历史 state（url/sha256/code 键）")
        except (json.JSONDecodeError, OSError) as e:
            _LOG.warning("state 读取失败，当作首次: %s", e)
            prev = {}

    prev_sha = prev.get("last_image_sha256") if isinstance(prev.get("last_image_sha256"), str) else None
    prev_code = prev.get("last_code") if isinstance(prev.get("last_code"), str) else None

    import httpx

    headers = {"User-Agent": DEFAULT_USER_AGENT}
    jsonp_url = build_jsonp_url()
    _LOG.info("请求 JSONP: %s", jsonp_url)
    t0 = time.monotonic()
    baseline_ready = prev_sha is not None
    interval = max(0.1, float(POLL_INTERVAL_S))
    last_poll_url: str | None = None
    with httpx.Client(headers=headers, timeout=30.0, follow_redirects=True) as client:
        loop = 0
        while True:
            loop += 1
            if WATCH_TIMEOUT_S > 0 and (time.monotonic() - t0) > WATCH_TIMEOUT_S:
                _LOG.error("已达总超时 %.1fs，退出 124", WATCH_TIMEOUT_S)
                return 124

            payload = fetch_invite_payload(client=client)
            if payload is None:
                _LOG.error("接口未返回 img_url，%.2fs 后重试", interval)
                time.sleep(interval)
                continue

            url = payload.img_url
            _LOG.info("当前 img_url: %s", url)
            print(url, flush=True)
            if last_poll_url is None:
                _LOG.info("img_url 相对上一轮轮询: （会话内首次）")
            else:
                _LOG.info(
                    "img_url 相对上一轮轮询: %s",
                    "已变化" if url != last_poll_url else "未变化",
                )
            try:
                _LOG.info("解析得到 img_url，开始下载 PNG …")
                png = download_image_bytes(url, client=client)
                sha = hashlib.sha256(png).hexdigest()

                if not baseline_ready:
                    prev_sha = sha
                    _LOG.info("轮询#%s：无历史 state，首轮执行 OCR 建立基线", loop)
                    if dbg_dir is not None:
                        _save_invite_debug_snapshots_from_png(png, dbg_dir)
                    code_now, _raw, _trace, _reports = extract_code_from_png_with_lines(png)
                    prev_code = code_now
                    baseline_ready = True
                    _LOG.info(
                        "轮询#%s：首次建立基线完成（邀请码=%r，不触发置前/退出），等待下一次变化",
                        loop,
                        prev_code,
                    )
                    STATE_FILE.write_text(
                        json.dumps(
                            {
                                "last_img_url": url,
                                "last_image_sha256": sha,
                                "last_code": prev_code,
                            },
                            ensure_ascii=False,
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                    _LOG.info("已写入初始基线 state: %s", STATE_FILE.resolve())
                    time.sleep(interval)
                    continue

                if prev_sha and sha == prev_sha:
                    if loop % 1000 == 0:
                        _LOG.info("轮询#%s：内容未变化（SHA 相同），继续", loop)
                    time.sleep(interval)
                    continue

                _LOG.info("轮询#%s：检测到内容变化，执行 OCR 解析", loop)
                if dbg_dir is not None:
                    _save_invite_debug_snapshots_from_png(png, dbg_dir)
                code_now, _raw, _trace, _reports = extract_code_from_png_with_lines(png)
                if not code_now:
                    _LOG.info("轮询#%s：图已变但未解析出邀请码，继续", loop)
                    prev_sha = sha
                    time.sleep(interval)
                    continue
                if prev_code and code_now == prev_code:
                    _LOG.info("轮询#%s：图已变但邀请码与历史相同 %r，继续", loop, code_now)
                    prev_sha = sha
                    time.sleep(interval)
                    continue

                try:
                    _copy_and_focus_on_change(code_now)
                except RuntimeError as e:
                    _LOG.error("input_assistant flow 失败（邀请码已识别但未完成键鼠）: %s", e)
                    return 3

                STATE_FILE.write_text(
                    json.dumps(
                        {
                            "last_img_url": url,
                            "last_image_sha256": sha,
                            "last_code": code_now,
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                _LOG.info("已更新 state: %s", STATE_FILE.resolve())
                print(code_now, flush=True)
                return 0
            finally:
                last_poll_url = url


if __name__ == "__main__":
    raise SystemExit(main())
