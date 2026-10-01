@tool
extends EditorPlugin
## Project-local, explicitly enabled bridge. The project must already be trusted.
## Never evaluates request code or dispatches arbitrary object methods.

const PROTOCOL_VERSION := 1
const IPC := "res://.godot/ai_bridge"
const MAX_BYTES := 1048576
const MAX_REQUEST_BYTES := 2097152
const MAX_SCAN := 64
const MAX_TREE_NODES := 2048
const OPERATIONS := ["status", "hierarchy", "node_inspect", "diagnostics", "scene_create", "scene_open", "scene_save", "node_create", "node_delete", "node_duplicate", "node_reparent", "node_rename", "property_set", "signal_connect", "signal_disconnect", "script_read", "script_write", "script_attach", "resource_create", "resource_assign", "editor_undo", "editor_redo", "play_current", "play_main", "play_custom", "stop"]
const SCENE_WRITES := ["scene_create", "scene_open", "scene_save", "node_create", "node_delete", "node_duplicate", "node_reparent", "node_rename", "property_set", "signal_connect", "signal_disconnect", "script_attach", "resource_assign", "editor_undo", "editor_redo", "play_current", "play_main", "play_custom"]
const NODE_TYPES := ["Node", "Node2D", "Node3D", "Control", "CanvasLayer", "Button", "Label", "RichTextLabel", "TextureRect", "Panel", "PanelContainer", "MarginContainer", "HBoxContainer", "VBoxContainer", "GridContainer", "CenterContainer", "ScrollContainer", "LineEdit", "TextEdit", "CheckBox", "CheckButton", "OptionButton", "ProgressBar", "HSlider", "VSlider", "ColorRect", "Sprite2D", "AnimatedSprite2D", "Camera2D", "TileMapLayer", "CharacterBody2D", "StaticBody2D", "RigidBody2D", "AnimatableBody2D", "CollisionShape2D", "Area2D", "RayCast2D", "Marker2D", "Polygon2D", "Line2D", "PointLight2D", "DirectionalLight2D", "MeshInstance3D", "Camera3D", "DirectionalLight3D", "OmniLight3D", "SpotLight3D", "StaticBody3D", "CharacterBody3D", "RigidBody3D", "AnimatableBody3D", "CollisionShape3D", "Area3D", "RayCast3D", "Marker3D", "WorldEnvironment", "AudioStreamPlayer", "AudioStreamPlayer2D", "AudioStreamPlayer3D", "Timer", "AnimationPlayer"]
const RESOURCE_TYPES := ["StandardMaterial3D", "ORMMaterial3D", "BoxMesh", "SphereMesh", "PlaneMesh", "QuadMesh", "CapsuleMesh", "CylinderMesh", "PrismMesh", "BoxShape3D", "SphereShape3D", "CapsuleShape3D", "CylinderShape3D", "RectangleShape2D", "CircleShape2D", "CapsuleShape2D", "SegmentShape2D", "Environment", "StyleBoxFlat"]
const BLOCKED_PROPERTIES := ["script", "owner", "name", "scene_file_path", "unique_name_in_owner", "editor_description", "multiplayer", "process_thread_group", "process_thread_group_order", "process_thread_messages", "resource_path", "resource_local_to_scene"]
const SCALAR_TYPES := [TYPE_BOOL, TYPE_INT, TYPE_FLOAT, TYPE_STRING, TYPE_STRING_NAME, TYPE_VECTOR2, TYPE_VECTOR2I, TYPE_VECTOR3, TYPE_VECTOR3I, TYPE_COLOR, TYPE_NODE_PATH]
const ARGUMENT_SCHEMAS := preload("argument_schemas.gd").SCHEMAS
var _completed_ids: Dictionary = {}
var _inherited_cache: Dictionary = {}
var _session_id := ""
var _project_root := ""
var _busy := false
var _ready_bridge := false
var _heartbeat_elapsed := 0.0
var _poll_elapsed := 0.0
var _logs: Array[Dictionary] = []
var _disk_hashes: Dictionary = {}
var _saved_versions: Dictionary = {}
var _history_ids: Dictionary = {}
var _save_observed_path := ""
var _error: Dictionary = {}
var _observed_revision := ""
var _revision_sequence := 0

func _enter_tree() -> void:
	_session_id = Crypto.new().generate_random_bytes(16).hex_encode()
	_project_root = ProjectSettings.globalize_path("res://").trim_suffix("/")
	if not _safe_ipc():
		push_error("AI Editor Bridge: IPC contains a symlink or cannot be created; bridge disabled.")
		return
	for folder in [IPC, IPC + "/requests", IPC + "/responses"]:
		if DirAccess.make_dir_recursive_absolute(folder) != OK:
			push_error("AI Editor Bridge: unable to create local IPC directory.")
			return
	_ready_bridge = true
	get_undo_redo().history_changed.connect(_on_history_event)
	get_undo_redo().version_changed.connect(_on_history_event)
	scene_changed.connect(_on_scene_changed)
	scene_saved.connect(_on_scene_saved)
	_on_scene_changed(EditorInterface.get_edited_scene_root())
	_write_status()
	set_process(true)

func _exit_tree() -> void:
	_ready_bridge = false
	set_process(false)
	if _safe_ipc():
		_atomic_json(IPC + "/status.json", {"protocol_version": PROTOCOL_VERSION, "session_id": _session_id, "project_root": _project_root, "heartbeat_unix": Time.get_unix_time_from_system(), "enabled": false})

func _process(delta: float) -> void:
	if not _ready_bridge:
		return
	_heartbeat_elapsed += delta
	_poll_elapsed += delta
	if _heartbeat_elapsed >= 0.5:
		_heartbeat_elapsed = 0.0
		_write_status()
	if _busy or _poll_elapsed < 0.05:
		return
	_poll_elapsed = 0.0
	_inherited_cache.clear()
	if not _safe_ipc():
		_ready_bridge = false
		push_error("AI Editor Bridge: IPC became unsafe; bridge stopped.")
		return
	var directory := DirAccess.open(IPC + "/requests")
	if directory == null:
		return
	directory.list_dir_begin()
	for _i in range(MAX_SCAN):
		var filename := directory.get_next()
		if filename.is_empty():
			break
		if directory.current_is_dir() or directory.is_link(filename) or not filename.ends_with(".json"):
			continue
		var request_id := filename.trim_suffix(".json")
		if not _valid_id(request_id):
			continue
		_busy = true
		_handle_request(request_id)
		break
	directory.list_dir_end()

func _valid_id(value: String) -> bool:
	if value.length() != 32:
		return false
	for character in value:
		if not character in "0123456789abcdef":
			return false
	return true

func _has_symlink(path: String) -> bool:
	var absolute := ProjectSettings.globalize_path(path)
	var drive := absolute.get_base_dir()
	var leaf := absolute.get_file()
	while not leaf.is_empty():
		var directory := DirAccess.open(drive)
		if directory != null and directory.is_link(leaf):
			return true
		var previous := drive
		leaf = drive.get_file()
		drive = drive.get_base_dir()
		if drive == previous:
			break
	return false

func _safe_ipc() -> bool:
	for path in ["res://.godot", IPC, IPC + "/requests", IPC + "/responses", IPC + "/status.json"]:
		if _has_symlink(path):
			return false
	return true

