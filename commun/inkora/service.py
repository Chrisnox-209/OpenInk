"""Private local session-agent control. There is no printer-write IPC command."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time


def runtime_paths(database):
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
    return [sys.executable,"-m","inkora", "--database",str(database),*arguments]


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
        self.handle=lock.with_suffix('.ui-lock').open('a+b')
        try:
            fcntl.flock(self.handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            self.path.touch(mode=0o600)
            self.handle.close()
            raise RuntimeError("Une fenêtre OpenInk est déjà ouverte.") from None
    def close(self):
        self.handle.close()
