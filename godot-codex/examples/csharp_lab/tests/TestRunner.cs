using Godot;
using System;
using System.Collections.Generic;
using System.Threading.Tasks;

/// <summary>Executable integration tests against the real Godot .NET runtime.</summary>
public partial class TestRunner : Node
{
    private readonly List<string> _failures = new();
    private int _checks;

    private void Expect(bool condition, string message)
    {
        _checks++;
        if (condition) return;
        _failures.Add(message);
        GD.PushError(message);
    }

    public override async void _Ready()
    {
        try
        {
            TestSignals();
            TestPackedOwnership();
            TestResources();
            await TestUiAndAutoload();
        }
        catch (Exception error)
        {
            _failures.Add(error.ToString());
            GD.PushError(error.ToString());
        }
        GD.Print("GODOT_CSHARP_TESTS=" + System.Text.Json.JsonSerializer.Serialize(new
        {
            checks = _checks, failures = _failures, passed = _failures.Count == 0
        }));
        GetTree().Quit(_failures.Count == 0 ? 0 : 1);
    }

    private void TestSignals()
    {
        var emitter = new PulseEmitter();
        AddChild(emitter);
        // A custom C# signal has an engine-to-managed bridge even with no listeners.
        int bridgeCount = emitter.GetSignalConnectionList(PulseEmitter.SignalName.Pulse).Count;
        var receiver = new SignalReceiver { Emitter = emitter };
        AddChild(receiver);
        emitter.Publish(3);
        Expect(receiver.Total == 6, "typed custom event and captured delegate deliver once");
        RemoveChild(receiver);
        Expect(emitter.GetSignalConnectionList(PulseEmitter.SignalName.Pulse).Count == bridgeCount,
            "tree exit retains only the engine-to-managed signal bridge");
        emitter.Publish(10);
        Expect(receiver.Total == 6, "detached receiver no longer gets updates");
        AddChild(receiver);
        emitter.Publish(2);
        Expect(receiver.Total == 10, "tree re-entry restores exactly one subscription");
        receiver.Free();
        Expect(emitter.GetSignalConnectionList(PulseEmitter.SignalName.Pulse).Count == bridgeCount,
            "freed receiver leaves no extra native connections");
        emitter.Publish(100);
        Expect(receiver.Total == 10, "freed receiver gets no captured managed callbacks");

        var namedReceiver = new SignalReceiver(); // Off-tree: no event subscription.
        var callable = Callable.From<int>(namedReceiver.Receive);
        for (int i = 0; i < 2; i++)
            if (!emitter.IsConnected(PulseEmitter.SignalName.Pulse, callable))
                Expect(emitter.Connect(PulseEmitter.SignalName.Pulse, callable) == Error.Ok,
                    "explicit custom signal Connect succeeds");
        Expect(emitter.GetSignalConnectionList(PulseEmitter.SignalName.Pulse).Count == bridgeCount + 1,
            "IsConnected guard prevents duplicate callbacks");
        emitter.Publish(5);
        Expect(namedReceiver.Total == 5, "named Callable receives one emission");
        namedReceiver.Free();
        Expect(emitter.GetSignalConnectionList(PulseEmitter.SignalName.Pulse).Count == bridgeCount,
            "Connect named-method receiver cleanup is automatic");
        emitter.Publish(100);
        emitter.Free();

        var firstEmitter = new PulseEmitter();
        AddChild(firstEmitter);
        var finalReceiver = new SignalReceiver { Emitter = firstEmitter };
        AddChild(finalReceiver);
        firstEmitter.Free();
        finalReceiver.Free();
        Expect(!GodotObject.IsInstanceValid(firstEmitter)
            && !GodotObject.IsInstanceValid(finalReceiver),
            "emitter-first destruction tolerates guarded unsubscribe");
    }

    private void TestPackedOwnership()
    {
        var root = new Node { Name = "PackedRoot" };
        var owned = new Node { Name = "Owned" };
        root.AddChild(owned);
        owned.Owner = root;
        var transient = new Node { Name = "Transient" };
        root.AddChild(transient);
        var packed = new PackedScene();
        Expect(packed.Pack(root) == Error.Ok, "PackedScene.Pack succeeds");
        var instance = packed.Instantiate();
        Expect(instance.HasNode("Owned"), "owned child is serialized");
        Expect(!instance.HasNode("Transient"), "parentage alone does not serialize child");
        instance.Free();
        root.Free();
    }

