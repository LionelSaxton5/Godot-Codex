"""Windows regression: editor status must remain atomically replaceable while read."""
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from editor_bridge_client import ProjectFiles, _normal_final_path, IPC

@unittest.skipUnless(os.name=='nt','Windows handle-sharing regression')
class WindowsSharingTests(unittest.TestCase):
    def test_windows_junction_parent_is_rejected(self):
        import subprocess
        from editor_bridge_client import BridgeError
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);root=base/'project';root.mkdir();outside=base/'outside';outside.mkdir()
            (root/'project.godot').write_text('config_version=5\n',encoding='utf-8')
            (outside/'secret.gd').write_text('secret',encoding='utf-8')
            link=root/'linked'
            result=subprocess.run(['cmd','/c','mklink','/J',str(link),str(outside)],capture_output=True)
            if result.returncode:self.skipTest('This Windows host cannot create a test junction')
            try:
                files=ProjectFiles(root)
                with self.assertRaises(BridgeError) as caught:files.resource('res://linked/secret.gd')
                self.assertEqual(caught.exception.code,'unsafe_path')
                self.assertEqual((outside/'secret.gd').read_text(encoding='utf-8'),'secret')
            finally:os.rmdir(link)

    def test_ntfs_deleted_status_is_retried_but_resources_stay_rejected(self):
        from unittest.mock import patch
        from editor_bridge_client import BridgeError
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'project.godot').write_text('config_version=5\n',encoding='utf-8')
            (root/IPC).mkdir(parents=True);(root/IPC/'status.json').write_bytes(b'{}')
            (root/'data.json').write_bytes(b'{}')
            files=ProjectFiles(root)
            deleted=Path(root.anchor)/'$Extend'/'$Deleted'/'old-status'
            with patch.object(Path,'resolve',return_value=deleted):
                with self.assertRaises(FileNotFoundError):files.checked_path(f'{IPC}/status.json')
                with self.assertRaises(BridgeError) as caught:files.checked_path('data.json')
                self.assertEqual(caught.exception.code,'unsafe_path')

    def test_extended_drive_and_unc_prefixes_normalize(self):
        self.assertEqual(_normal_final_path(Path('\\\\?\\D:\\test\\file')),Path('D:\\test\\file'))
        self.assertEqual(_normal_final_path(Path('\\\\?\\UNC\\host\\share\\file')),Path('\\\\host\\share\\file'))
        outside=_normal_final_path(Path('\\\\?\\D:\\outside\\file'))
        self.assertFalse(outside.is_relative_to(Path('D:\\project')))

    def test_transient_missing_status_is_read_without_mutation_retry(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'project.godot').write_text('config_version=5\n',encoding='utf-8')
            files=ProjectFiles(root)
            with patch.object(files,'_read_once',side_effect=[FileNotFoundError(),b'{}']) as read:
                self.assertEqual(files.read(f'{IPC}/status.json',100),b'{}')
                self.assertEqual(read.call_count,2)
            with patch.object(files,'_read_once',side_effect=FileNotFoundError()) as read:
                with self.assertRaises(FileNotFoundError):files.read(f'{IPC}/responses/missing.json',100)
                self.assertEqual(read.call_count,1)

    def test_read_waits_for_transient_windows_sharing_lock(self):
        import ctypes,threading,time
        from ctypes import wintypes
        with tempfile.TemporaryDirectory(prefix='Windows IPC 中文 空间 ') as directory:
            root=Path(directory)
            (root/'project.godot').write_text('config_version=5\n',encoding='utf-8')
            files=ProjectFiles(root)
            path=root/'status.json';path.write_bytes(b'new snapshot')
            api=ctypes.WinDLL('kernel32',use_last_error=True)
            create=api.CreateFileW
            create.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
            create.restype=wintypes.HANDLE
            close=api.CloseHandle;close.argtypes=[wintypes.HANDLE]
            handle=create(str(path),0x80000000,0,None,3,0,None)
            self.assertNotEqual(handle,ctypes.c_void_p(-1).value)
            released=threading.Event()
            def unlock():
                time.sleep(.05);close(handle);released.set()
            thread=threading.Thread(target=unlock);thread.start()
            try:
                self.assertEqual(files.read('status.json',100),b'new snapshot')
                self.assertTrue(released.is_set())
            finally:thread.join()

    def test_confined_read_keeps_regular_file_byte_limit(self):
        with tempfile.TemporaryDirectory(prefix='Windows IPC 中文 空间 ') as directory:
            root=Path(directory);(root/'project.godot').write_text('config_version=5\n',encoding='utf-8')
            (root/'data.json').write_bytes(b'12345')
            files=ProjectFiles(root)
            self.assertEqual(files.read('data.json',5),b'12345')
            from editor_bridge_client import BridgeError
            with self.assertRaises(BridgeError) as caught:files.read('data.json',4)
            self.assertEqual(caught.exception.code,'payload_too_large')
