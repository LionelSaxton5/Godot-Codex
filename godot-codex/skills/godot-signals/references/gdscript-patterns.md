# GDScript signal lifetime patterns

Godot 4 typed signal, stable callable, one authoritative connection owner:

```gdscript
# emitter.gd
extends Node
signal damaged(amount: int)

func hit(amount: int) -> void:
    damaged.emit(amount)
```

```gdscript
# receiver.gd: emitter is injected before this node enters the tree.
extends Node
var emitter: Node
var total: int = 0

func _enter_tree() -> void:
    if is_instance_valid(emitter) and not emitter.damaged.is_connected(_on_damaged):
        emitter.damaged.connect(_on_damaged)

func _exit_tree() -> void:
    if is_instance_valid(emitter) and emitter.damaged.is_connected(_on_damaged):
        emitter.damaged.disconnect(_on_damaged)

func _on_damaged(amount: int) -> void:
    total += amount
```

This deliberately ties listening to tree membership. `_ready` alone will not subscribe again on ordinary remove/re-add because ready is normally called once. Use `_ready` when dependencies require child readiness and re-entry is not part of the lifecycle, or deliberately request readiness and test that design. For an `@onready` child reference, it is not initialized during the first `_enter_tree`; choose a compatible injection/lookup point rather than copying this pattern unchanged.

GDScript object-bound connections are normally cleaned up when a receiver is freed. Exiting the tree does not free the object; explicit disconnect above prevents a detached receiver handling global events. A lambda capture has different lifetime considerations: retain the Callable if later disconnecting it, and never access a freed captured Node without validating it. A one-shot connection remains until one emission or disconnection, not until its conceptual gameplay task is cancelled.

The bundled `examples/native_lab/tests/test_native.gd` executes duplicate-guard, delivery, receiver-free, captured-Callable cleanup, explicit exit/re-entry and emitter-first teardown checks. The C# fixture tests corresponding event lifecycles. Avoid treating that as evidence for every lambda/await arrangement.

[Godot 4.6 signals tutorial](https://docs.godotengine.org/en/4.6/getting_started/step_by_step/signals.html), [Object connections](https://docs.godotengine.org/en/4.6/classes/class_object.html). Checked 2026-09-30.
