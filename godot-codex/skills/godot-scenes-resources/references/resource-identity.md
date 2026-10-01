# Resource identity

Read this before fixing shared health, material, inventory, or nested data bugs. Decide which objects may be shared before choosing a copying API.

## Configuration versus state

A weapon definition can safely share its icon, sound, and base damage with every weapon instance. Ammo count and cooldown usually belong to each actor. Moving those counters into actor state can fix unwanted coupling without copying expensive assets.

For Inspector-authored data, use a top-level C# Resource class in its own matching file, with `partial`, optional `[GlobalClass]`, and exported serializable properties. Retain a parameterless constructor; C# optional constructor parameters do not substitute for one. Arbitrary unexported managed fields are not a serialization contract. [Custom Resources](https://docs.godotengine.org/en/4.6/tutorials/scripting/resources.html)

```csharp
// WeaponDefinition.cs
using Godot;

[GlobalClass]
public partial class WeaponDefinition : Resource
{
    [Export] public int BaseDamage { get; set; } = 8;
    [Export] public Texture2D Icon { get; set; } = null!;
}
```

Keep this definition shared; put `AmmoRemaining` on the actor unless the requested design needs a serializable runtime Resource. If a mutable custom Resource drives observers, call `EmitChanged()` from meaningful state changes; modifying a custom property does not notify observers by itself.

## Godot 4.6 copying contract

- `Duplicate()` copies stored/exported properties; nested Resources and collections remain shared
- `Duplicate(true)` also recursively duplicates collections and internal/local Resources; external-path Resources may remain shared
- `DuplicateDeep(Resource.DeepDuplicateMode.All)` also requests duplication of external subresources; it can copy large assets unnecessarily
- Deep-copy modes `None` and `Internal` offer narrower subresource policies
- Repeated references preserve their alias relationship inside the duplicate; cloning is not “one new object per field”
- Property usage flags can override duplication, and required GDScript `_init` parameters can prevent it
- `ResourceLocalToScene` requests per-scene-instance copies during instantiation; changing it afterward does not repair existing instances

[Resource API and duplication modes](https://docs.godotengine.org/en/4.6/classes/class_resource.html)

Do not apply pre-4.6 advice that every Resource inside an Array or Dictionary always stays shared. Conversely, do not describe `Duplicate(true)` as an arbitrary deep clone of all C# objects.

## Pick a scope and test it

For scene-owned mutable data, configure Local To Scene on the intended Resource before instantiation. Two references within one scene may intentionally point to the same scene-local copy. Per-node uniqueness within that scene needs an additional explicit copy or construction step.

For a caller-selected clone policy, illustrate it with the actual custom type:

```csharp
// Template is an assigned Resource. Verify each nested dependency's policy.
var runtime = (Resource)Template.Duplicate(true);
```

Prefer a typed cast in real code, and assign the result back to the consuming node. Duplicating a Resource but continuing to use its original reference fixes nothing.

Test a realistic graph: two actor instances, a mutable child Resource, a shared texture, and the same child referenced twice. Compare `GetInstanceId()` values before mutating state. Assert the intended sharing contract, not that every identity differs. Save/reload exported data separately from in-memory copying. If identity matches the contract but behavior still leaks, inspect static fields, Autoload data, and event subscriptions.

Official sources checked 2026-09-30 against Godot 4.6. Examples here have not been compiled merely by being documented.
