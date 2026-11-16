"""Session-panel icon via StatusNotifierItem and DBusMenu, without a Tk window.

Only the monitor reads the printer. This process reads the private local IPC,
opens the UI on request and stays independent of its window lifetime.
"""
import html
import signal
import subprocess
import threading

from . import __version__
from .i18n import tr,set_language,saved_language
from .branding import ASSETS
from .service import launch_command,launch_environment,request,tray_name,stop_desktop

ITEM='org.kde.StatusNotifierItem'
MENU='com.canonical.dbusmenu'
CONTROL='io.github.Chrisnox209.OpenInk.Tray'
ITEM_XML='''<node><interface name="org.kde.StatusNotifierItem">
 <property name="Category" type="s" access="read"/>
 <property name="Id" type="s" access="read"/>
 <property name="Title" type="s" access="read"/>
 <property name="Status" type="s" access="read"/>
 <property name="WindowId" type="u" access="read"/>
 <property name="IconName" type="s" access="read"/>
 <property name="IconPixmap" type="a(iiay)" access="read"/>
 <property name="IconThemePath" type="s" access="read"/>
 <property name="OverlayIconName" type="s" access="read"/>
 <property name="OverlayIconPixmap" type="a(iiay)" access="read"/>
 <property name="AttentionIconName" type="s" access="read"/>
 <property name="AttentionIconPixmap" type="a(iiay)" access="read"/>
 <property name="AttentionMovieName" type="s" access="read"/>
 <property name="ToolTip" type="(sa(iiay)ss)" access="read"/>
 <property name="ItemIsMenu" type="b" access="read"/>
 <property name="Menu" type="o" access="read"/>
 <method name="Activate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
 <method name="SecondaryActivate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
 <method name="ContextMenu"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
 <method name="Scroll"><arg type="i" direction="in"/><arg type="s" direction="in"/></method>
 <signal name="NewIcon"/><signal name="NewToolTip"/><signal name="NewTitle"/>
 <signal name="NewStatus"><arg type="s"/></signal>
 </interface><interface name="io.github.Chrisnox209.OpenInk.Tray">
 <method name="Version"><arg type="s" direction="out"/></method>
 <method name="Quit"/>
 </interface></node>'''
MENU_XML='''<node><interface name="com.canonical.dbusmenu">
 <property name="Version" type="u" access="read"/>
 <property name="TextDirection" type="s" access="read"/>
 <property name="Status" type="s" access="read"/>
 <property name="IconThemePath" type="as" access="read"/>
 <method name="GetLayout"><arg type="i" direction="in"/><arg type="i" direction="in"/><arg type="as" direction="in"/>
 <arg type="u" direction="out"/><arg type="(ia{sv}av)" direction="out"/></method>
 <method name="GetGroupProperties"><arg type="ai" direction="in"/><arg type="as" direction="in"/><arg type="a(ia{sv})" direction="out"/></method>
 <method name="GetProperty"><arg type="i" direction="in"/><arg type="s" direction="in"/><arg type="v" direction="out"/></method>
 <method name="Event"><arg type="i" direction="in"/><arg type="s" direction="in"/><arg type="v" direction="in"/><arg type="u" direction="in"/></method>
 <method name="EventGroup"><arg type="a(isvu)" direction="in"/><arg type="ai" direction="out"/></method>
 <method name="AboutToShow"><arg type="i" direction="in"/><arg type="b" direction="out"/></method>
 <method name="AboutToShowGroup"><arg type="ai" direction="in"/><arg type="ai" direction="out"/><arg type="ai" direction="out"/></method>
 <signal name="LayoutUpdated"><arg type="u"/><arg type="i"/></signal>
 <signal name="ItemsPropertiesUpdated"><arg type="a(ia{sv})"/><arg type="a(ias)"/></signal>
 <signal name="ItemActivationRequested"><arg type="i"/><arg type="u"/></signal>
 </interface></node>'''


def status_lines(info):
    if not info.get('running'):return 'Surveillance indisponible','Ouvrir OpenInk pour reprendre le suivi.'
    if not info.get('online'):return 'Imprimante hors ligne','Le suivi reprendra à la reconnexion.'
    color,mono=info.get('color_pages'),info.get('mono_pages')
    pages=f'{color+mono} pages · {color} couleur · {mono} noir et blanc'if isinstance(color,int)and isinstance(mono,int)else'Compteurs en cours de lecture'
    status='Encre basse · vérifier les cartouches'if info.get('low_colors')else'Surveillance active'
    return status,pages


