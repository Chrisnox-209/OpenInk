"""macOS integration tests with all native commands and printer I/O simulated."""
import contextlib
from dataclasses import replace
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import socket
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'commun'))
from inkora import macos_support
from inkora.i18n import set_language, tr


class SessionTests(unittest.TestCase):
    def test_short_private_socket_path_even_with_long_database_path(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'ipc'
            path, lock = macos_support.runtime_paths(Path(folder) / ('user' * 80) / 'state.sqlite3', root=root)
            self.assertLess(len(os.fsencode(path)), 104)
            self.assertEqual(root.stat().st_mode & 0o777, 0o700)
            self.assertEqual(path.stem, lock.stem)

    def test_symlink_runtime_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'target'
            target.mkdir()
            link = Path(folder) / 'link'
            link.symlink_to(target, target_is_directory=True)
            with self.assertRaises(RuntimeError):
                macos_support.runtime_paths('test.sqlite3', root=link)

    def test_foreign_runtime_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch('inkora.macos_support.os.getuid', return_value=os.getuid() + 1):
                with self.assertRaises(RuntimeError):
                    macos_support.runtime_paths('test.sqlite3', root=Path(folder) / 'ipc')

    def test_native_paths_selected_by_service(self):
        from inkora.service import runtime_paths
        with patch.object(sys, 'platform', 'darwin'), \
                patch('inkora.macos_support.runtime_paths', return_value=('socket', 'lock')) as native:
            self.assertEqual(runtime_paths('db'), ('socket', 'lock'))
            native.assert_called_once_with('db')

    def test_source_helpers_use_macos_launcher(self):
        from inkora.service import launch_command
        with patch.object(sys, 'platform', 'darwin'):
            command = launch_command('database name.sqlite3', '--agent')
            self.assertEqual(Path(command[1]), ROOT / 'macos/openink_macos.py')
            self.assertEqual(command[-1], '--agent')


class StartupTests(unittest.TestCase):
    def test_per_user_plist_preserves_paths_and_is_opt_in(self):
        with tempfile.TemporaryDirectory(prefix='OpenInk Mac ') as folder:
            with patch.object(Path, 'home', return_value=Path(folder)):
                macos_support.set_autostart(Path(folder) / 'database name.sqlite3', True)
                path = Path(folder) / 'Library/LaunchAgents' / (macos_support.AUTOSTART_LABEL + '.plist')
                value = plistlib.loads(path.read_bytes())
                self.assertTrue(value['RunAtLoad'])
                self.assertNotIn('KeepAlive', value)
                self.assertEqual(value['ProgramArguments'][-1], '--background')
                self.assertIn(str(Path(folder) / 'database name.sqlite3'), value['ProgramArguments'])
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                macos_support.set_autostart('db', False)
                self.assertFalse(path.exists())

    def test_frozen_plist_uses_bundled_executable(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(Path, 'home', return_value=Path(folder)), \
                    patch.object(sys, 'frozen', True, create=True), \
                    patch.object(sys, 'executable', '/Applications/OpenInk.app/Contents/MacOS/OpenInk'):
                macos_support.set_autostart('db', True)
                path = Path(folder) / 'Library/LaunchAgents' / (macos_support.AUTOSTART_LABEL + '.plist')
                value = plistlib.loads(path.read_bytes())
                self.assertEqual(value['ProgramArguments'][0], sys.executable)
                self.assertNotIn('PYTHONPATH', value['EnvironmentVariables'])
                self.assertNotIn('-m', value['ProgramArguments'])


class NativeCommandTests(unittest.TestCase):
    def test_notification_arguments_cannot_change_applescript(self):
        title = 'OpenInk " & do shell script "unexpected'
        detail = 'Line one\nLine two'
        notifier = macos_support.DesktopNotifications('db')
        with patch('inkora.macos_support.subprocess.run', return_value=SimpleNamespace(returncode=0)) as run:
            self.assertEqual(notifier.send(title, detail), 'macOS-accepted')
            args = run.call_args.args[0]
            self.assertEqual(args[:4], ['/usr/bin/osascript', '-e', macos_support.NOTIFICATION_SCRIPT, '--'])
            self.assertEqual(args[-2:], [title, detail])
            self.assertNotIn(title, args[2])

    def test_notification_failure_is_not_marked_sent(self):
        with patch('inkora.macos_support.subprocess.run', return_value=SimpleNamespace(returncode=1, stderr='denied')):
            with self.assertRaises(OSError):
                macos_support.DesktopNotifications('db').send('OpenInk', 'test')

    def test_packaged_libusb_selected_without_loading_device(self):
        with tempfile.TemporaryDirectory() as folder:
            library = Path(folder) / 'libusb.dylib'
            library.write_bytes(b'test fixture')
            package = SimpleNamespace(get_library_path=Mock(return_value=library))
            with patch.dict(os.environ, {}, clear=True), patch.dict(sys.modules, {'libusb_package': package}):
                self.assertEqual(macos_support.configure_libusb(True), str(library))
                self.assertEqual(os.environ['EPSON_USB_LIBUSB'], str(library))

    def test_explicit_libusb_override_preserved(self):
        with patch.dict(os.environ, {'EPSON_USB_LIBUSB': '/custom/library.dylib'}):
            self.assertEqual(macos_support.configure_libusb(True), '/custom/library.dylib')

    def test_missing_libusb_does_not_block_network(self):
        with patch.dict(os.environ, {}, clear=True), patch.dict(sys.modules, {'libusb_package': None}):
            self.assertIsNone(macos_support.configure_libusb())
            with self.assertRaises(ValueError):
                macos_support.configure_libusb(True)

    def test_mac_flash_uses_caffeinate_and_full_verify_flag(self):
        from inkora.firmware import launch_job
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            (path / 'request.json').write_text(json.dumps({'database': 'database name.sqlite3'}))
            with patch.object(sys, 'platform', 'darwin'), patch.object(Path, 'is_file', return_value=True), \
                    patch('inkora.firmware.job_folder', return_value=path), \
                    patch('inkora.firmware.subprocess.Popen') as spawn:
                launch_job('a' * 32, verify_only=True)
                command = spawn.call_args.args[0]
                self.assertEqual(command[:2], ['/usr/bin/caffeinate', '-is'])
                self.assertIn('--firmware-job', command)
                self.assertEqual(command[-1], '--verify-firmware')
                self.assertTrue(spawn.call_args.kwargs['start_new_session'])

    def test_mac_never_uses_linux_restart_detection(self):
        from inkora.firmware_usb import normal_usb_generation, normal_usb_port
        with patch.object(sys, 'platform', 'darwin'):
            self.assertIsNone(normal_usb_generation('TEST'))
            self.assertIsNone(normal_usb_port('1:2'))


class AppearanceTests(unittest.TestCase):
    def test_mac_texts_for_each_language(self):
        try:
            with patch.object(sys, 'platform', 'darwin'):
                for language in ('fr', 'en', 'es'):
                    set_language(language)
                    self.assertIn('macOS', tr('Au démarrage d’Ubuntu'))
                    self.assertNotIn('Ubuntu', tr('Au démarrage d’Ubuntu'))
                set_language('fr')
                self.assertEqual(tr('Au démarrage d’Ubuntu'), 'Au démarrage de macOS')
        finally:
            set_language('fr')

    def test_cocoa_monitor_coordinates_convert_to_tk(self):
        def rect(x, y, w, h):
            return SimpleNamespace(origin=SimpleNamespace(x=x, y=y), size=SimpleNamespace(width=w, height=h))
        screens = [SimpleNamespace(frame=lambda: rect(0, 0, 1440, 900), visibleFrame=lambda: rect(0, 30, 1440, 845)),
                   SimpleNamespace(visibleFrame=lambda: rect(1440, 0, 1280, 720))]
        appkit = SimpleNamespace(NSScreen=SimpleNamespace(screens=lambda: screens))
        with patch.dict(sys.modules, {'AppKit': appkit}):
            root = SimpleNamespace(winfo_pointerxy=lambda: (1500, 300))
            self.assertEqual(macos_support.active_monitor(root), (1280, 720, 1440, 180))


class TrayTests(unittest.TestCase):
    def test_private_control_socket_version_invalid_command_and_quit(self):
        from inkora import macos_tray
        class Menu:
            SEPARATOR = object()
            def __init__(self, *args):
                self.items = args
        class Icon:
            def __init__(self, *args):
                self.closed = threading.Event()
            def run(self, setup):
                worker = threading.Thread(target=setup, args=(self,))
                worker.start()
                self.closed.wait(10)
                worker.join(6)
            def stop(self):
                self.closed.set()
        package = SimpleNamespace(Menu=Menu, MenuItem=lambda *args, **kwargs: (args, kwargs), Icon=Icon)
        with tempfile.TemporaryDirectory() as folder:
            path, lock = Path(folder) / 'session.sock', Path(folder) / 'session.lock'
            with patch.dict(sys.modules, {'pystray': package}), \
                    patch('inkora.macos_tray.runtime_paths', return_value=(path, lock)), \
                    patch('inkora.macos_tray.request', return_value={'online': False}):
                worker = threading.Thread(target=macos_tray.run_tray, args=(Path(folder) / 'db',))
                worker.start()
                try:
                    for _ in range(100):
                        try:
                            version = macos_tray.tray_request('db')
                            break
                        except (OSError, ValueError):
                            time.sleep(.02)
                    else:
                        self.fail('Icon socket did not start')
                    self.assertEqual(version, ('1.7.0',))
                    self.assertEqual(path.with_suffix('.tray').stat().st_mode & 0o777, 0o600)
                    with self.assertRaises(ConnectionError):
                        macos_tray.tray_request('db', 'firmware-write')
                    self.assertEqual(macos_tray.tray_request('db', 'Quit'), ())
                finally:
                    if worker.is_alive():
                        with contextlib.suppress(OSError):
                            macos_tray.tray_request('db', 'Quit')
                    worker.join(10)
                self.assertFalse(worker.is_alive())
                self.assertFalse(path.with_suffix('.tray').exists())


class BuildTests(unittest.TestCase):
    def test_build_script_refuses_non_mac_host(self):
        if sys.platform == 'darwin':
            self.skipTest('This check applies only to non-macOS hosts')
        result = subprocess.run([sys.executable, str(ROOT / 'macos/build_macos.py')], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('exige un Mac', result.stderr)

    def test_build_spec_and_commands_have_valid_syntax(self):
        spec = ROOT / 'macos/OpenInk.spec'
        compile(spec.read_text(encoding='utf-8'), str(spec), 'exec')
        for path in [ROOT / 'macos/bootstrap.sh', *sorted((ROOT / 'macos').glob('*.command'))]:
            subprocess.run(['bash', '-n', str(path)], check=True)

    def test_existing_mac_app_is_preserved(self):
        spec = importlib.util.spec_from_file_location('openink_install_test', ROOT / 'macos/install_app.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            executable = root / 'macos/dist/OpenInk.app/Contents/MacOS/OpenInk'
            executable.parent.mkdir(parents=True)
            executable.write_text('test fixture')
            existing = root / 'user/Applications/OpenInk.app'
            existing.mkdir(parents=True)
            marker = existing / 'keep.txt'
            marker.write_text('preserve')
            with patch.object(sys, 'platform', 'darwin'), patch.object(module, '__file__', str(root / 'macos/install_app.py')), \
                    patch.object(Path, 'home', return_value=root / 'user'), patch.object(module.shutil, 'copytree') as copy, \
                    patch.object(module.subprocess, 'run') as run, contextlib.redirect_stdout(__import__('io').StringIO()):
                module.main()
                copy.assert_not_called()
                self.assertEqual(run.call_args.args[0][:2], ['/usr/bin/open', '-R'])
            self.assertEqual(marker.read_text(), 'preserve')


class PrintingTests(unittest.TestCase):
    def test_mac_cups_submission_selects_one_color_page(self):
        from inkora import printing
        from inkora.printer import demo_snapshot
        snapshot = replace(demo_snapshot(), demo=False, ready=True,
                           observed_at=datetime.now(timezone.utc).isoformat())
        selected = {'name': 'EPSON_XP2200', 'confirmed': True, 'enabled': True}
        results = [SimpleNamespace(returncode=0, stdout='', stderr=''),
                   SimpleNamespace(returncode=0, stdout='request id is EPSON_XP2200-42 (1 file)', stderr='')]
        with patch.object(sys, 'platform', 'darwin'), \
                patch('inkora.printing.hardware_session', return_value=contextlib.nullcontext()), \
                patch('inkora.printing.cups_printers', return_value=[selected]), \
                patch('inkora.printing.subprocess.run', side_effect=results) as run:
            value = printing.submit_test_page(snapshot, 'EPSON_XP2200')
            args = run.call_args.args[0]
            self.assertIn('ColorModel=RGB', args)
            self.assertIn('print-color-mode=color', args)
            self.assertEqual(args[args.index('-n') + 1], '1')
            self.assertEqual(value['job_id'], 'EPSON_XP2200-42')
            self.assertFalse(value['printed_verified'])


if __name__ == '__main__':
    unittest.main()
