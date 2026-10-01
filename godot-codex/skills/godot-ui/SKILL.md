---
name: godot-ui
description: "Build or repair Godot Control-based menus, HUDs, and pause screens using Containers, anchors, themes, focus, and GUI input. Use for resize, overlap, click-through, or keyboard/controller-navigation bugs; not world-space Node2D movement or third-party web UI."
---

# Godot UI

Use Godot's `Control` layout, focus, and event routing. Preserve the project's scene and C# conventions. Examples target Godot 4.6; use the installed engine's reference for changed APIs.

## Read the layout and input owners

Inspect the target `.tscn`, scripts, inherited scene, Theme, viewport/stretch settings, and input actions. Identify the UI root, each direct Container parent, any camera-dependent placement, and the Control that receives a failed click or navigation event. Diagnose with the running Remote tree and actual control rectangles where available.

Before changing a layout, establish which sizes must remain fixed, which should expand, the minimum supported window, and the intended keyboard/controller path. Infer existing conventions; ask only when a missing choice materially changes the design.

## Build with the right authority

- Anchor a screen root to its parent Control/viewport; use `CanvasLayer` when a HUD must remain independent of the world camera
- Let Containers arrange their direct Control children. Change container structure, minimum sizes, size flags, and theme spacing instead of fighting computed offsets
- Use anchors/offsets for Controls outside Containers; anchoring an edge and clearing its offsets are separate choices
- Use reusable scenes and Theme resources for repeated UI. Avoid per-node overrides unless intentional; check whether a Theme or StyleBox is shared before mutating it
- Keep data/model state outside visual widgets; expose a small update API or bind signals with an explicit lifetime

Read [layout and interaction recipes](references/layout-input.md) when implementing a menu or debugging resize, focus, or input problems.

## Input is part of the UI

Use Buttons and their signals for ordinary activation. Handle custom widget input in `_GuiInput` and consume handled events with `AcceptEvent`. Gameplay event handlers usually belong in `_UnhandledInput`, after GUI routing. `_Input` runs earlier; a visual overlay cannot undo actions already performed there. Polling `Input` also requires a gameplay-state gate.

Give every interactive screen an initial focus target and deliberate directional/Tab neighbors when automatic navigation is ambiguous. Keep built-in `ui_*` actions for UI; use separate gameplay actions. Restore or choose valid focus after closing a popup, hiding a tab, or deleting a row.

A modal screen needs mouse coverage, keyboard/controller focus, and gameplay input suppression. `MouseFilter.Stop` alone is not a complete modal design. A pause menu additionally needs a process mode that remains active while the scene tree is paused.

## Verify visually and behaviorally

Test the intended viewport, a smaller window, and a materially different aspect ratio. Check long text, minimum-size pressure, clipping/scrolling, and focus visibility. Navigate every interactive control without a mouse, then test mouse input over background and decorative children. Reopen the menu and reload the scene to catch duplicate callbacks or lost focus.

For pause UI, verify open, resume, nested settings/back, and scene change. Ensure gameplay neither receives consumed UI actions nor remains unintentionally paused. A headless parse cannot establish visual layout or navigation quality. Report screenshots/runtime checks separately from source-only or C# compile checks; never claim .NET execution with only the standard editor.

Official Godot 4.6 sources, checked 2026-09-30: [Containers](https://docs.godotengine.org/en/4.6/tutorials/ui/gui_containers.html), [anchors](https://docs.godotengine.org/en/4.6/tutorials/ui/size_and_anchors.html), [focus](https://docs.godotengine.org/en/4.6/tutorials/ui/gui_navigation.html), [input routing](https://docs.godotengine.org/en/4.6/tutorials/inputs/inputevent.html).
