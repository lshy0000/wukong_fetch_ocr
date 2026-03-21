# 悟空邀请码自动化流程 — 设计文档

本文档描述在 **Windows** 上实现「官网发现邀请码 → 写入剪贴板 → 打开钉钉悟空并完成粘贴与确认」的整体方案。实现时按 **模块拆分、函数边界清晰、每步可单独测试**，最后再串联集成。

---

## 一、目标流程（端到端）

1. **轮询或监听**钉钉官网（或你最终确定的展示邀请码的页面）HTML/接口，解析出当前邀请码字符串。  
2. 与本地记录的「上一次邀请码」比对；若**发生变化**，将新码写入**系统剪贴板**。  
3. 通过**键盘鼠标自动化**（或更稳妥的 **UI 自动化**）切换到钉钉客户端中的悟空入口，在**固定交互路径**下完成：聚焦输入框 → 粘贴 → 触发「绑定 / 开始体验」等按钮。  

> **前提假设**：邀请码出现在可 HTTP 获取的页面或固定 JSON 接口中；若实际为强人机校验、仅登录态可见且 token 复杂，则「提取」模块需改为 **浏览器扩展 / Playwright 已登录会话**，下文在 2.1 节说明分支。

---

## 二、核心问题 1：如何提取邀请码

### 2.1 先确认「码」在哪里（调研任务，写进测试清单）

在动手写解析逻辑前，必须用浏览器 **开发者工具（F12）** 完成一次事实核查：

| 检查项 | 目的 |
|--------|------|
| 邀请码是 **SSR 写在 HTML** 里，还是 **XHR/fetch 拉 JSON** 后再渲染？ | 决定用「静态 HTML 正则/DOM」还是「抓接口 + JSONPath」 |
| 不登录是否可见？ | 决定能否用简单 `requests`/`httpx`，还是必须 **Cookie / Playwright 登录态** |
| 是否有 **CDN 缓存**、时间戳参数、签名？ | 决定轮询 URL 是否要带 cache-bust、是否要复用 Session |
| 页面结构是否经常改版？ | 决定解析用 **脆弱的正则** 还是 **稍稳的结构化选择器（若用浏览器自动化）** |

**输出物**：一页「提取规格」——示例 URL、示例响应片段、邀请码字段名或前后缀模式。

### 2.1.1 已落实的提取规格（2026-03 官网悟空页）

| 项 | 结论 |
|----|------|
| 入口页 | `https://www.dingtalk.com/wukong`（bundle：`wukong_office_network`） |
| 数据形态 | **非明文**：前端用 JSONP 拉取配置，返回字段 **`img_url`**，指向 `gw.alicdn.com` 上的 **PNG**（页面上「邀请码」即该图） |
| JSONP URL | `https://hudong.alicdn.com/api/data/v2/438eae9715f945468d599660d2d92aeb.js?t={ms}&callback=img_url` |
| 响应示例 | `img_url({"img_url":"https://gw.alicdn.com/imgextra/...png"})` |
| 登录 | 拉取 **无需** 钉钉登录（与页面同源公开配置） |
| 文本码获取 | 对 PNG 做 **飞桨 PaddleOCR**（主路径）；可选 Tesseract 降级；URL 变化即表示运营换了新图 |
| 工程实现 | 见 `src/wukong_invite/hudong_fetch.py`、`ocr_extract.py`（多路图像变体 + `pick_invite_candidate` 抽邀请码） |

**准确率相关（2026-03）**：

- **默认预处理**：带 Alpha 的 PNG 先 **`pil_invite_to_rgb`**：透明像素用**红底**（默认 `255,0,0`，勿用白底）再参与后续；「反色」= **仅 ``#FFFFFF`` → ``#000000``**（可调 `WUKONG_INVITE_WHITE_MIN`）→ **仅几何 ROI 裁剪**（与 full 一致、无抹除；`--save-debug`：`last_raw`、`last_inv_full`、`last_inv_crop`）。默认识别序：**仅反色+ROI裁剪**（不跑原图，提速）；需双路时用 `WUKONG_INVITE_OCR_VARIANTS=raw_and_crop`。
- 旧实验链路：`WUKONG_INVITE_OCR_VARIANTS=legacy_chain`（含放大、FFF、CLAHE/Otsu 等）；`legacy3`＝原图+旧 A+B。
- Paddle：`text_det_limit_type` 默认 **`max`**（避免 `min` 把矮条横幅放大到「16375×2560」再撞 `max_side_limit=4000` 打日志）；可调 `WUKONG_PADDLE_TEXT_DET_LIMIT_*`。

