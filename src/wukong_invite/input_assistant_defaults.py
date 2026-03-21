"""
与 ``register_input_assistant_task.ps1``、打包目录内脚本共用的**本机默认密钥**。

仅用于 **127.0.0.1** 助手服务；面向新手 zip 分发，避免再配置环境变量。
若已存在 ``%LOCALAPPDATA%\\wukong_input_assistant\\secret.txt``，仍以文件为准（优先于本常量）。
"""

# 修改时务必同步更新 scripts/register_input_assistant_task.ps1 中的 $BundledAssistantSecret
BUNDLED_INPUT_ASSISTANT_SECRET = (
    "wukong-invite-local-v1-7f3c9a2e4b8d1f6e0c5a9b3d7e1f4a8c2e6b0d4f8a1c5e9b3d7f0a4c8e2b6"
)
