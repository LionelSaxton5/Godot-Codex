#!/usr/bin/env python3
"""Static checks by default; Godot import/parse/runtime checks require explicit trust."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
from godot_inspect import ProjectError, project_root, resource_path, scan_project

ERROR_LINE = re.compile(r'(?m)^\s*(?:SCRIPT ERROR:|ERROR:|Parse Error:|Shader error:)')
MAX_LOG_BYTES = 2 * 1024 * 1024
ANSI_ESCAPE = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')


def execute(command: list[str], *, timeout: float, env: dict | None = None, cwd: str | Path | None = None) -> dict:
    """No shell; kill the process group on POSIX timeout; preserve bounded diagnostics."""
    with tempfile.TemporaryFile() as output:
        process = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT,
                                   env=env, cwd=cwd, start_new_session=(os.name == 'posix'))
        timed_out = False
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            if os.name == 'posix':
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
            process.wait()
        output.seek(0, 2)
        length = output.tell()
        output.seek(0)
        raw = output.read(MAX_LOG_BYTES)
        log = raw.decode('utf-8', errors='replace')
    truncated = length > MAX_LOG_BYTES
    return {'command': command, 'returncode': process.returncode, 'timed_out': timed_out,
            'log_truncated': truncated, 'log': log,
            'ok': not timed_out and process.returncode == 0 and not ERROR_LINE.search(ANSI_ESCAPE.sub('', log)) and not truncated}


def validate(project: str, *, godot: str = 'godot', allow_project_code: bool = False,
             timeout: float = 60, smoke_frames: int = 0, test_script: str | None = None,
             test_scene: str | None = None, dotnet: str = 'dotnet', csproj: str | None = None) -> dict:
    root = project_root(project)
    report = {'schema_version': 1, 'static': scan_project(root), 'checks': [],
              'mode': 'static-read-only', 'csharp': 'not-checked', 'ok': False}
    if report['static']['errors']:
        return report
    if not report['static']['complete']:
        report['blocker'] = 'Inventory is incomplete (for example symlinks were skipped). Review warnings and validate a complete project copy.'
        return report
    if not allow_project_code:
        report['ok'] = True
        report['notice'] = 'Static inventory passed. Engine checks NOT RUN; use --allow-project-code only for a trusted project.'
        return report
    if timeout <= 0 or smoke_frames < 0:
        raise ProjectError('Timeout must be positive and smoke frames must be nonnegative')
    if test_script:
        target = resource_path(root, test_script)
        if target.suffix != '.gd':
            raise ProjectError('--test-script must reference a .gd SceneTree/MainLoop script')
    if test_scene and resource_path(root, test_scene).suffix not in ('.tscn', '.scn'):
        raise ProjectError('--test-scene must reference a .tscn or .scn scene')
    if csproj and resource_path(root, csproj).suffix != '.csproj':
        raise ProjectError('--csproj must reference a .csproj project')
    binary = shutil.which(godot)
    if not binary:
        raise ProjectError(f'Godot executable not found: {godot}')
    report['mode'] = 'trusted-project-engine-execution'
    report['notice'] = 'Build, import and checks can execute build targets/tool scripts/plugins/native code and write .godot/import metadata; runtime may write saves or access network. This is NOT a sandbox.'
    # Isolate Godot preferences and user:// data. Project and external side effects remain possible.
    with tempfile.TemporaryDirectory(prefix='godot-validation-') as temporary:
        env = os.environ.copy()
        for key, folder in [('XDG_DATA_HOME', 'data'), ('XDG_CONFIG_HOME', 'config'), ('XDG_CACHE_HOME', 'cache')]:
            path = Path(temporary) / folder
            path.mkdir()
            env[key] = str(path)
        home = Path(temporary) / 'home'
        home.mkdir()
        env['HOME'] = str(home)
        env['NO_COLOR'] = '1'
        # The .NET engine needs its runtime before even the capability probe.
        available_dotnet = shutil.which(dotnet)
        if available_dotnet:
            early_dotnet_root = str(Path(available_dotnet).resolve().parent)
            env['DOTNET_ROOT'] = early_dotnet_root
            env['PATH'] = early_dotnet_root + os.pathsep + env.get('PATH', '')
        probe = Path(temporary) / 'probe.gd'
        probe.write_text('extends SceneTree\nfunc _init():\n print("GODOT_PROBE=" + JSON.stringify({"version": Engine.get_version_info(), "csharp": ClassDB.class_exists("CSharpScript")}))\n quit()\n', encoding='utf-8')
        check = execute([binary, '--headless', '--path', temporary, '--script', str(probe)], timeout=timeout, env=env, cwd=temporary)
        check['name'] = 'engine-capabilities'
        report['checks'].append(check)
        if not check['ok']:
            return report
        matches = re.findall(r'^GODOT_PROBE=(.+)$', check['log'], re.MULTILINE)
        if not matches:
            raise ProjectError('Godot capability probe produced no JSON marker')
        report['engine'] = json.loads(matches[-1])
        if report['engine']['version']['major'] != 4:
            raise ProjectError('This plugin supports Godot 4 only')
        has_csharp = bool(report['static']['scripts']['csharp'] or report['static']['csharp_projects'])
        if has_csharp:
            report['csharp'] = 'detected-not-compiled'
            if not report['engine']['csharp']:
                report['blocker'] = 'C# project requires Godot .NET; selected engine lacks CSharpScript. No engine project checks run.'
                return report
            projects = report['static']['csharp_projects']
            if csproj:
                project_file = resource_path(root, csproj)
            elif len(projects) == 1:
                project_file = root / projects[0]
            else:
                report['blocker'] = 'C# build requires exactly one .csproj or an explicit --csproj res://path.csproj.'
                return report
            dotnet_binary = shutil.which(dotnet)
            if not dotnet_binary:
                report['blocker'] = f'.NET SDK executable not found: {dotnet}'
                return report
            dotnet_root = str(Path(dotnet_binary).resolve().parent)
            env['DOTNET_ROOT'] = dotnet_root
            env['PATH'] = dotnet_root + os.pathsep + env.get('PATH', '')
            env['DOTNET_CLI_HOME'] = str(home)
            env['DOTNET_CLI_TELEMETRY_OPTOUT'] = '1'
            env['DOTNET_SKIP_FIRST_TIME_EXPERIENCE'] = '1'
            env.setdefault('NUGET_PACKAGES', str(root / '.godot' / 'dotnet' / 'nuget'))
            build = execute([dotnet_binary, 'build', str(project_file), '--nologo', '--verbosity', 'minimal'], timeout=timeout, env=env, cwd=root)
            build['name'] = 'csharp-build'
            report['checks'].append(build)
            if not build['ok']:
                return report
            report['csharp'] = 'build-passed-runtime-not-yet-checked'
        else:
            report['csharp'] = 'not-applicable'
        base = [binary, '--headless', '--path', str(root)]
        steps = [('import', base + ['--import'])]
        steps.extend((f'parse:{path}', base + ['--script', f'res://{path}', '--check-only'])
                     for path in report['static']['scripts']['gdscript'])
        if test_script:
            steps.append(('test-script', base + ['--script', test_script]))
        if test_scene:
            steps.append(('test-scene', base + [test_scene]))
        if smoke_frames:
            steps.append(('main-scene-smoke', base + ['--quit-after', str(smoke_frames)]))
        for name, command in steps:
            check = execute(command, timeout=timeout, env=env, cwd=root)
            check['name'] = name
            report['checks'].append(check)
            if not check['ok']:
                return report
    report['ok'] = True
    if report['csharp'].startswith('build-passed'):
        report['csharp'] = 'build-and-requested-checks-passed'
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project')
    parser.add_argument('--godot', default='godot', help='Trusted Godot executable name or path')
    parser.add_argument('--allow-project-code', action='store_true', help='Allow project build/restore/import, tool scripts/plugins/native code, and optional runtime; NOT a sandbox')
    parser.add_argument('--dotnet', default='dotnet', help='Trusted .NET SDK executable for C# projects')
    parser.add_argument('--csproj', help='Select res://path.csproj when the project contains multiple .csproj files')
    parser.add_argument('--timeout', type=float, default=60, help='Seconds per engine invocation')
    parser.add_argument('--smoke-frames', type=int, default=0, help='Run main scene for this many frames (no visual assurance)')
    parser.add_argument('--test-script', help='res:// path to an explicit executable .gd SceneTree/MainLoop test')
    parser.add_argument('--test-scene', help='res:// path to an explicit runtime test scene (including C#)')
    args = parser.parse_args()
    if (args.smoke_frames or args.test_script or args.test_scene) and not args.allow_project_code:
        parser.error('Runtime checks require --allow-project-code')
    try:
        report = validate(args.project, godot=args.godot, allow_project_code=args.allow_project_code,
                          timeout=args.timeout, smoke_frames=args.smoke_frames, test_script=args.test_script,
                          test_scene=args.test_scene, dotnet=args.dotnet, csproj=args.csproj)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report['ok'] else 1
    except (ProjectError, OSError, ValueError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

if __name__ == '__main__':
    sys.exit(main())
