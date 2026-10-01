# Engine commands and build boundaries

These are Godot 4.6 commands, checked 2026-09-30 against [official CLI documentation](https://docs.godotengine.org/en/4.6/tutorials/editor/command_line_tutorial.html). Use a trusted engine executable; quote paths and pass arguments as a list from code, never concatenate untrusted shell strings.

```sh
godot --version
godot --headless --path "/project" --import
godot --headless --path "/project" --script res://scripts/player.gd --check-only
godot --headless --path "/project" --script res://tests/test_native.gd
godot --headless --path "/project" --quit-after 60
```

`--check-only` accompanies `--script`: it parses that script, not every project script automatically. The wrapper iterates the static `.gd` inventory. `--import` starts editor import work and quits after import, unlike assuming `--editor --quit` waits for everything. A test runner executed with `--script` must extend SceneTree or MainLoop.

## C#

The included wrapper detects C#, rejects a standard engine, selects the single `.csproj` (or requires `--csproj`), runs `dotnet build`, then imports and executes requested tests with the .NET engine. Use `--test-scene` for the bundled C# test scene. The .NET fixture was separately compiled and run; a standard-engine pass alone never establishes C# correctness.

For a real C# project, first verify a Godot .NET build and compatible .NET SDK. Inspect `.csproj`, `global.json`, target framework and existing NuGet configuration. Use the project's existing build process, for example `dotnet build "Game.csproj"`, then run the matching .NET engine against its scenes. Build/restore can access configured package sources and execute project build targets; treat the project as executable code and do not restore unknown dependencies without authorization. `--build-solutions` is an engine option for the same class of task, not a substitute for verifying SDK availability.

C# native signal events, source-generated `SignalName`/`PropertyName` and exported fields need a successful build. Do not insert guessed generated members or edit generated output. Preserve engine/SDK versions rather than upgrading during a narrow fix.

Godot 4.6 documentation says C# cannot export to Web; Android/iOS have additional limitations. Check current docs for the actual target/version instead of promising all Godot platforms. [C# basics](https://docs.godotengine.org/en/4.6/tutorials/scripting/c_sharp/c_sharp_basics.html)

Exports need installed export templates and correct named presets. A local smoke test does not verify packaging, signing, platform permissions, mobile deployment or store acceptance; no export is part of the bundled v0.1 verification.
