---
name: godot-scenes-resources
description: "Create, refactor, or diagnose Godot scenes, PackedScene spawning, Resource sharing, and Autoload state. Use for missing saved children, cross-instance data changes, scene dependencies, and lifecycle bugs; not for UI layout or physics tuning."
---

# Godot scenes and resources

Work with Godot's scene composition and Resource identity directly. Preserve the project's language and existing scene boundaries. Examples target Godot 4.6 and C#; verify the installed version before applying version-sensitive APIs.

## Inspect the actual boundary

Read `project.godot`, the relevant `.tscn`/`.tres`, and their scripts. Identify the instance root, parent, serialized owner, exported dependencies, and mutable data. Check inherited scenes and external resources before changing the source: editing a base scene or shared resource can affect every consumer.

Choose the smallest suitable mechanism:

- A reusable actor, level chunk, or effect: a scene with an appropriate root and a narrow public API
- Designer-authored configuration: an exported Resource, normally shared and treated as immutable during play
- Per-run or per-actor state: instance fields, a deliberately unique Resource, or an explicitly constructed runtime model
- State needed across scene changes: an existing persistent root or a narrowly scoped Autoload

Do not introduce global services just to avoid passing an actor or dependency. Prefer explicit exported references or caller configuration; reserve scene-unique `%Name` lookups for their owning scene. See [scene boundaries and C# patterns](references/scene-patterns.md).

## Preserve the important distinctions

- `AddChild` establishes the hierarchy and child lifetime. `Owner` controls scene serialization; it is not the runtime parent or a memory-management owner. An owner must be an ancestor. For editor-generated children, add them first, then set the intended scene owner. Ordinary runtime spawns do not require ownership assignment.
- `PackedScene` is a stored scene recipe; `Instantiate` creates a node tree. Configure values needed during initialization before adding it to an active tree. Child readiness precedes parent readiness; `_Ready` is not automatically repeated after tree re-entry.
- A Resource reference may be shared even when stored inside a scene. Loading the same path is not a uniqueness operation. Choose the scope of mutable state before duplicating anything.
- Autoloads enter before the main scene and persist between scene changes. Respect their configured order; do not free an Autoload to reset a run. Reset its data explicitly and remove stale scene references.

For cloning semantics, nested collections, custom Resource constructors, and per-scene locality, read [Resource identity](references/resource-identity.md). Do not assume older Godot duplication limitations still apply to 4.6.

## Verify the behavior that motivated the change

1. Instantiate two copies. Confirm intended shared assets stay shared and modifying one actor's runtime data does not change the other.
2. Reload any edited scene from disk. Check newly saved children and references rather than trusting the editor's current tree.
3. Run the scene independently where supported, then through the normal entry scene. Exercise a scene change and tree re-entry if relevant.
4. Check import/parse errors and missing paths. For C#, require a Godot .NET build and compatible SDK for compile/runtime evidence; the standard editor cannot validate C# execution.

Report affected files, the chosen ownership/sharing contract, and exactly which checks ran. A source review is not a successful runtime test.

Official Godot 4.6 references, checked 2026-09-30: [Node](https://docs.godotengine.org/en/4.6/classes/class_node.html), [PackedScene](https://docs.godotengine.org/en/4.6/classes/class_packedscene.html), [Resources](https://docs.godotengine.org/en/4.6/tutorials/scripting/resources.html), [Autoload](https://docs.godotengine.org/en/4.6/tutorials/scripting/singletons_autoload.html).
