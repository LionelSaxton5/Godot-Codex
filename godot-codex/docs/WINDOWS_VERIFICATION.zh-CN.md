# Godot-codex 0.2.1 Windows 验证说明

官方 Godot 4.6.3 普通版与 .NET 版均已验证。Python 99 项通过、13 项因符号链接权限跳过、零失败；GDScript/C# 真实编辑器检查分别 184/185 项通过，实际 Codex→MCP→编辑器调用也分别通过，均覆盖全部 26 个工具。2D/3D、中文与空格路径、保存重开、撤销重做、失败及超时处理已覆盖。

公开候选包仅调整名称和文档，并单独验证从新 ZIP 解压后的隔离安装及 26 项工具发现。完整功能验收继承自未经逻辑改动的 Windows 0.2.1；不宣称已再次执行全套编辑器检查。

要求 Python 3.10+、Godot 4.6.3；C# 另需 .NET 版编辑器和兼容 SDK。Windows 可使用可运行的 Python 完整路径调用安装脚本，安装器会把该解释器写入隔离安装的 MCP 配置。Godot 4.4.1 缺少所需 API，不受支持。

参见[安装说明](EDITOR_SETUP.zh-CN.md)、[能力边界](EDITOR_CAPABILITIES.md)和[验证摘要](VERIFICATION.md)。公开包不包含本机路径、账号信息、原始日志或调试转录。
