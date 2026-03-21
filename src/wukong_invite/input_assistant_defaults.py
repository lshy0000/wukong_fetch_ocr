"""
与 ``input_assistant_server``、``wukong_fetch_ocr``、``input_assistant_client`` 共用的**内置密钥常量**。

默认仅用于 **127.0.0.1** 助手；服务端与客户端均直接使用本常量，**不**读密钥文件、不设环境变量。
"""

# 修改时务必同步重新打包 exe / 分发 zip，并通知用户重装助手计划任务（若已注册）
BUNDLED_INPUT_ASSISTANT_SECRET = (
    "wukong-invite-local-v1-7f3c9a2e4b8d1f6e0c5a9b3d7e1f4a8c2e6b0d4f8a1c5e9b3d7f0a4c8e2b6"
)