func _atomic_json(path: String, value: Dictionary) -> bool:
	if _has_symlink(path):
		return false
	var temporary := path + "." + _session_id + ".tmp"
	if _has_symlink(temporary):
		return false
	var file := FileAccess.open(temporary, FileAccess.WRITE)
	if file == null:
		return false
	file.store_string(JSON.stringify(value))
	file.flush()
	file.close()
	return DirAccess.rename_absolute(temporary, path) == OK

func _handle_request(request_id: String) -> void:
	var path := IPC + "/requests/" + request_id + ".json"
	var response_path := IPC + "/responses/" + request_id + ".json"
	if _has_symlink(path) or _has_symlink(response_path):
		_busy = false
		return
	# A completed ID is never executed twice, including after transport timeouts.
	if FileAccess.file_exists(response_path):
		DirAccess.remove_absolute(path)
		_busy = false
		return
	_error = {}
	if _completed_ids.has(request_id):
		_atomic_json(response_path, {"id": request_id, "session_id": _session_id, "ok": false, "result": null, "error": {"code": "request_replayed", "message": "Request ID has already completed; it will not be executed again."}})
		DirAccess.remove_absolute(path)
		_busy = false
		return
	var result: Variant = null
	var operation := ""
	var request: Variant = null
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		_fail("request_unreadable", "Cannot read request.")
	elif file.get_length() > MAX_REQUEST_BYTES:
		_fail("request_too_large", "Maximum request size is 2 MiB.")
	else:
		request = JSON.parse_string(file.get_as_text())
	if file != null:
		file.close()
	if _error.is_empty():
		if not request is Dictionary or request.get("id", "") != request_id:
			_fail("invalid_request", "Request must be an object with the filename's ID.")
		elif request.get("session_id", "") != _session_id:
			_fail("stale_session", "Request belongs to another editor session; refresh status.")
		elif request.get("project_root", "") != _project_root:
			_fail("project_mismatch", "Request project_root does not match this editor.")
		elif not request.get("operation") is String or not request.get("arguments", {}) is Dictionary:
			_fail("invalid_request", "operation must be a string and arguments an object.")
		else:
			operation = request.operation
			result = await _dispatch(operation, request.get("arguments", {}))
	_completed_ids[request_id] = true
	if _completed_ids.size() > 4096:
		_completed_ids.erase(_completed_ids.keys()[0])
	var response := {"id": request_id, "session_id": _session_id, "ok": _error.is_empty(), "result": result}
	if not _error.is_empty():
		response["error"] = _error.duplicate(true)
	_record(operation, request_id, response.ok, _error)
	if _safe_ipc() and _atomic_json(response_path, response):
		DirAccess.remove_absolute(path)
	_write_status()
	_busy = false

func _fail(code: String, message: String) -> Variant:
	_error = {"code": code, "message": message}
	return null

func _record(operation: String, request_id: String, okay: bool, error: Dictionary) -> void:
	_logs.append({"time_unix": Time.get_unix_time_from_system(), "operation": operation, "id": request_id, "ok": okay, "error": error.duplicate(true)})
	if _logs.size() > 100:
		_logs.pop_front()

func _history(root: Node) -> UndoRedo:
	if root == null:
		return null
	var manager := get_undo_redo()
	var identity := str(root.get_instance_id())
	# Inactive scene roots are detached. Godot otherwise deduces the CURRENT
	# scene history for them; retain the ID captured while each tab is active.
	if root == EditorInterface.get_edited_scene_root():
		_history_ids[identity] = manager.get_object_history_id(root)
	if not _history_ids.has(identity):
		return null
	return manager.get_history_undo_redo(int(_history_ids[identity]))

func _on_history_event() -> void:
	_revision_sequence += 1

func _revision() -> String:
	var root := EditorInterface.get_edited_scene_root()
	var raw := "none"
	if root != null:
		var history := _history(root)
		raw = "%s:%s:%s" % [root.get_instance_id(), get_undo_redo().get_object_history_id(root), history.get_version() if history != null else -1]
	if raw != _observed_revision:
		_observed_revision = raw
		_revision_sequence += 1
	return "%s:%s:%s" % [_session_id, raw, _revision_sequence]

func _scene_info() -> Dictionary:
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		return {"path": "", "root_name": "", "root_type": "", "revision": _revision(), "root_instance_id": "", "disk_sha256": "", "dirty": false}
	var path := root.scene_file_path
	if not path.is_empty() and not _disk_hashes.has(path) and FileAccess.file_exists(path) and not _has_symlink(path):
		_disk_hashes[path] = FileAccess.get_sha256(path)
	var history := _history(root)
	var version := history.get_version() if history != null else -1
	var dirty := path.is_empty() or EditorInterface.is_object_edited(root) or version != int(_saved_versions.get(str(root.get_instance_id()), version))
	return {"path": path, "root_name": str(root.name), "root_type": root.get_class(), "revision": _revision(), "root_instance_id": str(root.get_instance_id()), "disk_sha256": _disk_hashes.get(path, ""), "dirty": dirty, "dirty_is_advisory": true}

func _status() -> Dictionary:
	return {"protocol_version": PROTOCOL_VERSION, "session_id": _session_id, "project_root": _project_root, "heartbeat_unix": Time.get_unix_time_from_system(), "enabled": _ready_bridge, "engine_version": Engine.get_version_info().string, "scene": _scene_info(), "playing": EditorInterface.is_playing_scene(), "playing_scene": EditorInterface.get_playing_scene(), "capabilities": OPERATIONS, "node_types": NODE_TYPES, "resource_types": RESOURCE_TYPES, "diagnostics_scope": "bridge operations only; not full engine output"}

func _write_status() -> void:
	if _safe_ipc():
		_atomic_json(IPC + "/status.json", _status())

func _on_scene_changed(root: Node) -> void:
	if root == null:
		return
	var path := root.scene_file_path
	if not path.is_empty() and not _disk_hashes.has(path) and not _has_symlink(path):
		_disk_hashes[path] = FileAccess.get_sha256(path) if FileAccess.file_exists(path) else ""
	var history := _history(root)
	if not _saved_versions.has(str(root.get_instance_id())):
		_saved_versions[str(root.get_instance_id())] = history.get_version() if history != null else -1

func _on_scene_saved(path: String) -> void:
	_save_observed_path = path
	if _has_symlink(path):
		return
	_disk_hashes[path] = FileAccess.get_sha256(path)
	for root in EditorInterface.get_open_scene_roots():
		if root.scene_file_path == path:
			var history := _history(root)
			_saved_versions[str(root.get_instance_id())] = history.get_version() if history != null else -1

func _guard_scene(arguments: Dictionary) -> bool:
	var scene := _scene_info()
	if not arguments.has("expected_revision") or not arguments.has("expected_scene_path"):
		_fail("guard_required", "Copy expected_revision and expected_scene_path from current status.scene.")
		return false
	if arguments.expected_revision != scene.revision or arguments.expected_scene_path != scene.path:
		_fail("stale_scene", "Scene or editor history changed; inspect current state before retrying.")
		return false
	return true

