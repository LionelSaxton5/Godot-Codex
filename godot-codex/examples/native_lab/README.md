# Godot GDScript Native Lab

Open `project.godot` with Godot 4.6.3 and run. Enter, Space and mouse click each increment the signal-driven counter once. Tiles are generated with native TileMapLayer/TileSet APIs; no external art or service is needed.

From the plugin root:

```sh
python3 scripts/godot_validate.py examples/native_lab --allow-project-code --test-script res://tests/test_native.gd --smoke-frames 8
```

The fixture checks GDScript signal delivery/duplicate guards/receiver lifecycle/captured Callables, PackedScene ownership, Resource cache and deep-copy behavior, scene-local Resources, Autoload persistence, keyboard GUI input, TileMapLayer cells/coordinates and pixel settings. It exits nonzero and prints errors for failed assertions.

A fixed low-resolution viewport deliberately scales UI with the world. This demonstrates integer scaling, not a recommendation for every game's typography or accessibility. The plugin's UI and pixel-art skills explain alternatives.
