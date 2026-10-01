using Godot;

public partial class PulseEmitter : Node
{
    [Signal] public delegate void PulseEventHandler(int value);
    public void Publish(int value) => EmitSignal(SignalName.Pulse, value);
}
