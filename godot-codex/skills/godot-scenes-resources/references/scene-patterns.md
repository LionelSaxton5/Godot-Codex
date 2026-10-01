# Scene boundaries and C# patterns

Read this for spawning, serialization ownership, or persistent-state decisions. These are adaptation examples, not files to install unchanged. C# compilation requires the Godot .NET editor and a compatible SDK.

## Spawn through a PackedScene

Attach this script to the `Node2D` that will parent the enemy instances. Assign a scene whose root inherits `Node2D` to `EnemyScene` in the Inspector.

```csharp
using Godot;

public partial class EnemySpawner : Node2D
{
    [Export] public PackedScene EnemyScene { get; set; } = null!;

    public Node2D SpawnAt(Vector2 worldPosition)
    {
        if (EnemyScene is null)
            throw new System.InvalidOperationException("Assign EnemyScene.");

        var enemy = EnemyScene.Instantiate<Node2D>();
        enemy.Position = ToLocal(worldPosition);
        // Assign initial stats or connect startup signals here, before AddChild.
        AddChild(enemy);
        return enemy;
    }
}
```

Setting local position relative to this spawner before `AddChild` lets initialization observe the spawn location. If the actor exposes an initialization method, define whether it runs before entering the tree or after `_Ready`; do not let callers guess. No `Owner` assignment is needed for transient enemies.

If a child emits a startup signal in its `_Ready`, a parent connection made in the parent's `_Ready` is too late. Connect before `AddChild`, or expose an explicit start phase after the caller has wired dependencies. Avoid relying on sibling order to repair this contract.

Godot scene composition supports keeping child internals private: the scene root can expose `TakeDamage` or a `Defeated` signal while its animation and collision children remain implementation details. Prefer this over long paths into another scene. [Scene organization](https://docs.godotengine.org/en/4.6/tutorials/best_practices/scene_organization.html)

## Save generated children deliberately

This fragment creates a standalone scene in memory. It does not overwrite an existing file:

```csharp
var root = new Node2D { Name = "Room" };
var marker = new Marker2D { Name = "SpawnPoint" };
root.AddChild(marker);
marker.Owner = root;

var packed = new PackedScene();
Error result = packed.Pack(root);
if (result != Error.Ok)
    GD.PushError($"Could not pack Room: {result}");

root.Free(); // The temporary node tree was never added to SceneTree.
// Save packed to an explicitly chosen path only after successful packing.
```

For a generated hierarchy, assess every newly created descendant that must be serialized. Do not recursively rewrite ownership on an existing instanced scene: its internal owner relationships preserve scene boundaries. When an editor tool adds a nested scene, persist the instance root under the edited scene and preserve the instance's internals. Inspect a save-and-reload diff to confirm intent. [PackedScene](https://docs.godotengine.org/en/4.6/classes/class_packedscene.html)

## Autoload is a lifetime decision

Use an Autoload for a concrete cross-scene concern such as an active single-player run or audio service. In C#, obtain the registered node with a typed path such as `GetNode<RunSession>("/root/RunSession")`; a static property is a project convention, not required magic. The registration name and class name need not match.

Keep run reset separate from node destruction. Store identifiers and data rather than references to freed players or UI. If an Autoload emits events, subscribers in replaceable scenes need a cleanup strategy. If it listens to scene-local objects, clear those connections and references on scene exit. Account for Autoload initialization order when one depends on another. [Autoload lifecycle](https://docs.godotengine.org/en/4.6/tutorials/scripting/singletons_autoload.html)

For simple scene replacement, prefer the existing `SceneTree.ChangeSceneToFile`/`ChangeSceneToPacked` flow and check its return value. Do not add a custom scene manager unless transitions, loading, or persistent composition actually require one.

## Paths and unique names

`GetNode<Button>("%Confirm")` is appropriate only when `Confirm` is marked unique in the relevant scene-owner scope. It is not a project-wide search. Export a reference when another scene supplies the dependency, and update saved paths after a rename. [Scene Unique Nodes](https://docs.godotengine.org/en/4.6/tutorials/scripting/scene_unique_nodes.html)

Sources above checked against Godot 4.6 on 2026-09-30. Runtime behavior and source review should be reported separately.
