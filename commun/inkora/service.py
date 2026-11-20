"""Private local session-agent control. There is no printer-write IPC command."""
from .filelock import fcntl
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time


def runtime_paths(database):
    if sys.platform == 'darwin':
        from .macos_support import runtime_paths as mac_paths
        return mac_paths(database)
    if os.name == "nt":
        from .windows_ipc import runtime_paths as windows_paths
        return windows_paths(database)
    root=Path(os.environ.get("XDG_RUNTIME_DIR", str(Path.home()/".cache")))/"inkora"
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    if root.stat().st_uid!=os.getuid():
        raise RuntimeError("Le répertoire de session n’appartient pas à cet utilisateur.")
    root.chmod(0o700)
    key=hashlib.sha256(str(Path(database).resolve()).encode()).hexdigest()[:12]
    return root/(key+".sock"),root/(key+".lock")


def request(database, command="ping", timeout=2):
    if command not in {"ping","refresh","stop","show"}:
        raise ValueError("Commande de session inconnue.")
    path,_=runtime_paths(database)
    if os.name == "nt":
        from .windows_ipc import request_path
        return request_path(path, command, timeout)
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        sock.connect(str(path))
        sock.sendall((json.dumps({"command":command})+"\n").encode())
        raw=b""
        while b"\n"not in raw and len(raw)<16384:
            chunk=sock.recv(4096)
            if not chunk:break
            raw+=chunk
        result=json.loads(raw)
        if not isinstance(result,dict):raise ValueError('Réponse de session invalide')
        return result


def launch_command(database, *arguments):
    if getattr(sys,"frozen",False):
        return [sys.executable,"--database",str(database),*arguments]
    if sys.platform == 'darwin':
        launcher=Path(__file__).resolve().parents[2]/'macos/openink_macos.py'
        if launcher.is_file():
            return [sys.executable,str(launcher),'--database',str(database),*arguments]
    executable = str(Path(sys.executable).with_name("pythonw.exe")) if os.name == "nt" else sys.executable
    return [executable,"-m","inkora", "--database",str(database),*arguments]


def launch_environment():
    return {**os.environ,"PYTHONPATH":str(Path(__file__).resolve().parent.parent)}


def ensure_agent(database):
    from . import __version__
    try:
        status=request(database)
        if status.get('app_version')==__version__:return status
        request(database,'stop')
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            try:request(database)
            except OSError:break
            time.sleep(.1)
        else:raise RuntimeError('L’ancien agent termine sa lecture ; relance OpenInk après sa fermeture.')
    except (OSError,ValueError):
        pass
    subprocess.Popen(launch_command(database,"--agent"),env=launch_environment(),
                     stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
    deadline=time.monotonic()+4
    while time.monotonic()<deadline:
        try:return request(database)
        except (OSError,ValueError):time.sleep(.08)
    raise RuntimeError("L’agent de surveillance n’a pas démarré. Consulter le journal OpenInk.")


class WindowLock:
    def __init__(self,database):
        path,lock=runtime_paths(database)
        self.path=path.with_suffix('.show')
        self.quit_path=path.with_suffix('.ui-quit')
        self.handle=lock.with_suffix('.ui-lock').open('a+b')
        try:
            fcntl.flock(self.handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            self.path.touch(mode=0o600)
            self.handle.close()
            raise RuntimeError("Une fenêtre OpenInk est déjà ouverte.") from None
        self.quit_path.unlink(missing_ok=True)
    def close(self):
        self.handle.close()


def tray_name(database):
    path,_=runtime_paths(database)
    return 'io.github.Chrisnox209.OpenInk.Tray.p'+path.stem


def tray_request(database,command='Version'):
    if sys.platform == 'darwin':
        from .macos_tray import tray_request as mac_request
        return mac_request(database,command)
    if os.name == 'nt':
        from .windows_ipc import tray_request as windows_request
        result = windows_request(database, command)
        return (result['version'],) if command == 'Version' else ()
    import gi
    gi.require_version('Gio','2.0')
    from gi.repository import Gio,GLib
    connection=Gio.bus_get_sync(Gio.BusType.SESSION,None)
    return connection.call_sync(tray_name(database),'/StatusNotifierItem',
        'io.github.Chrisnox209.OpenInk.Tray',command,None,None,Gio.DBusCallFlags.NONE,1000,None).unpack()


def ensure_tray(database):
    """One session icon per database, without creating a Tk window."""
    from . import __version__
    try:previous=tray_request(database)
    except Exception:previous=None
    if previous==(__version__,):return True
    if previous:
        try:tray_request(database,'Quit')
        except Exception:return False
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            try:tray_request(database)
            except Exception:break
            time.sleep(.05)
        else:return False
    subprocess.Popen(launch_command(database,'--tray'),env=launch_environment(),
                     stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
    deadline=time.monotonic()+3
    while time.monotonic()<deadline:
        try:
            if tray_request(database)==(__version__,):return True
        except Exception:pass
        time.sleep(.1)
    return False


def stop_desktop(database,stop_icon=True):
    """Stop UI, monitor and icon; never interrupts a firmware worker."""
    path,_=runtime_paths(database)
    path.with_suffix('.ui-quit').touch(mode=0o600)
    try:request(database,'stop')
    except (OSError,ValueError):pass
    if stop_icon:
        try:tray_request(database,'Quit')
        except Exception:pass
