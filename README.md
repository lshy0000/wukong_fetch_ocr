# 悟空邀请码助手（轮询 + 飞桨 OCR + 剪贴板 + 可选 UI 粘贴）

## 新手：只用 Release，不用懂代码

**你要做的事只有一条线：下载整包 → 解压 → 注册一次助手 → 以后双击 exe。**

| 步骤 | 做什么 |
|------|--------|
| ① 下载 | 打开本仓库 **Releases**，下 **整包 zip**（里面有很多文件，**不是**只拿一个 exe）。 |
| ② 解压 | 整个文件夹解压出来再用；**禁止**只复制 `wukong_fetch_ocr.exe` 到别处。 |
| ③ 第一次用 | 在解压目录打开 PowerShell，执行：`.\register_input_assistant_task.ps1`（注册键鼠助手，**只做一次**）。 |
| ④ 每次抢码 | 钉钉已登录、悟空已打开 → **只接一台显示器** → 双击 `wukong_fetch_ocr.exe`。 |

### 重点（不遵守容易白跑）

1. **多屏必坑**：用前拔掉副屏或关掉，**只留一块屏幕**；开抢前也别改分辨率或 DPI。
2. **看完整说明**：解压包里的 **`README_wukong_fetch_ocr_NOVICE.txt`**（与仓库 **`packaging/README_wukong_fetch_ocr_NOVICE.txt`** 相同）；本 README 下文 **「Release 包使用说明（面向新手）」** 是同一套内容的展开版。

---

**开发者**（克隆仓库、`pip`、改源码、自己打包）：从下面 **「功能」**、**「安装」** 读起。

---

官网悟空页通过**互动中台 JSONP**返回「邀请码展示图」的 CDN 地址（`img_url`），邀请码多为 **5 个汉字**（在「当前邀请码：」后）；另有活动态特殊四字码 **「感谢支持」**（解析器单独识别）。**默认预处理**：「反色」= **仅绝对 `#FFFFFF` 改为 `#000000`**（其余像素不变，可调 `WUKONG_INVITE_WHITE_MIN`）→ **按 ROI 精准裁剪**（不放大、无 CLAHE/Otsu）。OCR **默认只跑** **反色+裁剪** 一路（更快）；需要原图兜底时：`WUKONG_INVITE_OCR_VARIANTS=raw_and_crop`。旧版放大/二值化：`legacy_chain`。

## 功能

- `once`：请求一次接口；若 `img_url` 与本地记录不同 → 下载 PNG → **PaddleOCR** → 写入剪贴板。
- `poll`：按间隔轮询；可配合 `--paste-ui` 在更新后尝试激活钉钉窗口并 `Ctrl+V`。
- `paste-ui`：仅执行激活窗口 + 粘贴（使用当前剪贴板）。

## 安装

