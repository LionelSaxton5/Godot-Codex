# Godot-codex 0.2.1


**Actual local editor control for AI tools**, with a Godot EditorPlugin, a dependency-free stdio MCP server, and seven Godot-native Codex skills. Supports the tested 2D/3D editor baseline and both GDScript/C# workflows.

[中文连接指南](docs/EDITOR_SETUP.zh-CN.md) · [Capabilities and limits](docs/EDITOR_CAPABILITIES.md) · [Tool schemas](docs/EDITOR_API.json) · [Verification report](docs/VERIFICATION.md)

This independent project is not an official Godot product. It does not promise every Godot editor function.

## What changed from v0.1

v0.1 provided skills, filesystem inspection, validation and language fixtures. v0.2 adds a real editor bridge: MCP calls reach `EditorInterface` and `EditorUndoRedoManager` in the open project. Nodes are added to the live editor scene, editable properties change, persistent connections are authored, and guarded saves write the scene.


## Editor tools

26 named tools cover:

- Status, hierarchy, native property and saved-connection inspection
- New/open/save scenes
- Create/delete/duplicate/reparent/rename nodes, guarded by scene revision and node identity
- Typed native properties and explicit Resource assignment
- Persistent safe script signal callbacks
- GDScript/C# source read/write and script attachment
- New native mesh/material/shape Resources
- Scene UndoRedo and editor-managed run/stop
- Bounded bridge-operation diagnostics

Scene graph changes use actual editor history. New files/source writes are distinct operations and are not erased by scene undo. Read [the capability contract](docs/EDITOR_CAPABILITIES.md) for unsupported operations and safety restrictions.

## Requirements and architecture

- Python 3.10+, standard library only
- Godot 4.6.3 editor; .NET variant + a compatible .NET SDK for C# projects
- An AI client supporting stdio MCP, or the included command-line client
- AI/MCP and Godot must access the **same explicit local project filesystem**

The EditorPlugin must be enabled and **Godot must remain running**. IPC is atomic JSON in the project's generated `.godot/ai_bridge/` directory. There is no socket/HTTP listener, cloud account, API key or paid backend. This trusted same-OS-user design is not a sandbox against malicious project code or other same-user processes.

## Setup

1. Install the Codex package using the opt-in personal installer from the extracted root:

```sh
python3 scripts/install_local.py --home "$HOME"
python3 scripts/install_local.py --home "$HOME" --apply
```

The first command is a dry run. The second prints the exact `codex plugin add` command for your personal marketplace; run it yourself to activate. Existing plugin paths/entries are refused rather than overwritten. Use Codex's normal update/reinstall workflow if v0.1 is already installed.

2. With the target project closed in Godot, preview then install/enable its EditorPlugin:

```sh
python3 scripts/setup_editor_bridge.py /path/to/project --enable
python3 scripts/setup_editor_bridge.py /path/to/project --apply --enable
```

An exact `project.godot.before-ai-bridge` backup is kept before configuration changes. Other enabled plugins are preserved. Omitting `--enable` copies only; enable it manually in Project Settings → Plugins.

3. Configure `GODOT_PROJECT_PATH` for the client's bundled MCP process, then reopen Godot and start a fresh Codex thread. The bundled `.mcp.json` uses a plugin-relative cwd; it does not depend on unimplemented plugin-root string expansion. A standalone explicit MCP registration command is also printed by setup for clients not using the bundled connection. Use only one connection route.

4. Call `godot_status`, verify the project and scene, and then use the live tools. A missing/stale editor produces an actionable error rather than choosing another project.

See the [Chinese setup guide](docs/EDITOR_SETUP.zh-CN.md) for desktop environment-variable caveats and precise steps.

## Direct client and tests

```sh
# Direct local status; the editor addon must already be enabled and running.
python3 scripts/editor_bridge_client.py --project /path/to/project status

# Stdio MCP server (normally started by the AI client).
python3 scripts/godot_mcp_server.py --project /path/to/project

# All offline Python regressions.
python3 -m unittest discover -s tests -v

# Real editor + MCP integration. Creates a NEW disposable directory only.
python3 tests/run_editor_integration.py --godot /path/to/godot \
  --language gdscript --work-dir /tmp/godot-editor-gd-test

python3 tests/run_editor_integration.py --godot /path/to/Godot.NET \
  --dotnet /path/to/dotnet --language csharp --work-dir /tmp/godot-editor-cs-test
```

C# initial restore may need NuGet access or official packages from the Godot .NET installation's `GodotSharp/Tools/nupkgs` directory. The archive does not redistribute engine or SDK binaries.

## Existing native development skills and helpers

The original six skills remain: project inspection, scenes/Resources/Autoload, signals, Control UI, pixel-art/TileMapLayer and debugging/validation. `godot-editor-control` routes actual editor work to the new tools while preserving the project's language.

`godot_inspect.py` remains a static read-only alternative. `godot_validate.py` performs explicit trusted project import/parse/build/runtime checks; it is not a sandbox. See the included `examples/native_lab` and `examples/csharp_lab` READMEs for their standalone checks.

## Package

`.codex-plugin/plugin.json` and `.mcp.json` define the Codex package. `editor_addon/ai_editor_bridge/` is copied into each opted-in Godot project. `scripts/` contains the stdio server/client, setup, inspection/validation, local installer and package builder. `tests/` includes transport/safety and real editor integration. `docs/` documents exact scope and evidence.

Build a release ZIP with `python3 scripts/build_package.py --output /path/to/godot-codex-0.2.1-public.zip`. Existing ZIP/checksum outputs are refused unless `--force` is explicitly passed; symlink outputs are always rejected.

MIT licensed. Official Godot/Microsoft tools retain their own licenses. No account install, publication or remote access is performed by this source package.

[Live editor screenshot / 实际编辑器截图](assets/live-editor-3d.png): scene objects and materials were created through the local MCP bridge, then verified in the open Godot editor.
