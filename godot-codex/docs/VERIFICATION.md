# Godot-codex 0.2.1 verification

The unchanged editor functionality was verified on Windows x64 using official Godot 4.6.3 standard and .NET editors, Python 3.13.13, Codex CLI 0.159.2, and .NET SDK 9.0.317.

- Python regressions: 99 passed, 13 skipped because Windows symbolic-link privileges were unavailable, zero failures.
- Real standard MCP to editor integration: GDScript 184 checks; C# 185 checks; all 26 tools called in each language.
- Real Codex app-server to MCP to editor integration: GDScript 184 checks; C# 185 checks; all 26 tools called in each language. No model inference or account authentication was required.
- Covered 2D/3D, Chinese and spaced paths, save/reopen, undo/redo, scripts, signals, resources, play/stop, guarded failures and timeouts. Both graphical editors were visually inspected.
- The final Windows revision archive was extracted into a fresh directory and retested, including both bundled editor examples.

This public candidate changes package branding and documentation only. A separate naming regression verifies installation and 26-tool discovery from its extracted archive; it does not claim another full editor integration run.

Godot 4.4.1 lacks required EditorInterface APIs and is unsupported. Other engine versions, macOS, other Windows hardware/filesystems, and model-backed inference are unverified. Earlier Linux 0.2.0 validation is historical and does not establish Linux acceptance for this revision.

Raw execution logs, machine-specific environment information, account identifiers, transfer receipts, and debugging transcripts are intentionally excluded from the public archive.
