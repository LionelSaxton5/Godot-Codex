---
name: godot-signals
description: "Implement or debug Godot signal wiring and C# event lifetimes, including duplicate callbacks, missed startup emissions, scene reloads, and captured lambdas. Use for communication between Godot nodes and Resources; not generic networking or a mandatory global event bus."
---

# Godot signals

Trace the emitter, signal, connection, receiver, and lifetime before changing architecture. Work in the project's existing language. C# examples target Godot 4.6; standard Godot cannot compile or run them.

## Diagnose the connection, not just the callback

Read relevant scripts and `.tscn` `[connection]` records. Establish:

- Who creates the connection: the saved scene, its parent, or the receiver?
- When is it established relative to the first emission?
- Can the emitter outlive the receiver, or can either leave and re-enter the tree?
- Is the callback connected by two different routes, or is the signal emitted twice?
- Is the receiver already queued for deletion, hidden, or otherwise logically inactive?

For duplicates, instrument emissions and callback counts with instance IDs. In C#, a custom event can retain an engine-to-managed bridge in the native connection list even without managed subscribers; compare behavior and the baseline rather than equating native connection count with subscriber count. Do not mask a double emission with an arbitrary boolean or disconnect someone else's listener. Use one authoritative wiring route for each relationship.

## Pick native scene or code wiring

Use persistent scene connections for stable relationships authored within a reusable scene. Use code for runtime instances, injected dependencies, conditional subscriptions, or connections with deliberate lifetime control. Preserve existing editor connections unless changing them is part of the fix. [Using signals](https://docs.godotengine.org/en/4.6/getting_started/step_by_step/signals.html)

Use direct methods for commands requiring a specific recipient or return value; signals are useful for notifying observers. A local gameplay signal does not justify adding an Autoload event bus.

For explicit `Connect`, retain the actual `Callable`, check `IsConnected` when setup may repeat, and inspect connection errors. Repeatedly constructing distinct lambdas creates distinct callbacks; it is not duplicate prevention. `OneShot` means one emission, while `Deferred` changes callback timing. Reference-counted connections are not a general cure for repeated initialization. [Object connections](https://docs.godotengine.org/en/4.6/classes/class_object.html)

For GDScript implementations, read [GDScript lifetime patterns](references/gdscript-patterns.md). Use the matching language rather than translating C# event syntax literally.

## C# rules that change the implementation

Prefer generated typed events for built-in signals. Declare custom Godot signals with `[Signal] public delegate void NameEventHandler(...)` and emit through `EmitSignal(SignalName.Name, ...)`; use Variant-compatible parameters. Build after adding a custom signal so the editor can discover it.

Do not assume receiver destruction always disconnects C# subscriptions: custom signals connected with `+=` and captured lambdas need particular care. Store delegates for unsubscription. Read [C# lifetime patterns](references/csharp-lifetimes.md) before wiring a long-lived emitter to a replaceable screen, actor, or scene. [C# signal reference](https://docs.godotengine.org/en/4.6/tutorials/scripting/c_sharp/c_sharp_signals.html)

## Verify the lifecycle

Test normal emission, repeated setup, receiver removal/freeing, scene reload, and emitter-first destruction as relevant. If nodes can re-enter, verify subscription restoration without accumulating handlers. Test a startup signal before and after adding the scene to the tree. A deferred callback or await must also respect the caller's lifetime.

Report connection ownership, cleanup point, observed callback count, and whether C# compilation/runtime verification was possible. Do not report a clean standard-editor run as proof that C# subscriptions work.

Sources linked above checked against Godot 4.6 on 2026-09-30.
