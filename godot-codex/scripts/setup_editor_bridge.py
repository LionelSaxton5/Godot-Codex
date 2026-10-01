#!/usr/bin/env python3
"""Copy the opt-in Godot EditorPlugin into a trusted project. Dry run by default."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from godot_inspect import ProjectError

PLUGIN_ID = 'ai_editor_bridge'
PLUGIN_RESOURCE = 'res://addons/ai_editor_bridge/plugin.cfg'
MAX_CONFIG_BYTES = 2 * 1024 * 1024


def no_symlink_components(path: Path) -> None:
    absolute = path.absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if current.is_symlink():
            raise ProjectError(f'Symlink path component is not supported: {current}')


def enable_in_config(original: str) -> str:
    """Preserve unrelated settings. Stop on an unfamiliar/ambiguous plugins value."""
    header_pattern = re.compile(r'^[ \t]*\[([^]\r\n]+)\][ \t]*(?:;[^\r\n]*)?\r?$', re.MULTILINE)
    all_headers = list(header_pattern.finditer(original))
    matches = [match for match in all_headers if match.group(1).strip() == 'editor_plugins']
    if len(matches) > 1:
        raise ProjectError('Duplicate [editor_plugins] sections; enable the plugin manually')
    if not matches:
        return original.rstrip() + f'\n\n[editor_plugins]\nenabled=PackedStringArray("{PLUGIN_RESOURCE}")\n'
    section_start = matches[0].end()
    following = next((h for h in all_headers if h.start() >= section_start), None)
    section_end = following.start() if following else len(original)
    section = original[section_start:section_end]
    enabled_lines = list(re.finditer(r'^[ \t]*enabled[ \t]*=', section, re.MULTILINE))
    if len(enabled_lines) > 1:
        raise ProjectError('Duplicate enabled setting; enable the plugin manually')
    if not enabled_lines:
        return original[:section_end].rstrip() + f'\nenabled=PackedStringArray("{PLUGIN_RESOURCE}")\n\n' + original[section_end:]
    match = re.search(r'^[ \t]*enabled[ \t]*=[ \t]*PackedStringArray\((.*?)\)[ \t]*(;[^\r\n]*)?\r?$', section, re.MULTILINE | re.DOTALL)
    if not match:
        raise ProjectError('Unrecognized editor_plugins/enabled format; enable manually')
    try:
        plugins = json.loads('[' + match.group(1) + ']')
    except json.JSONDecodeError as exc:
        raise ProjectError('Cannot safely parse enabled plugins; enable manually') from exc
    if not isinstance(plugins, list) or not all(isinstance(p, str) for p in plugins):
        raise ProjectError('Enabled plugin paths must be strings')
    if PLUGIN_RESOURCE not in plugins:
        plugins.append(PLUGIN_RESOURCE)
    comment = (' ' + match.group(2)) if match.group(2) else ''
    replacement = 'enabled=PackedStringArray(' + ', '.join(json.dumps(p, ensure_ascii=False) for p in plugins) + ')' + comment
    return original[:section_start] + section[:match.start()] + replacement + section[match.end():] + original[section_end:]


def setup(project: Path, *, source: Path | None = None, apply: bool = False, enable: bool = False) -> dict:
    project = project.expanduser().absolute()
    if project.name == 'project.godot':
        project = project.parent
    no_symlink_components(project)
    project = project.resolve()
    config = project / 'project.godot'
    if not config.is_file():
        raise ProjectError('Project must contain project.godot')
    no_symlink_components(config)
    if config.stat().st_size > MAX_CONFIG_BYTES:
        raise ProjectError('project.godot exceeds configuration size limit')
    original_bytes = config.read_bytes()
    original_text = original_bytes.decode('utf-8-sig')
    updated = enable_in_config(original_text) if enable else original_text
    if original_bytes.startswith(b'\xef\xbb\xbf'):
        updated_bytes = b'\xef\xbb\xbf' + updated.encode('utf-8')
    else:
        updated_bytes = updated.encode('utf-8')
    source = source or Path(__file__).resolve().parents[1] / 'editor_addon' / PLUGIN_ID
    source = source.absolute()
    no_symlink_components(source)
    if not (source / 'plugin.cfg').is_file():
        raise ProjectError('EditorPlugin source not present in this package')
    for directory, dirs, files in os.walk(source, followlinks=False):
        for name in dirs + files:
            no_symlink_components(Path(directory) / name)
    destination = project / 'addons' / PLUGIN_ID
    no_symlink_components(destination)
    if destination.exists():
        raise ProjectError('Addon already exists; this new-install helper never overwrites it')
    if destination.is_relative_to(source.resolve()) or source.resolve().is_relative_to(destination):
        raise ProjectError('Addon source and destination overlap')
    backup = project / 'project.godot.before-ai-bridge'
    if enable and (backup.exists() or backup.is_symlink()):
        raise ProjectError('Existing config backup would be overwritten; stop and review it')
    server = Path(__file__).resolve().parent / 'godot_mcp_server.py'
    plan = {'apply': apply, 'project': str(project), 'addon_destination': str(destination),
            'enable': enable, 'original_config_sha256': hashlib.sha256(original_bytes).hexdigest(),
            'mcp_command': ['codex','mcp','add','godot-editor','--env',f'GODOT_PROJECT_PATH={project}','--',sys.executable,str(server)],
            'notice': 'Copies a project-local editor addon only. No account/MCP registration is performed. Enabling it allows local same-user AI tools to edit this trusted project while Godot is running.'}
    if not apply:
        return plan
    # All predictable validation occurs before touching the project.
    destination.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.ai-editor-stage-', dir=destination.parent) as temporary:
        stage = Path(temporary) / PLUGIN_ID
        shutil.copytree(source, stage)
        if config.read_bytes() != original_bytes:
            raise ProjectError('project.godot changed during setup; no addon installed')
        if destination.exists() or destination.is_symlink():
            raise ProjectError('Addon destination appeared during setup')
        if enable:
            with backup.open('xb') as output:
                output.write(original_bytes)
        stage.rename(destination)
        if enable:
            config_stage = project / ('.project-ai-bridge-' + os.urandom(8).hex() + '.tmp')
            try:
                with config_stage.open('xb') as output:
                    output.write(updated_bytes)
                config_stage.replace(config)
            finally:
                if config_stage.exists():
                    config_stage.unlink()
    plan['enabled_in_project_config'] = enable
    plan['next_step'] = 'Open/reopen this project in Godot. The AI Bridge plugin must be enabled. Keep the editor running.'
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', type=Path)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--enable', action='store_true', help='Also enable the addon in project.godot, keeping an exact config backup')
    args = parser.parse_args()
    try:
        print(json.dumps(setup(args.project, apply=args.apply, enable=args.enable), ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError) as error:
        print(json.dumps({'ok': False, 'error': str(error)}, ensure_ascii=False))
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