func _resource_path(value: Variant, extensions: Array = []) -> String:
	if not value is String or not value.begins_with("res://") or value.length() > 1024 or "\\" in value or _control_characters(value):
		_fail("invalid_path", "Use a canonical project-relative res:// path.")
		return ""
	var relative: String = value.trim_prefix("res://")
	var segments := relative.split("/", true)
	for segment in segments:
		if segment.is_empty() or segment in [".", ".."] or ":" in segment:
			_fail("invalid_path", "Empty, traversal and colon path segments are forbidden.")
			return ""
	if segments[0].to_lower() in [".godot", ".git", ".codex", ".agents"] or relative.to_lower().begins_with("addons/ai_editor_bridge/") or relative.to_lower() == "project.godot":
		_fail("protected_path", "Bridge internals, project settings and metadata are protected.")
		return ""
	if not extensions.is_empty() and not relative.get_extension().to_lower() in extensions:
		_fail("invalid_extension", "This operation does not support that file extension.")
		return ""
	if _has_symlink(value):
		_fail("symlink_forbidden", "Symlinks and reparse points are forbidden in resource paths.")
		return ""
	return value

func _node(value: Variant, editable := false) -> Node:
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		_fail("no_scene", "No scene is open.")
		return null
	if not value is String or value.is_empty() or value.length() > 1024 or value.begins_with("/") or ":" in value or "\\" in value or _control_characters(value):
		_fail("invalid_node_path", "Use a root-relative node path, or '.' for the root.")
		return null
	if value != ".":
		for segment in value.split("/", true):
			if segment in ["", ".", ".."]:
				_fail("invalid_node_path", "Traversal and empty node path components are forbidden.")
				return null
	var node := root.get_node_or_null(NodePath(value))
	if node == null:
		_fail("node_not_found", "Node was not found in the current scene.")
		return null
	if editable and not _guard_builtin(node):
		return null
	if editable and not _editable(node):
		_fail("instanced_node_protected", "Inherited or instanced scene contents are protected; edit their source scene instead.")
		return null
	return node

func _editable(node: Node) -> bool:
	var root := EditorInterface.get_edited_scene_root()
	if root == null or ClassDB.class_get_api_type(node.get_class()) != ClassDB.API_CORE or _inherited_scene(root):
		return false
	if node == root:
		return true
	if node.owner != root:
		return false
	var parent := node.get_parent()
	while parent != null and parent != root:
		if not parent.scene_file_path.is_empty():
			return false
		parent = parent.get_parent()
	return true

func _inherited_scene(root: Node) -> bool:
	# Godot's internal inherited-state accessor is not exposed to GDScript.
	# Inspect only the textual root declaration; never load a resource to read it.
	var path := root.scene_file_path
	if path.is_empty():
		return true # Save unnamed scenes explicitly before bridge structural editing.
	if path.get_extension().to_lower() != "tscn" or _has_symlink(path):
		return true
	if _inherited_cache.has(path):
		return _inherited_cache[path]
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return true
	while not file.eof_reached() and file.get_position() < 1048576:
		var line := file.get_line().strip_edges()
		if line.begins_with("[node "):
			file.close()
			_inherited_cache[path] = "instance=" in line
			return _inherited_cache[path]
	file.close()
	return true

func _guard_node(node: Node, arguments: Dictionary, key := "expected_node_id") -> bool:
	if node == null:
		return false
	if not arguments.get(key) is String or arguments[key] != str(node.get_instance_id()):
		_fail("stale_node", "%s must match this node's node_id from hierarchy or node_inspect." % key)
		return false
	return true

func _valid_name(value: Variant) -> bool:
	if not value is String or value.is_empty() or value.length() > 128 or value != value.validate_node_name() or value in [".", ".."] or _control_characters(value):
		_fail("invalid_name", "Provide a valid nonempty Godot node name, maximum 128 characters.")
		return false
	return true

func _node_info(node: Node) -> Dictionary:
	var root := EditorInterface.get_edited_scene_root()
	var script: Script = node.get_script()
	return {"path": str(root.get_path_to(node)), "name": str(node.name), "type": node.get_class(), "node_id": str(node.get_instance_id()), "instance_id": str(node.get_instance_id()), "owner_path": str(root.get_path_to(node.owner)) if node.owner != null and (node.owner == root or root.is_ancestor_of(node.owner)) else "", "scene_file_path": node.scene_file_path, "editable": _editable(node), "script_path": script.resource_path if script != null else ""}

func _walk_tree(node: Node, depth: int, max_depth: int, output: Array) -> void:
	if output.size() >= MAX_TREE_NODES:
		return
	var information := _node_info(node)
	information["depth"] = depth
	information["child_count"] = node.get_child_count()
	output.append(information)
	if depth < max_depth:
		for child in node.get_children():
			_walk_tree(child, depth + 1, max_depth, output)

func _guard_builtin(object: Object) -> bool:
	# ClassDB includes third-party GDExtension APIs, not just engine built-ins.
	# Do not enumerate or invoke custom getters/setters through reflection.
	if object == null or ClassDB.class_get_api_type(object.get_class()) != ClassDB.API_CORE:
		_fail("unsupported_node_type" if object is Node else "unsupported_resource_type", "Only built-in Godot core classes are supported; GDExtension/editor-extension classes are excluded.")
		return false
	return true

func _script_declared_properties(object: Object) -> Dictionary:
	# Inspect declaration metadata only. A C# exported lowercase name may shadow
	# an engine property (for example `position` versus native `Position`).
	# Object.get/set dispatch could otherwise invoke that custom getter/setter.
	var names := {}
	var seen := {}
	var script: Script = object.get_script()
	while script != null and not seen.has(script.get_instance_id()):
		seen[script.get_instance_id()] = true
		if not script.get_class() in ["GDScript", "CSharpScript"]:
			_fail("unsupported_script_type", "Only GDScript and C# declaration metadata is supported for property inspection.")
			return names
		for declaration in script.get_script_property_list():
			names[str(declaration.name)] = true
		script = script.get_base_script()
	return names

func _native_properties(object: Object) -> Dictionary:
	var properties := {}
	if not _guard_builtin(object):
		return properties
	var script_properties := _script_declared_properties(object)
	if not _error.is_empty():
		return properties
	for information in ClassDB.class_get_property_list(object.get_class(), false):
		var property := str(information.name)
		if script_properties.has(property) or property in BLOCKED_PROPERTIES or property.begins_with("_") or property.begins_with("metadata/"):
			continue
		if int(information.usage) & PROPERTY_USAGE_EDITOR == 0:
			continue
		if int(information.usage) & PROPERTY_USAGE_READ_ONLY:
			continue
		properties[property] = information
	return properties

func _encode(value: Variant) -> Variant:
	match typeof(value):
		TYPE_NIL, TYPE_BOOL, TYPE_INT, TYPE_FLOAT, TYPE_STRING:
			return value
		TYPE_STRING_NAME:
			return str(value)
		TYPE_VECTOR2, TYPE_VECTOR2I:
			return {"type": "Vector2i" if value is Vector2i else "Vector2", "x": value.x, "y": value.y}
		TYPE_VECTOR3, TYPE_VECTOR3I:
			return {"type": "Vector3i" if value is Vector3i else "Vector3", "x": value.x, "y": value.y, "z": value.z}
		TYPE_COLOR:
			return {"type": "Color", "r": value.r, "g": value.g, "b": value.b, "a": value.a}
		TYPE_NODE_PATH:
			return {"type": "NodePath", "value": str(value)}
		TYPE_OBJECT:
			if value is Resource:
				return {"type": "Resource", "path": value.resource_path, "class": value.get_class()}
	return {"type": type_string(typeof(value)), "supported": false}

