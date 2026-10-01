"""Real stdio transcripts and adversarial file-IPC tests; Python stdlib only."""
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from platform_support import SYMLINK_AVAILABLE
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
from editor_bridge_client import (BridgeError, EditorBridgeClient, OPERATIONS, ProjectFiles,
                                  MAX_REQUEST_BYTES, MAX_RESPONSE_BYTES, validate_schema)
from godot_mcp_server import MAX_FRAME_BYTES, McpServer, serve


def frame(value):
    return json.dumps(value, ensure_ascii=False).encode('utf-8') + b'\n'


def request(method, params=None, ident=1):
    value = {'jsonrpc': '2.0', 'id': ident, 'method': method}
    if params is not None:
        value['params'] = params
    return value


def initialize(version='2025-11-25', ident=1):
    return request('initialize', {'protocolVersion': version, 'capabilities': {}, 'clientInfo': {'name': 'transport-tests', 'version': '1.0'}}, ident)


INITIALIZED = {'jsonrpc': '2.0', 'method': 'notifications/initialized'}
SESSION = 'a' * 32


class FakeEditor:
    def __init__(self, root, handler=None):
        self.root = root
        self.bridge = root / '.godot/ai_bridge'
        (self.bridge / 'requests').mkdir(parents=True)
        (self.bridge / 'responses').mkdir()
        self.status_value = {'protocol_version': 1, 'session_id': SESSION, 'project_root': str(root),
                             'engine_version': {'string': '4.6.3'}, 'scene': {'path': 'res://main.tscn', 'root_name': 'Main',
                             'root_type': 'Node2D', 'revision': 'session:123:7', 'root_instance_id': '123', 'disk_sha256': 'b' * 64},
                             'playing': False, 'capabilities': list(OPERATIONS), 'heartbeat_unix': time.time()}
        self.handler = handler
        self.seen = []
        self.event = threading.Event()
        self.thread = None
        self.thread_error = None
        self.write_status()

    def write_status(self):
        path = self.bridge / 'status.json'
        temp = self.bridge / 'status.tmp'
        temp.write_text(json.dumps(self.status_value), encoding='utf-8')
        deadline = time.monotonic() + 0.25
        while True:
            try:
                temp.replace(path)
                break
            except PermissionError:
                if os.name != 'nt' or time.monotonic() >= deadline:
                    raise
                time.sleep(0.005)

    def __enter__(self):
        def run():
            try:
                while not self.event.wait(0.005):
                    for path in (self.bridge / 'requests').glob('*.json'):
                        # Match the real addon's completed-ID cache before reopening a file.
                        if any(old['id'] == path.stem for old in self.seen):
                            continue
                        try:
                            value = json.loads(path.read_text(encoding="utf-8"))
                        except (FileNotFoundError, ValueError):
                            continue
                        except PermissionError:
                            if os.name != 'nt':
                                raise
                            continue
                        if any(old['id'] == value['id'] for old in self.seen):
                            continue
                        self.seen.append(value)
                        result = self.handler(value, self) if self.handler else {'id': value['id'], 'session_id': SESSION, 'ok': True,
                                                                             'result': {'echo': value['arguments'], 'operation': value['operation']}}
                        if result is not None:
                            response = self.bridge / 'responses' / path.name
                            temp = response.with_suffix('.tmp')
                            temp.write_bytes(result if isinstance(result, bytes) else json.dumps(result).encode())
                            temp.replace(response)
            except Exception as exc:
                self.thread_error = exc
        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.event.set()
        if self.thread:
            self.thread.join(timeout=3)
        if self.thread_error is not None:
            raise RuntimeError("Fake editor background failed") from self.thread_error


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='godot IPC 空间 ')
        self.root = Path(self.temp.name).resolve() / 'project with spaces'
        self.root.mkdir()
        (self.root / 'project.godot').write_text('config_version=5\n', encoding="utf-8")
        (self.root / 'main.tscn').write_text('[gd_scene format=3]\n[node name="Main" type="Node2D"]\n', encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def client(self, **kwargs):
        return EditorBridgeClient(self.root, timeout=kwargs.pop('timeout', 0.15), **kwargs)

    def transcript(self, messages, *, project=True, raw=False, extra_env=None):
        env = os.environ.copy()
        env.pop('GODOT_PROJECT_PATH', None)
        env.update(extra_env or {})
        command = [sys.executable, str(SCRIPTS / 'godot_mcp_server.py'), '--timeout', '0.15']
        if project:
            command += ['--project', str(self.root)]
        data = messages if raw else b''.join(frame(m) for m in messages)
        result = subprocess.run(command, input=data, capture_output=True, env=env, timeout=5)
        return result, [json.loads(line) for line in result.stdout.splitlines()]

    def assert_error(self, code, fn):
        with self.assertRaises(BridgeError) as caught:
            fn()
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_explicit_project_required(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assert_error('project_required', lambda: EditorBridgeClient())

    def test_config_regular_file_required(self):
        (self.root / 'project.godot').unlink()
        self.assert_error('invalid_project', self.client)

    def test_no_project_still_lists_tools_and_explains_configuration(self):
        proc, messages = self.transcript([initialize(), INITIALIZED, request('tools/list', ident=2),
                                         request('tools/call', {'name': 'godot_status', 'arguments': {}}, 3)], project=False)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stderr, b'')
        self.assertEqual(len(messages[1]['result']['tools']), len(OPERATIONS))
        self.assertEqual(messages[2]['result']['structuredContent']['error']['code'], 'project_required')

    def test_real_subprocess_handshake_call_and_protocol_only_stdout(self):
        with FakeEditor(self.root) as editor:
            proc, messages = self.transcript([initialize(), INITIALIZED, request('ping', ident='p'),
                request('tools/list', ident=3), request('tools/call', {'name': 'godot_hierarchy', 'arguments': {'max_depth': 2}}, 4)])
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stderr, b'')
        self.assertEqual([m['id'] for m in messages], [1, 'p', 3, 4])
        self.assertEqual(messages[0]['result']['protocolVersion'], '2025-11-25')
        self.assertEqual(messages[3]['result']['structuredContent']['operation'], 'hierarchy')
        self.assertEqual(len(editor.seen), 1)
        self.assertEqual(editor.seen[0]['project_root'], str(self.root))
        self.assertEqual(editor.seen[0]['session_id'], SESSION)
        self.assertRegex(editor.seen[0]['id'], r'^[0-9a-f]{32}$')
        self.assertFalse(list((editor.bridge / 'requests').iterdir()))
        self.assertFalse(list((editor.bridge / 'responses').iterdir()))

    def test_env_project_selection(self):
        with FakeEditor(self.root):
            proc, messages = self.transcript([initialize(), INITIALIZED, request('tools/call', {'name': 'godot_status'})],
                                             project=False, extra_env={'GODOT_PROJECT_PATH': str(self.root)})
        self.assertFalse(messages[-1]['result']['isError'])

    def test_version_negotiation(self):
        for version, expected in [('2025-06-18', '2025-06-18'), ('2025-03-26', '2025-03-26'), ('future', '2025-11-25')]:
            with self.subTest(version=version):
                proc, messages = self.transcript([initialize(version)], project=False)
                self.assertEqual(messages[0]['result']['protocolVersion'], expected)

    def test_handshake_required(self):
        proc, messages = self.transcript([request('tools/list'), initialize(ident=2), request('tools/list', ident=3),
                                         INITIALIZED, request('tools/list', ident=4)], project=False)
        self.assertEqual(messages[0]['error']['code'], -32002)
        self.assertEqual(messages[2]['error']['code'], -32002)
        self.assertIn('tools', messages[3]['result'])

    def test_unknown_methods_tools_and_extra_fields(self):
        proc, messages = self.transcript([initialize(), INITIALIZED, request('exec', ident=2),
            request('tools/call', {'name': 'godot_eval', 'arguments': {'code': 'unsafe'}}, 3),
            request('tools/call', {'name': 'godot_status', 'arguments': [], 'extra': 1}, 4), request('tools/list', {'cursor': 'invalid'}, 5)], project=False)
        self.assertEqual([m['error']['code'] for m in messages[1:]], [-32601, -32602, -32602, -32602])

    def test_bad_frames_recover_and_stdout_remains_json(self):
        bad = [b'{broken}\n', b'Content-Length: 12\n', b'\xff\n', b'[]\n', b'{"jsonrpc":"2.0","method":0}\n',
               b'{"jsonrpc":"2.0","id":1,"id":2,"method":"ping"}\n', b'{"jsonrpc":"2.0","id":1,"method":"ping","params":{"x":NaN}}\n',
               b'{"jsonrpc":"2.0","id":1,"method":"ping","params":{"x":"\\ud800"}}\n']
        proc, messages = self.transcript(b''.join(bad) + frame(request('ping', ident=99)), raw=True, project=False)
        self.assertEqual(len(messages), len(bad) + 1)
        self.assertEqual(messages[-1], {'jsonrpc': '2.0', 'id': 99, 'result': {}})
        self.assertEqual(proc.stderr, b'')

    def test_invalid_ids_are_rejected(self):
        for ident in [None, True, 1.25, [], {}, 'x' * 257]:
            with self.subTest(ident=ident):
                proc, messages = self.transcript([request('ping', ident=ident)], project=False)
                self.assertEqual(messages[0]['id'], None)
                self.assertEqual(messages[0]['error']['code'], -32600)

    def test_no_tools_executed_as_notification(self):
        with FakeEditor(self.root) as editor:
            call = {'jsonrpc': '2.0', 'method': 'tools/call', 'params': {'name': 'godot_stop', 'arguments': {}}}
            proc, messages = self.transcript([initialize(), INITIALIZED, call, request('ping', ident=2)])
            self.assertEqual(editor.seen, [])
        self.assertEqual(len(messages), 2)

    def test_oversized_and_unterminated_frames_close_connection(self):
        for data in [b'x' * (MAX_FRAME_BYTES + 1) + b'\n', b'{"jsonrpc":"2.0","id":1,"method":"ping"}']:
            proc, messages = self.transcript(data, raw=True, project=False)
            self.assertEqual(proc.returncode, 2)
            self.assertEqual(messages[0]['error']['code'], -32700)

    def test_every_schema_and_annotations_are_explicit(self):
        for name, spec in OPERATIONS.items():
            self.assertEqual(spec['inputSchema']['type'], 'object', name)
            self.assertFalse(spec['inputSchema']['additionalProperties'], name)
            self.assertEqual(set(spec['annotations']), {'readOnlyHint', 'destructiveHint', 'idempotentHint', 'openWorldHint'})
            self.assertEqual(spec['annotations']['openWorldHint'], name.startswith('play_'))
        self.assertTrue(OPERATIONS['node_delete']['annotations']['destructiveHint'])
        self.assertTrue(OPERATIONS['script_read']['annotations']['readOnlyHint'])

    def test_invalid_arguments_never_reach_editor(self):
        cases = [('status', {'unknown': 1}), ('hierarchy', {'max_depth': True}), ('hierarchy', {'max_depth': 99}),
                 ('node_create', {'type': 'Node', 'name': 'A', 'parent_path': '.'}),
                 ('property_set', {'expected_scene_path': 'res://main.tscn', 'expected_revision': 'r', 'node_path': '.',
                    'expected_node_id': '123', 'property': 'position', 'value': {'type': 'Object', 'method': 'call'}}),
                 ('script_write', {'path': 'res://a.gd', 'source': 'extends Node', 'overwrite': True}),
                 ('script_write', {'path': 'res://a.gd', 'source': 'extends Node', 'expected_sha256': 'a' * 64})]
        with FakeEditor(self.root) as editor:
            for operation, arguments in cases:
                self.assert_error('invalid_arguments', lambda: self.client().call(operation, arguments))
            self.assertEqual(editor.seen, [])

    def test_resource_traversals_aliases_and_internal_paths_rejected(self):
        client = self.client()
        for path in ['res://../secret.gd', 'res:///etc/secret.gd', 'res://a//b.gd', 'res://a/./b.gd', 'res://a/../b.gd',
                     'res://a\\b.gd', 'res://C:/a.gd', 'res://a:stream.gd', 'user://a.gd', 'res://.godot/a.gd',
                     'res://.git/a.gd', 'res://.codex/config.gd', 'res://.agents/private.gd', 'res://project.godot', 'res://addons/ai_editor_bridge/plugin.gd', 'res://addons/godot_ai_bridge/plugin.gd',
                     'res://AUX.gd', 'res://path. /a.gd', 'res://a\nb.gd']:
            with self.subTest(path=path):
                self.assert_error('unsafe_path', lambda: client.validate_arguments('script_read', {'path': path}))

    def test_node_traversal_rejected(self):
        for path in ['..', '../A', '/root/Main', 'A/../B', 'A//B', 'A:position', 'A\\B']:
            self.assert_error('unsafe_node_path', lambda: self.client().validate_arguments('node_inspect', {'node_path': path}))

    def test_unicode_project_and_resource_path(self):
        self.client().validate_arguments('script_write', {'path': 'res://场景 source.gd', 'source': 'extends Node\n'})

    @unittest.skipUnless(SYMLINK_AVAILABLE, 'Symlinks unavailable')
    def test_symlink_project_config_and_resource_rejected(self):
        outside = Path(self.temp.name) / 'external.gd'
        outside.write_text('secret', encoding="utf-8")
        (self.root / 'linked.gd').symlink_to(outside)
        self.assert_error('unsafe_path', lambda: self.client().validate_arguments('script_read', {'path': 'res://linked.gd'}))
        (self.root / 'project.godot').unlink()
        (self.root / 'project.godot').symlink_to(outside)
        self.assert_error('unsafe_path', self.client)
        linked_project = Path(self.temp.name) / 'linked-project'
        linked_project.symlink_to(self.root, target_is_directory=True)
        self.assert_error('unsafe_path', lambda: EditorBridgeClient(linked_project))

    @unittest.skipUnless(SYMLINK_AVAILABLE, 'Symlinks unavailable')
    def test_symlink_resource_parent_and_ipc_directory_rejected(self):
        outside = Path(self.temp.name) / 'external'
        outside.mkdir()
        (self.root / 'subdir').symlink_to(outside, target_is_directory=True)
        self.assert_error('unsafe_path', lambda: self.client().validate_arguments('script_write', {'path': 'res://subdir/new.gd', 'source': ''}))
        (self.root / '.godot').symlink_to(outside, target_is_directory=True)
        self.assert_error('unsafe_path', lambda: self.client().call('status'))

    @unittest.skipUnless(SYMLINK_AVAILABLE, 'Symlinks unavailable')
    def test_symlink_response_never_read_and_foreign_file_untouched(self):
        outside = Path(self.temp.name) / 'secret.json'
        outside.write_text('{"secret":"never read"}', encoding="utf-8")
        def handler(value, editor):
            (editor.bridge / 'responses' / (value['id'] + '.json')).symlink_to(outside)
        with FakeEditor(self.root, handler):
            self.assert_error('unsafe_path', lambda: self.client().call('status'))
        self.assertEqual(outside.read_text(encoding="utf-8"), '{"secret":"never read"}')

    def test_unavailable_stale_foreign_and_invalid_status(self):
        self.assert_error('editor_unavailable', lambda: self.client().call('status'))
        editor = FakeEditor(self.root)
        for field, value, code in [('heartbeat_unix', time.time() - 100, 'editor_stale'), ('heartbeat_unix', time.time() + 100, 'editor_stale'),
                                  ('project_root', '/other/project', 'project_mismatch'), ('session_id', '../../bad', 'invalid_status'),
                                  ('protocol_version', 99, 'protocol_mismatch')]:
            old = editor.status_value[field]
            editor.status_value[field] = value
            editor.write_status()
            self.assert_error(code, lambda: self.client().call('status'))
            editor.status_value[field] = old
        self.assertEqual(editor.seen, [])

    def test_valid_editor_error_is_not_unknown_outcome(self):
        def handler(value, editor):
            return {'id': value['id'], 'session_id': SESSION, 'ok': False, 'error': {'code': 'stale_revision', 'message': 'Inspect scene first'}}
        with FakeEditor(self.root, handler) as editor:
            self.assert_error('stale_revision', lambda: self.client().call('stop'))
            self.assertEqual(len(editor.seen), 1)

    def test_timeout_unknown_mutation_no_retry_cleanup_only_own_files(self):
        with FakeEditor(self.root, lambda value, editor: None) as editor:
            foreign = editor.bridge / 'requests' / ('f' * 32 + '.json')
            # Keep the fake editor from parsing a foreign malformed request.
            editor.seen.append({'id': 'f' * 32})
            foreign.write_text(json.dumps({'id': 'f' * 32, 'operation': 'status', 'arguments': {}}), encoding="utf-8")
            error = self.assert_error('outcome_unknown', lambda: self.client().call('stop'))
            self.assertEqual(error.details['cause']['code'], 'timeout')
            self.assertEqual(len(editor.seen), 2)
            self.assertTrue(foreign.exists())
            self.assertEqual(list((editor.bridge / 'requests').glob('*.json')), [foreign])
            self.assertFalse(list((editor.bridge / 'responses').iterdir()))

    def test_read_timeout_is_not_mutation_uncertainty(self):
        with FakeEditor(self.root, lambda value, editor: None) as editor:
            self.assert_error('timeout', lambda: self.client().call('hierarchy'))
            self.assertEqual(len(editor.seen), 1)

    def test_session_replacement_during_call(self):
        def handler(value, editor):
            editor.status_value['session_id'] = 'c' * 32
            editor.write_status()
            return None
        with FakeEditor(self.root, handler):
            error = self.assert_error('outcome_unknown', lambda: self.client(timeout=0.4).call('stop'))
            self.assertEqual(error.details['cause']['code'], 'stale_session')

    def test_invalid_response_id_and_session_and_envelope(self):
        for response in [{'id': '../bad', 'session_id': SESSION, 'ok': True, 'result': {}},
                         {'id': '', 'session_id': 'c' * 32, 'ok': True, 'result': {}},
                         {'id': '', 'session_id': SESSION, 'ok': 'true', 'result': {}}]:
            # Fresh IPC folders for each fake editor.
            import shutil
            shutil.rmtree(self.root / '.godot', ignore_errors=True)
            def handler(value, editor):
                return {**response, 'id': response['id'] or value['id']}
            with FakeEditor(self.root, handler):
                self.assert_error('invalid_response', lambda: self.client().call('status'))

    def test_oversized_response_and_status_bounded(self):
        with FakeEditor(self.root, lambda value, editor: b'x' * 300):
            self.assert_error('payload_too_large', lambda: self.client(max_response_bytes=128).call('status'))
        (self.root / '.godot/ai_bridge/status.json').write_bytes(b'x' * (128 * 1024 + 1))
        self.assert_error('payload_too_large', lambda: self.client().status())

    def test_script_utf8_byte_limit_and_request_limit(self):
        self.assert_error('payload_too_large', lambda: self.client().validate_arguments('script_write', {'path': 'res://a.gd', 'source': '界' * 400000}))
        with FakeEditor(self.root):
            self.assert_error('payload_too_large', lambda: self.client().files.atomic_request('.godot/ai_bridge/requests/' + 'd' * 32 + '.json', b'x' * (MAX_REQUEST_BYTES + 1)))

    def test_mutation_schema_guards_are_not_added_implicitly(self):
        with FakeEditor(self.root) as editor:
            self.assert_error('invalid_arguments', lambda: self.client().call('node_rename', {'node_path': '.', 'name': 'changed'}))
            self.assertEqual(editor.seen, [])

    def test_collision_does_not_delete_another_clients_files(self):
        from types import SimpleNamespace
        editor = FakeEditor(self.root)
        collision = 'd' * 32
        for folder in ('requests', 'responses'):
            path = editor.bridge / folder / (collision + '.json')
            path.write_text('foreign data', encoding="utf-8")
            with patch('editor_bridge_client.uuid.uuid4', return_value=SimpleNamespace(hex=collision)):
                self.assert_error('id_collision', lambda: self.client().call('status'))
            self.assertEqual(path.read_text(encoding="utf-8"), 'foreign data')
            path.unlink()

    def test_invalid_generated_request_id_is_never_published(self):
        from types import SimpleNamespace
        editor = FakeEditor(self.root)
        with patch('editor_bridge_client.uuid.uuid4', return_value=SimpleNamespace(hex='../invalid')):
            self.assert_error('invalid_id', lambda: self.client().call('status'))
        self.assertEqual(list((editor.bridge / 'requests').iterdir()), [])

    def test_integer_vector_typed_values(self):
        guard = {'expected_scene_path': 'res://main.tscn', 'expected_revision': 'r',
                 'node_path': '.', 'expected_node_id': '123', 'property': 'some_vector'}
        for value in [{'type': 'Vector2i', 'x': 1, 'y': -2}, {'type': 'Vector3i', 'x': 1, 'y': 2, 'z': 3}]:
            self.client().validate_arguments('property_set', {**guard, 'value': value})
        for value in [{'type': 'Vector2i', 'x': True, 'y': 1}, {'type': 'Vector2i', 'x': 1.5, 'y': 1},
                      {'type': 'Vector2i', 'x': 2147483648, 'y': 1}, {'type': 'Vector3i', 'x': 1, 'y': 2},
                      {'type': 'Vector3i', 'x': 1, 'y': 2, 'z': 3, 'unknown': 4}]:
            self.assert_error('invalid_arguments', lambda: self.client().validate_arguments('property_set', {**guard, 'value': value}))

    def test_property_nodepath_separate_from_root_relative_node_target(self):
        guard = {'expected_scene_path': 'res://main.tscn', 'expected_revision': 'r',
                 'node_path': 'Button', 'expected_node_id': '123', 'property': 'focus_neighbor_left'}
        for value in ['', '.', '..', '../Sibling', '../../Parent/Sibling', './Sibling']:
            self.client().validate_arguments('property_set', {**guard, 'value': {'type': 'NodePath', 'value': value}})
        for value in ['/root/Main', 'Sibling:position', 'Sibling\\Child', 'Sibling//Child', 'Sibling/', 'bad\npath']:
            self.assert_error('unsafe_node_path', lambda: self.client().validate_arguments('property_set', {**guard, 'value': {'type': 'NodePath', 'value': value}}))
        # Traversal allowed for a property value is still forbidden for operation targets.
        self.assert_error('unsafe_node_path', lambda: self.client().validate_arguments('node_inspect', {'node_path': '../Sibling'}))

    def test_api_json_matches_runtime_tools(self):
        api = json.loads((SCRIPTS.parent / 'docs/EDITOR_API.json').read_text(encoding="utf-8"))
        self.assertEqual(api['tools'], [{'name': 'godot_' + name, 'operation': name, **spec} for name, spec in OPERATIONS.items()])


if __name__ == '__main__':
    unittest.main()