    private void TestResources()
    {
        var template = GD.Load<LabStats>("res://resources/stats.tres");
        var cached = GD.Load<LabStats>("res://resources/stats.tres");
        Expect(template.GetInstanceId() == cached.GetInstanceId(), "Resource load cache preserves identity");
        var duplicate = (LabStats)template.Duplicate(true);
        duplicate.Health = 8;
        Expect(template.Health == 100 && duplicate.Health == 8, "Resource scalar copy isolates mutation");

        var child = new LabStats { Health = 40 };
        var graph = new LabStats { Child = child };
        graph.Items.Add(child);
        graph.Items.Add(template); // External resource, deliberately shared by Internal mode.
        var shallow = (LabStats)graph.Duplicate();
        Expect(shallow.Child!.GetInstanceId() == child.GetInstanceId(), "shallow copy retains Resource identity");
        var deep = (LabStats)graph.Duplicate(true);
        Expect(deep.Child!.GetInstanceId() != child.GetInstanceId(), "deep copy duplicates internal Resource");
        Expect(deep.Child.GetInstanceId() == deep.Items[0].GetInstanceId(), "deep copy preserves aliases across array and property");
        Expect(deep.Items[1].GetInstanceId() == template.GetInstanceId(), "deep Internal mode retains external Resource");
        var all = (LabStats)graph.DuplicateDeep(Resource.DeepDuplicateMode.All);
        Expect(all.Items[1].GetInstanceId() != template.GetInstanceId(), "deep All mode duplicates external Resource");
        deep.Items.Clear();
        Expect(graph.Items.Count == 2, "deep copy isolates collection mutation");

        var scene = GD.Load<PackedScene>("res://scenes/actor.tscn");
        var actorA = scene.Instantiate<LabActor>();
        var actorB = scene.Instantiate<LabActor>();
        Expect(actorA.Stats.GetInstanceId() != actorB.Stats.GetInstanceId(), "Local To Scene creates unique per-instance Resources");
        actorA.Stats.Health = 1;
        Expect(actorB.Stats.Health == 100, "scene-local Resource mutation is isolated");
        actorA.Free();
        actorB.Free();
    }

    private async Task TestUiAndAutoload()
    {
        var session = GetNode<Session>("/root/Session");
        Expect(session.IsInsideTree(), "C# Autoload enters before test scene");
        session.ResetRun();
        var scene = GD.Load<PackedScene>("res://scenes/main.tscn");
        var lab = scene.Instantiate<Main>();
        AddChild(lab);
        await ToSignal(GetTree(), SceneTree.SignalName.ProcessFrame);
        lab.FireButton.EmitSignal(Button.SignalName.Pressed);
        Expect(lab.Count == 1, "built-in Button.Pressed routes through typed C# signal once");
        Expect(session.EmittedCount == 1, "Autoload records run state");
        Expect(lab.Counter.Text == "Pulses received: 1", "Control label reflects custom signal");
        Expect(lab.FireButton.FocusMode == Control.FocusModeEnum.All && lab.FireButton.HasFocus(),
            "button receives initial keyboard focus");

        // Exercise Godot's GUI action path, not only manual signal emission.
        Input.ParseInputEvent(new InputEventAction { Action = "ui_accept", Pressed = true });
        await ToSignal(GetTree(), SceneTree.SignalName.ProcessFrame);
        Input.ParseInputEvent(new InputEventAction { Action = "ui_accept", Pressed = false });
        await ToSignal(GetTree(), SceneTree.SignalName.ProcessFrame);
        Expect(lab.Count == 2, "focused button responds once to UI accept input");
        Expect(lab.TileLayer.GetUsedCells().Count == 136, "TileMapLayer paints expected cells");
        var cell = new Vector2I(4, 2);
        Expect(lab.TileLayer.LocalToMap(lab.TileLayer.MapToLocal(cell)) == cell, "TileMapLayer coordinate conversion roundtrip");
        Expect(ProjectSettings.GetSetting("display/window/stretch/mode").AsString() == "viewport",
            "viewport stretch is configured");
        Expect(ProjectSettings.GetSetting("display/window/stretch/scale_mode").AsString() == "integer",
            "integer scaling is configured");
        lab.Free();
        var second = scene.Instantiate<Main>();
        AddChild(second);
        await ToSignal(GetTree(), SceneTree.SignalName.ProcessFrame);
        second.FireButton.EmitSignal(Button.SignalName.Pressed);
        Expect(session.EmittedCount == 3, "Autoload persists while replacement scene starts clean");
        Expect(second.Count == 1, "replacement scene has no stale or duplicate subscriptions");
        second.Free();
    }
}