func _contains_nul(value: String) -> bool:
	for index in range(value.length()):
		if value.unicode_at(index) == 0:
			return true
	return false

func _control_characters(value: String) -> bool:
	for index in range(value.length()):
		if value.unicode_at(index) < 32 or value.unicode_at(index) == 127:
			return true
	return false

func _number(value: Variant) -> bool:
	return (value is int or value is float) and is_finite(float(value))

func _decode(value: Variant, kind: int) -> Variant:
	if kind == TYPE_BOOL and value is bool:
		return value
	if kind == TYPE_INT and _number(value) and float(value) == floor(float(value)) and abs(float(value)) <= 9007199254740991.0:
		return int(value)
	if kind == TYPE_FLOAT and _number(value):
		return float(value)
	if kind in [TYPE_STRING, TYPE_STRING_NAME] and value is String and value.length() <= 65536:
		return StringName(value) if kind == TYPE_STRING_NAME else value
	if value is Dictionary:
		if kind in [TYPE_VECTOR2, TYPE_VECTOR2I] and value.get("type") == ("Vector2i" if kind == TYPE_VECTOR2I else "Vector2") and _number(value.get("x")) and _number(value.get("y")):
			if kind == TYPE_VECTOR2I:
				if float(value.x) != floor(float(value.x)) or float(value.y) != floor(float(value.y)):
					return _fail("invalid_value", "Vector2i components must be integers.")
				return Vector2i(int(value.x), int(value.y))
			return Vector2(float(value.x), float(value.y))
		if kind in [TYPE_VECTOR3, TYPE_VECTOR3I] and value.get("type") == ("Vector3i" if kind == TYPE_VECTOR3I else "Vector3") and _number(value.get("x")) and _number(value.get("y")) and _number(value.get("z")):
			if kind == TYPE_VECTOR3I:
				if float(value.x) != floor(float(value.x)) or float(value.y) != floor(float(value.y)) or float(value.z) != floor(float(value.z)):
					return _fail("invalid_value", "Vector3i components must be integers.")
				return Vector3i(int(value.x), int(value.y), int(value.z))
			return Vector3(float(value.x), float(value.y), float(value.z))
		if kind == TYPE_COLOR and value.get("type") == "Color" and _number(value.get("r")) and _number(value.get("g")) and _number(value.get("b")) and _number(value.get("a", 1.0)):
			return Color(float(value.r), float(value.g), float(value.b), float(value.get("a", 1.0)))
		if kind == TYPE_NODE_PATH and value.get("type") == "NodePath" and value.get("value") is String:
			var path: String = value.value
			if not path.begins_with("/") and not ":" in path and not "\\" in path and not _control_characters(path) and (path.is_empty() or not "" in path.split("/", true)):
				return NodePath(path)
	return _fail("invalid_value", "Value must exactly match the native property type and supported JSON codec.")

func _inspect(node: Node) -> Dictionary:
	if not _guard_builtin(node):
		return {}
	var properties := []
	var native := _native_properties(node)
	if not _error.is_empty():
		return {}
	for property in native:
		var description: Dictionary = native[property]
		var kind := int(description.type)
		if kind in SCALAR_TYPES or kind == TYPE_OBJECT:
			properties.append({"name": property, "type": type_string(kind), "hint": description.hint, "hint_string": description.hint_string, "value": _encode(node.get(property)), "writable": kind in SCALAR_TYPES, "resource_assignable": kind == TYPE_OBJECT and description.hint == PROPERTY_HINT_RESOURCE_TYPE})
	var connections := []
	var root := EditorInterface.get_edited_scene_root()
	for signal_info in node.get_signal_list():
		for connection in node.get_signal_connection_list(signal_info.name):
			if connection.flags & CONNECT_PERSIST == 0:
				continue
			var callback: Callable = connection.callable
			var target := callback.get_object()
			if target is Node and (target == root or root.is_ancestor_of(target)):
				connections.append({"signal": str(signal_info.name), "target_path": str(root.get_path_to(target)), "method": str(callback.get_method()), "flags": connection.flags, "bound_argument_count": callback.get_bound_arguments_count()})
	return {"node": _node_info(node), "properties": properties, "connections": connections, "scene": _scene_info()}

func _scene_result(extra: Dictionary = {}) -> Dictionary:
	extra["scene"] = _scene_info()
	return extra

func _dispatch(operation: String, arguments: Dictionary) -> Variant:
	if not operation in OPERATIONS:
		return _fail("unsupported_operation", "Operation is not supported by this bridge.")
	if not _validate_schema(arguments, ARGUMENT_SCHEMAS[operation], "arguments"):
		return null
	if operation in SCENE_WRITES and not _guard_scene(arguments):
		return null
	match operation:
		"status":
			return _status()
		"diagnostics":
			var limit := clampi(int(arguments.get("limit", 50)), 1, 100)
			return {"scope": "bridge operations only; not full engine output", "entries": _logs.slice(maxi(0, _logs.size() - limit))}
		"hierarchy":
			var node := _node(arguments.get("node_path", "."))
			if node == null:
				return null
			var nodes := []
			_walk_tree(node, 0, clampi(int(arguments.get("max_depth", 8)), 0, 32), nodes)
			return {"nodes": nodes, "truncated": nodes.size() >= MAX_TREE_NODES, "scene": _scene_info()}
		"node_inspect":
			var node := _node(arguments.get("node_path", "."))
			return _inspect(node) if node != null else null
		"scene_create":
			return await _scene_create(arguments)
		"scene_open":
			return await _scene_open(arguments)
		"scene_save":
			return _scene_save(arguments)
		"node_create":
			return _node_create(arguments)
		"node_delete", "node_duplicate", "node_reparent", "node_rename":
			return _node_structure(operation, arguments)
		"property_set":
			return _property_set(arguments)
		"signal_connect", "signal_disconnect":
			return _signal_edit(operation, arguments)
		"script_read":
			return _script_read(arguments)
		"script_write":
			return _script_write(arguments)
		"script_attach":
			return _script_attach(arguments)
		"resource_create":
			return _resource_create(arguments)
		"resource_assign":
			return _resource_assign(arguments)
		"editor_undo", "editor_redo":
			var root := EditorInterface.get_edited_scene_root()
			if root == null:
				return _fail("no_scene", "No scene is open.")
			var history := _history(root)
			if history == null or (operation == "editor_undo" and not history.has_undo()) or (operation == "editor_redo" and not history.has_redo()):
				return _fail("history_empty", "No action is available in this scene's editor history.")
			var changed := history.undo() if operation == "editor_undo" else history.redo()
			return _scene_result({"changed": changed, "history_scope": "current scene editor history, including manual editor actions"})
		"play_current", "play_main", "play_custom":
			return await _play(operation, arguments)
		"stop":
			EditorInterface.stop_playing_scene()
			return {"playing": EditorInterface.is_playing_scene(), "stop_requested": true}
	return null

