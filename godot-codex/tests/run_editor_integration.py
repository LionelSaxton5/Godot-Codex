#!/usr/bin/env python3
"""Real editor + real stdio MCP integration harness. Uses disposable projects only."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import queue
import threading
import re
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from setup_editor_bridge import setup

class CheckFailure(RuntimeError): pass

class Mcp:
    def __init__(self, project: Path, env: dict, log):
        self.process = subprocess.Popen([sys.executable, str(ROOT/'scripts'/'godot_mcp_server.py'), '--project', str(project), '--timeout','15'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, env=env, text=True, bufsize=1)
        self.counter=0;self.trace=[]
        self.lines=queue.Queue()
        def read_lines():
            try:
                for line in self.process.stdout:
                    self.lines.put(line)
            finally:
                self.lines.put(None)
        self.reader=threading.Thread(target=read_lines,daemon=True)
        self.reader.start()
        self.request('initialize', {'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'godot-live-integration','version':'0.2.0'}})
        self.notify('notifications/initialized',{})
        self.tools=self.request('tools/list',{})['tools']
    def notify(self, method, params):
        self.process.stdin.write(json.dumps({'jsonrpc':'2.0','method':method,'params':params})+'\n');self.process.stdin.flush()
    def request(self,method,params):
        self.counter+=1
        message={'jsonrpc':'2.0','id':self.counter,'method':method,'params':params}
        self.process.stdin.write(json.dumps(message)+'\n');self.process.stdin.flush()
        try:line=self.lines.get(timeout=25)
        except queue.Empty:raise CheckFailure(f'MCP response timed out: {method}')
        if not line:raise CheckFailure(f'MCP stopped unexpectedly: {self.process.poll()}')
        response=json.loads(line);self.trace.append({'request':message,'response':response})
        if response.get('id')!=self.counter or 'error' in response:raise CheckFailure(f'Unexpected JSON-RPC response: {response}')
        return response['result']
    def call(self,op,args=None,*,error=False):
        result=self.request('tools/call',{'name':'godot_'+op,'arguments':args or {}})
        data=result.get('structuredContent')
        if data is None:data=json.loads(result['content'][0]['text'])
        if error is not None and bool(result.get('isError')) != error:raise CheckFailure(f'{op} unexpected result: {result}')
        return data
    def close(self):
        if self.process.poll() is None:
            self.process.stdin.close()
            try:self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait()

class Scenario:
    def __init__(self,mcp:Mcp):self.mcp=mcp;self.checks=[]
    def check(self,condition,description):
        self.checks.append({'check':description,'passed':bool(condition)})
        if not condition:raise CheckFailure(description)
    def status(self):return self.mcp.call('status')
    def guard(self):
        scene=self.status()['scene']
        return {'expected_scene_path':scene['path'],'expected_revision':scene['revision']}
    def inspect(self,path):return self.mcp.call('node_inspect',{'node_path':path})
    def node_guard(self,path):
        result=self.inspect(path)
        node=result.get('node',result)
        return {**self.guard(),'node_path':path,'expected_node_id':str(node['node_id'])}
    def mutate(self,op,args=None,path=None):
        guard=self.node_guard(path) if path is not None else self.guard()
        return self.mcp.call(op,{**guard,**(args or {})})
    def create_node(self,parent,node_type,name):
        data=self.inspect(parent);node=data.get('node',data)
        return self.mutate('node_create',{'parent_path':parent,'expected_parent_id':str(node['node_id']),'type':node_type,'name':name})
    def save(self):
        status=self.status();scene=status['scene']
        return self.mcp.call('scene_save',{'expected_scene_path':scene['path'],'expected_revision':scene['revision'],'expected_disk_sha256':scene['disk_sha256']})
    def value(self,path,property_name):
        values={p['name']:p['value'] for p in self.inspect(path)['properties']}
        return values[property_name]
    def paths(self):
        return [n['path'] for n in self.mcp.call('hierarchy',{'max_depth':32})['nodes']]
    def expect_error(self,op,args,code=None):
        data=self.mcp.call(op,args,error=True)
        self.check('error' in data,f'{op} rejects invalid operation')
        if code:self.check(data['error']['code']==code,f'{op} reports {code}')
        return data
    def initial_create(self,create_args,project):
        # Reconcile only definite pre-mutation startup rejection in a NEW test project.
        deadline=time.monotonic()+10
        while True:
            response=self.mcp.call('scene_create',{**self.guard(),**create_args},error=None)
            if 'error' not in response:return response
            target=project/create_args['path'][6:]
            if response['error']['code']!='stale_scene' or target.exists() or time.monotonic()>=deadline:
                raise CheckFailure(f'Initial fixture scene creation failed: {response}')
            time.sleep(.1)

    def run(self,language,project):
        self.check(len(self.mcp.tools)==26,'MCP discovers all 26 explicit editor tools')
        status=self.status()
        self.check(status['protocol_version']==1,'Live editor protocol version matches')
        self.check(Path(status['project_root']).resolve()==project.resolve(),'Editor identity matches configured project')
        for dimensions in (2,3):
            scene_path=f'res://scenes/World{dimensions}D.tscn'
            create_args={'path':scene_path,'root_type':f'Node{dimensions}D','root_name':f'World{dimensions}D'}
            if dimensions==2:
                # A cold editor can finish loading layout/history after its first heartbeat.
                # Retry ONLY a definitive pre-mutation stale_scene rejection for this new
                # disposable fixture file. Never retry timeout/outcome_unknown or an existing file.
                self.initial_create(create_args,project)
            else:
                self.mutate('scene_create',create_args)
            self.check(self.status()['scene']['path']==scene_path,f'{dimensions}D scene created and opened in editor')
            self.check(self.paths()==['.'],f'{dimensions}D root appears in live hierarchy')
            self.create_node('.',f'Node{dimensions}D','Actor')
            actor_id=self.inspect('Actor')['node']['node_id']
            vector={'type':f'Vector{dimensions}','x':32,'y':48}
            if dimensions==3:vector['z']=-4
            self.mutate('property_set',{'property':'position','value':vector},'Actor')
            self.check(self.value('Actor','position')==vector,f'{dimensions}D native typed position changed')
            stale=self.node_guard('Actor')
            self.mutate('node_rename',{'name':'Hero'},'Actor')
            self.expect_error('property_set',{**stale,'property':'visible','value':False},'stale_scene')
            self.check(self.inspect('Hero')['node']['node_id']==actor_id,f'{dimensions}D rename preserves node identity')
            self.mutate('node_duplicate',{'name':'HeroCopy'},'Hero')
            self.check('HeroCopy' in self.paths(),f'{dimensions}D duplicate exists')
            self.check(self.inspect('HeroCopy')['node']['node_id']!=actor_id,f'{dimensions}D duplicate has distinct identity')
            self.create_node('.',f'Node{dimensions}D','Group')
            parent=self.inspect('Group')['node']
            self.mutate('node_reparent',{'new_parent_path':'Group','expected_new_parent_id':parent['node_id'],'keep_global_transform':True},'HeroCopy')
            self.check('Group/HeroCopy' in self.paths(),f'{dimensions}D reparent changes live hierarchy')
            self.mutate('node_delete',{},'Group/HeroCopy')
            self.check('Group/HeroCopy' not in self.paths(),f'{dimensions}D delete removes live node')
            self.mutate('editor_undo')
            self.check('Group/HeroCopy' in self.paths(),f'{dimensions}D native undo restores deleted node')
            self.mutate('editor_redo')
            self.check('Group/HeroCopy' not in self.paths(),f'{dimensions}D native redo deletes again')
            self.expect_error('node_delete',self.node_guard('.'),'root_protected')
            wrong={**self.node_guard('Hero'),'expected_node_id':'1'}
            self.expect_error('node_rename',{**wrong,'name':'Wrong'},'stale_node')
            self.expect_error('property_set',{**self.node_guard('Hero'),'property':'script','value':'not allowed'},'property_forbidden')
            suffix='cs' if language=='csharp' else 'gd'
            source_path=f'res://scripts/Written{dimensions}D.{suffix}'
            source=(f'using Godot;\npublic partial class Written{dimensions}D : Node{dimensions}D {{ }}\n' if language=='csharp' else f'extends Node{dimensions}D\nvar marker: int = {dimensions}\nfunc OnPressed() -> void:\n\thide()\n')
            write=self.mcp.call('script_write',{'path':source_path,'source':source})
            read=self.mcp.call('script_read',{'path':source_path})
            self.check(read['source']==source and read['sha256']==write['sha256'],f'{language} script create/read and hash agree')
            self.expect_error('script_write',{'path':source_path,'source':source+'\n','overwrite':True,'expected_sha256':'0'*64},'disk_conflict')
            edited=self.mcp.call('script_write',{'path':source_path,'source':source+'\n','overwrite':True,'expected_sha256':read['sha256']})
            self.check(edited['sha256']!=read['sha256'],f'{language} guarded script edit changes content hash')
            attach_path=f'res://scripts/BridgeActor{dimensions}D.cs' if language=='csharp' else source_path
            self.mutate('script_attach',{'script_path':attach_path},'Hero')
            self.check(self.inspect('Hero')['node']['script_path']==attach_path,f'{language} script attached to {dimensions}D node')
            if dimensions==2:
                self.create_node('.','Button','HideButton')
                self.mutate('property_set',{'property':'text','value':'Hide hero'},'HideButton')
                self.check(self.value('HideButton','text')=='Hide hero','Native Control text is editable')
                hero=self.inspect('Hero')['node']
                signal_args={'signal':'pressed','target_path':'Hero','expected_target_id':hero['node_id'],'method':'OnPressed'}
                self.mutate('signal_connect',signal_args,'HideButton')
                self.check(len(self.inspect('HideButton')['connections'])==1,'Persistent signal connection is visible')
                self.expect_error('signal_connect',{**self.node_guard('HideButton'),**signal_args},'connection_exists')
                self.mutate('signal_disconnect',signal_args,'HideButton')
                self.check(not self.inspect('HideButton')['connections'],'Signal disconnect removes persistent connection')
                self.mutate('editor_undo')
                self.check(len(self.inspect('HideButton')['connections'])==1,'Undo restores persistent signal connection')
                self.expect_error('signal_connect',{**self.node_guard('HideButton'),'signal':'pressed','target_path':'.','expected_target_id':self.inspect('.')['node']['node_id'],'method':'queue_free'})
                self.check('.' in self.paths(),'Signal guard prevents native root-destruction callback')
                self.create_node('.','Button','RefButton')
                self.mutate('property_set',{'property':'focus_neighbor_right','value':{'type':'NodePath','value':'../RefButton'}},'HideButton')
                self.expect_error('node_rename',{**self.node_guard('RefButton'),'name':'BrokenReference'})
                self.check('RefButton' in self.paths(),'Referenced native NodePath target stays unchanged')
                self.create_node('.','CollisionShape2D','Collider')
                self.mcp.call('resource_create',{'path':'res://resources/collision2d.tres','type':'RectangleShape2D','properties':{'size':{'type':'Vector2','x':20,'y':12}}})
                self.mutate('resource_assign',{'property':'shape','resource_path':'res://resources/collision2d.tres'},'Collider')
                self.check(self.value('Collider','shape')['class']=='RectangleShape2D','2D shape Resource assigned through editor')
            else:
                self.create_node('.','MeshInstance3D','Mesh')
                self.mcp.call('resource_create',{'path':'res://resources/box.tres','type':'BoxMesh','properties':{'size':{'type':'Vector3','x':2,'y':1,'z':3}}})
                self.mutate('resource_assign',{'property':'mesh','resource_path':'res://resources/box.tres'},'Mesh')
                self.check(self.value('Mesh','mesh')['class']=='BoxMesh','3D mesh Resource assigned through editor')
                self.mcp.call('resource_create',{'path':'res://resources/material.tres','type':'StandardMaterial3D','properties':{'albedo_color':{'type':'Color','r':.2,'g':.6,'b':.9,'a':1}}})
                self.mutate('resource_assign',{'property':'material_override','resource_path':'res://resources/material.tres'},'Mesh')
                self.check(self.value('Mesh','material_override')['class']=='StandardMaterial3D','3D material Resource assigned')
                self.create_node('.','Camera3D','Camera')
                self.mutate('property_set',{'property':'position','value':{'type':'Vector3','x':0,'y':2,'z':6}},'Camera')
                self.mutate('property_set',{'property':'current','value':True},'Camera')
                self.create_node('.','DirectionalLight3D','Sun')
                self.check('Camera' in self.paths() and 'Sun' in self.paths(),'3D camera and light created live')
            self.save()
            self.check((project/scene_path[6:]).is_file(),f'{dimensions}D scene saved to disk')
            self.check('Hero' in (project/scene_path[6:]).read_text(encoding="utf-8"),f'{dimensions}D saved content contains edited node')
        # Explicit current/main/custom execution goes through EditorInterface, never shell eval.
        for operation,args in [('play_current',{}),('play_main',{}),('play_custom',{'path':'res://scenes/World2D.tscn'})]:
            result=self.mutate(operation,args)
            self.check(result.get('play_requested') is True,f'{operation} accepted by real editor')
            deadline=time.monotonic()+10
            while not self.status()['playing'] and time.monotonic()<deadline:time.sleep(.05)
            self.check(self.status()['playing'],f'{operation} reaches playing state')
            self.mcp.call('stop')
            deadline=time.monotonic()+10
            while self.status()['playing'] and time.monotonic()<deadline:time.sleep(.05)
            self.check(not self.status()['playing'],f'{operation} stops through editor')
        self.mutate('scene_open',{'path':'res://scenes/World2D.tscn'})
        self.check('Hero' in self.paths(),'Opening existing scene restores edited hierarchy')
        self.check(len(self.inspect('HideButton')['connections'])==1,'Saved signal connection survives tab reopening')
        self.expect_error('scene_create',{**self.guard(),'path':'res://scenes/World2D.tscn','root_type':'Node2D','root_name':'Overwrite'},'file_exists')
        self.expect_error('script_write',{'path':'res://../escape.gd','source':'extends Node'},'unsafe_path')
        self.expect_error('script_read',{'path':'res://addons/ai_editor_bridge/plugin.gd'},'unsafe_path')
        self.expect_error('script_write',{'path':'res://scripts/tool.gd','source':'@tool\nextends Node\n'},'tool_script_forbidden')
        self.check(not (project/'scripts/tool.gd').exists(),'Rejected tool source creates no file')
        current=project/'scenes/World2D.tscn';original=current.read_bytes()
        current.write_bytes(original+b'\n; external change\n')
        self.expect_error('scene_save',{**self.guard(),'expected_disk_sha256':self.status()['scene']['disk_sha256']},'disk_conflict')
        self.check(current.read_bytes()==original+b'\n; external change\n','Disk conflict preserves external content')
        current.write_bytes(original)
        diagnostics=self.mcp.call('diagnostics',{'limit':100})
        self.check(any(not e['ok'] for e in diagnostics['entries']),'Bridge diagnostics include rejected operations')
        catalog_status=self.status()
        self.mutate('scene_create',{'path':'res://scenes/NativeCatalog.tscn','root_type':'Node','root_name':'NativeCatalog'})
        for node_type in catalog_status['node_types']:
            name='Test'+node_type
            self.create_node('.',node_type,name)
            self.check(self.inspect(name)['node']['type']==node_type,f'Allowlisted native node creates and inspects: {node_type}')
        for resource_type in catalog_status['resource_types']:
            result=self.mcp.call('resource_create',{'path':f'res://resources/catalog_{resource_type}.tres','type':resource_type})
            self.check(result['type']==resource_type,f'Allowlisted native Resource saves: {resource_type}')
        self.mutate('property_set',{'property':'hframes','value':2},'TestSprite2D')
        self.mutate('property_set',{'property':'vframes','value':2},'TestSprite2D')
        self.mutate('property_set',{'property':'frame_coords','value':{'type':'Vector2i','x':1,'y':1}},'TestSprite2D')
        self.check(self.value('TestSprite2D','frame_coords')=={'type':'Vector2i','x':1,'y':1},'Native integer-vector property codec roundtrip')
        self.save()
        return {'checks':self.checks,'status':self.status(),'operations_tested':sorted({e['request'].get('params',{}).get('name','')[6:] for e in self.mcp.trace if e['request']['method']=='tools/call'})}


def engine_environment(base:Path,dotnet:str|None):
    env=os.environ.copy()
    for key,name in [('XDG_DATA_HOME','data'),('XDG_CONFIG_HOME','config'),('XDG_CACHE_HOME','cache'),('DOTNET_CLI_HOME','dotnet_home')]:
        folder=base/name;folder.mkdir(parents=True,exist_ok=True);env[key]=str(folder)
    env['HOME']=str(base/'home');Path(env['HOME']).mkdir()
    for key,folder in [('USERPROFILE','home'),('APPDATA','appdata'),('LOCALAPPDATA','localappdata'),('NUGET_PACKAGES','nuget')]:
        path=base/folder;path.mkdir(exist_ok=True);env[key]=str(path)
    env['PYTHONUTF8']='1'
    env['DOTNET_CLI_TELEMETRY_OPTOUT']='1';env['DOTNET_SKIP_FIRST_TIME_EXPERIENCE']='1';env['DOTNET_GENERATE_ASPNET_CERTIFICATE']='false'
    if dotnet:
        env['DOTNET_ROOT']=str(Path(dotnet).resolve().parent);env['PATH']=env['DOTNET_ROOT']+os.pathsep+env.get('PATH','')
    return env


def wait_for_editor_ready(engine, status_path, *, previous_session=None, expected_scene="res://scenes/Seed.tscn", timeout=60):
    """Wait for the explicit CLI scene and progressing, stable editor heartbeat."""
    deadline=time.monotonic()+timeout
    stable_key=None;stable_since=0.0;first_heartbeat=None
    while time.monotonic()<deadline:
        if engine.poll() is not None:raise CheckFailure(f'Editor exited during startup: {engine.returncode}')
        try:
            value=json.loads(status_path.read_text(encoding="utf-8"))
            scene=value.get('scene',{})
            valid=(value.get('enabled') and value.get('session_id')!=previous_session
                   and bool(scene.get('path'))
                   and (expected_scene is None or scene.get('path')==expected_scene))
            key=(value.get('session_id'),scene.get('path'),scene.get('revision')) if valid else None
            heartbeat=value.get('heartbeat_unix')
            now=time.monotonic()
            if key is None:
                stable_key=None
            elif key!=stable_key:
                stable_key=key;stable_since=now;first_heartbeat=heartbeat
            elif now-stable_since>=1.0 and isinstance(heartbeat,(int,float)) and heartbeat!=first_heartbeat:
                return value
        except (FileNotFoundError,json.JSONDecodeError):
            stable_key=None
        time.sleep(.1)
    raise CheckFailure('Editor did not activate and settle a valid startup scene')


def stop_editor(engine, project, log):
    if engine.poll() is not None:return False
    log.write('\nBRIDGE_TEST_SHUTDOWN_BEGIN\n');log.flush()
    (project/'.godot'/'editor_bridge_test_quit').write_text('quit', encoding="utf-8")
    try:
        engine.wait(timeout=15)
        return False
    except subprocess.TimeoutExpired:
        log.write('\nBRIDGE_TEST_FORCED_TERMINATION\n');log.flush()
        engine.terminate()
        try:engine.wait(timeout=5)
        except subprocess.TimeoutExpired:engine.kill();engine.wait()
        return True


def run(godot:str,dotnet:str|None,language:str,work:Path):
    work.mkdir(parents=True,exist_ok=False)
    project=work/'project 空间';project.mkdir()
    (project/'project.godot').write_text('config_version=5\n[application]\nconfig/name="Editor Bridge Integration"\nrun/main_scene="res://scenes/Seed.tscn"\n[editor]\nrun/main_run_args="--headless"\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n',encoding='utf-8')
    (project/'scenes').mkdir();(project/'scripts').mkdir();(project/'resources').mkdir()
    (project/'scenes'/'Seed.tscn').write_text('[gd_scene format=3]\n[node name="Seed" type="Node2D"]\n', encoding="utf-8")
    if language=='csharp':
        with (project/'project.godot').open('a') as config:
            config.write('\n[dotnet]\nproject/assembly_name="BridgeTest"\n')
        (project/'BridgeTest.csproj').write_text('<Project Sdk="Godot.NET.Sdk/4.6.3"><PropertyGroup><TargetFramework>net8.0</TargetFramework><EnableDynamicLoading>true</EnableDynamicLoading><Nullable>enable</Nullable></PropertyGroup></Project>\n', encoding="utf-8")
    setup(project,apply=True,enable=True)
    # Fixture-only orderly shutdown. Not a production MCP operation or shipped addon.
    shutdown=project/'addons'/'editor_test_shutdown';shutdown.mkdir()
    (shutdown/'plugin.cfg').write_text('[plugin]\nname="Integration Shutdown"\ndescription="Disposable test fixture only"\nauthor="Test Harness"\nversion="1"\nscript="shutdown.gd"\n', encoding="utf-8")
    (shutdown/'shutdown.gd').write_text('@tool\nextends EditorPlugin\nfunc _enter_tree() -> void:\n\tset_process(true)\nfunc _process(_delta: float) -> void:\n\tif FileAccess.file_exists("res://.godot/editor_bridge_test_quit"):\n\t\tDirAccess.remove_absolute("res://.godot/editor_bridge_test_quit")\n\t\tget_tree().quit()\n', encoding="utf-8")
    config=(project/'project.godot').read_text(encoding="utf-8")
    config=config.replace('enabled=PackedStringArray("res://addons/ai_editor_bridge/plugin.cfg")', 'enabled=PackedStringArray("res://addons/ai_editor_bridge/plugin.cfg", "res://addons/editor_test_shutdown/plugin.cfg")')
    (project/'project.godot').write_text(config, encoding="utf-8")
    env=engine_environment(work,dotnet)
    if language=='csharp':
        for dimensions in (2,3):
            (project/'scripts'/f'BridgeActor{dimensions}D.cs').write_text(f'using Godot;\npublic partial class BridgeActor{dimensions}D : Node{dimensions}D {{ public void OnPressed() {{ Hide(); }} }}\n', encoding="utf-8")
        build=subprocess.run([dotnet,'build',str(project/'BridgeTest.csproj'),'--nologo'],cwd=project,env=env,capture_output=True,text=True,timeout=120)
        (work/'csharp-initial-build.log').write_text(build.stdout+build.stderr, encoding="utf-8")
        if build.returncode:raise CheckFailure('Initial C# fixture build failed')
    editor_log=(work/'editor.log').open('w');mcp_log=(work/'mcp.log').open('w')
    engine=subprocess.Popen([godot,'--headless','--editor','--path',str(project),'res://scenes/Seed.tscn'],stdout=editor_log,stderr=subprocess.STDOUT,env=env)
    mcp=None;scenario=None
    try:
        status_path=project/'.godot/ai_bridge/status.json'
        wait_for_editor_ready(engine,status_path)
        mcp=Mcp(project,env,mcp_log)
        scenario=Scenario(mcp);result=scenario.run(language,project)
        first_session=result['status']['session_id'];first_trace=list(mcp.trace)
        mcp.close();mcp=None
        if stop_editor(engine,project,editor_log):raise CheckFailure('Orderly editor restart required force termination')
        editor_log.write('\nBRIDGE_TEST_RESTART_BEGIN\n');editor_log.flush()
        engine=subprocess.Popen([godot,'--headless','--editor','--path',str(project),'res://scenes/Seed.tscn'],stdout=editor_log,stderr=subprocess.STDOUT,env=env)
        wait_for_editor_ready(engine,status_path,previous_session=first_session,expected_scene=None)
        mcp=Mcp(project,env,mcp_log);reopened=Scenario(mcp)
        reopened.check(reopened.status()['session_id']!=first_session,'Editor restart establishes a new guarded session')
        for dimensions in (2,3):
            reopened.mutate('scene_open',{'path':f'res://scenes/World{dimensions}D.tscn'})
            reopened.check('Hero' in reopened.paths() and 'Group' in reopened.paths(),f'{dimensions}D hierarchy survives process restart')
            reopened.check('Group/HeroCopy' not in reopened.paths(),f'{dimensions}D redo deletion persists after restart')
            script_path=reopened.inspect('Hero')['node']['script_path']
            reopened.check(script_path.endswith('.cs' if language=='csharp' else '.gd'),f'{dimensions}D {language} attachment persists after restart')
            if dimensions==2:reopened.check(len(reopened.inspect('HideButton')['connections'])==1,'Signal connection persists after process restart')
            else:reopened.check(reopened.value('Mesh','mesh')['class']=='BoxMesh','3D mesh assignment persists after process restart')
        result['checks'].extend(reopened.checks)
        if language=='csharp':
            build=subprocess.run([dotnet,'build',str(project/'BridgeTest.csproj'),'--nologo'],cwd=project,env=env,capture_output=True,text=True,timeout=120)
            (work/'csharp-final-build.log').write_text(build.stdout+build.stderr, encoding="utf-8")
            if build.returncode:raise CheckFailure('Final generated C# sources did not compile')
            result['checks'].append({'check':'MCP-written C# sources compile with the project','passed':True})
        runtime_checks=[]
        for dimensions in (2,3):
            runtime=subprocess.run([godot,'--headless','--path',str(project),f'res://scenes/World{dimensions}D.tscn','--quit-after','8'],env=env,cwd=project,capture_output=True,text=True,timeout=30)
            log=runtime.stdout+runtime.stderr
            (work/f'runtime-{dimensions}d.log').write_text(log, encoding="utf-8")
            if runtime.returncode or re.search(r'(?m)^\s*(?:SCRIPT ERROR:|ERROR:)',log):
                raise CheckFailure(f'Generated {dimensions}D scene runtime validation failed; inspect runtime-{dimensions}d.log')
            runtime_checks.append({'scene':f'World{dimensions}D.tscn','returncode':runtime.returncode,'clean_log':True})
            result['checks'].append({'check':f'Generated {dimensions}D scene runs with no engine/script error log','passed':True})
        editor_log.flush()
        raw_log=(work/'editor.log').read_text(encoding="utf-8")
        active_log='';active=True
        for line in raw_log.splitlines():
            if line=='BRIDGE_TEST_SHUTDOWN_BEGIN':active=False;continue
            if line=='BRIDGE_TEST_RESTART_BEGIN':active=True;continue
            if active:active_log+=line+'\n'
        if re.search(r'(?m)^\s*(?:SCRIPT ERROR:|ERROR:)',active_log):
            (work/'active-editor-errors.log').write_text(active_log, encoding="utf-8")
            raise CheckFailure('Active editor emitted an engine/script error; inspect active-editor-errors.log')
        result['checks'].append({'check':'Active editor log has no engine/script errors (teardown boundaries recorded)','passed':True})
        result.update(passed=True,language=language,project=str(project),godot=godot,restarted=True,runtime_checks=runtime_checks,orderly_restart=True,teardown_log_boundaries_recorded=True)
        (work/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n', encoding="utf-8")
        (work/'mcp-transcript.json').write_text(json.dumps(first_trace+mcp.trace,ensure_ascii=False,indent=2)+'\n', encoding="utf-8")
        return result
    finally:
        if mcp:
            (work/'latest-mcp-transcript.json').write_text(json.dumps(mcp.trace,ensure_ascii=False,indent=2)+'\n', encoding="utf-8")
        if scenario:
            (work/'latest-checks.json').write_text(json.dumps(scenario.checks,ensure_ascii=False,indent=2)+'\n', encoding="utf-8")
        if mcp:mcp.close()
        if engine.poll() is None:
            stop_editor(engine,project,editor_log)
        editor_log.close();mcp_log.close()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--godot',required=True);p.add_argument('--dotnet');p.add_argument('--language',choices=['gdscript','csharp'],default='gdscript');p.add_argument('--work-dir',type=Path,required=True);a=p.parse_args()
    try:
        result=run(a.godot,a.dotnet,a.language,a.work_dir)
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    except Exception as e:
        print(json.dumps({'passed':False,'error':str(e),'work_dir':str(a.work_dir)},ensure_ascii=False));return 1
if __name__=='__main__':raise SystemExit(main())
