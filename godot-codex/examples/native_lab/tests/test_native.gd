extends SceneTree
## Explicit test runner. It executes fixture code and creates in-memory objects.
var failures: Array[String] = []
var checks: int = 0

class Emitter extends Node:
	signal pulse(value: int)

class Receiver extends Node:
	var total: int = 0
	func receive(value: int) -> void:
		total += value

class TreeReceiver extends Node:
	var emitter: Node
	var total: int = 0
	var callback: Callable
	func _enter_tree() -> void:
		var multiplier: int = 2
		callback = func(value: int) -> void: total += value * multiplier
		if is_instance_valid(emitter) and not emitter.pulse.is_connected(callback):
			emitter.pulse.connect(callback)
	func _exit_tree() -> void:
		if is_instance_valid(emitter) and emitter.pulse.is_connected(callback):
			emitter.pulse.disconnect(callback)

func expect(condition: bool, message: String) -> void:
	checks += 1
	if not condition:
		failures.append(message)
		push_error(message)

func _initialize() -> void:
	call_deferred("run_tests")

func run_tests() -> void:
	var emitter := Emitter.new()
	var receiver := Receiver.new()
	root.add_child(emitter)
	root.add_child(receiver)
	for attempt in range(2):
		if not emitter.pulse.is_connected(receiver.receive):
			emitter.pulse.connect(receiver.receive)
	expect(emitter.pulse.get_connections().size() == 1, "duplicate connection guard")
	emitter.pulse.emit(3)
	expect(receiver.total == 3, "typed signal delivery")
	receiver.free()
	expect(emitter.pulse.get_connections().is_empty(), "freed receiver disconnects bound method")
	emitter.pulse.emit(1)
	var tree_receiver := TreeReceiver.new()
	tree_receiver.emitter = emitter
	root.add_child(tree_receiver)
	emitter.pulse.emit(3)
	expect(tree_receiver.total == 6, "captured GDScript Callable receives once")
	root.remove_child(tree_receiver)
	emitter.pulse.emit(10)
	expect(tree_receiver.total == 6, "detached receiver is explicitly unsubscribed")
	root.add_child(tree_receiver)
	emitter.pulse.emit(2)
	expect(tree_receiver.total == 10, "tree re-entry restores one subscription")
	tree_receiver.free()
	expect(emitter.pulse.get_connections().is_empty(), "captured Callable cleanup on free")
	emitter.free()
	var first_emitter := Emitter.new()
	root.add_child(first_emitter)
	var last_receiver := TreeReceiver.new()
	last_receiver.emitter = first_emitter
	root.add_child(last_receiver)
	first_emitter.free()
	last_receiver.free()
	expect(not is_instance_valid(first_emitter) and not is_instance_valid(last_receiver), "emitter-first teardown is safe")

	var scene_root := Node.new()
	scene_root.name = "PackedRoot"
	var owned := Node.new()
	owned.name = "Owned"
	scene_root.add_child(owned)
	owned.owner = scene_root
	var runtime_only := Node.new()
	runtime_only.name = "Unowned"
	scene_root.add_child(runtime_only)
	var packed := PackedScene.new()
	expect(packed.pack(scene_root) == OK, "PackedScene pack succeeds")
	var instance := packed.instantiate()
	expect(instance.has_node("Owned"), "owned child is serialized")
	expect(not instance.has_node("Unowned"), "unowned child is not serialized")
	instance.free()
	scene_root.free()

	var first: Resource = load("res://resources/stats.tres")
	var shared: Resource = load("res://resources/stats.tres")
	expect(first == shared, "cached external Resource identity is shared")
	var copied: Resource = first.duplicate(true)
	copied.set("health", 8)
	expect(first.get("health") == 100, "duplicated Resource scalar mutation is isolated")
	var child: Resource = load("res://scripts/stats.gd").new()
	child.set("health", 40)
	var graph: Resource = load("res://scripts/stats.gd").new()
	graph.set("child", child)
	graph.get("items").append(child)
	graph.get("items").append(first)
	var shallow: Resource = graph.duplicate()
	expect(shallow.get("child") == child, "shallow copy retains Resource identity")
	var deep: Resource = graph.duplicate(true)
	expect(deep.get("child") != child, "deep copy duplicates internal Resource")
	expect(deep.get("child") == deep.get("items")[0], "deep copy preserves aliases")
	expect(deep.get("items")[1] == first, "deep Internal mode shares external Resource")
	var all: Resource = graph.duplicate_deep(Resource.DEEP_DUPLICATE_ALL)
	expect(all.get("items")[1] != first, "deep All mode duplicates external Resource")
	deep.get("items").clear()
	expect(graph.get("items").size() == 2, "deep copy isolates collection mutation")
	var actor_scene: PackedScene = load("res://scenes/actor.tscn")
	var actor_a := actor_scene.instantiate()
	var actor_b := actor_scene.instantiate()
	expect(actor_a.get("stats") != actor_b.get("stats"), "resource_local_to_scene creates per-instance Resource")
	actor_a.get("stats").set("health", 1)
	expect(actor_b.get("stats").get("health") == 100, "scene-local mutation is isolated")
	actor_a.free()
	actor_b.free()

	var session := root.get_node_or_null("Session")
	expect(session != null, "Autoload registered before test runner")
	var main_scene: PackedScene = load("res://scenes/main.tscn")
	var lab := main_scene.instantiate()
	root.add_child(lab)
	await process_frame
	var button: Button = lab.get("fire_button")
	button.pressed.emit()
	expect(lab.get("count") == 1, "UI button emits gameplay signal once")
	expect(session.get("emitted_count") == 1, "Autoload receives explicit durable state")
	var label: Label = lab.get("counter")
	expect(label.text == "Pulses received: 1", "UI label reflects signal state")
	expect(button.focus_mode == Control.FOCUS_ALL, "button supports keyboard focus")
	expect(button.has_focus(), "button receives initial keyboard focus")
	var accept_down := InputEventAction.new()
	accept_down.action = "ui_accept"
	accept_down.pressed = true
	Input.parse_input_event(accept_down)
	await process_frame
	var accept_up := InputEventAction.new()
	accept_up.action = "ui_accept"
	accept_up.pressed = false
	Input.parse_input_event(accept_up)
	await process_frame
	expect(lab.get("count") == 2, "focused button responds once to UI accept input")
	var layer: TileMapLayer = lab.get("tile_layer")
	expect(layer.get_used_cells().size() == 136, "TileMapLayer cell count")
	expect(layer.local_to_map(layer.map_to_local(Vector2i(4, 2))) == Vector2i(4, 2), "tile coordinate roundtrip")
	expect(ProjectSettings.get_setting("display/window/stretch/mode") == "viewport", "viewport stretch configured")
	expect(ProjectSettings.get_setting("display/window/stretch/scale_mode") == "integer", "integer scaling configured")
	lab.free()
	var replacement := main_scene.instantiate()
	root.add_child(replacement)
	await process_frame
	var next_button: Button = replacement.get("fire_button")
	next_button.pressed.emit()
	expect(session.get("emitted_count") == 3, "Autoload state survives replacement scene")
	expect(replacement.get("count") == 1, "replacement starts clean without stale callbacks")
	replacement.free()
	print("GODOT_NATIVE_TESTS=" + JSON.stringify({"checks": checks, "failures": failures, "passed": failures.is_empty()}))
	quit(0 if failures.is_empty() else 1)