```powershell
cd d:\ai\2026
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

### 飞桨 OCR（必装，主路径）

按 [飞桨安装文档](https://www.paddlepaddle.org.cn/install/quick) 先装 **paddlepaddle**（CPU 或 GPU），再装 paddleocr：

```powershell
# CPU 示例（版本号以官网为准）
python -m pip install paddlepaddle==3.2.0 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
pip install -e ".[paddle]"
# 或：pip install -r requirements-paddle.txt
```

更多说明见 [PaddleOCR 快速开始](https://paddlepaddle.github.io/PaddleOCR/latest/quick_start.html)。

### Tesseract（可选，仅作降级）

若 Paddle 未装好或识别失败，可装 `pytesseract` + 系统 Tesseract（环境变量 `WUKONG_OCR_BACKEND=tesseract` 可强制使用）。

```powershell
pip install -e ".[tesseract]"
```

## 使用

```powershell
python -m wukong_invite once
python -m wukong_invite poll --interval 0.5
python -m wukong_invite poll --interval 0.5 --paste-ui --window-title-re ".*钉钉.*"
python -m wukong_invite paste-ui
```

状态文件默认：`%USERPROFILE%\.wukong_invite_state.json`。

## 环境变量

| 变量 | 含义 |
|------|------|
| `WUKONG_OCR_BACKEND=tesseract` | 跳过 Paddle，仅用 Tesseract（测试或兜底） |
| `WUKONG_OCR_FORCE_TESSERACT=1` | Paddle 未命中邀请码时仍强制跑 Tesseract；默认若合并行为活动类文案（不含特殊码）且无「邀请码：」锚点会**跳过**兜底以省时间 |
| `WUKONG_INVITE_ALPHA_FILL_RGB` | 透明 PNG 转 RGB 时的底色，默认 `255,0,0`（红），勿用白底以免与纯白字混淆 |
| `WUKONG_INVITE_CROP_TOP` | 默认 `0.44`，保留图高上方比例（过小会切掉邀请码下半部分） |
| `WUKONG_INVITE_CROP_WIDTH` | 默认 `0.83`（略宽于旧 0.778，减少裁掉邀请码末字） |
| `WUKONG_INVITE_ROI_BR_X0` / `WUKONG_INVITE_ROI_BR_Y0` | **仅 legacy_chain**（旧 A/B/C 灰度 ROI）右下抹除；主路径「反色+裁剪」**不用**，避免擦掉邀请码 |
| `WUKONG_INVITE_OCR_VARIANTS` | 默认 `all`＝**仅**反色+裁剪；`raw_and_crop`＝原图+裁剪；`raw` / `inv_full`；`legacy3` / `legacy_chain` 见文档 |
| `WUKONG_INVITE_RAW_UPSCALE` | 仅 **`legacy_chain`** 等旧路用，原图放大倍数（默认 `2.0`） |
| `WUKONG_INVITE_WHITE_MIN` | 默认 `255`（仅严格 `#FFFFFF` 改黑）；设 `254` 等则 RGB 均 ≥ 该值即改黑（主路径与 legacy 共用） |
| `WUKONG_PADDLE_TEXT_DET_LIMIT_SIDE_LEN` | 与下面 `limit_type` 配合；默认 `960`（速度优先，可调大换精度） |
| `WUKONG_PADDLE_TEXT_DET_LIMIT_TYPE` | 默认 `max`（只缩小过大边）；勿随意改 `min`，否则窄裁剪条会被拉成上万像素宽并触发库内告警 |
| `WUKONG_PADDLE_TEXT_DET_THRESH`、`WUKONG_PADDLE_TEXT_DET_BOX_THRESH`、`WUKONG_PADDLE_TEXT_REC_SCORE_THRESH` | 可选，调 Paddle 检出/识别阈值 |
| `WUKONG_DEBUG_MOUSE=1` | 仅 UI 自动化：打印 ``[wukong mouse]`` 目标坐标与 ``GetCursorPos``（与 ``scripts/diag_mouse_to_screen_center.py`` 对照） |
| `WUKONG_CENTER_CLICK_OFFSET_Y` | 相对窗口几何中心向下偏移像素（默认代码内 `108`；脚本可用 `--center-offset-y` 覆盖） |
| `WUKONG_CENTER_CLICK_BUTTON=right` | 中心点击用右键（脚本可用 `--right-click`）；默认左键。右键常会弹出菜单，若阻碍后续粘贴可先 `Esc` 关闭 |
| `WUKONG_INPUT_USE_CLIPBOARD=0` | UI 填入文本时不用剪贴板+Ctrl+V，强制 `type_keys`（默认走剪贴板，利于 WebView） |
| `WUKONG_CENTER_CLICK_DELIVERY` | 中心点击投递：`mouse`（默认，依赖系统光标） / `postmessage`（`WM_*BUTTON`，**不移动光标**） / `postmessage_then_mouse`（先试消息再试物理） |
| `WUKONG_SKIP_MOUSE_BEFORE_FOCUS=1` | 不在「置前目标窗」**之前**移动鼠标，仅在置前之后再对齐/点击（脚本等价：`--mouse-after-focus-only`） |

### Windows：为何「悟空到最前后就控不了鼠标」

这不是单纯「先移鼠还是先置前」能彻底解决的逻辑顺序问题，而是 **Windows 对用户界面合成输入的限制**（常与 **UIPI / 完整性级别** 一起出现）：

