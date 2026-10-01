# Live editor bridge example · csharp

These 2D/3D scenes, native Resources and script attachments were created through the actual MCP editor tools during integration tests. Open project.godot using Godot 4.6.3 .NET and build BridgeTest.csproj first. The production AI Editor Bridge addon is already enabled in this disposable example.

- World2D.tscn: edited hierarchy, shape Resource, Button signal to a non-tool script callback
- World3D.tscn: BoxMesh, material, camera, light and script-attached node
- NativeCatalog.tscn: every curated native node type created by the bridge; this is a capability fixture, not a finished game
- resources/: all curated native resource types created/saved by the bridge

The integration harness used headless launch arguments and a test-only graceful-shutdown addon; those two test conveniences are removed here so normal editor Play displays a game window. Main scene is World3D. The production bridge code and saved scenes/resources are unchanged. No SDK, engine binary, cache, compiled assembly or test-only control addon is included.

Use the setup guide in the plugin docs to configure the MCP project path. A source write does not compile C# automatically.
