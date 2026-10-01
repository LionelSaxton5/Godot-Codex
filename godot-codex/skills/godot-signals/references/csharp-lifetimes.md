# C# signal lifetime patterns

These focused examples assume a Godot 4.6 .NET project. They have no relationship to C# events in another game engine. Adapt class names, paths, and export assignments to the actual scene.

## Custom emitter and replaceable listener

An Autoload named `RunSession` can publish score changes. Its subscribers should not be kept alive accidentally after changing scenes.

```csharp
// RunSession.cs
using Godot;

public partial class RunSession : Node
{
    [Signal]
    public delegate void ScoreChangedEventHandler(int score);

    public int Score { get; private set; }

    public void AddScore(int amount)
    {
        Score += amount;
        EmitSignal(SignalName.ScoreChanged, Score);
    }
}
```

```csharp
// ScoreLabel.cs, attached to a Label in a replaceable scene.
using Godot;

public partial class ScoreLabel : Label
{
    private RunSession? _session;

    public override void _EnterTree()
    {
        _session = GetNode<RunSession>("/root/RunSession");
        _session.ScoreChanged += OnScoreChanged;
        OnScoreChanged(_session.Score);
    }

    public override void _ExitTree()
    {
        if (GodotObject.IsInstanceValid(_session))
            _session!.ScoreChanged -= OnScoreChanged;
        _session = null;
    }

    private void OnScoreChanged(int score) => Text = score.ToString();
}
```

The entry/exit pair defines a subscription only while this listener is in the tree. Initial rendering reads current state so a missed historical notification cannot leave the label blank. An exported emitter reference is equally valid when it is scene-supplied; the absolute path here is specifically for a registered Autoload.

Avoid mixing `_Ready` subscription with `_ExitTree` cleanup for nodes expected to re-enter: `_Ready` normally runs only once. If child initialization is required, retain explicit activation/deactivation methods or deliberately request readiness again; do not move child-dependent work blindly into `_EnterTree`. [Node lifecycle](https://docs.godotengine.org/en/4.6/classes/class_node.html)

## Captured lambdas need the same delegate

For a row-specific button callback, retain both emitter and delegate. Calling `-=` with a newly written lambda does not remove the original. The button below is supplied in the Inspector before tree entry.

```csharp
using Godot;
using System;

public partial class ChoiceRow : Control
{
    [Export] public Button ChooseButton { get; set; } = null!;
    [Export] public string ChoiceId { get; set; } = "";

    private Button? _button;
    private Action? _chooseHandler;

    public override void _EnterTree()
    {
        _button = ChooseButton;
        string idForThisEntry = ChoiceId;
        _chooseHandler = () => GD.Print($"Selected {idForThisEntry}");
        _button.Pressed += _chooseHandler;
    }

    public override void _ExitTree()
    {
        if (_chooseHandler is not null && GodotObject.IsInstanceValid(_button))
            _button!.Pressed -= _chooseHandler;
        _chooseHandler = null;
        _button = null;
    }
}
```

This captures a value per entry; if a pooled row changes its binding while remaining in the tree, explicitly unbind and rebind. Prefer a named method when no captured value is needed.

Wrapping a capturing lambda in `Callable.From` does not fix its receiver identity. A custom signal connected through `Connect` to a named receiver method can use Godot's automatic receiver cleanup, but explicit cleanup may still be needed on tree exit. Emitter destruction reliably ends its connections. [C# cleanup exceptions](https://docs.godotengine.org/en/4.6/tutorials/scripting/c_sharp/c_sharp_signals.html)

## Idempotent explicit connections

Use `Connect` when signals originate in GDScript or flags are required. Keep a stable callable for checking and disconnecting:

```csharp
// Fields in the receiver: private Callable _pressed;
// Initialize once: _pressed = Callable.From(OnPressed);
if (!button.IsConnected(Button.SignalName.Pressed, _pressed))
{
    Error result = button.Connect(Button.SignalName.Pressed, _pressed);
    if (result != Error.Ok)
        GD.PushError($"Connection failed: {result}");
}

// During the matching cleanup, while button is still valid:
if (button.IsConnected(Button.SignalName.Pressed, _pressed))
    button.Disconnect(Button.SignalName.Pressed, _pressed);
```

This is an alternative to event subscription, not an extra connection to layer over it. If the saved scene already owns this relationship, inspect or repair that record instead. [Connection API](https://docs.godotengine.org/en/4.6/classes/class_object.html)

## Pause, deletion, and awaits

Paused processing does not inherently disable signal callbacks. Gate a gameplay action when its logical state forbids it. After `QueueFree`, a node can still exist until frame cleanup, so remove it from active registries immediately if needed. For `await ToSignal(...)`, define what happens if the expected emission never occurs or the screen closes; do not assume a signal await is a cancellation mechanism. Use the project's cancellation/generation checks before touching UI after asynchronous work.

Test with a callback counter: add/remove the listener twice, then emit once and require exactly one active callback. Free the listener, emit again, and require no access to disposed objects. Test the actual .NET runtime for these cases.

Official sources checked 2026-09-30: links above and [pausing behavior](https://docs.godotengine.org/en/4.6/tutorials/scripting/pausing_games.html).
