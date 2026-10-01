# Layout and interaction recipes

Use only the parts needed for the current screen. This is a native Godot 4.6 workflow; C# examples require the .NET editor and compatible SDK to compile.

## A responsive menu tree

```text
CanvasLayer                 # Optional screen-space layer over a 2D game.
└── MenuRoot (Control)       # Full Rect, zero offsets.
    ├── Backdrop (ColorRect) # Full Rect; deliberate mouse filter.
    └── MarginContainer     # Full Rect; Theme margins provide outer padding.
        └── CenterContainer
            └── PanelContainer
                └── MarginContainer
                    └── VBoxContainer
                        ├── Title (Label)
                        ├── Continue (Button)
                        ├── Settings (Button)
                        └── Back (Button)
```

Use a `ScrollContainer` when content can exceed available height. Give its content a coherent minimum width and expansion policy; setting every minimum size to the design screenshot's size can make small-window clipping unavoidable. Test actual text length rather than using blank placeholder labels.

`Fill` fills the allocation a Container assigns; `Expand` requests participation in spare space. Configure the relevant axis. For example, a settings row can keep a label content-sized and give the slider `ExpandFill`. The container's separation and margins should carry spacing, rather than empty spacer labels. [Containers](https://docs.godotengine.org/en/4.6/tutorials/ui/gui_containers.html)

For a standalone HUD counter, anchors can pin it to the top-right while offsets provide padding. If the counter is a Container child, adjust that Container instead. A position that snaps back after a resize usually indicates conflicting layout ownership. [Anchors and offsets](https://docs.godotengine.org/en/4.6/tutorials/ui/size_and_anchors.html)

Do not change the entire game's stretch mode to repair one Control. Check how the existing base viewport, content scale, aspect policy, and 2D artwork interact first. Pixel-art world rendering and readable UI can require separate composition decisions. [Multiple resolutions](https://docs.godotengine.org/en/4.6/tutorials/rendering/multiple_resolutions.html)

## Click-through diagnosis

Inspect the Control under the cursor and its ancestors. `Ignore` allows a purely decorative Control not to intercept mouse input. `Pass` bubbles unhandled mouse events toward ancestors; it does not mean “click all overlapping siblings.” `Stop` blocks further mouse propagation. Set decorative labels/textures over buttons to Ignore when they are not interactive. [Control mouse filters](https://docs.godotengine.org/en/4.6/classes/class_control.html)

If firing a weapon continues while clicking a menu, inspect whether gameplay runs in `_Input` or polls `Input` in a frame callback. GUI consumption only governs event propagation. Move appropriate actions to `_UnhandledInput` and/or disable gameplay input while a modal is active. Do not put a second ad-hoc click handler on every button to compensate. [Input propagation](https://docs.godotengine.org/en/4.6/tutorials/inputs/inputevent.html)

## Focus-aware C# panel

Attach this to a menu root. Assign `FirstButton` in the Inspector, make relevant buttons focusable, and begin with the panel hidden. The caller owns game pause and background-screen activation; this component owns its own focus transition.

```csharp
using Godot;

public partial class MenuPanel : Control
{
    [Export] public Button FirstButton { get; set; } = null!;
    private Control? _returnFocus;

    public void Open()
    {
        if (Visible) return;
        _returnFocus = GetViewport().GuiGetFocusOwner();
        Show();
        CallDeferred(MethodName.FocusFirst);
    }

    private void FocusFirst()
    {
        if (IsVisibleInTree() && !FirstButton.Disabled)
            FirstButton.GrabFocus();
    }

    public void Close()
    {
        Hide();
        if (GodotObject.IsInstanceValid(_returnFocus)
            && _returnFocus!.IsInsideTree()
            && _returnFocus.IsVisibleInTree())
            _returnFocus.GrabFocus();
        _returnFocus = null;
    }

    public override void _UnhandledInput(InputEvent @event)
    {
        if (IsVisibleInTree() && @event.IsActionPressed("ui_cancel"))
        {
            Close();
            GetViewport().SetInputAsHandled();
        }
    }
}
```

Wire a Back button to `Close` once. If closing must also resume the game, route all close paths through the caller's close operation or emit a close request instead of letting this example hide independently. Disable background controls' focusability or restrict navigation while modal; focus neighbors must not escape into an underlying screen. When the remembered control was removed or disabled, choose a screen-specific fallback.

Directional neighbors and Tab next/previous links are different navigation paths. Confirm both. Hidden Controls lose focus, so returning from a submenu needs an explicit decision. [Keyboard/controller navigation](https://docs.godotengine.org/en/4.6/tutorials/ui/gui_navigation.html)

## Pause behavior

Use `SceneTree.Paused` for a simple single-player pause. Set the menu branch to `WhenPaused`, or use `Always` for a controller that opens and closes the menu in both states. A controller that only processes while paused cannot receive the action that initially pauses gameplay. Keep gameplay nodes pausable, and decide whether audio/animations should continue. Signal callbacks can still execute while processing is paused. [Pausing and process modes](https://docs.godotengine.org/en/4.6/tutorials/scripting/pausing_games.html)

One pause owner should coordinate nested menus. A settings panel should not independently unpause when a parent pause panel still exists. Restore the correct pause state before leaving for a title scene, using the existing scene-change flow.

Sources checked against Godot 4.6 on 2026-09-30. Visual verification requires an actual running viewport; .NET verification requires the appropriate toolchain.
