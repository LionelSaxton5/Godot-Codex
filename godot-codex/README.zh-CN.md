# Godot-codex 0.2.1

Windows 修订的实际结果、使用方法和版本边界见 [Windows 验证说明](docs/WINDOWS_VERIFICATION.zh-CN.md)。

这一版让 AI **真正操作正在运行的 Godot 编辑器**，同时保留原来的 Godot 原生开发技能。

它包含：

- Godot EditorPlugin：实际创建场景/节点、改属性、连接信号、处理资源、保存、撤销重做、运行停止
- 本地 stdio MCP：把这些编辑器操作提供给 Codex 等 AI 客户端
- 7 项技能：实际编辑器控制，以及项目检查、场景/Resources/Autoload、信号、UI、2D 像素地图、调试验证
- GDScript 与 C# 工作流，2D 与 3D 编辑基础
- 工具、安全边界、自动化测试和完整验收记录

不是只有 Markdown，也不是直接改 `.tscn` 冒充编辑器操作。MCP 请求会交给打开的项目里的 EditorPlugin，再调用 Godot 编辑器 API。

## 从这里开始

1. 阅读 [中文连接与安装指南](docs/EDITOR_SETUP.zh-CN.md)
2. 查看 [具体能力与限制](docs/EDITOR_CAPABILITIES.md)
3. 查看 [实际测试报告](docs/VERIFICATION.md)

**必须保持 Godot 编辑器打开、addon 已启用，并让 AI/MCP 与 Godot 能访问同一个工程目录。** 普通 Godot 不运行 C#；C# 工程仍需 Godot .NET 版和匹配 SDK。

连接使用本地工程内文件队列，不开网络端口、不需要 API Key。它只适合你信任且授权 AI 编辑的工程，不是隔离恶意工程代码的安全沙箱。

## 可以这样用

- “在当前 Godot 编辑器创建一个 3D 场景，加方块网格、材质、灯光和摄像机，保存并运行”
- “查看当前场景的真实节点，把指定 Node2D 的位置改掉，再撤销、重做验证”
- “新增按钮，把 pressed 连接到已有非 tool 脚本的方法，并确认保存后的连接”
- “为这两个节点分别使用现有 GDScript/C# 脚本，保持项目原来的语言”

v0.2 的范围是已实现并验收的编辑器基础操作，并不代表 Godot 的所有菜单、动画工具、导入器、调试器、导出平台和自定义插件都已自动化。遇到未支持的能力会明确报告，不会以任意执行代码绕过限制。


[Live editor screenshot / 实际编辑器截图](assets/live-editor-3d.png): scene objects and materials were created through the local MCP bridge, then verified in the open Godot editor.
