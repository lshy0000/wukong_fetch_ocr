#!/usr/bin/env python3
"""
先加载 Paddle OCR，再按固定间隔拉 JSONP → 下载 PNG → 识别邀请码。

与 state 中「上次图片 SHA + 上次识别码」对比：**图片变化**且解析出**与上次不同的非空邀请码**时，
写回 state、打印新码并退出 0。

无 state 文件时：首轮拉取仅建立基线（不写盘），之后同上。

用法（仓库根目录 d:\\ai\\2026）:
  python scripts/watch_invite_until_update.py
  python scripts/watch_invite_until_update.py --interval 2 --state .wukong_test_state.json
  python scripts/watch_invite_until_update.py --timeout 600
  python scripts/watch_invite_until_update.py --save-debug
  python scripts/watch_invite_until_update.py --save-debug D:\\tmp\\invite_dbg

加 ``--save-debug`` 时，每次实际跑 OCR 前会写入 ``last_raw`` / ``last_inv_full`` / ``last_inv_crop``
（与 ``run_test_01_fetch_ocr.py`` 相同；图未变跳过 OCR 时不写盘）。

日志默认写到 **stdout**，与 Paddle 打到 **stderr** 的模型日志分开。

Paddle 初始化后常会清空 ``logging`` 的 **root handlers**，仅依赖向上冒泡的 logger 会全部失声；
本脚本对 ``wukong_invite`` / ``wukong.watch_invite`` 使用独立 Handler（``propagate=False``），
并在预热结束后再装一次，保证主循环与 ``ocr_extract`` 的 INFO 始终可见。
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import logging
import sys
import time
from pathlib import Path

import httpx
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wukong_invite.config import DEFAULT_USER_AGENT  # noqa: E402
from wukong_invite.hudong_fetch import (  # noqa: E402
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

_LOG = logging.getLogger("wukong.watch_invite")


class _FlushingStreamHandler(logging.StreamHandler):
    """避免与 Paddle/glog 共用 stderr 时管道写满导致后续日志阻塞。"""

    def emit(self, record: logging.LogRecord) -> None:
        super().emit(record)
        self.flush()


def _setup_logging(*, level: int, stream) -> None:
    """
    配置 root，并为 ``wukong_invite``、``wukong.watch_invite`` 各挂独立 Handler。

    Paddle/PaddleX 在创建引擎时常会 ``root.handlers.clear()`` 或改掉 root，
    子 logger 若仅 ``propagate`` 到 root，预热后主流程与 ocr_extract 的 INFO 会全部消失。
    对上述两个命名空间使用 ``propagate=False`` + 自有 Handler，可避免被 Paddle 清掉。

    在 ``warmup_paddle_ocr()`` 返回后必须再调用本函数一次。
    """
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    rh = _FlushingStreamHandler(stream)
    rh.setLevel(level)
    rh.setFormatter(fmt)
    root.addHandler(rh)

    for name in ("wukong_invite", "wukong.watch_invite"):
        lg = logging.getLogger(name)
        lg.setLevel(level)
        lg.handlers.clear()
        lg.propagate = False
        h = _FlushingStreamHandler(stream)
        h.setLevel(level)
        h.setFormatter(fmt)
        lg.addHandler(h)


def _apply_third_party_log_noise() -> None:
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("paddle").setLevel(logging.WARNING)


def _load_state(path: Path) -> tuple[str | None, str | None]:
    if not path.is_file():
        return None, None
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        _LOG.warning("读取 state 失败，当作无基线: %s", e)
        return None, None
    sha = d.get("last_image_sha256")
    code = d.get("last_code")
    if isinstance(sha, str) and sha.strip():
        sha = sha.strip()
    else:
        sha = None
    if isinstance(code, str) and code.strip():
        code = code.strip()
    else:
        code = None
    return sha, code


def _write_state(path: Path, *, url: str, sha: str, code: str | None) -> None:
    path.write_text(
        json.dumps(
            {"last_img_url": url, "last_image_sha256": sha, "last_code": code},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _short_url(url: str, *, head: int = 80, tail: int = 24) -> str:
    if len(url) <= head + tail + 3:
        return url
    return f"{url[:head]}…{url[-tail:]}"


def _log_variant_reports(vr: list[tuple[str, list[str], tuple[int, int]]]) -> None:
    if not vr:
        _LOG.info("     （无 Paddle 变体明细，或非 Paddle 后端）")
        return
    _LOG.info("     各路 OCR 摘要（共 %s 路）:", len(vr))
    for i, (label, vlines, (vw, vh)) in enumerate(vr, 1):
        if not vlines:
            _LOG.info("       [%s/%s] «%s» %sx%s → （无 rec 行）", i, len(vr), label, vw, vh)
            continue
        head = " | ".join(repr(x) for x in vlines[:5])
        extra = f" | …共 {len(vlines)} 行" if len(vlines) > 5 else ""
        _LOG.info("       [%s/%s] «%s» %sx%s → %s%s", i, len(vr), label, vw, vh, head, extra)


def main() -> int:
    default_debug = ROOT / "debug" / "invite_ocr"
    p = argparse.ArgumentParser(description="预热 OCR 后轮询邀请图，识别到新邀请码即退出")
    p.add_argument("--interval", type=float, default=1.0, help="轮询间隔秒（默认 1）")
    p.add_argument(
        "--state",
        type=Path,
        default=ROOT / ".wukong_test_state.json",
        help="与 run_test_01 同结构的 state 路径",
    )
    p.add_argument("--timeout", type=float, default=0.0, help="最长运行秒数，0 表示不限；超则退出 124")
    p.add_argument("--log-level", default="INFO", help="DEBUG / INFO / WARNING")
    p.add_argument(
        "--save-debug",
        nargs="?",
        const=str(default_debug),
        default=None,
        metavar="DIR",
        help=(
            "每次 OCR 前保存 last_raw / last_inv_full / last_inv_crop；"
            f"缺省目录: {default_debug}"
        ),
    )
    args = p.parse_args()

    dbg_dir: Path | None = None
    if args.save_debug is not None:
        dbg_dir = Path(args.save_debug).expanduser().resolve()

    lv = getattr(logging, args.log_level.upper(), logging.INFO)
    _setup_logging(level=lv, stream=sys.stdout)
    _apply_third_party_log_noise()

    state_path = args.state.expanduser().resolve()
    ref_sha, ref_code = _load_state(state_path)
    _LOG.info("基线: state=%s | 上次SHA=%s | 上次码=%r", state_path, ref_sha or "（无）", ref_code or "（无）")

    _LOG.info(
        "即将预热 Paddle OCR。说明：加载模型时 Paddle 会向 stderr 打日志；"
        "本脚本业务日志在 stdout。若需跳过联网检查可设置环境变量 "
        "PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True"
    )
    warmup_paddle_ocr()
    # Paddle 初始化常破坏 root 日志；恢复 root + 专用 logger（见 _setup_logging 文档）
    _setup_logging(level=lv, stream=sys.stdout)
    _apply_third_party_log_noise()
    _LOG.info(
        "预热阶段结束（业务日志在 stdout；Paddle 原生日志在 stderr）。开始主循环：间隔 %.2fs",
        args.interval,
    )

    t0 = time.monotonic()
    headers = {"User-Agent": DEFAULT_USER_AGENT}
    baseline_set = ref_sha is not None
    iteration = 0

    try:
        _LOG.info("正在创建 httpx.Client（connect/read 超时 30s）…")
        with httpx.Client(headers=headers, timeout=30.0, follow_redirects=True) as client:
            _LOG.info("httpx.Client 已就绪，进入 while 轮询")
            while True:
                iteration += 1
                elapsed = time.monotonic() - t0
                left = ""
                if args.timeout > 0:
                    rem = max(0.0, args.timeout - elapsed)
                    left = f" │ 超时剩余 {rem:.0f}s"
                _LOG.info(
                    "════════ 轮询 #%s │ 已运行 %.1fs │ 本地 %s%s ════════",
                    iteration,
                    elapsed,
                    time.strftime("%H:%M:%S"),
                    left,
                )

                if args.timeout > 0 and elapsed > args.timeout:
                    _LOG.error("已达 --timeout %.0fs，退出 124", args.timeout)
                    return 124

                t_jsonp = time.monotonic()
                _LOG.info("  [1/4] 请求 JSONP …")
                payload = fetch_invite_payload(client=client)
                _LOG.info("  [1/4] JSONP 结束，用时 %.2fs", time.monotonic() - t_jsonp)
                if payload is None:
                    _LOG.warning("  未拿到 img_url，本轮放弃")
                    _LOG.info(
                        "  ⏸ 休眠 %.2fs │ 下一轮 #%s │ 唤醒约 %s",
                        args.interval,
                        iteration + 1,
                        time.strftime("%H:%M:%S", time.localtime(time.time() + args.interval)),
                    )
                    time.sleep(args.interval)
                    continue

                url = payload.img_url
                _LOG.info("  img_url: %s", _short_url(url))

                t_dl = time.monotonic()
                _LOG.info("  [2/4] 下载 PNG …")
                png = download_image_bytes(url, client=client)
                _LOG.info(
                    "  [2/4] 下载完成：%s 字节，用时 %.2fs",
                    len(png),
                    time.monotonic() - t_dl,
                )
                sha = hashlib.sha256(png).hexdigest()
                _LOG.info("  [3/4] 内容 SHA256: %s", sha)

                if baseline_set and sha == ref_sha:
                    _LOG.info(
                        "  [4/4] 与当前基线 SHA 相同 → 跳过 OCR（基线前16位 %s…）",
                        ref_sha[:16] if ref_sha else "",
                    )
                    _LOG.info(
                        "  ⏸ 休眠 %.2fs │ 下一轮 #%s │ 唤醒约 %s",
                        args.interval,
                        iteration + 1,
                        time.strftime("%H:%M:%S", time.localtime(time.time() + args.interval)),
                    )
                    time.sleep(args.interval)
                    continue

                _LOG.info("  [4/4] SHA 与基线不同或尚无基线 → 执行 OCR + 解析")
                if dbg_dir is not None:
                    dbg_dir.mkdir(parents=True, exist_ok=True)
                    _LOG.info("  保存调试图 → %s（先删 last_*.png 再覆盖）", dbg_dir)
                    t_dbg = time.monotonic()
                    pil = pil_invite_to_rgb(Image.open(io.BytesIO(png)))
                    paths = save_invite_debug_snapshots(pil, dbg_dir)
                    for k, fp in paths.items():
                        _LOG.info("    已写入 %s → %s", k, fp)
                    _LOG.info("  调试图写入用时 %.2fs", time.monotonic() - t_dbg)

                t_ocr = time.monotonic()
                _LOG.info("  调用 extract_code_from_png_with_lines（内部多路 Paddle，可能较慢）…")
                code, _lines, trace, vr = extract_code_from_png_with_lines(png)
                _LOG.info(
                    "  OCR+解析结束，用时 %.2fs │ 邀请码=%r",
                    time.monotonic() - t_ocr,
                    code,
                )
                for t in trace:
                    _LOG.info("     解析留痕: %s", t)
                _log_variant_reports(vr)

                if not baseline_set:
                    ref_sha, ref_code = sha, code
                    baseline_set = True
                    _LOG.info(
                        "  已建立内存基线（本轮不退出）: SHA 前16=%s… │ 码=%r",
                        sha[:16],
                        code,
                    )
                    _LOG.info(
                        "  ⏸ 休眠 %.2fs │ 下一轮 #%s │ 唤醒约 %s",
                        args.interval,
                        iteration + 1,
                        time.strftime("%H:%M:%S", time.localtime(time.time() + args.interval)),
                    )
                    time.sleep(args.interval)
                    continue

                if code is None:
                    _LOG.info("  图已变但未解析出邀请码，继续轮询")
                    _LOG.info(
                        "  ⏸ 休眠 %.2fs │ 下一轮 #%s │ 唤醒约 %s",
                        args.interval,
                        iteration + 1,
                        time.strftime("%H:%M:%S", time.localtime(time.time() + args.interval)),
                    )
                    time.sleep(args.interval)
                    continue

                if ref_code is not None and code == ref_code:
                    _LOG.info("  图已变但识别码与基线相同 %r，继续轮询", code)
                    _LOG.info(
                        "  ⏸ 休眠 %.2fs │ 下一轮 #%s │ 唤醒约 %s",
                        args.interval,
                        iteration + 1,
                        time.strftime("%H:%M:%S", time.localtime(time.time() + args.interval)),
                    )
                    time.sleep(args.interval)
                    continue

                print(code, flush=True)
                _LOG.info("邀请码已更新: %r → 写入 %s", code, state_path)
                _write_state(state_path, url=url, sha=sha, code=code)
                return 0

    except KeyboardInterrupt:
        _LOG.info("用户中断（最后一轮 #%s）", iteration)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
