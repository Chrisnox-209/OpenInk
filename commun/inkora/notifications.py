"""Optional local desktop notification; never communicates with a printer."""
import shutil
import subprocess
import sys
import time
from .i18n import tr


class DesktopNotifications:
    """Native D-Bus notifications with an optional Open OpenInk action.

    A successful return only means accepted by the desktop, never read by a user.
    The agent pumps the GLib context without blocking its printer/IPC loop.
    """
    def __init__(self,database):
        self.database=database
        self.connection=None
        self.context=None
        self.ids=set()
        self.next_connection_attempt=0

    def _connect(self):
        if self.connection:return
        import gi
        gi.require_version('Gio','2.0')
        from gi.repository import Gio,GLib
        self.Gio,self.GLib=Gio,GLib
        self.context=GLib.MainContext.default()
        self.connection=Gio.bus_get_sync(Gio.BusType.SESSION,None)
        self.connection.signal_subscribe('org.freedesktop.Notifications','org.freedesktop.Notifications',
            'ActionInvoked','/org/freedesktop/Notifications',None,Gio.DBusSignalFlags.NONE,self._action)

    def _action(self,connection,sender,path,interface,signal,parameters,*_):
        identifier,action=parameters.unpack()
        if action=='open' and identifier in self.ids:
            from .service import launch_command,launch_environment
            subprocess.Popen(launch_command(self.database),env=launch_environment(),
                             stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)

    def send(self,title,detail,critical=False):
        self._connect()
        Gio,GLib=self.Gio,self.GLib
        result=self.connection.call_sync('org.freedesktop.Notifications','/org/freedesktop/Notifications',
            'org.freedesktop.Notifications','GetCapabilities',None,GLib.VariantType.new('(as)'),
            Gio.DBusCallFlags.NONE,3000,None)
        capabilities=result.unpack()[0]
        actions=['open',tr('Ouvrir OpenInk')] if 'actions' in capabilities else []
        # Reserve alerts stay at normal urgency: the desktop decides how to
        # present them, including its Do Not Disturb setting.
        hints={'desktop-entry':GLib.Variant('s','openink'), 'urgency':GLib.Variant('y',1)}
        args=GLib.Variant('(susssasa{sv}i)',('OpenInk',0,'openink',tr(title),tr(detail),actions,hints,-1))
        reply=self.connection.call_sync('org.freedesktop.Notifications','/org/freedesktop/Notifications',
            'org.freedesktop.Notifications','Notify',args,GLib.VariantType.new('(u)'),
            Gio.DBusCallFlags.NONE,3000,None)
        identifier=reply.unpack()[0]
        self.ids.add(identifier)
        return identifier

    def poll(self):
        if self.connection is None and time.monotonic()>=self.next_connection_attempt:
            self.next_connection_attempt=time.monotonic()+60
            try:self._connect()
            except Exception:return
        if self.context:
            if self.connection and self.connection.is_closed():
                raise ConnectionError('La session de notifications est terminée.')
            while self.context.pending():self.context.iteration(False)


def send_notification(title, detail):
    if not sys.platform.startswith("linux"):
        return False
    command = shutil.which("notify-send")
    if not command:
        return False
    try:
        result = subprocess.run([command, "--app-name=OpenInk", "--icon=dialog-warning",
                                 tr(title), tr(detail)], capture_output=True, timeout=5)
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False