func _validate_schema(value: Variant, schema: Dictionary, location: String) -> bool:
	if schema.has("anyOf"):
		for candidate in schema.anyOf:
			if _validate_schema(value, candidate, location):
				_error = {}
				return true
		_fail("invalid_arguments", location + " does not match a supported value type.")
		return false
	var kind: String = schema.get("type", "")
	var correct := true
	match kind:
		"object": correct = value is Dictionary
		"array": correct = value is Array
		"string": correct = value is String
		"boolean": correct = value is bool
		"number": correct = _number(value)
		"integer": correct = _number(value) and float(value) == floor(float(value))
		"null": correct = value == null
	if not correct:
		_fail("invalid_arguments", location + " has an invalid JSON type.")
		return false
	if schema.has("const") and value != schema.const:
		_fail("invalid_arguments", location + " has an unsupported value.")
		return false
	if schema.has("enum") and not value in schema.enum:
		_fail("invalid_arguments", location + " has an unsupported value.")
		return false
	if kind == "object":
		for key in schema.get("required", []):
			if not value.has(key):
				_fail("invalid_arguments", location + "." + key + " is required.")
				return false
		var properties: Dictionary = schema.get("properties", {})
		for key in value:
			if properties.has(key):
				if not _validate_schema(value[key], properties[key], location + "." + key):
					return false
			elif schema.get("additionalProperties", true) is Dictionary:
				if not _validate_schema(value[key], schema.additionalProperties, location + "." + key):
					return false
			elif schema.get("additionalProperties", true) == false:
				_fail("invalid_arguments", location + "." + key + " is not supported.")
				return false
	if kind == "string":
		if value.length() < int(schema.get("minLength", 0)) or value.length() > int(schema.get("maxLength", MAX_BYTES)):
			_fail("invalid_arguments", location + " has an invalid string length.")
			return false
		if schema.has("pattern"):
			var regex := RegEx.new()
			if regex.compile(schema.pattern) != OK or regex.search(value) == null:
				_fail("invalid_arguments", location + " has an invalid format.")
				return false
	if kind in ["number", "integer"]:
		if (schema.has("minimum") and value < schema.minimum) or (schema.has("maximum") and value > schema.maximum):
			_fail("invalid_arguments", location + " is outside the supported range.")
			return false
	return true

func _new_file_path(arguments: Dictionary, extensions: Array) -> String:
	var path := _resource_path(arguments.get("path"), extensions)
	if path.is_empty():
		return ""
	if FileAccess.file_exists(path) or DirAccess.dir_exists_absolute(path):
		_fail("file_exists", "Refusing to overwrite an existing file.")
		return ""
	if not DirAccess.dir_exists_absolute(path.get_base_dir()):
		_fail("parent_missing", "Parent directory must already exist.")
		return ""
	return path

func _scene_create(arguments: Dictionary) -> Variant:
	var path := _new_file_path(arguments, ["tscn"])
	if path.is_empty():
		return null
	var kind: Variant = arguments.get("root_type", "Node2D")
	if not kind in ["Node", "Node2D", "Node3D", "Control"]:
		return _fail("unsupported_type", "Scene root must be Node, Node2D, Node3D, or Control.")
	var name_value: Variant = arguments.get("root_name", "Scene")
	if not _valid_name(name_value):
		return null
	var node: Node = ClassDB.instantiate(kind)
	node.name = name_value
	var packed := PackedScene.new()
	var error := packed.pack(node)
	node.free()
	if error != OK:
		return _fail("pack_failed", "Failed to pack new scene.")
	error = ResourceSaver.save(packed, path)
	if error != OK:
		return _fail("save_failed", "Failed to write the new scene.")
	EditorInterface.get_resource_filesystem().update_file(path)
	EditorInterface.open_scene_from_path(path)
	await get_tree().process_frame
	await get_tree().process_frame
	return _scene_result({"path": path, "created": true, "undoable": false, "previous_scene_retained": true})

func _scene_open(arguments: Dictionary) -> Variant:
	var path := _resource_path(arguments.get("path"), ["tscn"])
	if path.is_empty():
		return null
	if not FileAccess.file_exists(path):
		return _fail("file_missing", "Scene file does not exist.")
	# Opening uses a new/existing editor tab; never close or reload another tab.
	EditorInterface.open_scene_from_path(path)
	await get_tree().process_frame
	await get_tree().process_frame
	var root := EditorInterface.get_edited_scene_root()
	if root == null or root.scene_file_path != path:
		return _fail("open_failed", "Editor did not activate the requested scene.")
	return _scene_result({"opened": true, "previous_scene_retained": true})

func _scene_save(arguments: Dictionary) -> Variant:
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		return _fail("no_scene", "No scene is open.")
	var path := _resource_path(root.scene_file_path, ["tscn"])
	if path.is_empty():
		return _fail("scene_path_required", "Scene must already have a safe .tscn path; create it first.")
	var actual := FileAccess.get_sha256(path) if FileAccess.file_exists(path) else ""
	var expected: String = _disk_hashes.get(path, "")
	if not arguments.get("expected_disk_sha256") is String or actual != expected or arguments.expected_disk_sha256 != actual:
		return _fail("disk_conflict", "Scene file changed outside the editor; refusing to overwrite it.")
	_save_observed_path = ""
	EditorInterface.save_scene_as(path, false)
	if _save_observed_path != path or not FileAccess.file_exists(path):
		return _fail("save_failed", "Editor did not confirm saving the scene.")
	_on_scene_saved(path)
	return _scene_result({"saved": true, "path": path, "sha256": FileAccess.get_sha256(path), "scope": "entire current scene, including existing manual edits"})

func _node_create(arguments: Dictionary) -> Variant:
	var parent := _node(arguments.get("parent_path", "."), true)
	if not _guard_node(parent, arguments, "expected_parent_id"):
		return null
	if not parent.scene_file_path.is_empty() and parent != EditorInterface.get_edited_scene_root():
		return _fail("instanced_node_protected", "Cannot add children inside an instanced scene.")
	var kind: Variant = arguments.get("type")
	if not kind in NODE_TYPES:
		return _fail("unsupported_type", "Node type is not in the native node allowlist.")
	if not _valid_name(arguments.get("name")):
		return null
	if parent.has_node(NodePath(arguments.name)):
		return _fail("name_exists", "A sibling with that name already exists.")
	var node: Node = ClassDB.instantiate(kind)
	node.name = arguments.name
	var root := EditorInterface.get_edited_scene_root()
	var history := get_undo_redo()
	history.create_action("AI: Create " + str(node.name), UndoRedo.MERGE_DISABLE, root)
	history.add_do_method(parent, "add_child", node, true)
	history.add_do_property(node, "owner", root)
	history.add_do_reference(node)
	history.add_undo_method(parent, "remove_child", node)
	history.commit_action()
	return _scene_result({"node": _node_info(node), "undoable": true})

func _owners(node: Node, output: Array) -> void:
	output.append({"node": node, "owner": node.owner})
	for child in node.get_children():
		_owners(child, output)

func _restore_owners(entries: Array) -> void:
	for entry in entries:
		if is_instance_valid(entry.node) and (entry.owner == null or is_instance_valid(entry.owner)):
			entry.node.owner = entry.owner

func _attach_node(parent: Node, node: Node, index: int, owners: Array) -> void:
	parent.add_child(node, true)
	parent.move_child(node, mini(index, parent.get_child_count() - 1))
	_restore_owners(owners)

func _move_node(node: Node, parent: Node, index: int, keep_global: bool, owners: Array) -> void:
	node.reparent(parent, keep_global)
	parent.move_child(node, mini(index, parent.get_child_count() - 1))
	_restore_owners(owners)