class PanelIcon:
    def __init__(self,database):
        import gi
        gi.require_version('Gio','2.0')
        from gi.repository import Gio,GLib
        self.Gio,self.GLib=Gio,GLib
        self.database=database;self.connection=None;self.registrations=[];self.watches=[]
        self.loop=GLib.MainLoop();self.info={};self.revision=1;self.polling=False;self.closed=False
        self.pixmaps=self.icon_pixmaps()

    def icon_pixmaps(self):
        from PIL import Image
        with Image.open(ASSETS/'openink-128.png')as source:
            image=source.convert('RGBA').resize((32,32),Image.Resampling.LANCZOS)
            rgba=image.tobytes();argb=bytes(channel for i in range(0,len(rgba),4)for channel in(rgba[i+3],rgba[i],rgba[i+1],rgba[i+2]))
        return [(32,32,argb)]

    def menu_items(self):
        status,pages=status_lines(self.info)
        from .firmware import SAFE_PHASES,current_operation
        try:
            operation=current_operation();busy=bool(operation and operation['phase']not in SAFE_PHASES)
        except (OSError,ValueError):busy=True
        if busy:status='OpenFlow en cours · suivi suspendu'
        return {0:{'label':'OpenInk','children-display':'submenu'},
                1:{'label':'Ouvrir OpenInk','enabled':True},
                2:{'label':status,'enabled':False},3:{'label':pages,'enabled':False},
                4:{'type':'separator'},5:{'label':'Actualiser le suivi','enabled':not busy},
                6:{'type':'separator'},7:{'label':'Quitter et arrêter le suivi','enabled':not busy}}

    def properties(self,identifier,names=()):
        result=self.menu_items().get(identifier)
        if result is None:raise ValueError('Élément de menu inconnu')
        return {key:self.GLib.Variant('b'if isinstance(value,bool)else's',tr(value))
                for key,value in result.items()if not names or key in names}

    def layout(self,identifier,depth,names):
        children=[]
        if identifier==0 and depth!=0:
            children=[self.GLib.Variant('(ia{sv}av)',self.layout(i,0,names))for i in range(1,8)]
        return identifier,self.properties(identifier,names),children

    def get_property(self,connection,sender,path,interface,name):
        G=self.GLib
        if interface==MENU:
            values={'Version':('u',4),'TextDirection':('s','ltr'),'Status':('s','normal'),'IconThemePath':('as',[str(ASSETS)])}
        else:
            status,pages=status_lines(self.info)
            values={'Category':('s','Hardware'),'Id':('s','OpenInk'),'Title':('s','OpenInk'),
                'Status':('s','Active'),'WindowId':('u',0),'IconName':('s',str(ASSETS/'openink-128.png')),
                'IconPixmap':('a(iiay)',self.pixmaps),'IconThemePath':('s',str(ASSETS)),
                'OverlayIconName':('s',''),'OverlayIconPixmap':('a(iiay)',[]),
                'AttentionIconName':('s','dialog-warning'),'AttentionIconPixmap':('a(iiay)',self.pixmaps),
                'AttentionMovieName':('s',''),'ToolTip':('(sa(iiay)ss)',('openink',self.pixmaps,'OpenInk',html.escape(tr(status)+'\n'+tr(pages)))),
                'ItemIsMenu':('b',False),'Menu':('o','/Menu')}
        signature,value=values[name];return G.Variant(signature,value)

    def open_ui(self):
        subprocess.Popen(launch_command(self.database),env=launch_environment(),
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)

    def action(self,identifier):
        if not self.menu_items().get(identifier,{}).get('enabled'):return
        if identifier==1:self.open_ui()
        elif identifier==5:
            def refresh():
                from .service import ensure_agent
                try:ensure_agent(self.database);request(self.database,'refresh')
                except (OSError,ValueError,RuntimeError):pass
            threading.Thread(target=refresh,daemon=True).start()
        elif identifier==7:stop_desktop(self.database,stop_icon=False);self.quit()

    def call(self,connection,sender,path,interface,method,parameters,invocation):
        G=self.GLib;args=parameters.unpack()
        try:
            if interface==CONTROL:
                if method=='Version':invocation.return_value(G.Variant('(s)',(__version__,)));return
                if method=='Quit':invocation.return_value(None);G.idle_add(self.quit);return
            elif interface==ITEM:
                if method in('Activate','SecondaryActivate'):self.open_ui()
                elif method=='ContextMenu':
                    connection.emit_signal(None,'/Menu',MENU,'ItemActivationRequested',G.Variant('(iu)',(0,0)))
                invocation.return_value(None);return
            elif interface==MENU:
                if method=='GetLayout':reply=G.Variant('(u(ia{sv}av))',(self.revision,self.layout(*args)))
                elif method=='GetGroupProperties':
                    ids,names=args;reply=G.Variant('(a(ia{sv}))',([(i,self.properties(i,names))for i in(ids or list(self.menu_items()))if i in self.menu_items()],))
                elif method=='GetProperty':reply=G.Variant('(v)',(self.properties(args[0])[args[1]],))
                elif method=='AboutToShow':reply=G.Variant('(b)',(False,))
                elif method=='AboutToShowGroup':reply=G.Variant('(aiai)',([],[i for i in args[0]if i not in self.menu_items()]))
                elif method=='Event':
                    if args[1]=='clicked':self.action(args[0])
                    reply=None
                elif method=='EventGroup':
                    errors=[]
                    for identifier,event,_,timestamp in args[0]:
                        if identifier not in self.menu_items():errors.append(identifier)
                        elif event=='clicked':self.action(identifier)
                    reply=G.Variant('(ai)',(errors,))
                else:raise ValueError('Méthode inconnue')
                invocation.return_value(reply);return
            raise ValueError('Méthode inconnue')
        except (ValueError,KeyError)as error:invocation.return_dbus_error('com.canonical.dbusmenu.Error',str(error))

    def watch(self,connection,name,owner):
        def complete(conn,result):
            try:conn.call_finish(result)
            except self.GLib.Error:pass
        connection.call(name,'/StatusNotifierWatcher',name,'RegisterStatusNotifierItem',
            self.GLib.Variant('(s)',(self.bus_name,)),None,self.Gio.DBusCallFlags.NONE,3000,None,complete)

    def poll(self):
        if self.closed:return False
        if not self.polling:
            self.polling=True
            def worker():
                set_language(saved_language(self.database))
                try:info=request(self.database,timeout=1.5)
                except (OSError,ValueError):info={'running':False}
                self.GLib.idle_add(self.received,info)
            threading.Thread(target=worker,daemon=True,name='OpenInk-panel-status').start()
        return True

    def received(self,info):
        self.polling=False
        if self.closed:return False
        from .i18n import get_language
        locale_changed=get_language()!=getattr(self,'display_language',None)
        self.display_language=get_language()
        if info!=self.info or locale_changed:
            self.info=info;self.revision+=1
            self.connection.emit_signal(None,'/StatusNotifierItem',ITEM,'NewToolTip',None)
            self.connection.emit_signal(None,'/Menu',MENU,'LayoutUpdated',self.GLib.Variant('(ui)',(self.revision,0)))
        return False

    def quit(self):
        self.closed=True;self.loop.quit();return False

    def run(self):
        import os
        G=self.GLib;Gio=self.Gio
        self.connection=Gio.bus_get_sync(Gio.BusType.SESSION,None)
        def own(name):
            return self.connection.call_sync('org.freedesktop.DBus','/org/freedesktop/DBus','org.freedesktop.DBus',
                'RequestName',G.Variant('(su)',(name,4)),None,Gio.DBusCallFlags.NONE,2000,None).unpack()[0]==1
        self.control_name=tray_name(self.database)
        if not own(self.control_name):return False
        self.bus_name=f'org.kde.StatusNotifierItem-{os.getpid()}-1'
        own(self.bus_name)
        for path,xml in[('/StatusNotifierItem',ITEM_XML),('/Menu',MENU_XML)]:
            for interface in Gio.DBusNodeInfo.new_for_xml(xml).interfaces:
                self.registrations.append(self.connection.register_object(path,interface,self.call,self.get_property,None))
        for name in('org.kde.StatusNotifierWatcher','org.freedesktop.StatusNotifierWatcher'):
            self.watches.append(Gio.bus_watch_name_on_connection(self.connection,name,Gio.BusNameWatcherFlags.NONE,self.watch,None))
        self.poll();timer=G.timeout_add_seconds(5,self.poll)
        self.connection.connect('closed',lambda *_:self.quit())
        for sig in(signal.SIGTERM,signal.SIGINT):signal.signal(sig,lambda *_:self.quit())
        try:self.loop.run()
        finally:
            self.closed=True;G.source_remove(timer)
            for watch in self.watches:Gio.bus_unwatch_name(watch)
            for registration in self.registrations:self.connection.unregister_object(registration)
            for name in(self.bus_name,self.control_name):
                try:self.connection.call_sync('org.freedesktop.DBus','/org/freedesktop/DBus','org.freedesktop.DBus','ReleaseName',G.Variant('(s)',(name,)),None,Gio.DBusCallFlags.NONE,1000,None)
                except G.Error:pass
        return True


def run_tray(database):
    return PanelIcon(database).run()
