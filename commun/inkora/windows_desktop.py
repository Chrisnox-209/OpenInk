"""Windows notification-area icon and per-user startup integration."""
import json
import subprocess
import threading
import time

from . import __version__
from .branding import ASSETS
from .filelock import fcntl
from .i18n import saved_language, set_language, tr
from .service import launch_command, launch_environment, request, stop_desktop
from .windows_ipc import authenticate, create_server, runtime_paths, tray_request


def set_autostart(database, enabled):
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                          r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
        if enabled:
            winreg.SetValueEx(key, 'OpenInk', 0, winreg.REG_SZ,
                             subprocess.list2cmdline(launch_command(database, '--background')))
        else:
            try:
                winreg.DeleteValue(key, 'OpenInk')
            except FileNotFoundError:
                pass


class DesktopNotifications:
    def __init__(self, database):
        self.database = database

    def poll(self):
        pass

    def send(self, title, detail, critical=False):
        result = tray_request(self.database, 'Notify', title=tr(title), detail=tr(detail))
        return result['id']


def run_tray(database):
    import pystray
    from PIL import Image
    path, lock = runtime_paths(database)
    endpoint = path.with_suffix('.tray')
    with lock.with_suffix('.tray-lock').open('a+b') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        closed = threading.Event()
        status = {'online': False}
        set_language(saved_language(database))

        def show(*_):
            subprocess.Popen(launch_command(database), env=launch_environment(),
                             creationflags=subprocess.CREATE_NO_WINDOW)

        def refresh(*_):
            try:
                request(database, 'refresh')
            except (OSError, ValueError):
                pass

        def quit_all(*_):
            stop_desktop(database, stop_icon=False)
            closed.set()
            icon.stop()

        def label(_):
            return tr('Connectée' if status.get('online') else 'Hors ligne')

        def menu():
            return pystray.Menu(
                pystray.MenuItem(tr('Ouvrir OpenInk'), show, default=True),
                pystray.MenuItem(label, None, enabled=False),
                pystray.MenuItem(tr('Actualiser'), refresh),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(tr('Quitter et arrêter le suivi'), quit_all))

        with Image.open(ASSETS / 'openink-128.png') as source:
            icon = pystray.Icon('OpenInk', source.copy(), 'OpenInk', menu())
        server = None

        def control():
            while not closed.is_set():
                try:
                    connection, _ = server.accept()
                except TimeoutError:
                    continue
                except OSError:
                    return
                with connection:
                    connection.settimeout(1)
                    stop_icon = False
                    try:
                        raw = b''
                        while b'\n' not in raw and len(raw) < 8192:
                            chunk = connection.recv(4096)
                            if not chunk:
                                break
                            raw += chunk
                        if len(raw) >= 8192:
                            raise ValueError('Requête trop grande')
                        value = json.loads(raw)
                        if not isinstance(value, dict):
                            raise ValueError('Requête invalide')
                        authenticate(value, secret)
                        command = value.get('command')
                        response = {'ok': True, 'version': __version__}
                        if command == 'Notify':
                            title, detail = value.get('title'), value.get('detail')
                            if not isinstance(title, str) or not isinstance(detail, str):
                                raise ValueError('Notification invalide')
                            icon.notify(detail[:255], title[:63])
                            response['id'] = time.time_ns()
                        elif command == 'Quit':
                            stop_icon = True
                        elif command != 'Version':
                            raise ValueError('Commande inconnue')
                    except (ValueError, OSError) as exc:
                        response = {'ok': False, 'error': str(exc)}
                    try:
                        connection.sendall((json.dumps(response) + '\n').encode())
                    except OSError:
                        pass
                    if stop_icon:
                        closed.set()
                        icon.stop()

        def setup(_):
            nonlocal server, secret
            icon.visible = True
            server, secret = create_server(endpoint)
            threading.Thread(target=control, daemon=True).start()
            while not closed.is_set():
                try:
                    status.update(request(database))
                except (OSError, ValueError):
                    status['online'] = False
                old = saved_language(database)
                set_language(old)
                icon.menu = menu()
                icon.title = 'OpenInk · ' + label(None)
                closed.wait(5)
        secret = ''
        try:
            icon.run(setup)
        finally:
            closed.set()
            if server:
                server.close()
            endpoint.unlink(missing_ok=True)
