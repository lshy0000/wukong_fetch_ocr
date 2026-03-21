# -*- mode: python ; coding: utf-8 -*-
"""
打包 ``scripts/run_test_01_fetch_ocr.py`` 为 Windows 目录版可执行程序（onedir）。

输出: ``dist/wukong_fetch_ocr/``（含 ``wukong_fetch_ocr.exe``、``_internal``、以及新手说明 / 注册脚本 / ``input_assistant_server.py`` / ``wukong_invite`` 源码包，需整目录分发）。

构建（在仓库根目录）::

    pip install -e ".[paddle,bundle]"
    pyinstaller --noconfirm packaging/run_test_01_fetch_ocr.spec
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

block_cipher = None

try:
    ROOT = Path(SPECPATH).resolve().parent
except NameError:
    ROOT = Path(__file__).resolve().parent.parent

SRC = ROOT / "src"
SCRIPT = ROOT / "scripts" / "run_test_01_fetch_ocr.py"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata

_extra_datas: list = []
_extra_binaries: list = []
_extra_hidden: list = []

for pkg in ("paddleocr", "paddle", "paddlex", "pywinauto", "comtypes"):
    try:
        d, b, h = collect_all(pkg)
        _extra_datas += d
        _extra_binaries += b
        _extra_hidden += h
    except Exception:
        pass

# PaddleX OCR 管线用 importlib.metadata 检查「ocr / ocr-core」可选依赖；冻结后若无 .dist-info 会误判未安装。
def _try_copy_metadata(dist_name: str) -> None:
    try:
        _extra_datas.extend(copy_metadata(dist_name))
    except Exception:
        pass


for _meta in (
    "paddlex",
    "paddleocr",
    "paddlepaddle",
    "numpy",
    "Pillow",
    "PyYAML",
    "packaging",
    # ocr-core（满足其一整套即可走通 OCRPipeline 依赖检查）
    "imagesize",
    "opencv-contrib-python",
    "opencv-python",
    "opencv-python-headless",
    "pyclipper",
    "pypdfium2",
    "python-bidi",
    "shapely",
    # ocr 额外依赖（本机若只装了 ocr 全套而未装齐 ocr-core 时备用）
    "beautifulsoup4",
    "einops",
    "ftfy",
    "Jinja2",
    "lxml",
    "openpyxl",
    "premailer",
    "regex",
    "safetensors",
    "scikit-learn",
    "scipy",
    "sentencepiece",
    "tiktoken",
    "tokenizers",
    "chardet",
    "colorlog",
    "filelock",
    "huggingface-hub",
    "modelscope",
    "pandas",
    "prettytable",
    "py-cpuinfo",
    "pydantic",
    "requests",
    "aistudio-sdk",
):
    _try_copy_metadata(_meta)

try:
    _wh = list(collect_submodules("wukong_invite"))
except Exception:
    _wh = [
        "wukong_invite",
        "wukong_invite.config",
        "wukong_invite.hudong_fetch",
        "wukong_invite.invite_image_preprocess",
        "wukong_invite.ocr_extract",
        "wukong_invite.ui_dingtalk",
        "wukong_invite.clipboard_util",
    ]

hiddenimports = sorted(
    set(
        _wh
        + _extra_hidden
        + [
            "wukong_invite.input_assistant_defaults",
            "win32timezone",
            "win32api",
            "win32con",
            "win32gui",
            "win32process",
            "pythoncom",
            "pywintypes",
        ]
    )
)

a = Analysis(
    [str(SCRIPT)],
    pathex=[str(ROOT), str(SRC)],
    binaries=_extra_binaries,
    datas=_extra_datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="wukong_fetch_ocr",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="wukong_fetch_ocr",
)

# PyInstaller 6 会把 datas 打进 _internal；注册脚本要求与 input_assistant_server 同目录且在 exe 旁，故 COLLECT 后复制到 dist 根。
_dist_root = ROOT / "dist" / "wukong_fetch_ocr"
if _dist_root.is_dir():
    for _src, _dst_name in (
        (ROOT / "packaging" / "README_wukong_fetch_ocr_NOVICE.txt", "README_wukong_fetch_ocr_NOVICE.txt"),
        (ROOT / "packaging" / "run_test_01_fetch_ocr.spec", "run_test_01_fetch_ocr.spec"),
        (ROOT / "scripts" / "input_assistant_server.py", "input_assistant_server.py"),
        (ROOT / "scripts" / "register_input_assistant_task.ps1", "register_input_assistant_task.ps1"),
    ):
        if _src.is_file():
            shutil.copy2(_src, _dist_root / _dst_name)
    _wi_dst = _dist_root / "wukong_invite"
    if _wi_dst.is_dir():
        shutil.rmtree(_wi_dst)
    shutil.copytree(
        ROOT / "src" / "wukong_invite",
        _wi_dst,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
