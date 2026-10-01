---
name: godot-2d-pixel-tilemap
description: "Configure and debug Godot 4 pixel-art 2D rendering and TileMapLayer/TileSet workflows, including integer scaling, nearest filtering, atlas cells, terrain painting and coordinate conversion. Use for pixel blur, uneven pixels or tilemap authoring; not a Unity RuleTile translation or automatic asset generation."
---

# Godot pixel art and TileMapLayer

Inspect the project's engine version, art pixel size, existing stretch/filter settings, Camera2D movement and tile architecture. Preserve a deliberate project style; pixel art does not automatically mean every animation and physics position should be rounded.

## Pixel rendering

Choose a design viewport from the actual artwork/game, not a universal preset. A low-resolution `viewport` stretch plus `integer` scale mode (Godot 4.2+) gives even whole-pixel enlargement; aspect `keep` trades unused borders for preserved framing. `canvas_items` renders directly at target resolution and is often more suitable for crisp scalable UI. Read [pixel configuration](references/pixel-and-tiles.md) before selecting a trade-off.

Set nearest texture filtering at the suitable project/Viewport/CanvasItem scope. Check local overrides, mipmaps, atlas padding/bleeding and transformations before changing every import. Godot 4 filtering is generally a CanvasItem/Viewport concern; do not follow Godot 3 import-filter instructions blindly.

For shimmer, inspect camera smoothing, fractional camera and sprite transforms, viewport scaling, physics interpolation and animation separately. Pixel snapping can improve some art while introducing jitter or breaking smooth motion elsewhere. Test the intended camera and motion before globally enabling snapping.

## Native tiles

For new Godot 4.3+ maps, use one or more `TileMapLayer` nodes; legacy `TileMap` is deprecated. Do not silently migrate an existing map during a small fix. A `TileSet` owns atlas sources, tile dimensions, physics/occlusion/navigation layers, custom data and terrain definitions. Multiple layers may share that Resource: make intended per-map editing explicit before mutating it.

Get actual source IDs, atlas coordinates and alternative tile IDs from the project's TileSet. An atlas coordinate alone does not identify a cell. Set cells using those IDs; `-1` erases rather than creates a tile. Convert positions with `to_local`, `local_to_map`, and `map_to_local`; account for transformed layers. Use Godot terrain sets and peering bits for terrain transitions, with the required tile combinations authored. Terrain connection painting can also change neighbors and is not a generic Unity RuleTile evaluator.

Use the layer's normal batched update unless immediate queries require `update_internals`; do not force rebuilds each frame. Separate static ground/decoration/interactive objects as needed rather than making each visual tile a Node. Tile collision polygons and physics layer/masks need verification; visible cells alone do not prove collision works.

## Verification

Check exact tile/source IDs and coordinate roundtrips in code, then inspect rendered results at integer and awkward window sizes. Test seams, camera motion, collision shapes and terrain borders relevant to the change. The bundled `examples/native_lab` validates basic TileMapLayer creation and coordinate conversion; it does not prove arbitrary terrain sets, collision or visual fidelity.

Official references: [Multiple resolutions](https://docs.godotengine.org/en/4.6/tutorials/rendering/multiple_resolutions.html), [Using TileMaps](https://docs.godotengine.org/en/4.6/tutorials/2d/using_tilemaps.html), [TileMapLayer](https://docs.godotengine.org/en/4.6/classes/class_tilemaplayer.html). Checked 2026-09-30.
