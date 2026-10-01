#!/usr/bin/env python3
"""Build a lightweight, deterministic ZIP of the plugin (no installation/network)."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import zipfile

EXCLUDED = {'.godot', '.mono', '.git', '__pycache__', 'bin', 'obj', '.tools'}
NAME = 'godot-codex'


def verify_structure(root: Path) -> list[Path]:
    # Reject links before reading metadata or documentation through them.
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if d not in EXCLUDED]
        for name in dirs + files:
            path = Path(directory) / name
            if path.is_symlink():
                raise ValueError(f'Symlink cannot be packaged: {path.relative_to(root)}')
    manifest = json.loads((root / '.codex-plugin' / 'plugin.json').read_text(encoding='utf-8'))
    if manifest.get('name') != NAME or root.name != NAME:
        raise ValueError('Folder and manifest names must both be godot-codex')
    if manifest.get('skills') != './skills/':
        raise ValueError('Unexpected skills path')
    skills = sorted((root / 'skills').glob('*/SKILL.md'))
    expected_skills = 7 if str(manifest.get('version', '')).startswith('0.2.') else 6
    if len(skills) != expected_skills:
        raise ValueError(f'Expected {expected_skills} skills for this release')
    for entry in skills:
        text = entry.read_text(encoding='utf-8')
        if not text.startswith('---\n') or f'name: {entry.parent.name}\n' not in text:
            raise ValueError(f'Invalid skill frontmatter: {entry}')
        if '\ndescription:' not in text.split('---', 2)[1]:
            raise ValueError(f'Missing skill description: {entry}')
        if not (entry.parent / 'agents' / 'openai.yaml').is_file():
            raise ValueError(f'Missing skill UI metadata: {entry}')
    for file in root.rglob('*.md'):
        if any(part in EXCLUDED for part in file.relative_to(root).parts):
            continue
        text = file.read_text(encoding='utf-8')
        if '[TODO:' in text:
            raise ValueError(f'Unfinished placeholder: {file}')
        for link in re.findall(r'\]\(([^)]+)\)', text):
            if '://' in link or link.startswith('#'):
                continue
            link = link.split('#', 1)[0]
            target = (file.parent / link).resolve()
            if not target.is_relative_to(root.resolve()) or not target.exists():
                raise ValueError(f'Broken/escaping local link in {file}: {link}')
    for relative in ['README.md', 'README.zh-CN.md', 'LICENSE', 'docs/VERIFICATION.md',
                     'examples/native_lab/project.godot', 'examples/csharp_lab/project.godot']:
        if not (root / relative).is_file():
            raise ValueError(f'Missing package file: {relative}')
    files = []
    for file in sorted(root.rglob('*')):
        relative = file.relative_to(root)
        if any(part in EXCLUDED for part in relative.parts) or file.suffix in ('.zip', '.pyc'):
            continue
        if file.is_symlink():
            raise ValueError(f'Symlink cannot be packaged: {relative}')
        if file.is_file():
            files.append(file)
    return files


def build(root: Path, output: Path, *, force: bool = False) -> dict:
    root = root.resolve()
    output = output.absolute()
    if output.suffix != '.zip':
        raise ValueError('Output must end in .zip')
    if output.is_symlink():
        raise ValueError('Output must not be a symlink')
    if output.exists() and not force:
        raise ValueError('Output already exists; use --force for intentional replacement')
    sidecar = output.with_suffix('.zip.sha256')
    if sidecar.is_symlink():
        raise ValueError('Checksum output must not be a symlink')
    if sidecar.exists() and not force:
        raise ValueError('Checksum output already exists; use --force for intentional replacement')
    if output.is_relative_to(root):
        raise ValueError('Write archives outside the plugin source directory')
    files = verify_structure(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='godot-package-', dir=output.parent) as temporary:
        staged = Path(temporary) / output.name
        with zipfile.ZipFile(staged, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for file in files:
                name = f'{NAME}/{file.relative_to(root).as_posix()}'
                info = zipfile.ZipInfo(name, date_time=(2026, 9, 30, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, file.read_bytes())
        with zipfile.ZipFile(staged) as archive:
            bad = archive.testzip()
            if bad:
                raise ValueError(f'ZIP integrity failure: {bad}')
        digest = hashlib.sha256(staged.read_bytes()).hexdigest()
        staged_checksum = Path(temporary) / sidecar.name
        staged_checksum.write_text(f'{digest}  {output.name}\n', encoding='utf-8')
        staged.replace(output)
        staged_checksum.replace(sidecar)
    return {'archive': str(output), 'files': len(files), 'bytes': output.stat().st_size, 'sha256': digest}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()
    try:
        print(json.dumps(build(Path(__file__).resolve().parents[1], args.output, force=args.force), indent=2))
        return 0
    except (OSError, ValueError) as error:
        print(json.dumps({'ok': False, 'error': str(error)}))
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