- 当**前台窗口所属进程**以**管理员（提升）**身份运行，而你的 **Python / 终端未提升**时，系统会阻止低完整性进程通过 `SetCursorPos`、`SendInput` 等去操纵正在接收输入的高完整性前台——现象就是：**置前成功，但光标再也过不去或点击无效**。这与「屏幕键盘等前台应用在前台时 `SetCursorPos` 突然失效」是同一类机制，社区结论多为 **让自动化进程与目标进程同级（例如都以管理员运行终端后再跑脚本）**。参见 [Stack Overflow：SetCursorPos 在前台为某些程序时无效](https://stackoverflow.com/questions/65691101)。
- **安全软件 / 反作弊** 也可能在驱动或内核层拦截合成鼠标（与钉钉无关时也可能遇到）。
- **不靠全局光标的折中**：可向目标 HWND **PostMessage(WM_LBUTTONDOWN/UP)**（本仓库 `WUKONG_CENTER_CLICK_DELIVERY=postmessage`）；**不保证** Chromium/WebView 认这套消息，许多内嵌浏览器只认真实输入。
- **更「硬」的选项**：经微软签名的 **UIAccess** 辅助技术程序、或 **硬件键鼠**/盒子、或 **虚拟机内** 自动化——见 [UI 自动化安全概述](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-securityoverview)。

## 手动集成测试脚本

```powershell
# 1）专用集成脚本：默认无必填参数；可选 --save-debug [目录] 在基线/OCR 前保存调试图（last_raw 等）。
#    启动时自检一次 Paddle（可自动 pip）与 input_assistant_server（须已运行）；
#    轮询直到新邀请码 → 剪贴板 → 置前 → flow。状态文件默认仓库根 .wukong_test_state.json。
python scripts/run_test_01_fetch_ocr.py
python scripts/run_test_01_fetch_ocr.py --save-debug
python scripts/run_test_01_fetch_ocr.py --save-debug D:\tmp\invite_dbg

# 2）悟空/钉钉窗口：默认按进程 DingTalkReal.exe 连接（避免标题误连）
python scripts/run_test_02_wukong_window.py --list-processes
python scripts/run_test_02_wukong_window.py --list-windows
python scripts/run_test_02_wukong_window.py --text "SMOKE_001"
# 仅标题匹配（旧行为）：python scripts/run_test_02_wukong_window.py --no-process --title-re "(?i).*钉钉.*" --text "SMOKE_001"
# 诊断：Win32 能否把鼠标移到主屏中心（排查「无法控制鼠标」）
python scripts/diag_mouse_to_screen_center.py
python scripts/diag_mouse_to_screen_center.py --hold 8

# 3）先预热 Paddle，再每秒拉图 OCR，直到识别到与 state 中不同的新邀请码后退出
python scripts/watch_invite_until_update.py
python scripts/watch_invite_until_update.py --interval 1.5 --timeout 1800
python scripts/watch_invite_until_update.py --save-debug
```

## 打包成 Windows exe（给他人用）

目标脚本：`scripts/run_test_01_fetch_ocr.py`。使用 **PyInstaller 目录版（onedir）**，输出 `dist/wukong_fetch_ocr/`，需**整文件夹** zip 分发（内含 dll、依赖，勿只拷单个 exe）。

构建脚本会在输出目录额外放入：`register_input_assistant_task.ps1`、`input_assistant_server.py`、`wukong_invite/` 源码包、`README_wukong_fetch_ocr_NOVICE.txt`。新手应**只使用解压目录内的注册脚本**安装键鼠助手；主程序与助手默认使用同一内置密钥（本机回环），无需配置环境变量。**面向新手的完整步骤**见下文「Release 包使用说明（面向新手）」一节（与分发包内 `README_wukong_fetch_ocr_NOVICE.txt` 一致）。

```powershell
cd d:\ai\2026
.\scripts\build_wukong_fetch_ocr_exe.ps1
# 或手动:
pip install -e ".[paddle,bundle]"
pyinstaller --noconfirm packaging/run_test_01_fetch_ocr.spec
# 手动打包时请自行将上述文件复制到 dist\wukong_fetch_ocr\（见 build_wukong_fetch_ocr_exe.ps1）
```

运行：`dist\wukong_fetch_ocr\wukong_fetch_ocr.exe`（与 exe 同目录会生成 `.wukong_test_state.json` 等）。

说明：包体较大（含 Paddle）；对方机器需 **64 位 Windows**，且首次 OCR 仍可能向用户目录下载/缓存模型（`%USERPROFILE%\.paddlex` 等）。若打包失败，多半是某依赖未 `collect_all` 到，可把报错贴 issue 再补 `hiddenimports`。

## Release 包使用说明（面向新手）

以下内容与 `packaging/README_wukong_fetch_ocr_NOVICE.txt` 及 **Release / `dist\wukong_fetch_ocr\`** 内同名 txt **保持一致**，便于在仓库中直接阅读；以你手头的解压包内 txt 为准亦可。

### 整包与依赖

本文件夹须**整包解压保留**（勿只复制 `wukong_fetch_ocr.exe`）。主程序依赖同目录的「键鼠助手」服务；首次使用必须先完成下方「第一步」。

### 重要（键鼠自动化）

**多台显示器时脚本极易点错窗口或点偏坐标，结果不可信。** 在双击运行 `wukong_fetch_ocr.exe` 之前，请 **拔掉或禁用副屏，只保留一台显示器**；运行期间也不要临时改分辨率或 DPI 缩放。

### 开抢前约 5 分钟（务必照做）

1. 若尚未安装或提示更新：完成 **钉钉** 下载/安装或更新，在钉钉内打开 **悟空**。
2. **登录** 用于抢码的钉钉账号，悟空相关界面保持在可切换、可操作状态。
3. 「第一步（注册助手）」只需做一次：若从未执行过，请提前完成，不要压到开抢前最后一分钟。
4. 确认 **仅一台显示器**（见上文「重要」），再双击运行 `wukong_fetch_ocr.exe`；运行期间保持钉钉已打开。
5. 开抢前 **不要** 改分辨率或 DPI 缩放，否则同样容易点偏。

### 第一步（必须，首次使用做一次）

1. 在本文件夹空白处按住 Shift + 右键 →「在此处打开 PowerShell 窗口」，或打开「Windows PowerShell（管理员）」。
2. 执行（把路径换成你解压后的实际目录）：

```powershell
cd "本文件夹完整路径"
.\register_input_assistant_task.ps1
```

3. 若弹出 UAC，请点「是」。完成后会注册为登录后自动启动的助手任务。助手与主程序使用同一**内置密钥常量**，无需密钥文件或环境变量。

### 第二步（每次使用）

仅一台显示器、分辨率与缩放已稳定 → 双击运行 `wukong_fetch_ocr.exe`；保持钉钉与悟空可用。

### 卸载助手（计划任务）

在本助手所在目录打开 PowerShell（管理员），执行：

```powershell
cd "本文件夹完整路径"
.\register_input_assistant_task.ps1 -Unregister
```

说明：在 **Windows PowerShell 5.1** 里请写 **-Unregister**（单横线）；`--Unregister` 往往无效。卸载后登录时不会再自动启动助手；若曾手动开过 `python .\input_assistant_server.py`，仍需自行结束该进程（见下节）。

### 关闭占用 47821 端口的助手进程（可选）

助手默认监听 **127.0.0.1:47821**。若端口被占用、需先关掉再手动重启，可在 **PowerShell** 中：

1. 查看谁在监听（最后一列为 **PID**，示例中为 22228，你机器上会是别的数字）：

```powershell
netstat -ano | findstr "47821"
```

示例输出：

```
TCP    127.0.0.1:47821        0.0.0.0:0              LISTENING       22228
```

2. 用上面看到的 PID 结束进程（把 22228 换成你的 PID）：

```powershell
Stop-Process -Id 22228 -Force
```

注意：若计划任务仍在且设为登录启动，下次登录或任务被触发时助手可能再次占用该端口；彻底不用时请先做上文「卸载助手」。

### 说明与排障

- `ping` 若一直 `"ok": false`：请看完整 JSON 里的 `error` 字段。
  - `unauthorized`：客户端与服务端密钥不一致（多为**混用不同版本**的 exe/助手脚本，或仅一侧使用了 `--secret`）。请整包同版本分发。
  - `bad json`：不是 HTTP/浏览器协议；须用 TCP 发**一行** JSON（见 `input_assistant_client.py`）。不要用浏览器访问本端口。
- 本目录除 exe 与 `_internal` 外，还应含：`README_wukong_fetch_ocr_NOVICE.txt`、`register_input_assistant_task.ps1`、`input_assistant_server.py`、`wukong_invite\`（供计划任务启动助手时 import）。另含 `run_test_01_fetch_ocr.spec` 仅供从源码重新打包参考。
- 临时手动启动助手（不调计划任务）：在本目录打开终端执行 `python .\input_assistant_server.py`。
- 排查 OCR 时可加参数（可选）：`wukong_fetch_ocr.exe --save-debug` 或 `--save-debug 自定义目录`，会在每次建立基线或图片变化跑 OCR 前保存 last_raw / last_inv_full / last_inv_crop。
- 助手只监听本机 127.0.0.1，不会对外网开放。
- 若注册失败，请确认已安装 Python 3.10+，且命令行能运行 `py -3` 或 `python` 且已经安装注册需要的所有依赖。分发包已带 `wukong_invite` 源码，一般无需再 pip install 本仓库；若用 `input_assistant_client.py ping` 验证，需在开发机仓库里执行。

## 测试

```powershell
pytest
```

## 说明

- 首次运行 PaddleOCR 可能下载模型，耗时较长。
- 轮询请勿过高频率，避免对 `hudong.alicdn.com` 造成压力。
- UI 自动化依赖钉钉窗口标题，详见 `docs/wukong-invite-automation.md`。
