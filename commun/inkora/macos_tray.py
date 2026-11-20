"""Cocoa menu-bar icon in its own process, with a private Unix control socket."""
import json
from pathlib import Path
import socket
import subprocess
import threading

from . import __version__
from .branding import ASSETS
from .filelock import fcntl
from .i18n import saved_language, set_language, tr
from .service import launch_command, launch_environment, request, runtime_paths, stop_desktop


def tray_request(database, command='Version'):
    path, _ = runtime_paths(database)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(2)
        sock.connect(str(path.with_suffix('.tray')))
        sock.sendall((json.dumps({'command': command}) + '\n').encode())
        raw = b''
        while b'\n' not in raw and len(raw) < 4096:
            chunk = sock.recv(4096)
            if not chunk:
                break
            raw += chunk
        result = json.loads(raw)
        if not isinstance(result, dict) or not result.get('ok'):
            raise ConnectionError('Commande de l’icône OpenInk refusée.')
        return (result['version'],) if command == 'Version' else ()


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
        endpoint.unlink(missing_ok=True)
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        closed = threading.Event()
        status = {'online': False}
        set_language(saved_language(database))

        def show(*_):
            subprocess.Popen(launch_command(database), env=launch_environment(),
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)

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
                pystray.MenuItem(tr('Actualiser'), refresh), pystray.Menu.SEPARATOR,
                pystray.MenuItem(tr('Quitter et arrêter le suivi'), quit_all))

        with Image.open(ASSETS / 'openink-128.png') as source:
            icon = pystray.Icon('OpenInk', source.copy(), 'OpenInk', menu())

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
                        while b'\n' not in raw and len(raw) < 4096:
                            chunk = connection.recv(4096)
                            if not chunk:
                                break
                            raw += chunk
                        if len(raw) >= 4096:
                            raise ValueError('Requête trop grande')
                        value = json.loads(raw)
                        if not isinstance(value, dict) or value.get('command') not in ('Version', 'Quit'):
                            raise ValueError('Commande inconnue')
                        response = {'ok': True, 'version': __version__}
                        stop_icon = value['command'] == 'Quit'
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
            icon.visible = True
            server.bind(str(endpoint))
            endpoint.chmod(0o600)
            server.listen(4)
            server.settimeout(.5)
            threading.Thread(target=control, daemon=True).start()
            while not closed.is_set():
                try:
                    status.update(request(database))
                except (OSError, ValueError):
                    status['online'] = False
                set_language(saved_language(database))
                icon.menu = menu()
                icon.title = 'OpenInk · ' + label(None)
                closed.wait(5)
        try:
            # Cocoa requires the icon's event loop to run on the main thread.
            icon.run(setup)
        finally:
            closed.set()
            server.close()
            endpoint.unlink(missing_ok=True)