### 2.2 推荐实现分层

```
fetch_raw()      → 返回 bytes 或 str（HTTP 或已渲染 DOM 文本）
parse_invite()   → 返回 Optional[str]，解析失败返回 None
normalize_code() → 去空白、统一大小写（若业务需要）
```

- **若纯 HTTP 可行**：Python `httpx`/`requests`，设置合理 `User-Agent`，必要时 `Session` 保持 Cookie。  
- **若必须执行 JS 或登录**：Python **Playwright**（或 Node Playwright）单独子进程，只负责 `page.content()` 或 `page.evaluate` 取文本，再交给同一套 `parse_invite()`。避免把「浏览器」和「键鼠控制」混在一个难以测试的大脚本里。

### 2.3 解析策略（按稳定性排序）

1. **JSON 字段**：若接口返回 `{"inviteCode":"XXXX"}` 之类，用 JSON 解析最稳。  
2. **HTML data 属性**：如 `data-invite-code="XXXX"`，用选择器或正则锚定属性名。  
3. **纯文案正则**：例如「邀请码[:：]\s*([A-Z0-9]{6,})」，易随文案改版失效，需集成测试里用快照 HTML 回归。

### 2.4 单元测试建议

- fixtures：保存 **真实页面脱敏后的 HTML/JSON 片段**（不要提交隐私 Cookie）。  
- 断言：`parse_invite(fixture_old) == "OLD"`，`parse_invite(fixture_new) == "NEW"`，`parse_invite(malformed) is None`。

---

## 三、核心问题 2：如何控制 Windows 键盘与鼠标

### 3.1 两类能力（建议优先 UI 自动化，键鼠作兜底）

| 方式 | 优点 | 缺点 |
|------|------|------|
| **UI Automation（推荐）** | 可按控件名/类型查找输入框、按钮，分辨率无关 | 需学习 Inspect/UIA，钉钉更新可能变控件树 |
| **坐标点击 + 快捷键** | 实现快 | 分辨率/DPI/窗口位置一变就偏；多显示器更易错 |

**建议主路径**：能 UIA 则 UIA；仅在无法稳定定位控件时，对「已知固定布局」的步骤使用 **相对窗口客户区的坐标**（见第五节）。

### 3.2 Windows 上常见技术选型

- **Python + `pyautogui`**：全局鼠标键盘，简单，适合 PoC。  
- **Python + `pywinauto`**：基于 Win32 / UIA，适合找钉钉窗口与控件。  
- **AutoHotkey v2**：热键、剪贴板、窗口激活极快，可与 Python 通过 CLI/文件通信。  
- **PowerShell + `System.Windows.Forms` / UIAutomation**：无额外语言时可选用。

文档级建议：**提取邀请码与写剪贴板用 Python**；**激活窗口与粘贴可用 pywinauto + 快捷键（Ctrl+V）**，比纯像素点击更抗轻微布局变化。

### 3.3 安全与体验

- 自动化运行前 **暂停几秒** 或要求 **热键触发**，避免抢鼠标误伤操作。  
- 使用 **剪贴板** 时注意：写入会覆盖用户剪贴板；可选「粘贴后恢复原剪贴板」（高级，需处理图片/HTML 格式时再议）。

---

## 四、次要问题 1：高速轮询与「一变即取」

### 4.1 轮询模型

```
last_code = None
loop:
    raw = fetch_raw()
    code = parse_invite(raw)
    if code and code != last_code:
        set_clipboard(code)
        notify_or_trigger_ui_automation()
        last_code = code
    sleep(interval)
```

### 4.2 `interval` 与礼貌

- 过短（如 50ms）可能对源站造成压力并触发风控；建议从 **200ms～1s** 起调，按实际更新频率与封禁情况调整。  
- 使用 **If-Modified-Since / ETag**（若服务器支持）可减少流量；很多营销页不支持，则可用 **响应 hash**（对 `raw` 做 SHA256）：hash 不变则跳过解析。

### 4.3 「立即」的工程含义

