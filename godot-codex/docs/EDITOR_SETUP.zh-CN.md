# v0.2：连接真正的 Godot 编辑器

Windows 请使用声明的 Godot 4.6.3 基线，并按 [Windows 安装与验证说明](WINDOWS_VERIFICATION.zh-CN.md) 使用实际 Python 解释器；本机 Godot 4.4.1 的编辑器 API 不满足此 addon。

这版由两部分组成：

- **Godot EditorPlugin**：在你打开的项目里运行，调用 Godot 的场景、节点、属性、UndoRedo 等编辑器 API
- **本地 MCP 服务**：让 Codex 或其他支持 stdio MCP 的 AI 客户端调用这些操作

只有 Markdown 技能时，AI 只能读写工程文件；这套连接会实际改变正在运行的编辑器。**Godot 必须保持打开，插件必须启用，AI 与编辑器必须访问同一台机器上的同一个工程目录。**

## 1. 安装技能/MCP 插件

解压 v0.2，在插件目录中先看计划：

```sh
python3 scripts/install_local.py --home "$HOME"
```

确认后使用 `--apply` 复制并登记，按输出的 `next_command` 激活 Codex 插件。这个安装器只处理新安装，不会覆盖同名旧插件。已有 v0.1 时应按 Codex 的插件更新流程升级；不要删除其他插件或直接覆盖个人配置。

打包的 `.mcp.json` 使用插件相对工作目录，启动 `python3 scripts/godot_mcp_server.py`。它读取明确配置的 `GODOT_PROJECT_PATH`，不会自行猜项目、扫描所有文件或自动选当前编辑器。

## 2. 把编辑器插件放入目标工程

先关闭该工程的 Godot 编辑器，再从本包目录运行：

```sh
python3 scripts/setup_editor_bridge.py "/你的Godot工程" --enable
```

这是预览，不会写入。确认路径与影响后：

```sh
python3 scripts/setup_editor_bridge.py "/你的Godot工程" --apply --enable
```

它会：

1. 复制到 `addons/ai_editor_bridge/`
2. 保留其他已启用的编辑器插件
3. 在修改 `project.godot` 前保存原始备份 `project.godot.before-ai-bridge`
4. 拒绝覆盖现有同名 addon、备份或符号链接路径

也可以不加 `--enable`，只复制 addon，然后在 Godot 的 Project Settings → Plugins 手动启用。打开工程后保持编辑器运行。

这是对你信任的工程显式开放本机编辑能力。它不开网络端口、不需要 API Key；同一操作系统用户下能写这个工程的其他程序也可能操作这条本地连接。因此它不是隔离恶意工程或恶意本机进程的安全沙箱。连接文件沿用工程所在目录的操作系统访问权限；请使用仅向你自己的账户开放的工程目录。能读取这些文件的账户也能读取连接内容，本插件不会替你更改系统权限或增加认证。

## 3. 明确告诉 AI 客户端项目路径

### 使用插件内置 MCP

让启动 Codex 的环境包含：

```sh
export GODOT_PROJECT_PATH="/你的Godot工程"
```

再启动 Codex 新对话。注意：从 Dock/开始菜单启动的桌面客户端通常不会继承某个终端里临时设置的环境变量，需用该客户端支持的 MCP 配置方式明确指定路径。

### 单独登记 MCP（不使用插件内置连接时）

`setup_editor_bridge.py` 会打印一条使用当前实际路径的命令，形式如下：

```sh
codex mcp add godot-editor --env GODOT_PROJECT_PATH="/你的Godot工程" -- python3 "/本插件绝对路径/scripts/godot_mcp_server.py"
```

只选择一种 MCP 连接方式，避免同一个工具出现两份。上述登记需由你在自己的环境明确执行；本交付没有替你修改账号或真实客户端配置。

其他 stdio MCP 客户端使用同样的 Python 命令、脚本绝对路径和环境变量即可。协议版本以 `EDITOR_API.json` 为准；不要把它当成需要公网 URL 的 HTTP 服务。

## 4. 先连接验证，再编辑

让 AI 调用 `godot_status`。应看到：

- 目标工程路径
- Godot 引擎版本与编辑器会话 ID
- 当前场景路径、版本、是否在运行
- 支持的操作列表

再用 `godot_hierarchy`、`godot_node_inspect` 查看真实节点。修改时工具需要最新的场景版本和节点身份，避免切换场景或手动编辑后操作错对象。

可以这样请求：

- “连接这个 Godot 工程，创建一个 Node3D 场景，加 MeshInstance3D、BoxMesh、材质、灯光和摄像机，保存后运行检查”
- “在当前 2D 场景里新增按钮，把 pressed 信号连到现有非 tool 脚本的方法，验证保存后仍存在”
- “查看这个节点有哪些可编辑属性，把 position 改成指定 Vector3，再撤销并重做”

C# 工程必须使用 **Godot .NET 编辑器和匹配的 .NET SDK**。创建/修改 `.cs` 文件不会自动编译；先用项目原来的构建流程或随包验证器编译，再附加脚本或运行。

## 安全边界与常见阻塞

- 编辑器没打开、addon 没启用、路径不一致：状态检查会失败，不会悄悄转向其他工程
- 场景版本或节点身份过期：重新查看现状，再决定操作，不盲目重试
- 已提交请求超时：结果可能已经发生；先检查编辑器，避免重复创建/删除
- 保存检测到磁盘被外部改过：停止覆盖，先处理冲突
- UndoRedo 操作的是当前场景的历史，里面也可能含手动编辑；文件创建/源码写入不等于场景撤销
- 路径穿越、符号链接、工程元数据和桥接插件自身文件被拒绝
- 代码、工具脚本、编辑器插件以及运行游戏都有执行权限；只连接你信任且允许 AI 操作的工程

[能力与验证范围](EDITOR_CAPABILITIES.md) 区分哪些功能已实现、实际测过、尚不支持。这里没有承诺 Godot 所有编辑器窗口和任意操作都已自动化。
