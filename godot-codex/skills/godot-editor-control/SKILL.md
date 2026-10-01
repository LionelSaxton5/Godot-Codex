---
name: godot-editor-control
description: "Control a running Godot editor through the bundled local MCP bridge: inspect live scenes, create/edit 2D or 3D nodes, manage typed properties, scene files, signals, scripts and Resources, use editor undo/redo and run/stop. Use when the user wants actual Godot editor changes; requires the project-local addon enabled and the matching project configured."
---

# Control the real Godot editor

Use the `godot_*` MCP tools supplied by this plugin for supported editor operations. These edit the running editor state; writing a `.tscn` externally is not equivalent. Do not invent operations when the tools or current capability listing do not support them.

## Connect to the intended project

Call the status tool first. Verify project path, engine version, current scene, session, and reported capabilities against the user's request. If the editor is unavailable, use the installed plugin's `docs/EDITOR_SETUP.zh-CN.md` to help enable the addon and configure the explicit project path. Keep the editor running. Never silently target another open project.

The bridge uses local files under the selected project's generated directory and a stdio MCP process. It has no network listener, account credentials, or public endpoint. This is a trusted same-user integration, not a sandbox against malicious code already running in the project or as the same OS user. A Godot project can execute tool scripts/plugins during editor loading; play and script changes can execute project code.

## Observe, mutate, verify

1. Read status and the relevant live hierarchy/node inspection
2. Use the exact scene path, current revision token and node instance ID required by the operation. Never manufacture guard values or reuse them after a change
3. Perform the smallest requested mutation, with typed values from the tool schema
4. Inspect the changed node/tree and its new revision. Save only when requested or clearly part of producing the scene; a save writes the entire current scene, including visible manual edits
5. Reopen or run a focused test when the result needs persistence/runtime proof

On a stale scene/node/session error, inspect again and reconcile the user's latest editor state before retrying. A timeout after submission has an uncertain outcome: inspect state and diagnostics, do not repeat a create/delete/rename/save blindly.

Node and Resource types/properties are intentionally constrained. Native scalar/vector/color properties are separate from resource assignment and script attachment. Do not bypass a rejected operation by calling arbitrary methods, evaluating code, modifying bridge internals, or weakening its guards. Ask for a different supported route when needed.

## Scenes and undo

Scene graph mutations use Godot's editor undo history. Undo/redo operate on the current scene history, which can contain the user's own edits; inspect/report the action being changed and follow their intent. New files and source-file writes are not equivalent to undoable scene changes. Never assume editor undo will erase a created file.

Preserve unsaved edits and instanced-scene ownership boundaries. A root cannot be deleted through the bridge. Do not silently make an instance's internal nodes local or rewrite ownership just to make a change succeed. Save conflicts caused by external file changes need reconciliation, not force overwrite.

## GDScript and C#

Preserve the project's language. Source read/write tools operate on `.gd`/`.cs` files with content-hash preconditions for existing files. Writing code does not mean it compiled, attached, ran, or passed tests. Tool scripts are outside the normal source-write/attach contract unless the capability explicitly says otherwise.

C# requires the Godot .NET editor and a matching SDK/assembly. Use the existing validation/build workflow to compile changed C# before treating attachment or signals as usable. The editor bridge itself is GDScript so it works with both editor variants; this is not a claim that the standard editor runs C#.

For pixel or UI changes, inspect rendered output as well as live properties. For 3D, a MeshInstance3D needs an assigned mesh and a useful camera/light arrangement before a visible scene is demonstrated.

## Completion

Report which scene and nodes changed, what was saved, and checks actually run. Use `docs/EDITOR_CAPABILITIES.md` for the implemented/tested/unsupported boundaries. Do not promise complete coverage of every Godot editor feature, full debugger capture, animation/import/export tooling or platform builds unless independently demonstrated.
