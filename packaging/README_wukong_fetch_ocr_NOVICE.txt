悟空邀请码助手（wukong_fetch_ocr）— 新手请按顺序做
====================================================

本文件夹须整包解压保留（勿只复制 wukong_fetch_ocr.exe）。主程序依赖同目录的「键鼠助手」服务；首次使用必须先完成下方「第一步」。

重要（键鼠自动化）
------------------
**多台显示器时脚本极易点错窗口或点偏坐标，结果不可信。** 在双击运行 ``wukong_fetch_ocr.exe`` 之前，请 **拔掉或禁用副屏，只保留一台显示器**；运行期间也不要临时改分辨率或 DPI 缩放。

开抢前约 5 分钟（务必照做）
---------------------------
1. 若尚未安装或提示更新：完成 **钉钉** 下载/安装或更新，在钉钉内打开 **悟空**。
2. **登录** 用于抢码的钉钉账号，悟空相关界面保持在可切换、可操作状态。
3. 「第一步（注册助手）」只需做一次：若从未执行过，请提前完成，不要压到开抢前最后一分钟。
4. 确认 **仅一台显示器**（见上文「重要」），再双击运行 wukong_fetch_ocr.exe；运行期间保持钉钉已打开。
5. 开抢前 **不要** 改分辨率或 DPI 缩放，否则同样容易点偏。

第一步（必须，首次使用做一次）
------------------------------
1. 在本文件夹空白处按住 Shift + 右键 →「在此处打开 PowerShell 窗口」，或打开「Windows PowerShell（管理员）」。
2. 执行（把路径换成你解压后的实际目录）：

   cd "本文件夹完整路径"
   .\register_input_assistant_task.ps1

3. 若弹出 UAC，请点「是」。完成后会注册为登录后自动启动的助手任务。
   助手与主程序使用同一**内置密钥常量**，无需密钥文件或环境变量。

第二步（每次使用）
------------------
仅一台显示器、分辨率与缩放已稳定 → 双击运行 wukong_fetch_ocr.exe；保持钉钉与悟空可用。

卸载助手（计划任务）
--------------------
在本助手所在目录打开 PowerShell（管理员），执行：

   cd "本文件夹完整路径"
   .\register_input_assistant_task.ps1 -Unregister

说明：在 **Windows PowerShell 5.1** 里请写 **-Unregister**（单横线）；``--Unregister`` 往往无效。
卸载后登录时不会再自动启动助手；若曾手动开过 ``python .\input_assistant_server.py``，仍需自行结束该进程（见下节）。

关闭占用 47821 端口的助手进程（可选）
--------------------------------------
助手默认监听 **127.0.0.1:47821**。若端口被占用、需先关掉再手动重启，可在 **PowerShell** 中：

1. 查看谁在监听（最后一列为 **PID**，示例中为 22228，你机器上会是别的数字）：

   netstat -ano | findstr "47821"

   示例输出：

   TCP    127.0.0.1:47821        0.0.0.0:0              LISTENING       22228

2. 用上面看到的 PID 结束进程（把 22228 换成你的 PID）：

   Stop-Process -Id 22228 -Force

注意：若计划任务仍在且设为登录启动，下次登录或任务被触发时助手可能再次占用该端口；彻底不用时请先做上文「卸载助手」。

说明
----
- ping 若一直 ``"ok": false``：请看完整 JSON 里的 ``error`` 字段。
  * ``unauthorized``：客户端与服务端密钥不一致（多为**混用不同版本**的 exe/助手脚本，或仅一侧使用了
    ``--secret``）。请整包同版本分发。
  * ``bad json``：不是 HTTP/浏览器协议；须用 TCP 发**一行** JSON（见 ``input_assistant_client.py``）。
    不要用浏览器访问本端口。
- 本目录除 exe 与 _internal 外，还应含：``README_wukong_fetch_ocr_NOVICE.txt``（本文件）、
  ``register_input_assistant_task.ps1``、``input_assistant_server.py``、``wukong_invite\``（供计划任务启动助手时 import）。
  另含 ``run_test_01_fetch_ocr.spec`` 仅供从源码重新打包参考。
- 临时手动启动助手（不调计划任务）：在本目录打开终端执行 ``python .\input_assistant_server.py``。
- 排查 OCR 时可加参数（可选）：``wukong_fetch_ocr.exe --save-debug`` 或 ``--save-debug 自定义目录``，
  会在每次建立基线或图片变化跑 OCR 前保存 last_raw / last_inv_full / last_inv_crop。
- 助手只监听本机 127.0.0.1，不会对外网开放。
- 若注册失败，请确认已安装 Python 3.10+，且命令行能运行 py -3 或 python 且已经安装注册需要的所有依赖。
  分发包已带 ``wukong_invite`` 源码，一般无需再 pip install 本仓库；若用 ``input_assistant_client.py ping`` 验证，需在开发机仓库里执行。
