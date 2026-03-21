悟空邀请码助手（wukong_fetch_ocr）— 新手请按顺序做
====================================================

本文件夹须整包保留（勿只复制 wukong_fetch_ocr.exe）。第一次使用前请先装「键鼠助手」服务。

第一步（必须，仅做一次，运行前请先保证只连接一个显示器）
------------------------
1. 在本文件夹空白处按住 Shift + 右键 →「在此处打开 PowerShell 窗口」或打开「Windows PowerShell（管理员）」。
2. 执行（路径请改成你解压后的实际目录）：

   cd "本文件夹完整路径"
   .\register_input_assistant_task.ps1

3. 若弹出 UAC，请点「是」。完成后会注册登录自动启动的助手服务。
   密钥已与主程序一致，无需再设置环境变量。

第二步
------
双击运行 wukong_fetch_ocr.exe，保持钉钉/悟空客户端已打开。

说明
----
- 本目录除 exe 与 _internal 外，还应含：``README_wukong_fetch_ocr_NOVICE.txt``（本文件）、
  ``register_input_assistant_task.ps1``、``input_assistant_server.py``、``wukong_invite\``（供计划任务启动助手时 import）。
  另含 ``run_test_01_fetch_ocr.spec`` 仅供从源码重新打包参考。
- 临时手动启动助手（不调计划任务）：在本目录打开终端执行 ``python .\input_assistant_server.py``。
- 排查 OCR 时可加参数（可选）：``wukong_fetch_ocr.exe --save-debug`` 或 ``--save-debug 自定义目录``，
  会在每次建立基线或图片变化跑 OCR 前保存 last_raw / last_inv_full / last_inv_crop。
- 助手只监听本机 127.0.0.1，不会对外网开放。
- 若注册失败，请确认已安装 Python 3.10+，且命令行能运行 py -3 或 python 且已经安装注册需要的所有依赖。
  分发包已带 ``wukong_invite`` 源码，一般无需再 pip install 本仓库；若用 ``input_assistant_client.py ping`` 验证，需在开发机仓库里执行。
