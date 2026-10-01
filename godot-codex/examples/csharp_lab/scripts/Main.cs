using Godot;

public partial class Main : Node2D
{
    [Signal] public delegate void PulseEventHandler(int value);
    public int Count { get; private set; }
    public Label Counter { get; private set; } = null!;
    public Button FireButton { get; private set; } = null!;
    public TileMapLayer TileLayer { get; private set; } = null!;

    public override void _Ready()
    {
        RenderingServer.SetDefaultClearColor(new Color("111a2b"));
        BuildTiles();
        BuildUi();
        Pulse += OnPulse;
        FireButton.Pressed += EmitPulse;
        FireButton.GrabFocus();
    }

    public override void _ExitTree()
    {
        Pulse -= OnPulse;
        if (GodotObject.IsInstanceValid(FireButton))
            FireButton.Pressed -= EmitPulse;
    }

    private void BuildTiles()
    {
        var image = Image.CreateEmpty(16, 16, false, Image.Format.Rgba8);
        image.Fill(new Color("386d77"));
        for (int x = 0; x < 16; x++)
        {
            image.SetPixel(x, 0, new Color("6ec9bd"));
            image.SetPixel(0, x, new Color("6ec9bd"));
        }
        var atlas = new TileSetAtlasSource
        {
            Texture = ImageTexture.CreateFromImage(image),
            TextureRegionSize = new Vector2I(16, 16)
        };
        atlas.CreateTile(Vector2I.Zero);
        var tiles = new TileSet { TileSize = new Vector2I(16, 16) };
        int sourceId = tiles.AddSource(atlas);
        TileLayer = new TileMapLayer
        {
            Name = "Ground", TileSet = tiles, Position = new Vector2(32, 248)
        };
        AddChild(TileLayer);
        for (int x = 0; x < 36; x++)
            for (int y = 0; y < 4; y++)
                if (y > 0 || x % 5 != 0)
                    TileLayer.SetCell(new Vector2I(x, y), sourceId, Vector2I.Zero);
    }

    private void BuildUi()
    {
        var canvas = new CanvasLayer { Name = "HUD" };
        AddChild(canvas);
        var margin = new MarginContainer { Name = "Margin" };
        canvas.AddChild(margin);
        margin.SetAnchorsAndOffsetsPreset(Control.LayoutPreset.FullRect);
        foreach (string side in new[] { "left", "top", "right", "bottom" })
            margin.AddThemeConstantOverride("margin_" + side, 28);
        var stack = new VBoxContainer { Name = "Stack" };
        stack.AddThemeConstantOverride("separation", 10);
        margin.AddChild(stack);
        var heading = new Label { Text = "GODOT / C# LAB" };
        heading.AddThemeFontSizeOverride("font_size", 24);
        stack.AddChild(heading);
        var subtitle = new Label
        {
            Text = "Signals · Scenes · Resources · Autoload · TileMapLayer"
        };
        subtitle.AddThemeFontSizeOverride("font_size", 14);
        stack.AddChild(subtitle);
        Counter = new Label { Name = "Counter", Text = "Pulses received: 0" };
        stack.AddChild(Counter);
        FireButton = new Button
        {
            Name = "EmitPulse", Text = "Emit a typed signal  [Enter / Space]",
            SizeFlagsHorizontal = Control.SizeFlags.ShrinkBegin
        };
        stack.AddChild(FireButton);
        var note = new Label
        {
            Text = "640 × 360 viewport / integer scale / 16 px tiles\nC# event cleanup is tested across tree exit and re-entry."
        };
        note.AddThemeFontSizeOverride("font_size", 12);
        stack.AddChild(note);
    }

    private void EmitPulse() => EmitSignal(SignalName.Pulse, Count + 1);

    private void OnPulse(int value)
    {
        Count = value;
        GetNode<Session>("/root/Session").EmittedCount++;
        Counter.Text = $"Pulses received: {value}";
    }
}
