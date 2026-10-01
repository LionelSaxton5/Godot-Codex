using Godot;

public partial class Session : Node
{
    public int EmittedCount { get; set; }
    public void ResetRun() => EmittedCount = 0;
}
