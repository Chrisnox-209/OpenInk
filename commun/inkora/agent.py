"""Single session monitor: reads status, stores events and delivers notifications."""
from datetime import datetime, timezone
import fcntl
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import signal
import socket
import threading
import time

from .service import runtime_paths
from .store import Store
from .usb import read_connected
from .notifications import DesktopNotifications
from . import __version__
from .i18n import set_language


class PrivateRotatingLog(RotatingFileHandler):
    def _open(self):
        return open(self.baseFilename,self.mode,encoding=self.encoding,errors=self.errors,
                    opener=lambda path,flags:os.open(path,flags,0o600))


class Agent:
    def __init__(self, database, reader=read_connected, notifier=None):
        self.database=database
        self.reader=reader
        self.notifier=notifier
        self.stop=threading.Event()
        self.wake=threading.Event()
        self.info={"running":True,"online":False,"error":"Connexion en cours","last_success":None,"pid":os.getpid(),'app_version':__version__}
        self.server=None

    def serve(self):
        while not self.stop.is_set():
            try:connection,_=self.server.accept()
            except (TimeoutError,socket.timeout):continue
            except OSError:break
            with connection:
                connection.settimeout(1)
                try:
                    data=b""
                    while b"\n"not in data and len(data)<4096:
                        chunk=connection.recv(4096)
                        if not chunk:break
                        data+=chunk
                    if len(data)>=4096:raise ValueError("Requête trop grande")
                    parsed=json.loads(data)
                    if not isinstance(parsed,dict):raise ValueError('Requête invalide')
                    command=parsed.get("command")
                    if command=="refresh":self.wake.set()
                    elif command=="stop":self.stop.set();self.wake.set()
                    elif command not in {"ping","show"}:raise ValueError("Commande non prise en charge")
                    response={**self.info,"ok":True}
                except (ValueError,OSError) as exc:response={"ok":False,"error":str(exc)}
                try:connection.sendall((json.dumps(response,ensure_ascii=False)+"\n").encode())
                except OSError:pass

    def run(self, max_cycles=None):
        path,lock=runtime_paths(self.database)
        with lock.open('a+b') as handle:
            try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:return False
            # Only the process holding the lock may replace its stale socket.
            path.unlink(missing_ok=True)
            store=Store(self.database)
            log_path=store.path.parent/'agent.log'
            logger=logging.getLogger('inkora.agent')
            handler=PrivateRotatingLog(log_path,maxBytes=500000,backupCount=2,encoding='utf-8')
            log_path.chmod(0o600)
            logger.addHandler(handler);logger.setLevel(logging.INFO)
            self.notifier=self.notifier or DesktopNotifications(self.database)
            server=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
            self.server=server
            try:
                server.bind(str(path));path.chmod(0o600);server.listen(4);server.settimeout(.5)
                thread=threading.Thread(target=self.serve,daemon=True,name='OpenInk-session-control');thread.start()
                failures=0;cycles=0;next_read=0
                while not self.stop.is_set():
                    if not Path(__file__).is_file():break  # Uninstalled package: stop without root intervention.
                    set_language(store.setting('language','auto'))
                    try:self.notifier.poll()
                    except ConnectionError:
                        logger.info('Fin de la session graphique, arrêt de la surveillance.')
                        break
                    if time.monotonic()>=next_read or self.wake.is_set():
                        self.wake.clear()
                        try:
                            snapshot=self.reader(store.setting('host','192.168.1.55'),store.setting('transport','network'))
                            store.observe(snapshot)
                            store.queue_reminders(snapshot)
                            self.info={"running":True,"online":True,"error":"","last_success":snapshot.observed_at,"pid":os.getpid(),'app_version':__version__,
                                       "printer_id":snapshot.printer_id,"transport":snapshot.transport,
                                       'color_pages':snapshot.color_pages,'mono_pages':snapshot.mono_pages,
                                       'low_colors':[color for color,item in store.estimates(snapshot).items()if item and item['state']in('warning','reserve')]}
                            failures=0
                        except Exception as exc:
                            failures+=1
                            self.info={**self.info,"online":False,"error":str(exc)}
                            logger.warning('Lecture indisponible: %s',exc)
                        if self.info['online'] and store.setting('notifications',True):
                            for item in store.pending_notifications(self.info.get('printer_id')):
                                try:
                                    identifier=self.notifier.send(item['title'],item['detail'],item.get('state')=='reserve')
                                    store.notification_delivery(item['id'],'sent',str(identifier))
                                except Exception as exc:
                                    store.notification_delivery(item['id'],'failed',str(exc))
                                    logger.warning('Notification indisponible: %s',exc)
                        next_read=time.monotonic()+min(120,15*(2**min(failures,3)))
                        cycles+=1
                        if max_cycles is not None and cycles>=max_cycles:break
                    self.stop.wait(.2)
            finally:
                self.stop.set();server.close();path.unlink(missing_ok=True)
                store.close();logger.removeHandler(handler);handler.close()
        return True


def run_agent(database):
    agent=Agent(database)
    for sig in (signal.SIGTERM,signal.SIGINT):
        signal.signal(sig,lambda *_: (agent.stop.set(),agent.wake.set()))
    return agent.run()
