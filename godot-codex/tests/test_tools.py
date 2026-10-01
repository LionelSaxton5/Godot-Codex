"""Offline, standard-library safety/behavior tests. No Godot or account changes."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from platform_support import SYMLINK_AVAILABLE
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
from godot_inspect import ProjectError, project_root, resource_path, scan_project
from godot_validate import execute, validate

class ToolsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='godot tools 空间 ')
        self.root = Path(self.temporary.name) / 'project with spaces'
        self.root.mkdir()
        (self.root / 'project.godot').write_text('config_version=5\n[application]\nconfig/name="Lab"\n', encoding='utf-8')

    def tearDown(self):
        self.temporary.cleanup()

    def test_project_file_argument(self):
        self.assertEqual(project_root(self.root / 'project.godot'), self.root)

    def test_missing_project_rejected(self):
        with self.assertRaises(ProjectError): project_root(self.root / 'missing')

    def test_config_required(self):
        (self.root / 'project.godot').unlink()
        with self.assertRaises(ProjectError): project_root(self.root)

    def test_spaces_unicode_paths(self):
        f = self.root / '场景 with spaces.tscn'
        f.write_text('[gd_scene format=3]\n[node name="Root with spaces" type="Node2D"]\n', encoding='utf-8')
        self.assertEqual(resource_path(self.root, 'res://场景 with spaces.tscn'), f)
        self.assertEqual(scan_project(self.root)['scenes'][0]['nodes'][0]['name'], 'Root with spaces')

    def test_traversal_rejected(self):
        for value in ['res://../outside', 'res:///etc/passwd', 'res://a/../../b', 'res://a/./b', 'res://a//b', 'res://C:/test', 'res://a\\b']:
            with self.subTest(value=value), self.assertRaises(ProjectError): resource_path(self.root, value)

    def test_non_resource_paths_rejected(self):
        for value in ['user://save.dat', '/etc/passwd', 'https://example.test/file', 'res://']:
            with self.subTest(value=value), self.assertRaises(ProjectError): resource_path(self.root, value)

    @unittest.skipUnless(SYMLINK_AVAILABLE, 'symlinks unavailable')
    def test_symlink_resource_rejected(self):
        outside = Path(self.temporary.name) / 'secret.txt'
        outside.write_text('not read', encoding="utf-8")
        (self.root / 'linked.txt').symlink_to(outside)
        with self.assertRaises(ProjectError): resource_path(self.root, 'res://linked.txt')
        report = scan_project(self.root)
        self.assertNotIn('linked.txt', report['files'])
        self.assertTrue(any('symlink' in w for w in report['warnings']))

    @unittest.skipUnless(SYMLINK_AVAILABLE, 'symlinks unavailable')
    def test_symlink_directory_not_followed(self):
        outside = Path(self.temporary.name) / 'outside'
        outside.mkdir()
        (outside / 'secret.gd').write_text('secret', encoding="utf-8")
        (self.root / 'linked').symlink_to(outside, target_is_directory=True)
        self.assertFalse(any('secret' in f for f in scan_project(self.root)['files']))
        with self.assertRaises(ProjectError): resource_path(self.root, 'res://linked/secret.gd')

    @unittest.skipUnless(SYMLINK_AVAILABLE, 'symlinks unavailable')
    def test_symlink_project_config_rejected(self):
        config = self.root / 'project.godot'
        target = self.root / 'real.godot'
        config.rename(target)
        config.symlink_to(target)
        with self.assertRaises(ProjectError): project_root(self.root)

    def test_generated_directories_skipped(self):
        for name in ['.godot', '.git', 'bin', 'obj']:
            (self.root / name).mkdir()
            (self.root / name / 'ignored.cs').write_text('ignored', encoding="utf-8")
        self.assertEqual(scan_project(self.root)['scripts']['csharp'], [])

    def test_missing_external_resource_is_error(self):
        (self.root / 'main.tscn').write_text('[gd_scene format=3]\n[ext_resource type="Script" path="res://missing.gd" id="1"]\n', encoding="utf-8")
        report = scan_project(self.root)
        self.assertEqual(report['references'][0]['status'], 'invalid')
        self.assertTrue(report['errors'])

    def test_connection_inventory(self):
        (self.root / 'main.tscn').write_text('[gd_scene format=3]\n[node name="Root" type="Node"]\n[connection signal="pressed" from="Button" to="." method="_on_pressed"]\n', encoding="utf-8")
        c = scan_project(self.root)['scenes'][0]['connections'][0]
        self.assertEqual((c['signal'], c['from'], c['method']), ('pressed', 'Button', '_on_pressed'))

    def test_uid_is_unresolved_not_missing(self):
        with (self.root / 'project.godot').open('a') as f: f.write('run/main_scene="uid://test123"\n')
        r = scan_project(self.root)
        self.assertFalse(r['errors'])
        self.assertEqual(r['references'][0]['status'], 'uid-unresolved-static')

    def test_autoload_reference(self):
        (self.root / 'session.gd').write_text('extends Node\n', encoding="utf-8")
        with (self.root / 'project.godot').open('a') as f: f.write('[autoload]\nSession="*res://session.gd"\n')
        r = scan_project(self.root)
        self.assertFalse(r['errors'])
        self.assertEqual(r['references'][0]['autoload'], 'Session')

    def test_csharp_detected_without_executing(self):
        (self.root / 'Player.cs').write_text('public partial class Player {}', encoding="utf-8")
        (self.root / 'Game.csproj').write_text('<Project/>', encoding="utf-8")
        r = scan_project(self.root)
        self.assertEqual(r['scripts']['csharp'], ['Player.cs'])
        self.assertEqual(r['csharp_projects'], ['Game.csproj'])

    def test_size_limit_is_reported(self):
        (self.root / 'big.gd').write_text('x' * 12, encoding="utf-8")
        with patch('godot_inspect.MAX_FILE_BYTES', 10):
            # project.godot too large must be a hard error, not a successful incomplete scan.
            with self.assertRaises(ProjectError): scan_project(self.root)

    def test_oversized_csharp_stays_classified_and_blocks_validation(self):
        (self.root / 'project.godot').write_text('config_version=5\n', encoding="utf-8")
        (self.root / 'Player.cs').write_text('x' * 51, encoding="utf-8")
        with patch('godot_inspect.MAX_FILE_BYTES', 50):
            r = scan_project(self.root)
            self.assertEqual(r['scripts']['csharp'], ['Player.cs'])
            self.assertTrue(r['errors'])
            with patch('godot_validate.execute', side_effect=AssertionError('must not execute')):
                self.assertFalse(validate(str(self.root), allow_project_code=True)['ok'])

    def test_colored_error_log_is_detected(self):
        r = execute([sys.executable, '-c', 'print("\\x1b[31mERROR: bad\\x1b[0m")'], timeout=2)
        self.assertFalse(r['ok'])

    def test_explicit_working_directory(self):
        r = execute([sys.executable, '-c', 'import os; print(os.getcwd())'], timeout=2, cwd=self.root)
        self.assertEqual(r['log'].strip(), str(self.root))

    def test_invalid_test_scene_traversal(self):
        with self.assertRaises(ProjectError):
            validate(str(self.root), allow_project_code=True, test_scene='res://../Test.tscn')

    def test_invalid_csproj_extension(self):
        (self.root / 'test.txt').write_text('invalid', encoding="utf-8")
        with self.assertRaises(ProjectError):
            validate(str(self.root), allow_project_code=True, csproj='res://test.txt')

    def _probe(self, csharp):
        payload = {'csharp': csharp, 'version': {'major': 4, 'minor': 6, 'patch': 3}}
        return {'ok': True, 'log': 'GODOT_PROBE=' + json.dumps(payload), 'returncode': 0}

    def test_csharp_standard_engine_is_blocked(self):
        (self.root / 'Player.cs').write_text('// C#', encoding="utf-8")
        with patch('godot_validate.shutil.which', return_value='/trusted/godot'), patch('godot_validate.execute', return_value=self._probe(False)) as run:
            r = validate(str(self.root), allow_project_code=True)
        self.assertFalse(r['ok'])
        self.assertIn('lacks CSharpScript', r['blocker'])
        self.assertEqual(run.call_count, 1)

    def test_csharp_ambiguous_projects_blocked(self):
        (self.root / 'A.csproj').write_text('<Project/>', encoding="utf-8")
        (self.root / 'B.csproj').write_text('<Project/>', encoding="utf-8")
        with patch('godot_validate.shutil.which', return_value='/trusted/godot'), patch('godot_validate.execute', return_value=self._probe(True)) as run:
            r = validate(str(self.root), allow_project_code=True)
        self.assertFalse(r['ok'])
        self.assertIn('exactly one', r['blocker'])
        self.assertEqual(run.call_count, 1)

    def test_csharp_missing_sdk_blocks_build(self):
        (self.root / 'A.csproj').write_text('<Project/>', encoding="utf-8")
        def locate(name):
            return '/trusted/godot' if name == 'godot' else None
        with patch('godot_validate.shutil.which', side_effect=locate), patch('godot_validate.execute', return_value=self._probe(True)) as run:
            r = validate(str(self.root), allow_project_code=True, dotnet='missing-dotnet')
        self.assertFalse(r['ok'])
        self.assertIn('SDK executable not found', r['blocker'])
        self.assertEqual(run.call_count, 1)

    def test_csharp_failed_build_stops_import(self):
        (self.root / 'A.csproj').write_text('<Project/>', encoding="utf-8")
        with patch('godot_validate.shutil.which', return_value='/trusted/tool'), patch('godot_validate.execute', side_effect=[self._probe(True), {'ok': False, 'log': 'build failed', 'returncode': 1}]) as run:
            r = validate(str(self.root), allow_project_code=True)
        self.assertFalse(r['ok'])
        self.assertEqual(run.call_count, 2)
        self.assertEqual(r['checks'][-1]['name'], 'csharp-build')

    def test_csharp_build_precedes_import_and_scene_test(self):
        (self.root / 'A.csproj').write_text('<Project/>', encoding="utf-8")
        (self.root / 'test.tscn').write_text('[gd_scene format=3]', encoding="utf-8")
        good = {'ok': True, 'log': '', 'returncode': 0}
        with patch('godot_validate.shutil.which', return_value='/trusted/tool'), patch('godot_validate.execute', side_effect=[self._probe(True), dict(good), dict(good), dict(good)]) as run:
            r = validate(str(self.root), allow_project_code=True, test_scene='res://test.tscn')
        self.assertTrue(r['ok'])
        self.assertEqual([c['name'] for c in r['checks']], ['engine-capabilities', 'csharp-build', 'import', 'test-scene'])
        self.assertEqual(run.call_args_list[1].kwargs['cwd'], self.root)

    def test_invalid_utf8_is_reported(self):
        (self.root / 'bad.gd').write_bytes(b'\xff\xfe')
        self.assertTrue(scan_project(self.root)['errors'])

    def test_read_only_no_side_effects_or_code_execution(self):
        sentinel = self.root / 'must_not_exist'
        (self.root / 'malicious.gd').write_text(f'@tool\nextends Node\n# pretend write to {sentinel}\n', encoding="utf-8")
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with patch('godot_validate.execute', side_effect=AssertionError('must not execute')):
            result = validate(str(self.root))
        after = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertTrue(result['ok'])
        self.assertEqual(before, after)
        self.assertFalse(sentinel.exists())

    def test_test_script_traversal_rejected_before_execution(self):
        with patch('godot_validate.execute', side_effect=AssertionError('must not execute')):
            with self.assertRaises(ProjectError): validate(str(self.root), allow_project_code=True, test_script='res://../evil.gd')

    def test_non_gd_test_script_rejected(self):
        (self.root / 'test.cs').write_text('// not executable by --script', encoding="utf-8")
        with self.assertRaises(ProjectError): validate(str(self.root), allow_project_code=True, test_script='res://test.cs')

    def test_static_error_stops_engine_execution(self):
        (self.root / 'main.tscn').write_text('[ext_resource path="res://missing.gd" type="Script" id="1"]', encoding="utf-8")
        with patch('godot_validate.execute', side_effect=AssertionError('must not execute')):
            self.assertFalse(validate(str(self.root), allow_project_code=True)['ok'])

    def test_no_shell_argument_injection(self):
        dangerous = '; echo injected && $(touch should_not_exist)'
        result = execute([sys.executable, '-c', 'import sys; print(sys.argv[1])', dangerous], timeout=2)
        self.assertTrue(result['ok'])
        self.assertEqual(result['log'].strip(), dangerous)

    def test_error_log_fails_even_exit_zero(self):
        for message in ['ERROR: problem', 'SCRIPT ERROR: invalid', 'Parse Error: bad']:
            with self.subTest(message=message):
                result = execute([sys.executable, '-c', f'print({message!r})'], timeout=2)
                self.assertEqual(result['returncode'], 0)
                self.assertFalse(result['ok'])

    def test_nonzero_exit_fails(self):
        self.assertFalse(execute([sys.executable, '-c', 'raise SystemExit(3)'], timeout=2)['ok'])

    def test_timeout_fails(self):
        r = execute([sys.executable, '-c', 'import time; time.sleep(10)'], timeout=0.05)
        self.assertTrue(r['timed_out'])
        self.assertFalse(r['ok'])

    def test_oversized_log_fails_closed(self):
        with patch('godot_validate.MAX_LOG_BYTES', 10):
            r = execute([sys.executable, '-c', 'print("a" * 100)'], timeout=2)
        self.assertTrue(r['log_truncated'])
        self.assertFalse(r['ok'])

    def test_cli_runtime_requires_trust_flag(self):
        r = subprocess.run([sys.executable, str(SCRIPTS / 'godot_validate.py'), str(self.root), '--smoke-frames', '1'], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('require --allow-project-code', r.stderr)

    def test_json_cli_parseable(self):
        r = subprocess.run([sys.executable, str(SCRIPTS / 'godot_inspect.py'), str(self.root), '--json'], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)['mode'], 'static-read-only')

if __name__ == '__main__':
    unittest.main(verbosity=2)
