"""Real D-Bus integration on an isolated session: no desktop or printer access.

Run with: dbus-run-session -- python3 linux/tests/check_tray.py
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'commun'))
import gi
gi.require_version('Gio','2.0')
from gi.repository import Gio,GLib
from inkora import __version__
from inkora.i18n import set_language,tr
from inkora.service import tray_name
from inkora.tray import CONTROL,ITEM,MENU


def main(language='fr'):
    set_language(language)
    with tempfile.TemporaryDirectory(prefix='openink-dbus-')as temporary:
        root=Path(temporary);database=root/'demo.sqlite3';registered=[]
        environment={**os.environ,'XDG_DATA_HOME':str(root/'data'),'XDG_RUNTIME_DIR':str(root/'runtime'),
                     'PYTHONPATH':str(Path(__file__).resolve().parents[2]/'commun')}
        os.environ['XDG_RUNTIME_DIR']=environment['XDG_RUNTIME_DIR']
        connection=Gio.bus_get_sync(Gio.BusType.SESSION,None)
        watcher=Gio.DBusNodeInfo.new_for_xml('''<node><interface name="org.kde.StatusNotifierWatcher">
        <method name="RegisterStatusNotifierItem"><arg type="s" direction="in"/></method>
        </interface></node>''').interfaces[0]
        def registration(conn,sender,path,interface,method,parameters,invocation):
            registered.append(parameters.unpack()[0]);invocation.return_value(None)
        identifier=connection.register_object('/StatusNotifierWatcher',watcher,registration,None,None)
        connection.call_sync('org.freedesktop.DBus','/org/freedesktop/DBus','org.freedesktop.DBus',
            'RequestName',GLib.Variant('(su)',('org.kde.StatusNotifierWatcher',4)),None,Gio.DBusCallFlags.NONE,2000,None)
        loop=GLib.MainLoop();thread=threading.Thread(target=loop.run,daemon=True);thread.start()
        script="""from pathlib import Path
import sys
from inkora.tray import PanelIcon
from inkora.i18n import set_language
set_language(sys.argv[3])
icon=PanelIcon(Path(sys.argv[1]))
icon.info={'running':True,'online':True,'color_pages':104,'mono_pages':60}
icon.poll=lambda:True
icon.open_ui=lambda:Path(sys.argv[2]).write_text('opened')
icon.run()
"""
        process=subprocess.Popen([sys.executable,'-c',script,str(database),str(root/'opened'),language],env=environment)
        def call(path,interface,method,args=None):
            return connection.call_sync(tray_name(database),path,interface,method,args,None,Gio.DBusCallFlags.NONE,2000,None)
        try:
            deadline=time.monotonic()+8
            while time.monotonic()<deadline:
                try:
                    assert call('/StatusNotifierItem',CONTROL,'Version').unpack()==(__version__,)
                    if registered:break
                except GLib.Error:pass
                time.sleep(.05)
            else:raise AssertionError('Icon not registered')
            properties=call('/StatusNotifierItem','org.freedesktop.DBus.Properties','GetAll',GLib.Variant('(s)',(ITEM,))).unpack()[0]
            assert properties['Title']=='OpenInk'and properties['Menu']=='/Menu'
            assert len(properties['IconPixmap'][0][2])==32*32*4
            layout=call('/Menu',MENU,'GetLayout',GLib.Variant('(iias)',(0,-1,[]))).unpack()
            assert len(layout[1][2])==7
            assert tr('164 pages · 104 couleur · 60 noir et blanc')==layout[1][2][2][1]['label']
            call('/Menu',MENU,'GetGroupProperties',GLib.Variant('(aias)',([1,2,3],[])))
            assert call('/Menu',MENU,'GetProperty',GLib.Variant('(is)',(1,'label'))).unpack()==(tr('Ouvrir OpenInk'),)
            call('/Menu',MENU,'AboutToShowGroup',GLib.Variant('(ai)',([0,1],)))
            call('/Menu',MENU,'Event',GLib.Variant('(isvu)',(1,'clicked',GLib.Variant('i',0),0)))
            assert(root/'opened').is_file()
            (root/'opened').unlink()
            call('/StatusNotifierItem',ITEM,'Activate',GLib.Variant('(ii)',(0,0)))
            assert(root/'opened').is_file()
            call('/StatusNotifierItem',CONTROL,'Quit');process.wait(timeout=4)
            assert process.returncode==0
            print(language+': D-Bus réel isolé, inscription, icône ARGB, menu, compteurs, activation et arrêt OK.')
        finally:
            if process.poll()is None:process.terminate();process.wait(timeout=4)
            loop.quit();thread.join(2);connection.unregister_object(identifier)


if __name__=='__main__':
    for language in('fr','en','es'):main(language)
