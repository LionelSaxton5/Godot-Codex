import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from platform_support import SYMLINK_AVAILABLE
from unittest.mock import patch
import zipfile

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
from build_package import build, NAME

class PackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='godot-package-test-')
        self.base = Path(self.tmp.name)
        self.root = self.base / NAME
        (self.root / '.codex-plugin').mkdir(parents=True)
        (self.root / '.codex-plugin' / 'plugin.json').write_text(json.dumps({'name':NAME,'skills':'./skills/'}), encoding="utf-8")
        for n in range(6):
            skill = self.root / 'skills' / f'skill-{n}'
            (skill / 'agents').mkdir(parents=True)
            (skill/'SKILL.md').write_text(f'---\nname: skill-{n}\ndescription: "Fixture skill for packaging tests"\n---\n', encoding="utf-8")
            (skill/'agents'/'openai.yaml').write_text('interface:\n  display_name: "Fixture"\n', encoding="utf-8")
        for rel in ['README.md','README.zh-CN.md','LICENSE','docs/VERIFICATION.md','examples/native_lab/project.godot','examples/csharp_lab/project.godot']:
            p=self.root/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('Fixture\n', encoding="utf-8")
        (self.root/'.godot').mkdir()
        (self.root/'.godot'/'cache').write_text('must not package', encoding="utf-8")

    def tearDown(self): self.tmp.cleanup()

    def test_deterministic_zip_integrity_and_exclusions(self):
        a=build(self.root,self.base/'a.zip')
        b=build(self.root,self.base/'b.zip')
        self.assertEqual(a['sha256'],b['sha256'])
        with zipfile.ZipFile(a['archive']) as z:
            self.assertIsNone(z.testzip())
            self.assertTrue(all(n.startswith(NAME+'/') and '..' not in Path(n).parts for n in z.namelist()))
            self.assertFalse(any('/.godot/' in n for n in z.namelist()))
        self.assertTrue((self.base/'a.zip.sha256').is_file())

    def test_existing_checksum_refused_without_force(self):
        checksum = self.base / 'a.zip.sha256'
        checksum.write_text('keep checksum', encoding="utf-8")
        with self.assertRaises(ValueError): build(self.root, self.base / 'a.zip')
        self.assertEqual(checksum.read_text(encoding="utf-8"), 'keep checksum')
        self.assertFalse((self.base/'a.zip').exists())
        result = build(self.root, self.base / 'a.zip', force=True)
        self.assertIn(result['sha256'], checksum.read_text(encoding="utf-8"))

    @unittest.skipUnless(SYMLINK_AVAILABLE,'symlinks unavailable')
    def test_checksum_symlink_never_overwrites_target(self):
        target = self.base / 'unrelated.txt'
        target.write_text('keep target', encoding="utf-8")
        (self.base/'a.zip.sha256').symlink_to(target)
        for force in (False, True):
            with self.assertRaises(ValueError): build(self.root, self.base/'a.zip', force=force)
        self.assertEqual(target.read_text(encoding="utf-8"), 'keep target')
        self.assertFalse((self.base/'a.zip').exists())

    @unittest.skipUnless(SYMLINK_AVAILABLE,'symlinks unavailable')
    def test_source_links_rejected_before_content_reads(self):
        (self.root/'README.md').unlink()
        (self.root/'README.md').symlink_to('/etc/passwd')
        with patch.object(Path,'read_text',side_effect=AssertionError('must not read before link check')):
            with self.assertRaises(ValueError):build(self.root,self.base/'a.zip')

    def test_existing_output_refused(self):
        output=self.base/'a.zip';output.write_bytes(b'keep')
        with self.assertRaises(ValueError):build(self.root,output)
        self.assertEqual(output.read_bytes(),b'keep')

    def test_output_inside_source_refused(self):
        with self.assertRaises(ValueError):build(self.root,self.root/'out.zip')

    def test_missing_local_link_fails(self):
        (self.root/'README.md').write_text('[missing](not-present.md)', encoding="utf-8")
        with self.assertRaises(ValueError):build(self.root,self.base/'out.zip')

    def test_escaping_local_link_fails(self):
        (self.base/'outside.md').write_text('outside', encoding="utf-8")
        (self.root/'README.md').write_text('[outside](../outside.md)', encoding="utf-8")
        with self.assertRaises(ValueError):build(self.root,self.base/'out.zip')

    @unittest.skipUnless(SYMLINK_AVAILABLE,'symlinks unavailable')
    def test_symlinks_not_packaged(self):
        (self.root/'link').symlink_to('/etc/passwd')
        with self.assertRaises(ValueError):build(self.root,self.base/'out.zip')

if __name__=='__main__':unittest.main()
