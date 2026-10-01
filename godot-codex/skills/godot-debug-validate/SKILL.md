---
name: godot-debug-validate
description: "Reproduce and validate Godot 4 script, import, scene startup or runtime failures using bounded engine checks and useful diagnostics. Use for debugging a Godot project or validating a change; distinguishes static inspection, GDScript parsing, runtime smoke tests and C# builds."
---

# Debug and validate Godot

Start with the smallest failing behavior and the user's actual engine/language. Read stack trace, first meaningful error, affected scene, and recent diff. Imports and engine execution are not read-only: editor plugins, `@tool`, GDExtensions, and runtime code may execute. Only run projects trusted and authorized for execution. The helper's trust flag does not grant permission or provide a sandbox.

## Validation ladder

1. Static inventory, no engine launch:
   `python3 "<plugin-root>/scripts/godot_validate.py" "/project"`
2. Trusted project: import and parse every discovered `.gd` (C# additionally requires the .NET toolchain and builds its selected `.csproj`):
   `python3 "<plugin-root>/scripts/godot_validate.py" "/project" --allow-project-code`
3. Explicit runtime check: add `--test-script res://tests/test_native.gd` for a SceneTree/MainLoop test already present, or `--test-scene res://tests/TestRunner.tscn` for a C# or mixed-language test scene; add `--smoke-frames 60` to launch the main scene briefly

`<plugin-root>` is two directories above this skill directory. Use `--godot /exact/engine/path`, `--dotnet /exact/dotnet/path` and `--timeout 60` as appropriate. With C#, select `--csproj res://Game.csproj` if multiple projects exist. Build/restore uses the project root as its working directory and may access configured package sources. Each process has a timeout; the timeout is not a total project budget. Inspect JSON `ok`, checks, logs, warnings and blockers. The tool fails on nonzero exits, timeout, truncated logs and detected engine error lines even if Godot exits zero.

The helper uses temporary Godot user/config/cache directories where supported and may write `.godot/` and import metadata in the project. It neither copies nor sandboxes the project, and cannot stop arbitrary script filesystem or network actions. On Windows, child-process timeout cleanup is best effort; POSIX terminates the spawned process group. Do not run untrusted downloaded projects with this flag.

## Pick checks that prove the fix

- Parser errors: import first when generated classes/resources are needed, then parse the exact script
- Missing nodes: validate the instanced scene and its ready order, ownership and node path
- Signals: count emissions/callbacks, reload the scene, test receiver and emitter lifetimes
- Resources: assert identity and changed values, not just the visible Inspector value
- UI: test focus, click-through, resize and pause behavior; headless startup cannot prove layout quality
- Pixel art/TileMaps: inspect pixels at multiple window sizes and verify collisions/terrain transitions separately

Read [engine commands and C# boundaries](references/commands.md) for manual checks and build requirements. Make the smallest supported fix, rerun the failing check, then the adjacent regression tests. A successful import is not a gameplay pass. A fixed frame smoke run is not a performance benchmark.

When a run stalls, use its timeout/logs and diagnose the specific wait. Do not delete `.godot`, rewrite all UIDs, disable plugins, or change renderer merely to hide the failure. Cache regeneration can be appropriate after diagnosis and within the user's authorized scope, with generated versus source files clearly separated.

Report engine version, language, exact checks, pass/fail and remaining untested behavior. Preserve failure evidence. Do not claim C# support from a standard-engine test.
