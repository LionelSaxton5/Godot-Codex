import os
from pathlib import Path
import sys
import tempfile
import unittest
from platform_support import SYMLINK_AVAILABLE
SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0,str(SCRIPTS))
from setup_editor_bridge import setup, enable_in_config, PLUGIN_RESOURCE, ProjectError

class EditorSetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='godot-editor-setup-')
        self.root=Path(self.tmp.name);self.project=self.root/'project';self.project.mkdir()
        (self.project/'project.godot').write_text('config_version=5\n[application]\nconfig/name="Fixture"\n', encoding="utf-8")
        self.source=self.root/'source';self.source.mkdir();(self.source/'plugin.cfg').write_text('[plugin]\nname="Fixture"\n', encoding="utf-8")
    def tearDown(self):self.tmp.cleanup()
    def test_dry_run_no_writes(self):
        result=setup(self.project,source=self.source,enable=True)
        self.assertFalse(result['apply']);self.assertFalse((self.project/'addons').exists())
        self.assertNotIn('editor_plugins',(self.project/'project.godot').read_text(encoding="utf-8"))
    def test_install_enable_exact_backup(self):
        before=(self.project/'project.godot').read_bytes()
        setup(self.project,source=self.source,apply=True,enable=True)
        self.assertEqual((self.project/'project.godot.before-ai-bridge').read_bytes(),before)
        self.assertIn(PLUGIN_RESOURCE,(self.project/'project.godot').read_text(encoding="utf-8"))
        self.assertTrue((self.project/'addons'/'ai_editor_bridge'/'plugin.cfg').is_file())
    def test_copy_without_enable(self):
        before=(self.project/'project.godot').read_bytes()
        setup(self.project,source=self.source,apply=True)
        self.assertEqual((self.project/'project.godot').read_bytes(),before)
    def test_existing_addon_refused(self):
        setup(self.project,source=self.source,apply=True)
        with self.assertRaises(ProjectError):setup(self.project,source=self.source,apply=True)
    def test_preserve_other_plugins_and_sections(self):
        old='[editor_plugins]\nenabled=PackedStringArray("res://addons/other/plugin.cfg")\n\n[rendering]\nkeep=true\n'
        new=enable_in_config(old)
        self.assertIn('res://addons/other/plugin.cfg',new);self.assertIn('[rendering]\nkeep=true',new)
        self.assertEqual(new.count(PLUGIN_RESOURCE),1)
        self.assertEqual(enable_in_config(new).count(PLUGIN_RESOURCE),1)
    def test_indented_existing_plugin_preserved(self):
        data='[editor_plugins]\n enabled=PackedStringArray("res://addons/existing/plugin.cfg")\n'
        result=enable_in_config(data)
        self.assertIn('res://addons/existing/plugin.cfg',result)
        self.assertEqual(result.count('enabled='),1)
        self.assertEqual(result.count('[editor_plugins]'),1)
    def test_commented_section_and_value_preserved(self):
        data='  [editor_plugins] ; saved comment\n\tenabled = PackedStringArray("res://addons/existing/plugin.cfg") ; keep note\n\n[rendering]\nkeep=true\n'
        result=enable_in_config(data)
        self.assertIn('res://addons/existing/plugin.cfg',result)
        self.assertIn('; saved comment',result);self.assertIn('; keep note',result)
        self.assertEqual(result.count('[editor_plugins]'),1)
        self.assertIn('[rendering]\nkeep=true',result)
    def test_commented_duplicate_section_refused(self):
        with self.assertRaises(ProjectError):
            enable_in_config('[editor_plugins] ; first\n[editor_plugins] ; second\n')

    def test_ambiguous_configuration_refused(self):
        for data in ['[editor_plugins]\nenabled=unknown()\n','[editor_plugins]\n[editor_plugins]\n','[editor_plugins]\nenabled=PackedStringArray()\nenabled=PackedStringArray()\n']:
            with self.subTest(data=data),self.assertRaises(ProjectError):enable_in_config(data)
    def test_existing_backup_preserved(self):
        (self.project/'project.godot.before-ai-bridge').write_text('keep', encoding="utf-8")
        with self.assertRaises(ProjectError):setup(self.project,source=self.source,apply=True,enable=True)
        self.assertFalse((self.project/'addons').exists())
    @unittest.skipUnless(SYMLINK_AVAILABLE,'no symlink support')
    def test_symlink_output_refused(self):
        outside=self.root/'outside';outside.mkdir();(self.project/'addons').symlink_to(outside,target_is_directory=True)
        with self.assertRaises(ProjectError):setup(self.project,source=self.source,apply=True)
        self.assertEqual(list(outside.iterdir()),[])
    @unittest.skipUnless(SYMLINK_AVAILABLE,'no symlink support')
    def test_symlink_source_refused(self):
        (self.source/'plugin.gd').symlink_to('/etc/passwd')
        with self.assertRaises(ProjectError):setup(self.project,source=self.source,apply=True)
    def test_utf8_bom_preserved(self):
        p=self.project/'project.godot';p.write_bytes(b'\xef\xbb\xbfconfig_version=5\n')
        setup(self.project,source=self.source,apply=True,enable=True)
        self.assertTrue(p.read_bytes().startswith(b'\xef\xbb\xbf'))

if __name__=='__main__':unittest.main()
