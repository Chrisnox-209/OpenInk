"""Offline Windows integration checks. No printer or print job is opened."""
from dataclasses import replace
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from contextlib import nullcontext

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'commun'))
from inkora.filelock import fcntl
from inkora.printer import demo_snapshot
from inkora.windows_usb import select_device
from inkora.windows_ipc import authenticate, create_server, request_path
from inkora import windows_printing

PATH = r'\\?\usb#vid_04b8&pid_11b1&mi_01#TEST001#{guid}'


class UsbSelectionTests(unittest.TestCase):
    def test_single_normal_device(self):
        self.assertEqual(select_device([PATH]), PATH)

    def test_interface_aliases_are_one_printer(self):
        self.assertEqual(select_device([PATH.replace('mi_01', 'mi_00'), PATH]), PATH)

    def test_two_physical_printers_are_rejected(self):
        with self.assertRaises(ValueError):
            select_device([PATH, PATH.replace('TEST001', 'TEST002')])

    def test_other_models_are_rejected(self):
        for paths in ([], [PATH.replace('pid_11b1', 'pid_118a')],
                      [PATH.replace('pid_11b1', 'pid_11b10')]):
            with self.assertRaises(ValueError):
                select_device(paths)

    def test_recovery_always_rejected(self):
        with self.assertRaises(ValueError):
            select_device([PATH, PATH.replace('pid_11b1', 'pid_0007')])


class IpcTests(unittest.TestCase):
    def test_invalid_tokens_rejected(self):
        for parsed in ({}, {'token': 1}, {'token': 'wrong'}):
            with self.assertRaises(ValueError):
                authenticate(parsed, 'secret')
        authenticate({'token': 'secret'}, 'secret')

    def test_authenticated_roundtrip(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'endpoint.json'
            server, secret = create_server(path)
            def serve():
                connection, _ = server.accept()
                with connection:
                    value = json.loads(connection.recv(4096))
                    authenticate(value, secret)
                    connection.sendall(b'{"ok":true,"running":true}\n')
            thread = threading.Thread(target=serve)
            thread.start()
            try:
                self.assertTrue(request_path(path, 'ping')['running'])
            finally:
                thread.join(3)
                server.close()

    def test_missing_session_is_connection_error(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ConnectionError):
                request_path(Path(folder) / 'missing', 'ping')


class PrinterTests(unittest.TestCase):
    def setUp(self):
        self.api = SimpleNamespace(PRINTER_ENUM_LOCAL=2, PRINTER_ENUM_CONNECTIONS=4,
                                  EnumPrinters=Mock(), OpenPrinter=Mock(return_value='handle'),
                                  GetPrinter=Mock(return_value={'cJobs': 0}),
                                  EnumJobs=Mock(return_value=[]), ClosePrinter=Mock())
        self.modules = patch.dict(sys.modules, {'win32print': self.api})
        self.modules.start()
        self.rows = [{'pPrinterName': 'EPSON XP-2200', 'pDriverName': 'EPSON XP-2200 Series',
                      'Status': 0, 'pPortName': 'USB001'}]
        self.api.EnumPrinters.return_value = self.rows

    def tearDown(self):
        self.modules.stop()

    def test_only_epson_queues_offered_with_confirmation(self):
        self.api.EnumPrinters.return_value = self.rows + [dict(self.rows[0], pPrinterName='Other', pDriverName='Other')]
        rows = windows_printing.cups_printers(None)
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]['confirmed'])
        self.assertTrue(rows[0]['enabled'])

    def test_paused_and_offline_queues_disabled(self):
        for status in (1, 0x80, 0x1000):
            self.rows[0]['Status'] = status
            self.assertFalse(windows_printing.cups_printers(None)[0]['enabled'])

    def test_busy_queue_refuses_usb(self):
        self.api.GetPrinter.return_value = {'cJobs': 1}
        with self.assertRaises(ValueError):
            windows_printing.require_empty_queues()
        self.api.ClosePrinter.assert_called_once_with('handle')

    def test_unavailable_spooler_refuses_usb(self):
        self.api.EnumPrinters.side_effect = OSError('Spooler stopped')
        with self.assertRaises(OSError):
            windows_printing.require_empty_queues()

    def test_empty_queue_allows_read(self):
        windows_printing.require_empty_queues()
        self.api.ClosePrinter.assert_called_once_with('handle')

    def prepare_submission(self):
        mode = SimpleNamespace(Fields=0)
        self.api.GetPrinter.return_value = {'cJobs': 0, 'pDevMode': mode}
        self.api.DocumentProperties = Mock(return_value=1)
        self.api.StartDoc = Mock(return_value=42)
        self.api.StartPage = Mock()
        self.api.EndPage = Mock()
        self.api.EndDoc = Mock()
        self.api.AbortDoc = Mock()
        self.api.GetDeviceCaps = Mock(return_value=1000)
        constants = SimpleNamespace(**{key: 1 for key in ('DM_PAPERSIZE', 'DM_COPIES', 'DM_DUPLEX',
            'DM_COLOR', 'DM_ORIENTATION', 'DM_IN_BUFFER', 'DM_OUT_BUFFER', 'HORZRES', 'VERTRES')})
        gui = SimpleNamespace(CreateDC=Mock(return_value=123), DeleteDC=Mock())
        self.addCleanup(patch.stopall)
        patch.dict(sys.modules, {'win32con': constants, 'win32gui': gui}).start()
        patch('inkora.windows_printing.hardware_session', return_value=nullcontext()).start()
        drawing = patch('PIL.ImageWin.Dib').start()
        snapshot = replace(demo_snapshot(), demo=False, ready=True,
                           observed_at=datetime.now(timezone.utc).isoformat())
        return snapshot, gui, drawing

    def test_explicit_submission_is_one_a4_color_page(self):
        snapshot, gui, drawing = self.prepare_submission()
        result = windows_printing.submit_test_page(snapshot, 'EPSON XP-2200', True)
        self.assertEqual(result['job_id'], '42')
        self.assertEqual(result['copies'], 1)
        self.assertFalse(result['printed_verified'])
        mode = self.api.GetPrinter.return_value['pDevMode']
        self.assertEqual((mode.PaperSize, mode.Copies, mode.Duplex, mode.Color, mode.Orientation), (9, 1, 1, 2, 1))
        self.api.StartPage.assert_called_once_with(123)
        self.api.EndPage.assert_called_once_with(123)
        self.api.EndDoc.assert_called_once_with(123)
        self.api.AbortDoc.assert_not_called()

    def test_destination_confirmation_required(self):
        snapshot, gui, _ = self.prepare_submission()
        with self.assertRaises(ValueError):
            windows_printing.submit_test_page(snapshot, 'EPSON XP-2200')
        gui.CreateDC.assert_not_called()

    def test_stale_snapshot_never_submits(self):
        snapshot, gui, _ = self.prepare_submission()
        snapshot.observed_at = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        with self.assertRaises(ValueError):
            windows_printing.submit_test_page(snapshot, 'EPSON XP-2200', True)
        gui.CreateDC.assert_not_called()

    def test_driver_refusal_never_submits(self):
        snapshot, gui, _ = self.prepare_submission()
        self.api.DocumentProperties.return_value = -1
        with self.assertRaises(ValueError):
            windows_printing.submit_test_page(snapshot, 'EPSON XP-2200', True)
        gui.CreateDC.assert_not_called()

    def test_render_failure_aborts_only_own_job(self):
        snapshot, gui, drawing = self.prepare_submission()
        drawing.return_value.draw.side_effect = OSError('GDI failure')
        with self.assertRaises(OSError):
            windows_printing.submit_test_page(snapshot, 'EPSON XP-2200', True)
        self.api.AbortDoc.assert_called_once_with(123)
        gui.DeleteDC.assert_called_once_with(123)


