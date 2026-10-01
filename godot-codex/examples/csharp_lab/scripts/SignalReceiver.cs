using Godot;

/// <summary>A replaceable receiver for a longer-lived custom C# emitter.</summary>
public partial class SignalReceiver : Node
{
    public PulseEmitter Emitter { get; set; } = null!;
    public int Total { get; private set; }
    private PulseEmitter? _subscribedEmitter;
    private PulseEmitter.PulseEventHandler? _handler;

    public override void _EnterTree()
    {
        _subscribedEmitter = Emitter;
        int multiplier = 2; // Deliberately captures a local to exercise cleanup.
        _handler = value => Total += value * multiplier;
        _subscribedEmitter.Pulse += _handler;
    }

    public override void _ExitTree()
    {
        if (GodotObject.IsInstanceValid(_subscribedEmitter) && _handler is not null)
            _subscribedEmitter!.Pulse -= _handler;
        _subscribedEmitter = null;
        _handler = null;
    }

    public void Receive(int value) => Total += value;
}
