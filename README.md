# Godot-Codex

**用自然语言让 Codex AI 操控 Godot 编辑器。**

[English](README.en.md) · [下载安装包](downloads/godot-codex-plugin-0.2.1-windows-verified.zip) · [详细安装说明](godot-codex-plugin/docs/EDITOR_SETUP.zh-CN.md) · [功能与限制](godot-codex-plugin/docs/EDITOR_CAPABILITIES.md)

Godot-Codex 把 Codex 与你本机正在运行的 Godot 编辑器连接起来。你描述想做什么，AI 通过本地 MCP 桥接调用 Godot 编辑器 API，查看和修改真实场景。

当前发布版本为 **0.2.1（Windows 验证版）**。这是独立的 MIT 开源项目，与 Godot 和 OpenAI 没有官方隶属关系。

## 能做什么

- 查看当前场景、节点层级、可编辑属性和信号连接。
- 创建、打开、保存场景；创建、删除、复制、重命名和调整节点层级。
- 修改属性，创建并分配原生材质、网格和碰撞形状等资源。
- 读取、写入、附加 GDScript 或 C# 脚本，连接持久化信号。
- 调用场景撤销、重做，以及编辑器运行、停止功能。
- 提供 7 项 Godot 开发技能，覆盖编辑器控制、项目检查、场景与资源、信号、UI、2D 像素与地图、调试验证。

共有 **26 项编辑器工具**。完整参数见 [工具定义](godot-codex-plugin/docs/EDITOR_API.json)。

![通过本地 MCP 桥接创建并在 Godot 中验证的 3D 场景](godot-codex-plugin/assets/live-editor-3d.png)

## 环境要求

- Python 3.10 或更新版本；插件 Python 部分只使用标准库。
- Godot **4.6.3** 是当前已验证版本。Godot 4.4.1 缺少所需编辑器 API，无法使用本版本桥接。
- C# 项目需要 Godot .NET 版和匹配的 .NET SDK。
- Codex 或其他支持 stdio MCP 的 AI 客户端。
- AI/MCP 和 Godot 必须能够访问同一台机器上的同一个项目目录。

桥接本身无需 API Key、云服务器或付费后端；AI 客户端的账号和费用由对应服务决定。使用时必须保持 Godot 编辑器打开，并启用项目内的 addon。

## Windows 快速开始

下载并解压上面的安装包，进入其中的 `godot-codex-plugin` 文件夹。下列命令中的 Python、插件和项目路径请替换成自己的实际路径。

### 1. 安装 Codex 插件

在 PowerShell 中运行：

```powershell
$Python = 'C:\Python313\python.exe'
& $Python scripts/install_local.py --home $env:USERPROFILE
& $Python scripts/install_local.py --home $env:USERPROFILE --apply
```

第一条命令预览安装计划，第二条执行安装。之后运行安装器输出的 `next_command`，完成 Codex 插件登记。安装器会写入当前 Python 的真实路径，避免 Windows 上没有 `python3` 的问题。

### 2. 为 Godot 项目安装编辑器桥接

先关闭目标项目的 Godot 编辑器：

```powershell
& $Python scripts/setup_editor_bridge.py 'D:\MyGodotProject' --enable
& $Python scripts/setup_editor_bridge.py 'D:\MyGodotProject' --apply --enable
```

第一条预览，第二条复制并启用 addon；修改项目配置前会保存备份。

### 3. 配置项目路径并连接

为启动 Codex 的进程配置 `GODOT_PROJECT_PATH`，然后重新打开 Godot 项目并开启新的 Codex 对话：

```powershell
$env:GODOT_PROJECT_PATH = 'D:\MyGodotProject'
```

此变量只作用于当前 PowerShell 及其启动的子进程。从开始菜单启动的客户端通常不会继承它；详细配置方式见 [安装说明](godot-codex-plugin/docs/EDITOR_SETUP.zh-CN.md)。也可按该说明使用独立 MCP 登记方式，选择一种连接方式即可。

先让 AI 调用 `godot_status`，确认连接的是正确项目，再开始编辑。

## 可以这样说

> 查看当前场景的节点层级，告诉我有哪些按钮和信号连接。

> 在当前 Godot 编辑器里创建一个 3D 场景，加入方块、材质、灯光和相机，保存并运行。

> 把指定 Node2D 的位置改到我给定的坐标，然后撤销一次，确认可以恢复。

> 为这个节点附加 C# 脚本，保持项目原本的语言；检查构建通过后再运行。

## 验证与边界

安装包包含 Windows 下的 Python 回归、真实 Godot 编辑器、stdio MCP 和 Codex app-server 验证记录，以及 GDScript/C# 的 2D/3D 示例。历史 Linux 0.2.0 记录单独保留。

[Windows 验证报告](godot-codex-plugin/docs/WINDOWS_VERIFICATION.zh-CN.md) · [验证记录](godot-codex-plugin/docs/VERIFICATION.md)

本版本覆盖已实现并验证的编辑器操作，不能操控 Godot 的所有菜单和功能。macOS、0.2.1 的 Linux 重测及其他 Godot 版本尚未验证。请只在自己信任并授权 AI 修改的项目中使用；桥接不是隔离恶意项目代码的沙箱。

## 源码与许可证

源码位于 [godot-codex-plugin](godot-codex-plugin/)，包含安装器、MCP 服务、Godot addon、技能、测试、示例和原始文档。仓库名称使用 Godot-Codex，内部包名保留 `godot-codex-plugin`，以兼容已有安装和构建脚本。

[MIT License](LICENSE)。欢迎通过 [Issues](https://github.com/LionelSaxton5/Godot-Codex/issues) 反馈问题；请附上 Godot 版本、操作系统和复现步骤，并去掉日志中的个人路径和敏感信息。
