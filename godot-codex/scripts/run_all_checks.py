#!/usr/bin/env python3
"""Run shipped unit/engine/editor checks into a NEW disposable work directory."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
from godot_validate import execute

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir',type=Path,required=True)
    parser.add_argument('--godot',required=True)
    parser.add_argument('--godot-dotnet')
    parser.add_argument('--dotnet')
    parser.add_argument('--include-engine',action='store_true',help='Run trusted bundled engine fixtures and actual editor integrations')
    args=parser.parse_args()
    work=args.work_dir.expanduser().absolute()
    if work.exists() or work.is_symlink():parser.error('--work-dir must not already exist')
    if args.include_engine and (not args.godot_dotnet or not args.dotnet):parser.error('Dual-language engine verification requires --godot-dotnet and --dotnet')
    work.mkdir(parents=True)
    commands=[('python-tests',[sys.executable,'-m','unittest','discover','-s',str(ROOT/'tests'),'-v'])]
    if args.include_engine:
        commands.extend([
            ('gdscript-runtime',[sys.executable,str(ROOT/'scripts/godot_validate.py'),str(ROOT/'examples/native_lab'),'--godot',args.godot,'--allow-project-code','--test-script','res://tests/test_native.gd','--smoke-frames','8']),
            ('csharp-runtime',[sys.executable,str(ROOT/'scripts/godot_validate.py'),str(ROOT/'examples/csharp_lab'),'--godot',args.godot_dotnet,'--dotnet',args.dotnet,'--allow-project-code','--test-scene','res://tests/TestRunner.tscn','--smoke-frames','8','--timeout','120']),
            ('gdscript-editor',[sys.executable,str(ROOT/'tests/run_editor_integration.py'),'--godot',args.godot,'--language','gdscript','--work-dir',str(work/'editor-gdscript')]),
            ('csharp-editor',[sys.executable,str(ROOT/'tests/run_editor_integration.py'),'--godot',args.godot_dotnet,'--dotnet',args.dotnet,'--language','csharp','--work-dir',str(work/'editor-csharp')]),
        ])
    results=[]
    for name,command in commands:
        log=work/(name+'.log')
        print('Running '+name,flush=True)
        run=execute(command,timeout=600,cwd=ROOT)
        log.write_text(run['log'], encoding="utf-8")
        record={'name':name,'returncode':run['returncode'],'passed':run['ok'],'timed_out':run['timed_out'],'log_truncated':run['log_truncated'],'log':str(log),'command':command}
        results.append(record)
        (work/'summary.json').write_text(json.dumps({'passed':all(r['passed'] for r in results),'checks':results},indent=2)+'\n', encoding="utf-8")
        if not record['passed']:
            print(json.dumps(record,indent=2));return 1
    print(json.dumps({'passed':True,'checks':results},indent=2));return 0

if __name__=='__main__':raise SystemExit(main())
