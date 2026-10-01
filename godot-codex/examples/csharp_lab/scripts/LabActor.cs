using Godot;

public partial class LabActor : Node2D
{
    [Export] public LabStats Stats { get; set; } = null!;
}
