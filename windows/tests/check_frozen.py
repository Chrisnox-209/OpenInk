"""Launch the actual compiled EXE against loopback only; never a printer."""
from pathlib import Path
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'commun'))
from inkora.service import request, stop_desktop, tray_request
from inkora.store import Store
from inkora.windows_ipc import tray_request as icon_command
import win32con
import win32gui
import win32process


def until(check, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            result = check()
            if result:
                return result
        except (OSError, ValueError):
            pass
        time.sleep(.1)
    raise AssertionError('Windows application did not reach expected state')


def main():
    executable = Path(__file__).resolve().parents[1] / 'dist/OpenInk/OpenInk.exe'
    with tempfile.TemporaryDirectory(prefix='OpenInk smoke ') as folder:
        database = Path(folder) / 'state.sqlite3'
        store = Store(database)
        store.set_setting('host', '127.0.0.1')
        store.set_setting('transport', 'network')
        store.set_setting('autostart', False)
        store.close()
        command = [str(executable), '--database', str(database)]
        process = subprocess.Popen(command)
        try:
            until(lambda: request(database)['running'])
            until(lambda: tray_request(database) == ('1.7.0',))
            def window():
                found = []
                def visit(hwnd, _):
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    if pid == process.pid and win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd).startswith('OpenInk'):
                        found.append(hwnd)
                win32gui.EnumWindows(visit, None)
                return found[0] if found else None
            hwnd = until(window)
            duplicate = subprocess.Popen(command)
            assert duplicate.wait(15) == 0
            assert window() == hwnd
            assert icon_command(database, 'Notify', title='OpenInk test', detail='Offline software check')['ok']
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
            assert process.wait(15) == 0
            assert request(database)['running'], 'Closing the UI must preserve monitoring'
            stop_desktop(database)
            def stopped():
                try:
                    request(database)
                    return False
                except OSError:
                    return True
            until(stopped)
            print('Compiled EXE: window, singleton, agent, tray, notification, close and stop OK')
        finally:
            stop_desktop(database)
            try:
                process.wait(15)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(5)


if __name__ == '__main__':
    main()
