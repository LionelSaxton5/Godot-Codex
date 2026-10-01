#!/usr/bin/env python3
"""Prepare a NEW personal Codex plugin registration. Dry run unless --apply; never installs it."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile

NAME = 'godot-codex'
SKIP = {'.godot', '.git', '__pycache__', 'bin', 'obj', '.tools'}


def prepare(source: Path, home: Path, *, apply: bool = False) -> dict:
    source = source.resolve()
    home = home.expanduser().absolute()
    if not home.is_dir():
        raise ValueError('--home must be an existing directory')
    if home.is_symlink():
        raise ValueError('--home must not be a symlink')
    home = home.resolve()
    manifest = json.loads((source / '.codex-plugin' / 'plugin.json').read_text(encoding='utf-8'))
    if manifest.get('name') != NAME:
        raise ValueError('Unexpected plugin name in source manifest')
    destination = home / 'plugins' / NAME
    marketplace = home / '.agents' / 'plugins' / 'marketplace.json'
    for path in [home / 'plugins', home / '.agents', home / '.agents' / 'plugins', marketplace, destination]:
        if path.is_symlink():
            raise ValueError(f'Refusing symlink destination: {path}')
    if destination.exists():
        raise ValueError('Plugin destination already exists; this installer never overwrites an existing plugin')
    if source == destination or source.is_relative_to(destination) or destination.is_relative_to(source):
        raise ValueError('Source and destination must not overlap')
    if marketplace.exists():
        payload = json.loads(marketplace.read_text(encoding='utf-8'))
        if not isinstance(payload, dict):
            raise ValueError('Marketplace must be a JSON object')
    else:
        payload = {'name': 'personal', 'interface': {'displayName': 'Personal'}, 'plugins': []}
    market_name = payload.get('name')
    if not isinstance(market_name, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', market_name):
        raise ValueError('Invalid existing marketplace name')
    plugins = payload.get('plugins')
    if not isinstance(plugins, list):
        raise ValueError('Marketplace plugins must be an array')
    if any(not isinstance(p, dict) for p in plugins):
        raise ValueError('Invalid marketplace plugin entry')
    if any(p.get('name') == NAME for p in plugins):
        raise ValueError('Plugin already registered; this installer never overwrites marketplace entries')
    plugins.append({'name': NAME, 'source': {'source': 'local', 'path': f'./plugins/{NAME}'},
                    'policy': {'installation': 'AVAILABLE', 'authentication': 'ON_INSTALL'},
                    'category': 'Productivity'})
    result = {'apply': apply, 'source': str(source), 'destination': str(destination),
              'marketplace': str(marketplace), 'marketplace_name': market_name,
              'next_command': ['codex', 'plugin', 'add', f'{NAME}@{market_name}'],
              'notice': 'Only prepares local files and registration. Does not run Codex, sign in, install into an account, or publish.'}
    if not apply:
        return result
    for directory, dirs, files in os.walk(source, followlinks=False):
        dirs[:] = [d for d in dirs if d not in SKIP]
        for name in dirs + files:
            if (Path(directory) / name).is_symlink():
                raise ValueError('Source contains a symlink; refusing to copy')
    destination.parent.mkdir(parents=True, exist_ok=True)
    marketplace.parent.mkdir(parents=True, exist_ok=True)
    # Stage first. No updates/removals of an existing destination or marketplace entry.
    with tempfile.TemporaryDirectory(prefix='.godot-plugin-stage-', dir=destination.parent) as temporary:
        staging = Path(temporary) / NAME
        shutil.copytree(source, staging, ignore=shutil.ignore_patterns(*SKIP))
        if destination.exists() or destination.is_symlink():
            raise ValueError('Destination appeared during preparation; stopping')
        mcp_path = staging / '.mcp.json'
        if mcp_path.is_file():
            mcp = json.loads(mcp_path.read_text(encoding='utf-8'))
            mcp['mcpServers']['godot-editor']['command'] = sys.executable
            mcp_path.write_text(json.dumps(mcp, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        staging.rename(destination)
    fd, staged_name = tempfile.mkstemp(prefix='.marketplace-', suffix='.json', dir=marketplace.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write('\n')
        # A local installer, not a concurrent marketplace transaction manager.
        os.replace(staged_name, marketplace)
    finally:
        if os.path.exists(staged_name):
            os.unlink(staged_name)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', required=True, type=Path, help='The user home to prepare (explicit, existing directory)')
    parser.add_argument('--apply', action='store_true', help='Actually copy/register; without it print the plan only')
    args = parser.parse_args()
    try:
        result = prepare(Path(__file__).resolve().parents[1], args.home, apply=args.apply)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}, ensure_ascii=False))
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
