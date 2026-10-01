---
name: godot-project-inspect
description: "Inspect a Godot 4 project, locate declared scenes, nodes, resources, scripts and saved signal connections, and establish version/language/Autoload context before changes. Use for project orientation and concrete asset lookup; does not execute the project or inspect a live editor."
---

# Inspect a Godot project

Use the actual `project.godot` root. Do not choose a different engine, project, scripting language, renderer, or platform silently. In a monorepo, identify which Godot project the request concerns.

## Start without executing project code

Run the bundled static helper with Python 3.10+. `<plugin-root>` is two directories above this skill directory:

```sh
python3 "<plugin-root>/scripts/godot_inspect.py" "/path/to/project" --json
```

It reports declared scene nodes, saved `[connection]` records, external resource paths, GDScript/C# files, `.csproj` paths, selected settings, and Autoloads. It skips generated directories and symlinks, caps text-file size, and reports unresolved UIDs. It does not evaluate configuration expressions or load engine resources. Read the result's errors, warnings, and limitations before drawing conclusions.

Use exact inventory paths to inspect relevant `.tscn`, `.tres`, `.gd`, and `.cs` files. Node names in a text scene are declarations, not a complete runtime hierarchy: inherited scenes, scene instances and runtime construction need deeper inspection. Binary `.scn`/`.res` are not parsed. A `uid://` reference is not a missing file merely because a static tool cannot resolve it. Resolve through the matching trusted Godot editor when needed; do not replace UIDs by guessing.

## Build a compact working map

Capture only information useful to this task:

- Requested scene and script, main scene, reusable instanced scenes, and external Resources
- Scene owner versus runtime parent, saved connections versus code subscriptions
- Autoload names and why their lifetime matters
- Project feature/version hints, selected Godot executable version, language and `.csproj` target SDK
- Renderer and target platform when they affect the change

Treat `config/features` as hints, not proof of the engine currently running. A standard Godot binary does not compile C#. When C# exists, preserve `partial` classes, exported properties, generated signal names and the project SDK; do not “fix” the project by converting it to GDScript.

For new project requests, use the chosen Godot version/renderer/language and generate in a new requested directory. Use the Godot .NET editor to create C# project metadata matching that engine; do not invent SDK versions from memory. The bundled `examples/native_lab` is a test/demo fixture, not a production starter to overwrite an existing project with.

## Report

Return the relevant `res://` paths and declared node paths, source line references where useful, and verified constraints. Distinguish a static finding from a runtime observation. If the user requested lookup only, do not modify scenes/settings or run imports.

Official references: [Project organization](https://docs.godotengine.org/en/4.6/tutorials/best_practices/project_organization.html), [Scene file format](https://docs.godotengine.org/en/4.6/contributing/development/file_formats/tscn.html), [ResourceUID](https://docs.godotengine.org/en/4.6/classes/class_resourceuid.html), [C# prerequisites](https://docs.godotengine.org/en/4.6/tutorials/scripting/c_sharp/c_sharp_basics.html). Checked 2026-09-30.
