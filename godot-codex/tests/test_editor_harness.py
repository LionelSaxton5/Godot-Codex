import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
from run_editor_integration import Scenario, CheckFailure

class StartupReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        (self.root/'scenes').mkdir()
        self.args={'path':'res://scenes/World2D.tscn','root_type':'Node2D','root_name':'World2D'}
        self.client=Mock();self.scenario=Scenario(self.client)
        self.scenario.guard=Mock(side_effect=[{'expected_revision':'first','expected_scene_path':''},{'expected_revision':'fresh','expected_scene_path':''}])
    def tearDown(self):self.tmp.cleanup()
    def test_definite_stale_refreshes_guard(self):
        self.client.call.side_effect=[{'error':{'code':'stale_scene'}},{'created':True}]
        with patch('run_editor_integration.time.sleep'):
            self.assertTrue(self.scenario.initial_create(self.args,self.root)['created'])
        self.assertEqual(self.client.call.call_count,2)
        self.assertEqual(self.client.call.call_args_list[1].args[1]['expected_revision'],'fresh')
    def test_unknown_outcome_never_retries(self):
        self.client.call.return_value={'error':{'code':'outcome_unknown'}}
        with self.assertRaises(CheckFailure):self.scenario.initial_create(self.args,self.root)
        self.assertEqual(self.client.call.call_count,1)
    def test_existing_target_never_retries(self):
        (self.root/'scenes/World2D.tscn').write_text('keep', encoding="utf-8")
        self.client.call.return_value={'error':{'code':'stale_scene'}}
        with self.assertRaises(CheckFailure):self.scenario.initial_create(self.args,self.root)
        self.assertEqual(self.client.call.call_count,1)
        self.assertEqual((self.root/'scenes/World2D.tscn').read_text(encoding="utf-8"),'keep')
    def test_reconciliation_has_deadline(self):
        self.client.call.return_value={'error':{'code':'stale_scene'}}
        with patch('run_editor_integration.time.monotonic',side_effect=[0,11]):
            with self.assertRaises(CheckFailure):self.scenario.initial_create(self.args,self.root)
        self.assertEqual(self.client.call.call_count,1)

if __name__=='__main__':unittest.main()
