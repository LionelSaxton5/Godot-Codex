#!/usr/bin/env python3
"""Conservative, read-only inventory of Godot text projects; never loads project code."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys

IGNORED = {'.godot', '.git', '.mono', 'bin', 'obj', 'node_modules', '__pycache__'}
TEXT_TYPES = {'.tscn', '.tres', '.gd', '.cs', '.godot', '.csproj', '.sln', '.gdextension'}
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_FILES = 10000
ATTR = re.compile(r'(\w+)="((?:[^"\\]|\\.)*)"')

class ProjectError(ValueError):
    pass


def project_root(value: str | Path) -> Path:
    path = Path(value).expanduser().absolute()
    if path.name == 'project.godot' and path.is_file():
        path = path.parent
    if not path.is_dir():
        raise ProjectError(f'Project directory does not exist: {path}')
    path = path.resolve()
    config = path / 'project.godot'
    if config.is_symlink() or not config.is_file():
        raise ProjectError('A regular project.godot file is required (symlinks rejected)')
    return path


def resource_path(root: Path, resource: str, *, must_exist: bool = True) -> Path:
    """Reject traversal, symlinks and non-resource paths instead of resolving them silently."""
    if not resource.startswith('res://'):
        raise ProjectError(f'Expected res:// resource path: {resource}')
    relative = resource[6:]
    parts = relative.split('/')
    if not relative or '\\' in relative or any(p in ('', '.', '..') for p in parts):
        raise ProjectError(f'Unsafe resource path: {resource}')
    if PurePosixPath(relative).is_absolute() or ':' in parts[0]:
        raise ProjectError(f'Unsafe resource path: {resource}')
    target = root
    for part in parts:
        target = target / part
        if target.is_symlink():
            raise ProjectError(f'Symlink resource is not followed: {resource}')
    if not target.resolve().is_relative_to(root):
        raise ProjectError(f'Resource escapes project: {resource}')
    if must_exist and not target.is_file():
        raise ProjectError(f'Missing resource: {resource}')
    return target


def unquote(value: str) -> str:
    value = value.strip()
    if value.startswith('"') and value.endswith('"'):
        # Godot strings are not arbitrary Python expressions. Never eval them.
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value[1:-1]
    return value


def project_settings(text: str) -> dict[str, dict[str, str]]:
    section = ''
    settings: dict[str, dict[str, str]] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(';'):
            continue
        if line.startswith('[') and line.endswith(']'):
            section = line[1:-1]
        elif '=' in line:
            key, value = line.split('=', 1)
            settings.setdefault(section, {})[key.strip()] = value.strip()
    return settings


def scan_project(root: Path) -> dict:
    report = {'schema_version': 1, 'project': str(root), 'mode': 'static-read-only', 'complete': True,
              'files': [], 'scenes': [], 'resources': [], 'scripts': {'gdscript': [], 'csharp': []},
              'csharp_projects': [], 'settings': {}, 'autoloads': {}, 'references': [],
              'warnings': [], 'errors': [], 'limitations': [
                  'Text inventory is not the Godot parser; binary resources and runtime-created nodes/connections are not inspected.',
                  'No scripts, plugins, imports, assemblies, or native extensions are executed.',
                  'UID-only references need Godot to resolve; inherited/instanced scene trees are not expanded.'
              ]}
    parsed: dict[str, str] = {}
    seen = 0
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in sorted(dirs):
            candidate = Path(directory) / name
            if candidate.is_symlink():
                report['complete'] = False
                report['warnings'].append(f'Skipped symlink directory: {candidate.relative_to(root).as_posix()}')
        dirs[:] = sorted(d for d in dirs if d not in IGNORED and not (Path(directory) / d).is_symlink())
        for name in sorted(files):
            seen += 1
            if seen > MAX_FILES:
                raise ProjectError(f'Inventory limit exceeded ({MAX_FILES} files); narrow the project')
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                report['complete'] = False
                report['warnings'].append(f'Skipped symlink file: {relative}')
                continue
            if not path.is_file():
                continue
            report['files'].append(relative)
            if path.suffix == '.gd':
                report['scripts']['gdscript'].append(relative)
            elif path.suffix == '.cs':
                report['scripts']['csharp'].append(relative)
            elif path.suffix == '.csproj':
                report['csharp_projects'].append(relative)
            elif path.suffix == '.tres':
                report['resources'].append(relative)
            if path.suffix not in TEXT_TYPES:
                continue
            if path.stat().st_size > MAX_FILE_BYTES:
                report['complete'] = False
                report['errors'].append(f'Incomplete inventory: oversized text file skipped: {relative}')
                continue
            try:
                parsed[relative] = path.read_text(encoding='utf-8-sig')
            except (UnicodeError, OSError) as exc:
                report['errors'].append(f'Cannot read {relative}: {exc}')
    if 'project.godot' not in parsed:
        raise ProjectError('project.godot could not be read within size and encoding limits')
    settings = project_settings(parsed['project.godot'])
    # Selected settings only; avoid dumping unrelated user configuration.
    report['settings'] = {k: settings.get(k, {}) for k in ('application', 'display', 'rendering', 'dotnet')}
    report['autoloads'] = settings.get('autoload', {})
    for relative, text in parsed.items():
        ext = Path(relative).suffix
        if ext in ('.tscn', '.tres'):
            scene = {'path': relative, 'nodes': [], 'connections': [], 'external_resources': []}
            for line_no, line in enumerate(text.splitlines(), 1):
                line = line.strip()
                if line.startswith('[node ') or line.startswith('[connection ') or line.startswith('[ext_resource '):
                    attrs = {k: unquote('"' + v + '"') for k, v in ATTR.findall(line)}
                    attrs['line'] = line_no
                    if line.startswith('[node '):
                        scene['nodes'].append(attrs)
                    elif line.startswith('[connection '):
                        scene['connections'].append(attrs)
                    else:
                        scene['external_resources'].append(attrs)
                        if 'path' in attrs:
                            report['references'].append({'source': relative, 'line': line_no, 'path': attrs['path']})
            if ext == '.tscn':
                report['scenes'].append(scene)
    main = unquote(settings.get('application', {}).get('run/main_scene', ''))
    if main:
        report['references'].append({'source': 'project.godot', 'path': main})
    for name, raw in report['autoloads'].items():
        report['references'].append({'source': 'project.godot', 'autoload': name, 'path': unquote(raw).lstrip('*')})
    for ref in report['references']:
        value = ref['path']
        if value.startswith('uid://'):
            ref['status'] = 'uid-unresolved-static'
            report['warnings'].append(f"UID requires engine resolution: {value} ({ref['source']})")
        else:
            try:
                resource_path(root, value)
                ref['status'] = 'exists'
            except ProjectError as exc:
                ref['status'] = 'invalid'
                report['errors'].append(f"{ref['source']}: {exc}")
    report['summary'] = {'files': len(report['files']), 'scenes': len(report['scenes']),
                         'gdscript': len(report['scripts']['gdscript']),
                         'csharp': len(report['scripts']['csharp']),
                         'errors': len(report['errors']), 'warnings': len(report['warnings'])}
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', help='Project directory or project.godot')
    parser.add_argument('--json', action='store_true', help='Emit a JSON inventory')
    args = parser.parse_args()
    try:
        report = scan_project(project_root(args.project))
    except (ProjectError, OSError) as exc:
        print(json.dumps({'error': str(exc)}) if args.json else f'Error: {exc}', file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Project: {report['project']} (static; no project code executed)")
        print(json.dumps(report['summary'], ensure_ascii=False))
        for scene in report['scenes']:
            print(f"Scene {scene['path']}: {len(scene['nodes'])} declared nodes, {len(scene['connections'])} saved connections")
        for kind in ('warnings', 'errors'):
            for issue in report[kind]:
                print(f'{kind.upper()}: {issue}')
    return 1 if report['errors'] else 0

if __name__ == '__main__':
    sys.exit(main())
