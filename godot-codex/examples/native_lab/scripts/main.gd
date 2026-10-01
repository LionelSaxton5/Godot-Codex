extends Node2D
## Runtime-created UI/nodes intentionally complement the static scene inventory.
signal pulse(value: int)
var count: int = 0
var counter: Label
var fire_button: Button
var tile_layer: TileMapLayer

func _ready() -> void:
	RenderingServer.set_default_clear_color(Color("111a2b"))
	_build_tiles()
	_build_ui()
	# Repeated setup is safe; a saved scene connection must also be checked.
	if not pulse.is_connected(_on_pulse):
		pulse.connect(_on_pulse)
	fire_button.pressed.connect(_emit_pulse)
	fire_button.grab_focus()

func _build_tiles() -> void:
	var image := Image.create(16, 16, false, Image.FORMAT_RGBA8)
	image.fill(Color("386d77"))
	for x in range(16):
		image.set_pixel(x, 0, Color("6ec9bd"))
		image.set_pixel(0, x, Color("6ec9bd"))
	var atlas := TileSetAtlasSource.new()
	atlas.texture = ImageTexture.create_from_image(image)
	atlas.texture_region_size = Vector2i(16, 16)
	atlas.create_tile(Vector2i.ZERO)
	var tiles := TileSet.new()
	tiles.tile_size = Vector2i(16, 16)
	var source_id := tiles.add_source(atlas)
	tile_layer = TileMapLayer.new()
	tile_layer.name = "Ground"
	tile_layer.tile_set = tiles
	tile_layer.position = Vector2(32, 248)
	add_child(tile_layer)
	for x in range(36):
		for y in range(4):
			if y > 0 or x % 5 != 0:
				tile_layer.set_cell(Vector2i(x, y), source_id, Vector2i.ZERO)

func _build_ui() -> void:
	var canvas := CanvasLayer.new()
	canvas.name = "HUD"
	add_child(canvas)
	var margin := MarginContainer.new()
	margin.name = "Margin"
	margin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	for side in ["left", "top", "right", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 28)
	canvas.add_child(margin)
	var stack := VBoxContainer.new()
	stack.name = "Stack"
	stack.add_theme_constant_override("separation", 10)
	margin.add_child(stack)
	var heading := Label.new()
	heading.text = "GODOT / NATIVE LAB"
	heading.add_theme_font_size_override("font_size", 24)
	stack.add_child(heading)
	var subheading := Label.new()
	subheading.text = "Signals · Scenes · Resources · Autoload · TileMapLayer"
	subheading.add_theme_font_size_override("font_size", 14)
	stack.add_child(subheading)
	counter = Label.new()
	counter.name = "Counter"
	counter.text = "Pulses received: 0"
	stack.add_child(counter)
	fire_button = Button.new()
	fire_button.name = "EmitPulse"
	fire_button.text = "Emit a typed signal  [Enter / Space]"
	fire_button.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
	stack.add_child(fire_button)
	var note := Label.new()
	note.text = "640 × 360 viewport / integer scale / 16 px tiles\nKeyboard focus is visible. Resize the window to compare scaling."
	note.add_theme_font_size_override("font_size", 12)
	stack.add_child(note)

func _emit_pulse() -> void:
	pulse.emit(count + 1)

func _on_pulse(value: int) -> void:
	count = value
	get_node("/root/Session").emitted_count += 1
	counter.text = "Pulses received: %d" % value
