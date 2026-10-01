using Godot;

[GlobalClass]
public partial class LabStats : Resource
{
    [Export] public int Health { get; set; } = 100;
    [Export] public Resource? Child { get; set; }
    [Export] public Godot.Collections.Array<Resource> Items { get; set; } = new();
}
