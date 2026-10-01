# AI Editor Bridge 0.2

This is a real Godot 4.6 `EditorPlugin`, installed at
`res://addons/ai_editor_bridge/`. Enable it only in a project you already trust.
It is written in GDScript and works in the standard and .NET editors; C# scripts
remain C# and require a matching installed .NET SDK and a successful project build
before attachment. There is no socket, network listener, shell, credential, eval,
or general-purpose method-call endpoint.

## Local protocol

The explicitly selected editor polls `res://.godot/ai_bridge/requests/` every
50 ms, executes one request at a time on the editor thread, and writes responses
in `responses/`. The heartbeat `status.json` is updated every 500 ms. Only one
editor process should have the same project open with this bridge enabled.

Request filenames are `<32 lowercase hexadecimal characters>.json` and contain:

```json
{"id":"0123456789abcdef0123456789abcdef","session_id":"FROM_STATUS","project_root":"FROM_STATUS","operation":"status","arguments":{}}
```

The `session_id` is regenerated on every enable/restart. `project_root` must match
status exactly. Responses include `id`, `session_id`, `ok`, `result`, and on failure
`error: {code, message, details?}`. Producers must publish requests atomically.
The bridge writes heartbeat and responses by temporary-file rename. The bridge
checks all IPC ancestors for symbolic links/junctions. Requests are limited to
2 MiB, source text to 1 MiB, diagnostics to the latest 100 operations, hierarchy
reads to 2,048 nodes and depth 32. Direct IPC gets the same strict argument schema
validation as the MCP transport. The latest 4,096 completed IDs are retained in a
session replay cache even after response cleanup. Never reuse request IDs.

`argument_schemas.gd` contains the operation argument schemas, generated from
`docs/EDITOR_API.json` in the plugin distribution. All 26 operations are exposed
in `status.capabilities`. No request has ambient access to other projects.

## Scene and node guards

Every scene mutation (including open/create/save/undo/redo/play) requires exact
`expected_scene_path` and `expected_revision` from a fresh status or inspection.
The revision combines session, root instance ID, real editor UndoRedo history ID
and version, plus a synchronous history/version event sequence. Manual editor
edits and undo-then-different-edit branches invalidate old guards.

Node-target changes also require `expected_node_id`. Create uses
`expected_parent_id`; reparent additionally uses `expected_new_parent_id`; signal
changes additionally use `expected_target_id`. Obtain string IDs from hierarchy
or node inspection; never invent them. Node paths are relative to the edited
root, with `.` denoting that root. All mutation results include the new `scene`
snapshot; most include the resulting `node`.

The bridge uses `EditorUndoRedoManager` transactions for every in-memory node,
property, resource assignment, script attachment, or signal change. Node ownership
is restored in undo/redo. Undo and redo apply to the current scene's editor history,
including manual edits, not just bridge operations. File creation/source writes,
scene save, tab switching and play are not undoable file transactions.

`scene_create` writes a new `.tscn` with a Node/Node2D/Node3D/Control root and opens
it. `scene_open` only opens/activates a tab; it never closes or reloads another tab,
so unsaved content in previous tabs is retained. Existing files are never replaced
by creation. Unnamed, binary and inherited scenes are conservatively protected for
node editing. Contents inside instanced scenes are protected; open the source scene.
The `dirty` status is advisory rather than a complete native editor dirty flag.

`scene_save` saves the entire current scene, including manual edits already present
when its guard was captured. It requires `expected_disk_sha256`, and checks both
that explicit hash and the bridge's remembered disk baseline. External disk changes
cause `disk_conflict`; the bridge never reloads/discards them automatically.

## Values and resources

Only built-in core (`ClassDB.API_CORE`) property metadata is inspected. GDExtension
and editor-extension classes are unsupported and rejected before reflected property
getters/setters. Names declared by attached or inherited GDScript/C# scripts are
also excluded, including exported names that overlap built-in properties. These
checks read declaration metadata only, never custom values. Text resource declarations are checked against the curated core
types before loading, including every subresource; inline Object/Resource constructors
are refused; custom script getters/setters,
Object/Callable values, `script`, `owner`, scene path and internal fields cannot be
set through `property_set`. Scalars are native JSON. Typed codecs are
`{type:"Vector2",x,y}`, `Vector3`, signed-32-bit `Vector2i`/`Vector3i`,
`{type:"Color",r,g,b,a}` and `{type:"NodePath",value}`. A nonempty property NodePath
resolves relative to its target node and must point inside the edited scene. Empty
NodePath clears a reference. Resource creation has no node context and rejects
nonempty NodePaths. Node-target argument paths do not permit `..`.

`resource_create` writes only new `.tres` files for the native types listed in
`status.resource_types` (materials, meshes, physics shapes, Environment, StyleBoxFlat).
`resource_assign` only assigns compatible native Resource properties. Supported
inputs are `.tres`, `.png`, `.jpg`, `.jpeg`, `.webp`. A `.tres` must have no scripts
or external dependencies and must resolve to a curated native type. Read operations
never load arbitrary resources. Property inspection returns a list of entries with
name, type, current encoded value, and writability flags.

## Scripts and signals

`script_read` reads disk text and SHA-256 without loading/evaluating it.
`script_write` accepts `.gd` or `.cs` text. New files are the default; an existing
file requires `overwrite: true` and a matching `expected_sha256`. It refuses scripts
open in ScriptEditor to avoid overwriting unseen unsaved editor buffers. Save and
close that script tab before writing. Source writes refresh the editor filesystem,
but do not build C#, attach scripts, or imply compile success. They are not undoable.

Tool annotations are conservatively blocked (`@tool`, `Tool`/`ToolAttribute` tokens)
for source writing and attachment. `script_attach` loads an existing same-language
Script resource, checks tool/base-type compatibility, and attaches via undo/redo.
Replacing a different existing script is refused because exported values could be
lost. Detach it explicitly in the editor if replacement is intended.

Persistent signal callbacks must be existing script-defined methods on a non-tool
target script. Native callbacks such as `hide`, `set`, `free`, `queue_free`, or
arbitrary Callable expressions are unsupported: they could execute inside the
editor and bypass scene mutation protections. Ordinary project code executes only
when the project is intentionally run, apart from code the trusted project/editor
already executes itself. This bridge is not a sandbox for a hostile project.

## Structural reference protection

Rename, reparent and delete preflight native NodePath references. Affected references
cause `reference_conflict` with locations; the bridge does not silently leave them
stale. Scenes containing AnimationMixer/AnimationPlayer or custom exported object/
NodePath references are conservatively refused for those structural operations.
Animation tracks, custom script getters, exported collections, and script strings
are not automatically refactored. Edit such references with Godot's own editor.

## Play and diagnostics

Play uses real `EditorInterface.play_current_scene`, `play_main_scene` or
`play_custom_scene`; `stop` uses its stop API. Playing executes project code and
may launch a separate game process. The bridge requires tracked open scenes to be
saved and disk-unchanged before play to prevent implicit overwrite. Headless test
projects can set `editor/run/main_run_args="--headless"` for child game processes.

`diagnostics` is a bounded bridge operation/error log. It does not claim to capture
all editor, compiler, import, debugger, or running-game console errors. Consult
Godot's normal Output/Debugger panels or the separate validation commands for those.

## API references

- https://docs.godotengine.org/en/4.6/classes/class_editorinterface.html
- https://docs.godotengine.org/en/4.6/classes/class_editorundoredomanager.html
- https://docs.godotengine.org/en/4.6/classes/class_undoredo.html
- https://docs.godotengine.org/en/4.6/classes/class_diraccess.html