func _node_structure(operation: String, arguments: Dictionary) -> Variant:
	var node := _node(arguments.get("node_path"), true)
	if not _guard_node(node, arguments):
		return null
	var root := EditorInterface.get_edited_scene_root()
	if node == root and operation != "node_rename":
		return _fail("root_protected", "Root cannot be deleted, duplicated, or reparented.")
	if operation in ["node_rename", "node_reparent", "node_delete"] and not _guard_references(node, operation):
		return null
	var parent := node.get_parent()
	var history := get_undo_redo()
	if operation == "node_rename":
		if not _valid_name(arguments.get("name")):
			return null
		if parent.has_node(NodePath(arguments.name)) and parent.get_node(NodePath(arguments.name)) != node:
			return _fail("name_exists", "A sibling with that name already exists.")
		history.create_action("AI: Rename node", UndoRedo.MERGE_DISABLE, root)
		history.add_do_property(node, "name", arguments.name)
		history.add_undo_property(node, "name", node.name)
		history.commit_action()
		return _scene_result({"node": _node_info(node), "undoable": true})
	if operation == "node_delete":
		var owners := []
		_owners(node, owners)
		history.create_action("AI: Delete " + str(node.name), UndoRedo.MERGE_DISABLE, root)
		history.add_do_method(parent, "remove_child", node)
		history.add_undo_method(self, "_attach_node", parent, node, node.get_index(), owners)
		history.add_undo_reference(node)
		history.commit_action()
		return _scene_result({"deleted_node_path": arguments.node_path, "undoable": true})
	if operation == "node_duplicate":
		if not _valid_name(arguments.get("name")):
			return null
		if parent.has_node(NodePath(arguments.name)):
			return _fail("name_exists", "A sibling with that name already exists.")
		var duplicate := node.duplicate(Node.DUPLICATE_SIGNALS | Node.DUPLICATE_GROUPS | Node.DUPLICATE_SCRIPTS | Node.DUPLICATE_USE_INSTANTIATION)
		if duplicate == null:
			return _fail("duplicate_failed", "Godot could not duplicate this node.")
		duplicate.name = arguments.name
		var owners := []
		_duplicate_owners(node, duplicate, root, owners)
		history.create_action("AI: Duplicate " + str(node.name), UndoRedo.MERGE_DISABLE, root)
		history.add_do_method(self, "_attach_node", parent, duplicate, node.get_index() + 1, owners)
		history.add_do_reference(duplicate)
		history.add_undo_method(parent, "remove_child", duplicate)
		history.commit_action()
		return _scene_result({"node": _node_info(duplicate), "undoable": true})
	if operation == "node_reparent":
		var new_parent := _node(arguments.get("new_parent_path"), true)
		if not _guard_node(new_parent, arguments, "expected_new_parent_id"):
			return null
		if new_parent == node or node.is_ancestor_of(new_parent):
			return _fail("cycle_forbidden", "Cannot reparent into this node or its descendants.")
		if not new_parent.scene_file_path.is_empty() and new_parent != root:
			return _fail("instanced_node_protected", "Cannot reparent into an instanced scene.")
		if new_parent.has_node(NodePath(str(node.name))):
			return _fail("name_exists", "New parent already has a child with that name.")
		var owners := []
		_owners(node, owners)
		var keep: bool = arguments.get("keep_global_transform", true)
		var local_transform: Variant = node.transform if node is Node2D or node is Node3D else (node.position if node is Control else null)
		history.create_action("AI: Reparent " + str(node.name), UndoRedo.MERGE_DISABLE, root)
		history.add_do_method(self, "_move_node", node, new_parent, new_parent.get_child_count(), keep, owners)
		history.add_undo_method(self, "_move_node", node, parent, node.get_index(), keep, owners)
		if node is Node2D or node is Node3D:
			history.add_undo_property(node, "transform", local_transform)
		elif node is Control:
			history.add_undo_property(node, "position", local_transform)
		history.commit_action()
		return _scene_result({"node": _node_info(node), "undoable": true})
	return null

func _guard_references(changed: Node, operation: String) -> bool:
	var root := EditorInterface.get_edited_scene_root()
	var stack: Array[Node] = [root]
	var inspected := 0
	var affected := []
	while not stack.is_empty():
		var source: Node = stack.pop_back()
		inspected += 1
		if inspected > MAX_TREE_NODES:
			_fail("reference_conflict", "Scene is too large for bounded structural reference preflight.")
			return false
		if source is AnimationMixer:
			affected.append({"node_path": str(root.get_path_to(source)), "property": "animation tracks", "reason": "Animation track paths are not refactored by this bridge."})
		var properties := _native_properties(source)
		if not _error.is_empty():
			return false
		for property in properties:
			if int(properties[property].type) != TYPE_NODE_PATH:
				continue
			var reference: NodePath = source.get(property)
			if reference.is_empty():
				continue
			var resolved := source.get_node_or_null(NodePath(str(reference).get_slice(":", 0)))
			var source_inside := source == changed or changed.is_ancestor_of(source)
			var target_inside := resolved != null and (resolved == changed or changed.is_ancestor_of(resolved))
			if (operation == "node_delete" and target_inside and not source_inside) or (operation != "node_delete" and (source_inside or target_inside)):
				affected.append({"node_path": str(root.get_path_to(source)), "property": property, "value": str(reference)})
		var script: Script = source.get_script()
		if script != null:
			for property in script.get_script_property_list():
				if int(property.type) == TYPE_NODE_PATH or (int(property.type) == TYPE_OBJECT and int(property.usage) & PROPERTY_USAGE_EDITOR):
					affected.append({"node_path": str(root.get_path_to(source)), "property": str(property.name), "reason": "Custom script references are not read or refactored."})
		for child in source.get_children():
			stack.append(child)
	if not affected.is_empty():
		_fail("reference_conflict", "Structural change may invalidate references. Update them in the editor first; bridge does not refactor NodePaths, animation tracks or custom script references.")
		_error["details"] = {"references": affected.slice(0, 64)}
		return false
	return true

func _duplicate_owners(original: Node, duplicate: Node, root: Node, entries: Array) -> void:
	if original.owner == root:
		entries.append({"node": duplicate, "owner": root})
	for index in range(mini(original.get_child_count(), duplicate.get_child_count())):
		_duplicate_owners(original.get_child(index), duplicate.get_child(index), root, entries)

func _property_set(arguments: Dictionary) -> Variant:
	var node := _node(arguments.get("node_path"), true)
	if not _guard_node(node, arguments):
		return null
	var property: Variant = arguments.get("property")
	var properties := _native_properties(node)
	if not _error.is_empty():
		return null
	if not property is String or not properties.has(property) or not int(properties[property].type) in SCALAR_TYPES:
		return _fail("property_forbidden", "Only supported native editable scalar/vector/color/node-path properties may be set.")
	var value: Variant = _decode(arguments.get("value"), int(properties[property].type))
	if not _error.is_empty():
		return null
	if value is NodePath and not value.is_empty():
		var resolved := node.get_node_or_null(value)
		var root := EditorInterface.get_edited_scene_root()
		if resolved == null or (resolved != root and not root.is_ancestor_of(resolved)):
			return _fail("invalid_node_reference", "NodePath must resolve to an existing node within the edited scene.")
	var history := get_undo_redo()
	history.create_action("AI: Set " + property, UndoRedo.MERGE_DISABLE, EditorInterface.get_edited_scene_root())
	history.add_do_property(node, property, value)
	history.add_undo_property(node, property, node.get(property))
	history.commit_action()
	return _scene_result({"node": _node_info(node), "property": property, "value": _encode(node.get(property)), "undoable": true})

