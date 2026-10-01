# Godot C# Skills Lab

A small, runnable companion to `../native_lab`. It uses native Godot scenes, Resources, typed signals, Containers, a C# Autoload, and a runtime-generated `TileMapLayer`. No paid service, external art, test framework, or game package is required.

## Requirements

- Godot **4.6.3 .NET**, matching `Godot.NET.Sdk/4.6.3` in the project
- A 64-bit .NET **8 SDK** or compatible newer SDK capable of targeting `net8.0`
- NuGet access for the initial build, or the official packages bundled under the .NET editor's `GodotSharp/Tools/nupkgs` directory configured as a local NuGet source

The standard Godot binary cannot run these C# scripts. Keep both engine variants if using the GDScript lab too. This fixture was compiled with SDK 8.0.425 and executed using Godot 4.6.3 .NET on Linux x64; other platforms require their own runtime/export checks.

## Build and run

From this directory, with `dotnet` available and `GODOT_DOTNET` pointing to the .NET engine executable:

```bash
dotnet build CSharpLab.csproj
"$GODOT_DOTNET" --headless --path . --import
"$GODOT_DOTNET" --path .
```

Click the button or use Enter/Space to publish a typed signal. Resize the window to inspect integer viewport scaling. The visible counter is scene-local; `Session.EmittedCount` persists across replacement scenes and has an explicit reset operation.

## Run integration checks

```bash
dotnet build CSharpLab.csproj
"$GODOT_DOTNET" --headless --path . --import
"$GODOT_DOTNET" --headless --path . res://tests/TestRunner.tscn
```

The runner exits with code 0 on success and prints a single machine-readable `GODOT_CSHARP_TESTS=` JSON result. Its 36 assertions cover:

- Custom typed events; captured-lambda cleanup on exit/free; reconnecting after tree re-entry; emitter-first destruction
- Explicit `Connect` duplicate guards and named-receiver automatic cleanup
- PackedScene ownership versus runtime-only children
- Cached Resource identity; shallow/deep duplication; nested collection isolation; alias preservation; external-resource deep-copy policy
- Local To Scene isolation across two instances
- Autoload startup/persistence, Button signals, actual `ui_accept` event routing, initial focus, and displayed text
- TileMapLayer population and coordinate conversion; viewport/integer settings

Godot's native connection list includes the bridge for a custom C# event even without managed subscribers. The tests preserve this baseline and verify callback behavior instead of treating a nonempty native list as evidence of a subscription leak.

A headless pass verifies behavior and configuration, not rendering quality. Visually check the main scene separately. Generated `.godot` caches and build outputs are disposable and should not be committed.

For a restricted environment, point `DOTNET_CLI_HOME`, `NUGET_PACKAGES`, `NUGET_HTTP_CACHE_PATH`, and the three `XDG_*_HOME` directories at writable scratch locations; keep machine-specific paths out of this project.

## Official references

Checked 2026-09-30: [Godot C# setup](https://docs.godotengine.org/en/4.6/tutorials/scripting/c_sharp/c_sharp_basics.html), [C# signal lifetimes](https://docs.godotengine.org/en/4.6/tutorials/scripting/c_sharp/c_sharp_signals.html), [Resource duplication](https://docs.godotengine.org/en/4.6/classes/class_resource.html), [Godot 4.6.3 downloads](https://godotengine.org/download/archive/4.6.3-stable/), [Microsoft SDK installation](https://learn.microsoft.com/en-us/dotnet/core/install/linux-scripted-manual).