@unittest.skipUnless(os.name == 'nt', 'Native Windows runtime required')
class NativeTests(unittest.TestCase):
    def test_lock_excludes_other_process_and_releases(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'process.lock'
            code = ('import sys;from inkora.filelock import fcntl;'
                    'h=open(sys.argv[1],"a+b");fcntl.flock(h,fcntl.LOCK_EX|fcntl.LOCK_NB)')
            env = {**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[2] / 'commun')}
            with path.open('a+b') as handle:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                result = subprocess.run([sys.executable, '-c', code, str(path)], env=env, capture_output=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(b'BlockingIOError', result.stderr)
            result = subprocess.run([sys.executable, '-c', code, str(path)], env=env, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_agent_controls_authenticated_without_printer(self):
        from inkora.agent import Agent
        from inkora.service import request, runtime_paths
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / 'data/state.sqlite3'
            with patch('inkora.store.default_database', return_value=database):
                agent = Agent(database, reader=lambda *_: demo_snapshot(), notifier=Mock())
                thread = threading.Thread(target=agent.run)
                thread.start()
                try:
                    for _ in range(50):
                        try:
                            state = request(database)
                            break
                        except (OSError, ValueError):
                            time.sleep(.1)
                    else:
                        self.fail('Agent did not start')
                    self.assertTrue(state['running'])
                    path, _ = runtime_paths(database)
                    endpoint = json.loads(path.read_text(encoding='utf-8'))
                    endpoint['token'] = 'invalid'
                    bad = path.with_name('bad.json')
                    bad.write_text(json.dumps(endpoint), encoding='utf-8')
                    with self.assertRaises(ConnectionError):
                        request_path(bad, 'stop')
                    self.assertTrue(request(database)['running'])
                    self.assertTrue(request(database, 'refresh')['ok'])
                    request(database, 'stop')
                finally:
                    agent.stop.set()
                    thread.join(5)
                self.assertFalse(thread.is_alive())

    def test_frozen_launch_does_not_use_module_mode(self):
        from inkora.service import launch_command
        with patch.object(sys, 'frozen', True, create=True):
            command = launch_command(Path('test.sqlite3'), '--agent')
        self.assertNotIn('-m', command)
        self.assertIn('--agent', command)

    def test_flash_uses_conservative_restart_detection(self):
        from inkora.firmware_usb import normal_usb_generation, normal_usb_port
        self.assertIsNone(normal_usb_generation('TEST'))
        self.assertIsNone(normal_usb_port(PATH))

    def test_startup_registration_is_per_user_and_quoted(self):
        import winreg
        from inkora.windows_desktop import set_autostart
        key = Mock()
        key.__enter__ = Mock(return_value=key)
        key.__exit__ = Mock(return_value=False)
        with patch.object(winreg, 'CreateKey', return_value=key) as create, \
                patch.object(winreg, 'SetValueEx') as write, patch.object(winreg, 'DeleteValue') as delete:
            set_autostart(Path('C:/User Folder/state.sqlite3'), True)
            self.assertEqual(create.call_args.args[0], winreg.HKEY_CURRENT_USER)
            self.assertIn('--background', write.call_args.args[-1])
            self.assertIn('"', write.call_args.args[-1])
            set_autostart(Path('C:/User Folder/state.sqlite3'), False)
            delete.assert_called_once_with(key, 'OpenInk')


if __name__ == '__main__':
    unittest.main()