func _signal_edit(operation: String, arguments: Dictionary) -> Variant:
	var node := _node(arguments.get("node_path"), true)
	if not _guard_node(node, arguments):
		return null
	var target := _node(arguments.get("target_path"), true)
	if not _guard_node(target, arguments, "expected_target_id"):
		return null
	var signal_name: Variant = arguments.get("signal")
	var method: Variant = arguments.get("method")
	if not signal_name is String or not node.has_signal(signal_name) or not method is String or not target.has_method(method):
		return _fail("invalid_connection", "Signal and existing target method are required.")
	# Persistent callbacks must be script-defined on a non-tool script. Native
	# free/queue_free/set and lifecycle shortcuts would execute inside the editor.
	var target_script: Script = target.get_script()
	if target_script == null or target_script.is_tool() or ClassDB.class_has_method(target.get_class(), method):
		return _fail("unsafe_callback", "Only non-tool script-defined methods are supported; native callbacks are forbidden.")
	var script_method_found := false
	var current_script := target_script
	while current_script != null:
		if current_script.is_tool():
			return _fail("unsafe_callback", "Tool script callbacks are forbidden.")
		for method_info in current_script.get_script_method_list():
			if str(method_info.name) == method:
				script_method_found = true
		current_script = current_script.get_base_script()
	if not script_method_found:
		return _fail("unsafe_callback", "Method must be declared by the target's non-tool script.")
	var callback := Callable(target, method)
	var present := node.is_connected(signal_name, callback)
	if operation == "signal_connect" and present:
		return _fail("connection_exists", "That exact signal connection already exists.")
	if operation == "signal_disconnect" and not present:
		return _fail("connection_missing", "That exact signal connection does not exist.")
	var flags := CONNECT_PERSIST
	if present:
		for connection in node.get_signal_connection_list(signal_name):
			if connection.callable == callback:
				flags = int(connection.flags)
		if flags & CONNECT_PERSIST == 0:
			return _fail("connection_not_persistent", "Only saved scene connections can be disconnected.")
	var history := get_undo_redo()
	history.create_action("AI: " + operation, UndoRedo.MERGE_DISABLE, EditorInterface.get_edited_scene_root())
	if operation == "signal_connect":
		history.add_do_method(node, "connect", signal_name, callback, CONNECT_PERSIST)
		history.add_undo_method(node, "disconnect", signal_name, callback)
	else:
		history.add_do_method(node, "disconnect", signal_name, callback)
		history.add_undo_method(node, "connect", signal_name, callback, flags)
	history.commit_action()
	return _scene_result({"connected": operation == "signal_connect", "undoable": true})

func _source_text(path: String) -> String:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		_fail("file_missing", "Script file does not exist or is unreadable.")
		return ""
	if file.get_length() > MAX_BYTES:
		file.close()
		_fail("file_too_large", "Script is larger than 1 MiB.")
		return ""
	var text := file.get_as_text()
	file.close()
	return text

func _has_tool(source: String) -> bool:
	var regex := RegEx.new()
	regex.compile("(?m)@\\s*tool|\\bTool(?:Attribute)?\\b")
	return regex.search(source) != null

func _script_read(arguments: Dictionary) -> Variant:
	var path := _resource_path(arguments.get("path"), ["gd", "cs"])
	if path.is_empty():
		return null
	var source := _source_text(path)
	if not _error.is_empty():
		return null
	return {"path": path, "source": source, "sha256": FileAccess.get_sha256(path), "language": "C#" if path.get_extension().to_lower() == "cs" else "GDScript"}

func _script_write(arguments: Dictionary) -> Variant:
	var path := _resource_path(arguments.get("path"), ["gd", "cs"])
	if path.is_empty():
		return null
	var source: Variant = arguments.get("source")
	if not source is String or source.to_utf8_buffer().size() > MAX_BYTES or _contains_nul(source):
		return _fail("invalid_source", "source must be text, no NUL, maximum 1 MiB.")
	if _has_tool(source):
		return _fail("tool_script_forbidden", "Tool scripts can execute in the editor; v0.2 does not write them.")
	if not DirAccess.dir_exists_absolute(path.get_base_dir()):
		return _fail("parent_missing", "Parent directory must already exist.")
	var exists := FileAccess.file_exists(path)
	if exists:
		for open_script in EditorInterface.get_script_editor().get_open_scripts():
			if open_script.resource_path == path:
				return _fail("script_buffer_conflict", "Script is open in the editor. Save and close its script tab before overwriting disk content.")
	if exists and (arguments.get("overwrite", false) != true or arguments.get("expected_sha256", "") != FileAccess.get_sha256(path)):
		return _fail("disk_conflict", "Existing scripts need overwrite=true and matching expected_sha256.")
	var temporary := path.get_base_dir().path_join(".ai_bridge_" + _session_id + ".tmp")
	if _has_symlink(temporary):
		return _fail("symlink_forbidden", "Temporary file path is a symlink.")
	var file := FileAccess.open(temporary, FileAccess.WRITE)
	if file == null:
		return _fail("write_failed", "Cannot create script temporary file.")
	file.store_string(source)
	file.flush()
	file.close()
	if _has_symlink(path) or (exists and arguments.get("expected_sha256", "") != FileAccess.get_sha256(path)) or (not exists and FileAccess.file_exists(path)):
		DirAccess.remove_absolute(temporary)
		return _fail("disk_conflict", "Script changed while preparing the write.")
	if DirAccess.rename_absolute(temporary, path) != OK:
		return _fail("write_failed", "Cannot atomically replace script file.")
	EditorInterface.get_resource_filesystem().update_file(path)
	return {"path": path, "sha256": FileAccess.get_sha256(path), "language": "C#" if path.get_extension().to_lower() == "cs" else "GDScript", "undoable": false, "build_performed": false, "attached": false, "created": not exists}

func _script_attach(arguments: Dictionary) -> Variant:
	var node := _node(arguments.get("node_path"), true)
	if not _guard_node(node, arguments):
		return null
	var path := _resource_path(arguments.get("script_path"), ["gd", "cs"])
	if path.is_empty():
		return null
	var source := _source_text(path)
	if not _error.is_empty():
		return null
	if _has_tool(source):
		return _fail("tool_script_forbidden", "Attaching @tool or [Tool] scripts is disabled.")
	if path.get_extension().to_lower() == "cs" and not ClassDB.class_exists("CSharpScript"):
		return _fail("dotnet_required", "C# attachment requires the Godot .NET editor and a built project.")
	var previous: Script = node.get_script()
	if previous != null and previous.resource_path != path:
		return _fail("script_exists", "Refusing to replace an existing script and risk losing its exported values. Detach it explicitly in the editor first.")
	var script := ResourceLoader.load(path, "Script", ResourceLoader.CACHE_MODE_REUSE) as Script
	if script == null:
		return _fail("script_load_failed", "Script could not be loaded. Check syntax, language and .NET build.")
	if script.is_tool():
		return _fail("tool_script_forbidden", "Tool scripts, including inherited tool scripts, are disabled.")
	if not node.is_class(script.get_instance_base_type()):
		return _fail("script_base_mismatch", "Script base type is incompatible with the target node.")
	var history := get_undo_redo()
	history.create_action("AI: Attach script", UndoRedo.MERGE_DISABLE, EditorInterface.get_edited_scene_root())
	history.add_do_method(node, "set_script", script)
	history.add_undo_method(node, "set_script", node.get_script())
	history.commit_action()
	return _scene_result({"node": _node_info(node), "language": "C#" if path.get_extension().to_lower() == "cs" else "GDScript", "undoable": true})

