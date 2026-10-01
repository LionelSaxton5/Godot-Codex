# Pixel and tile recipes

## Deliberate project settings

For a low-resolution example, not an automatic patch to every project:

```ini
[display]
window/size/viewport_width=640
window/size/viewport_height=360
window/stretch/mode="viewport"
window/stretch/aspect="keep"
window/stretch/scale_mode="integer"

[rendering]
textures/canvas_textures/default_texture_filter=0
```

Integer scaling leaves extra borders at awkward sizes; smaller-than-design windows still need a product decision. Text is pixelated together with the low-resolution viewport. If the game needs high-resolution UI over a low-resolution world, use a separate world SubViewport and native-resolution Control layer rather than pretending one global setting solves both. `canvas_items` and integer scaling are another trade-off depending on art and layout.

Project settings are defaults; CanvasItem `texture_filter` or inherited overrides can change the result. In GDScript use `CanvasItem.TEXTURE_FILTER_NEAREST`; in C# use `CanvasItem.TextureFilterEnum.Nearest`. Do not confuse the enum values of different APIs. These adaptation snippets are source-reviewed; the bundled C# fixture separately compiles and exercises TileMapLayer with the .NET engine.

## Cell coordinate example

```gdscript
# world_position is in global/world space. layer may be transformed.
var cell: Vector2i = layer.local_to_map(layer.to_local(world_position))
var center: Vector2 = layer.to_global(layer.map_to_local(cell))
# These identifiers must come from the current TileSet:
layer.set_cell(cell, existing_source_id, existing_atlas_coords, existing_alternative_id)
```

```csharp
Vector2I cell = layer.LocalToMap(layer.ToLocal(worldPosition));
Vector2 center = layer.ToGlobal(layer.MapToLocal(cell));
layer.SetCell(cell, existingSourceId, existingAtlasCoords, existingAlternativeId);
```

Cell origin and a tile texture's visual origin need not coincide. `map_to_local` returns cell center, not a guarantee that an oversized/offset atlas texture's visible center lies there.

Use `set_cells_terrain_connect` / `SetCellsTerrainConnect` only after inspecting terrain set index, terrain index, peering bits and empty-terrain policy. Godot chooses available tile combinations and may update neighboring cells. Missing combinations can produce surprising results. For an existing map, first work on a disposable copy and compare border cells; this skill does not generate missing art or infer a complete terrain atlas from one image.

Sources: [CanvasItem texture filter](https://docs.godotengine.org/en/4.6/classes/class_canvasitem.html), [TileMapLayer API](https://docs.godotengine.org/en/4.6/classes/class_tilemaplayer.html), [TileSet API](https://docs.godotengine.org/en/4.6/classes/class_tileset.html). Checked 2026-09-30.
