# v0.2 editor capability contract

Target: Godot 4.6.3. Original v0.2.0 verification: Linux x64. Windows x64 v0.2.1 acceptance: [Windows report](WINDOWS_VERIFICATION.zh-CN.md). Both standard and .NET editors use the same project-local EditorPlugin. C# project code still requires the .NET editor and a successfully built assembly.

The exact machine-readable tool schemas are in [EDITOR_API.json](EDITOR_API.json). Operations are 26 named MCP tools; they do not expose generic eval, arbitrary object calls, shell execution, a network listener, or unrestricted filesystem access.

## Implemented baseline

| Area | Operations | Contract |
|---|---|---|
| Connection | status | Explicit project, session identity, heartbeat, engine version, current scene/revision, type capability lists |
| Inspection | hierarchy, node_inspect, diagnostics | Live scene nodes/identities; native properties; persistent connections; bounded bridge diagnostics |
| Scene files | scene_create, scene_open, scene_save | New text scenes; preserve other tabs; save current scene with revision and disk hash checks |
| Scene graph | node_create, node_delete, node_duplicate, node_reparent, node_rename | Curated native 2D/3D/UI classes; exact node identity; current-scene UndoRedo; protected roots/instances |
| Properties | property_set | Native editable typed values; no arbitrary script/custom setters or object injection |
| Signals | signal_connect, signal_disconnect | Persistent direct connections with explicit identities and safe callback restrictions |
| Scripts | script_read, script_write, script_attach | Bounded .gd/.cs text; hashed existing-file writes; language preserved; tool scripts rejected |
| Resources | resource_create, resource_assign | Curated native materials, meshes and shapes; new .tres files; compatible node resource slots |
| History | editor_undo, editor_redo | Current scene's actual editor history, which can include the user's manual actions |
| Execution | play_current, play_main, play_custom, stop | Editor-managed play/stop; trusted code execution; save/dirty conflicts checked |

## Explicit limitations

- This is a coherent editor-control foundation, not every Godot function or menu. Animation timeline editing, shader-graph authoring, import dialogs, export/signing, project-wide settings, asset-store installation, debugger breakpoints, profiler automation and custom editor extensions are not automated
- The node/resource allowlists and runtime property metadata define what is supported. A node type being creatable does not mean all of that subsystem's specialist authoring workflows are implemented
- Signal destinations must be script-defined methods on non-tool project scripts. Native Object/Node callbacks such as free, queue_free, hide and show are not accepted directly, because persistent connections can also fire during editor changes. There is no arbitrary-method escape hatch
- Source writes do not build C#, attach a script, run it, or prove compilation. C# build remains an explicit separate step. Existing source files open in ScriptEditor cannot be overwritten through this bridge; save/close the buffer first. Replacing an already attached different script is refused to avoid silently losing exported values; attach-to-empty or the same script is supported
- Bridge diagnostics record bridge operations/errors. They are not a complete feed of the editor Output, game debugger, compiler, shader errors or profiler. Use normal Godot diagnostics and the included validation helper for those
- No remote editor, cloud-to-laptop tunnel, multi-user authorization, or protection against malicious same-user local processes. Run AI and Godot where the same explicit project filesystem is available. OS project-directory permissions govern access to IPC content; use a private project directory. This bridge does not configure authentication or change OS permission settings
- Rename/reparent/delete do not automatically refactor references. They refuse edits affecting native NodePath references; they also conservatively refuse structural edits when any AnimationMixer or custom exported NodePath/object property exists anywhere in the scene, including unrelated custom Resource fields. Arbitrary script-string, animation-track and external project references are not automatically rewritten
- New scene/resource files and script source writes are filesystem operations. Scene UndoRedo does not remove those files
- Editor opening/importing and playing a trusted project may execute existing project code or plugins. The bridge is not an untrusted-project sandbox
- Windows x64 is separately verified for v0.2.1 on Godot 4.6.3. macOS and other engine versions remain unverified; Linux evidence here refers to the original v0.2.0

## Verification evidence

The release verification report records actual results after the final integration runs. Its required checks include a real Godot editor (not an in-memory fake), standard MCP initialization/list/call, all operation routes, 2D and 3D scene persistence, both languages, stale identity/session and malformed-request behavior, UndoRedo, source/disk conflicts, project-path protection, plus extracted-package tests.

Windows 0.2.1 completed all 26 operations through the real Codex app-server in both languages. See [the public verification summary](VERIFICATION.md) for scope and limitations.

## Official API references

- [EditorPlugin](https://docs.godotengine.org/en/4.6/classes/class_editorplugin.html)
- [EditorInterface](https://docs.godotengine.org/en/4.6/classes/class_editorinterface.html)
- [EditorUndoRedoManager](https://docs.godotengine.org/en/4.6/classes/class_editorundoredomanager.html)
- [UndoRedo](https://docs.godotengine.org/en/4.6/classes/class_undoredo.html)
- [Godot C#](https://docs.godotengine.org/en/4.6/tutorials/scripting/c_sharp/c_sharp_basics.html)
- [MCP stdio transport](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)
- [Codex plugin MCP configuration source](https://github.com/openai/codex/blob/main/codex-rs/codex-mcp/src/plugin_config.rs)

Checked 2026-09-30. Protocol dialect/version is pinned in the API schema rather than assumed from a moving “latest” page.