- 网络 + 解析通常在毫秒～百毫秒级；真正的延迟往往来自 **页面 CDN 缓存** 与 **官网更新频率**，脚本无法快过源站发布。  
- 若同一 URL 强缓存：尝试 **query cache buster**（如 `?_t=timestamp`）仅在你确认不会破坏签名且合规时使用。

### 4.4 可选：非轮询

若官网通过 **WebSocket / SSE** 推送（少见），可改为事件驱动；否则轮询仍是默认方案。

---

## 五、次要问题 2：定位程序窗口与快速输入

### 5.1 窗口级定位（优先于屏幕坐标）

1. 用 **窗口标题类名** 或 **进程名** 找到钉钉主窗口（`pywinauto` 的 `Application(backend="uia").connect(...)`）。  
2. **置前（set_focus）** 再发送键盘消息，避免输入落到后台窗口。  
3. 打开悟空的路径：若存在 **全局快捷键 / 命令面板**，比纯点击更稳；否则记录 **从主界面到输入框** 的固定按键序列（Tab 次数等）并做冒烟测试。

### 5.2 输入方式对比

| 方法 | 适用 |
|------|------|
| **Ctrl+V 粘贴** | 邀请码在剪贴板，最快且与中文输入法冲突小 |
| `typewrite` 逐字符 | 仅当目标框禁止粘贴时；慢且易受输入法影响 |

### 5.3 固定像素点击时（兜底）

- 使用 **窗口客户区坐标**：先 `GetWindowRect` / 客户区原点，再换算点击位置，避免任务栏、多显示器导致的绝对坐标漂移。  
- DPI：在 **100%/125%/150%** 下各测一遍，或强制钉钉「兼容性 DPI」设置并文档化。

### 5.4 调试手段

- Windows **「步骤记录器」** 或录屏，对照你的手工操作与脚本步骤。  
- `pywinauto` 的 `print_control_identifiers()` 导出控件树，保存到 `debug/` 供版本升级后 diff。

---

## 六、推荐模块划分与测试矩阵

### 6.1 模块

| 模块 | 职责 | 可独立测试 |
|------|------|------------|
| `fetch` | HTTP 或 Playwright 取 raw | Mock 服务器返回固定 HTML/JSON |
| `parse` | 提取邀请码 | 纯单元测试 |
| `state` | 持久化 `last_code`（内存或本地小文件） | 重启进程后是否重复触发 |
| `clipboard` | 写入剪贴板 | 读回断言 |
| `ui` | 激活钉钉、导航、粘贴、确认 | **人工监督下** 的分步集成测试 |
| `orchestrator` | 轮询间隔、日志、热键启停 | 集成测试可用 fake ui |

### 6.2 测试顺序（建议）

1. **parse**（无网络）  
2. **fetch + parse**（对 staging 或保存的 snapshot）  
3. **clipboard**  
4. **ui 单步**：仅激活窗口；仅粘贴到记事本验证坐标/焦点  
5. **全链路**：官网 mock 变码 → 剪贴板 → 悟空流程（最后再做）

---

## 七、风险与合规（实现前必读）

- 自动化需符合 **钉钉用户协议** 与官网 **robots/合理使用**；过高频请求可能导致 IP 或账号限制。  
- 若邀请码发放带 **人机验证**，HTTP 抓取会失败，应改为 **人工半自动** 或 **已登录浏览器自动化**，不得尝试绕过安全机制。  
- 键鼠脚本可能在误焦点时操作错误窗口；务必 **可一键中止**（如全局热键停止循环）。

---

## 八、下一步（落地清单）

1. 在浏览器中确定邀请码的 **确切 DOM/接口**，填写本文 **§2.1 提取规格**。  
2. 选定技术栈：**Python + httpx + pywinauto**（或加 Playwright 分支）。  
3. 实现 `parse_invite` + 测试 fixtures。  
4. 实现 `fetch_raw` + hash 优化轮询。  
5. 在记事本验证 **窗口激活 + Ctrl+V**。  
6. 映射悟空 UI 步骤，写入 `ui` 模块并做端到端试运行。

---

## 九、文档修订记录

| 版本 | 日期 | 说明 |
|------|------|------|
| 0.1 | 2026-03-20 | 初稿：流程拆分、两大核心问题、两次要问题、模块与测试顺序 |