func _resource_create(arguments: Dictionary) -> Variant:
	var path := _new_file_path(arguments, ["tres"])
	if path.is_empty():
		return null
	var kind: Variant = arguments.get("type")
	if not kind in RESOURCE_TYPES:
		return _fail("unsupported_type", "Resource type is not in the safe native allowlist.")
	var properties: Variant = arguments.get("properties", {})
	if not properties is Dictionary:
		return _fail("invalid_properties", "properties must be an object.")
	var resource: Resource = ClassDB.instantiate(kind)
	var native := _native_properties(resource)
	if not _error.is_empty():
		return null
	for property in properties:
		if not native.has(property) or not int(native[property].type) in SCALAR_TYPES:
			return _fail("property_forbidden", "Resource properties must be supported native scalar/vector/color values.")
		var value: Variant = _decode(properties[property], int(native[property].type))
		if not _error.is_empty():
			return null
		if value is NodePath and not value.is_empty():
			return _fail("invalid_node_reference", "Resource creation has no scene-node context for nonempty NodePaths.")
		resource.set(property, value)
	if ResourceSaver.save(resource, path) != OK:
		return _fail("save_failed", "Failed to save the new resource.")
	EditorInterface.get_resource_filesystem().update_file(path)
	return {"path": path, "type": resource.get_class(), "sha256": FileAccess.get_sha256(path), "undoable": false}

func _safe_resource_declarations(source: String) -> bool:
	# Variant text also supports Object(Class, ...) and Resource(path), which
	# could construct an extension or load an unvalidated dependency inline.
	var inline_objects := RegEx.new()
	inline_objects.compile("\\b(?:Object|Resource|ExtResource)\\b")
	if inline_objects.search(source) != null:
		_fail("unsafe_resource", "Inline Object/Resource constructors are forbidden; use curated SubResource declarations only.")
		return false
	if "script" in source.to_lower() or "ext_resource" in source.to_lower():
		_fail("unsafe_resource", "Only native .tres without scripts or external dependencies are supported.")
		return false
	var declaration := RegEx.new()
	declaration.compile('^\\[(gd_resource|sub_resource)\\s+type="([A-Za-z0-9_]+)"(?:\\s|\\])')
	var header_seen := false
	for line in source.split("\n"):
		var stripped := line.strip_edges()
		if not (stripped.begins_with("[gd_resource") or stripped.begins_with("[sub_resource")):
			continue
		var match_result := declaration.search(stripped)
		if match_result == null:
			_fail("unsafe_resource", "Resource declarations must use the supported native text format.")
			return false
		var kind := match_result.get_string(2)
		if not kind in RESOURCE_TYPES or not ClassDB.class_exists(kind) or ClassDB.class_get_api_type(kind) != ClassDB.API_CORE:
			_fail("unsupported_resource_type", "Resource and subresource declarations must be curated built-in core types; extensions are excluded before loading.")
			return false
		if match_result.get_string(1) == "gd_resource":
			header_seen = true
	if not header_seen:
		_fail("unsafe_resource", "Missing native resource type declaration.")
	return header_seen

func _resource_assign(arguments: Dictionary) -> Variant:
	var node := _node(arguments.get("node_path"), true)
	if not _guard_node(node, arguments):
		return null
	var property: Variant = arguments.get("property")
	var native := _native_properties(node)
	if not _error.is_empty():
		return null
	if not property is String or not native.has(property) or int(native[property].type) != TYPE_OBJECT or native[property].hint != PROPERTY_HINT_RESOURCE_TYPE:
		return _fail("property_forbidden", "Property must be a native editor Resource property.")
	var path := _resource_path(arguments.get("resource_path"), ["tres", "png", "jpg", "jpeg", "webp"])
	if path.is_empty():
		return null
	if not FileAccess.file_exists(path):
		return _fail("file_missing", "Resource does not exist.")
	if path.get_extension().to_lower() == "tres":
		var source := _source_text(path)
		if not _error.is_empty():
			return null
		# A conservative safe subset: no embedded/custom scripts or external dependencies.
		if not _safe_resource_declarations(source):
			return null
	var resource := ResourceLoader.load(path, "", ResourceLoader.CACHE_MODE_REUSE)
	if resource != null and not _guard_builtin(resource):
		return null
	if resource == null or resource.get_script() != null or (not resource.get_class() in RESOURCE_TYPES and not resource is Texture2D):
		return _fail("unsupported_resource", "Resource type is outside the native safe allowlist.")
	var matches := false
	for accepted in str(native[property].hint_string).split(","):
		if resource.is_class(accepted):
			matches = true
	if not matches:
		return _fail("resource_type_mismatch", "Resource class is incompatible with the property.")
	var history := get_undo_redo()
	history.create_action("AI: Assign resource", UndoRedo.MERGE_DISABLE, EditorInterface.get_edited_scene_root())
	history.add_do_property(node, property, resource)
	history.add_undo_property(node, property, node.get(property))
	history.commit_action()
	return _scene_result({"node": _node_info(node), "property": property, "resource": _encode(resource), "undoable": true})

func _play(operation: String, arguments: Dictionary) -> Variant:
	# Godot play may save scenes automatically. Require all tabs to be clean by
	# observed history, and don't use play as an implicit way to overwrite files.
	for root in EditorInterface.get_open_scene_roots():
		var path := root.scene_file_path
		var history := _history(root)
		var saved: int = _saved_versions.get(str(root.get_instance_id()), -1)
		if path.is_empty() or history == null or EditorInterface.is_object_edited(root) or history.get_version() != saved:
			_fail("unsaved_changes", "Save open scenes explicitly before starting play.")
			_error["details"] = {"path": path, "node_id": str(root.get_instance_id()), "history_version": history.get_version() if history != null else -1, "saved_version": saved, "object_edited": EditorInterface.is_object_edited(root)}
			return null
		if _disk_hashes.has(path) and (not FileAccess.file_exists(path) or _disk_hashes[path] != FileAccess.get_sha256(path)):
			return _fail("disk_conflict", "An open scene changed on disk; play is blocked to avoid implicit overwrite.")
	var path := ""
	if operation == "play_custom":
		path = _resource_path(arguments.get("path"), ["tscn"])
		if path.is_empty():
			return null
		if not FileAccess.file_exists(path):
			return _fail("file_missing", "Custom scene file does not exist.")
	elif operation == "play_main":
		path = str(ProjectSettings.get_setting("application/run/main_scene", ""))
		if path.is_empty():
			return _fail("main_scene_missing", "Project has no main scene configured.")
	elif EditorInterface.get_edited_scene_root() == null:
		return _fail("no_scene", "No scene is open.")
	match operation:
		"play_current":
			EditorInterface.play_current_scene()
		"play_main":
			EditorInterface.play_main_scene()
		"play_custom":
			EditorInterface.play_custom_scene(path)
	await get_tree().process_frame
	return {"play_requested": true, "playing": EditorInterface.is_playing_scene(), "playing_scene": EditorInterface.get_playing_scene(), "scene": _scene_info()}
