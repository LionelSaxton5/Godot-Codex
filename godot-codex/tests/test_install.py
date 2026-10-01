import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from platform_support import SYMLINK_AVAILABLE

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
from install_local import prepare, NAME

class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='plugin-install-test-')
        self.base = Path(self.temp.name)
        self.source = self.base / 'source'
        (self.source / '.codex-plugin').mkdir(parents=True)
        (self.source / '.codex-plugin' / 'plugin.json').write_text(json.dumps({'name':NAME}), encoding="utf-8")
        (self.source / 'data.txt').write_text('fixture', encoding="utf-8")
        (self.source / '.godot').mkdir()
        (self.source / '.godot' / 'cache.txt').write_text('skip', encoding="utf-8")
        self.home = self.base / 'home'
        self.home.mkdir()

    def test_mcp_install_pins_actual_python_interpreter(self):
        (self.source/'.mcp.json').write_text(json.dumps({'mcpServers':{'godot-editor':{'command':'python3','args':['scripts/godot_mcp_server.py'],'cwd':'.'}}}),encoding='utf-8')
        result=prepare(self.source,self.home,apply=True)
        installed=json.loads((Path(result['destination'])/'.mcp.json').read_text(encoding='utf-8'))
        self.assertEqual(installed['mcpServers']['godot-editor']['command'],sys.executable)
        self.assertEqual(installed['mcpServers']['godot-editor']['cwd'],'.')

    def tearDown(self):
        self.temp.cleanup()

    def test_dry_run_writes_nothing(self):
        result = prepare(self.source, self.home)
        self.assertFalse(result['apply'])
        self.assertEqual(list(self.home.iterdir()), [])

    def test_registration_and_cache_exclusion(self):
        result = prepare(self.source, self.home, apply=True)
        dest = Path(result['destination'])
        self.assertEqual((dest / 'data.txt').read_text(encoding="utf-8"), 'fixture')
        self.assertFalse((dest / '.godot').exists())
        manifest = json.loads(Path(result['marketplace']).read_text(encoding="utf-8"))
        self.assertEqual(manifest['plugins'][0]['source']['path'], './plugins/godot-codex')
        self.assertEqual(result['next_command'], ['codex','plugin','add','godot-codex@personal'])

    def test_existing_plugin_never_overwritten(self):
        prepare(self.source, self.home, apply=True)
        with self.assertRaises(ValueError): prepare(self.source, self.home, apply=True)

    def test_existing_marketplace_preserved(self):
        path = self.home / '.agents' / 'plugins' / 'marketplace.json'
        path.parent.mkdir(parents=True)
        payload = {'name':'mine','interface':{'displayName':'My Plugins'},'plugins':[{'name':'other','source':{'source':'local','path':'./plugins/other'}}]}
        path.write_text(json.dumps(payload), encoding="utf-8")
        result = prepare(self.source, self.home, apply=True)
        after = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(after['interface'],payload['interface'])
        self.assertEqual(after['plugins'][0],payload['plugins'][0])
        self.assertEqual(result['marketplace_name'],'mine')

    def test_invalid_marketplace_stops(self):
        path = self.home / '.agents' / 'plugins' / 'marketplace.json'
        path.parent.mkdir(parents=True)
        path.write_text('{"name":"bad; command","plugins":[]}', encoding="utf-8")
        with self.assertRaises(ValueError): prepare(self.source,self.home,apply=True)
        self.assertFalse((self.home/'plugins'/NAME).exists())

    @unittest.skipUnless(SYMLINK_AVAILABLE,'symlinks unavailable')
    def test_symlink_destination_stops(self):
        outside = self.base / 'outside'
        outside.mkdir()
        (self.home / 'plugins').symlink_to(outside,target_is_directory=True)
        with self.assertRaises(ValueError): prepare(self.source,self.home,apply=True)
        self.assertEqual(list(outside.iterdir()),[])

    @unittest.skipUnless(SYMLINK_AVAILABLE,'symlinks unavailable')
    def test_symlink_source_stops(self):
        (self.source/'leak').symlink_to('/etc/passwd')
        with self.assertRaises(ValueError): prepare(self.source,self.home,apply=True)

if __name__=='__main__':
    unittest.main()
