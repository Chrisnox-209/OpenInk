"""Portable Tk/Canvas desktop interface. All printer I/O runs off the UI thread."""
from datetime import datetime
import ipaddress
import queue
import threading
import time
from .widgets import tk,ttk
from tkinter import filedialog

from .printer import COLORS, NAMES, read_printer
from .store import DEFAULT_WARNING, DEFAULT_RESERVE
from .notifications import send_notification
from .diagnostics import cartridge_diagnostics
from .reset import capability,request_reset
from .dialogs import focus_existing,register_dialog,scrollable_content
from .i18n import tr
from .branding import ASSETS,initial_geometry,active_monitor
from . import __version__

BG = "#F4F6FB"
WHITE = "#FFFFFF"
INK = "#20283D"
MUTED = "#818A9E"
LINE = "#E8ECF3"
NAV = "#171F31"
PURPLE = "#7560E8"
AMBER = "#B87A17"
RED = "#BD4D4D"
INKS = {"black": "#354057", "cyan": "#23B8D4", "magenta": "#E95C99", "yellow": "#EDB936"}
TINTS = {"black": "#EDF0F5", "cyan": "#E5F8FC", "magenta": "#FDEDF4", "yellow": "#FFF7DF"}
PAGES = ("Vue d’ensemble", "Cartouches", "Historique", "Réglages", "OpenFlow")


def number(value):
    return "—" if value is None else f"{value:,}".replace(",", " ")


def local_date(value, fmt="%d/%m à %H:%M"):
    try:
        return datetime.fromisoformat(value).astimezone().strftime(tr(fmt))
    except (ValueError, TypeError):
        return "—"


class Application:
    def __init__(self, root, store, demo=False,managed=False):
        self.root, self.store, self.demo = root, store, demo
        self.managed=managed
        self.service_polling=False
        self.last_service_poll=0
        self.window_lock=None
        self.host = store.setting("host", "192.168.1.55")
        self.snapshot = store.latest()
        self.online = bool(demo)
        self.busy, self.closed = False, False
        self.page, self.dialog = 0, None
        self.messages = queue.Queue()
        self.notice = ""
        self.focus_action = -1
        self.host_var = tk.StringVar(value=self.host)
        self.coverage_var = tk.StringVar(value={1.0: "Documents courants", 1.8: "Documents chargés", 5.0: "Photos / aplats"}.get(store.setting("coverage", 1.0), "Documents courants"))
        self.warning_var = tk.StringVar(value=f"{store.setting('warning_percent', DEFAULT_WARNING):g}")
        self.reserve_var = tk.StringVar(value=f"{store.setting('reserve_percent', DEFAULT_RESERVE):g}")
        self.notifications_var = tk.BooleanVar(value=store.setting("notifications", True))
        self.startup_var=tk.BooleanVar(value=store.setting('autostart',True))
        from .i18n import LANGUAGES
        self.language_var=tk.StringVar(value=LANGUAGES.get(store.setting('language','auto'),'Automatique'))
        self.transport_var=tk.StringVar(value={'network':'Wi-Fi','usb':'USB','auto':'Auto'}.get(store.setting('transport','network'),'Wi-Fi'))
        self.reminder_var=tk.StringVar(value={0:'Rappel : aucun',60:'Rappel : 1 h',240:'Rappel : 4 h'}.get(store.setting('reminder_minutes',0),'Rappel : aucun'))
        root.title(f"OpenInk {__version__} · Epson XP-2200")
        self.monitor_geometry=active_monitor(root)
        monitor_w,monitor_h,monitor_x,monitor_y=self.monitor_geometry
        width,height,min_width,min_height=initial_geometry(monitor_w,monitor_h)
        root.geometry(f'{width}x{height}{monitor_x+(monitor_w-width)//2:+d}{monitor_y+(monitor_h-height)//2:+d}')
        root.minsize(min_width,min_height)
        root.configure(bg=BG)
        self.family = "Lato"
        from tkinter import font
        families = font.families(root)
        self.family = next((f for f in ("Lato", "Segoe UI", "Helvetica Neue", "DejaVu Sans") if f in families), "TkDefaultFont")
        # Normalize actual font metrics to our pixel-based Canvas layout.
        # Some Linux fontconfig setups apply a second display scaling factor.
        measured=font.Font(root,font=(self.family,-14)).metrics("linespace")
        self.font_correction=17/max(1,measured)
        root.option_add("*Font", self.font(11))
        style = ttk.Style(root)
        self.style=style
        style.theme_use("clam")
        style.configure("TCombobox", padding=7, fieldbackground=WHITE, foreground=INK,
                        background=WHITE, bordercolor=LINE, arrowcolor=PURPLE)
        style.configure("TCheckbutton", background=WHITE, foreground=INK, padding=7,font=self.font(11))
        style.map("TCheckbutton", background=[("active", WHITE)])
        self.canvas = tk.Canvas(root, bg=BG, highlightthickness=0, takefocus=True)
        self.canvas.pack(fill="both", expand=True)
        self.widgets, self.actions = [], []
        self.scale, self.ox, self.oy = 1, 0, 0
        self.resize_job = None
        self.canvas.bind("<Configure>", self.resize)
        root.bind("<Tab>", self.next_focus)
        root.bind("<Return>", self.activate_focus)
        root.bind("<F5>", lambda _e: self.refresh())
        root.bind("<Control-r>", lambda _e: self.refresh())
        root.protocol("WM_DELETE_WINDOW", self.close)
        self._icon()
        self.render()
        root.after(120, self.refresh)
        root.after(100, self.poll)
        root.after(15000, self.auto_refresh)
        from .firmware_ui import poll as firmware_poll
        root.after(1000,lambda:firmware_poll(self))

    def _icon(self):
        from PIL import Image
        self.icon=tk.PhotoImage(file=str(ASSETS/'openink-128.png'))
        self.root.iconphoto(True,self.icon)
        with Image.open(ASSETS/'openink-512.png')as source:self.logo_source=source.convert('RGBA')
        self.brand_images={}

    def brand_image(self):
        from PIL import Image
        from io import BytesIO
        size=max(28,round(42*self.scale))
        if size not in self.brand_images:
            if len(self.brand_images)>8:self.brand_images.clear()
            encoded=BytesIO();self.logo_source.resize((size,size),Image.Resampling.LANCZOS).save(encoded,format='PNG')
            self.brand_images[size]=tk.PhotoImage(data=encoded.getvalue(),format='png',master=self.root)
        return self.brand_images[size]

    def font(self,size,weight="normal",scaled=False):
        factor=getattr(self,"scale",1) if scaled else 1
        pixels=max(4,round(size*4/3*self.font_correction*factor))
        return (self.family,-pixels,weight)

    def resize(self, _event=None):
        if self.resize_job:
            self.root.after_cancel(self.resize_job)
        self.resize_job = self.root.after(70, self.render)

    def point(self, x, y):
        if x>=210:x=210+(x-210)*getattr(self,'content_stretch',1)
        return self.ox+x*self.scale, self.oy+y*self.scale

    def rect(self, x, y, w, h, fill, radius=14, outline=None, width=1):
        r = min(radius, w/2, h/2)
        points = [x+r,y,x+w-r,y,x+w,y,x+w,y+r,x+w,y+h-r,x+w,y+h,x+w-r,y+h,
                  x+r,y+h,x,y+h,x,y+h-r,x,y+r,x,y]
        flat = []
        for i in range(0,len(points),2):
            flat.extend(self.point(points[i],points[i+1]))
        return self.canvas.create_polygon(flat, smooth=True, splinesteps=24,
                   fill=fill, outline=outline or fill, width=max(1,width*self.scale))

    def text(self, x, y, value, size=11, color=INK, weight="normal", anchor="w", width=0):
        a,b = self.point(x,y)
        return self.canvas.create_text(a,b,text=tr(value),fill=color,anchor=anchor,
                    font=self.font(size,weight,scaled=True),
                    width=width*self.scale*(self.content_stretch if x>=210 else 1)if width else 0)

    def line(self, x1,y1,x2,y2, color=LINE, width=1):
        return self.canvas.create_line(*self.point(x1,y1),*self.point(x2,y2),fill=color,width=width*self.scale)

    def circle(self,x,y,r,color,outline=None,width=1):
        cx,cy=self.point(x,y);radius=r*self.scale
        return self.canvas.create_oval(cx-radius,cy-radius,cx+radius,cy+radius,
                    fill=color,outline=outline or color,width=width*self.scale)

    def button(self,x,y,w,h,label,callback,primary=False,subtle=False,icon=None):
        enabled = callback is not None
        fill = PURPLE if primary else (BG if subtle else WHITE)
        foreground = WHITE if primary else INK
        if not enabled:
            fill,foreground = "#E8EAF1",MUTED
        shape = self.rect(x,y,w,h,fill,10,outline=None if primary or subtle else LINE)
        txt = self.text(x+w/2,y+h/2,label,10,foreground,"bold",anchor="center")
        if enabled:
            action_index = len(self.actions)
            self.actions.append((shape,callback))
            def enter(_e):
                self.canvas.configure(cursor="hand2")
                self.canvas.itemconfigure(shape,fill="#6852DC" if primary else "#EBE8FB")
            def leave(_e):
                self.canvas.configure(cursor="")
                self.canvas.itemconfigure(shape,fill=fill)
            for item in (shape,txt):
                self.canvas.tag_bind(item,"<Enter>",enter)
                self.canvas.tag_bind(item,"<Leave>",leave)
                self.canvas.tag_bind(item,"<Button-1>",lambda _e,fn=callback,i=action_index: self.click(fn,i))

    def click(self,callback,index):
        self.focus_action = index
        callback()

    def next_focus(self,_event):
        if self.dialog or self.page==3:
            return None
        if self.actions:
            self.focus_action=(self.focus_action+1)%len(self.actions)
            for i,(shape,_fn) in enumerate(self.actions):
                self.canvas.itemconfigure(shape,outline=PURPLE if i==self.focus_action else self.canvas.itemcget(shape,"fill"),width=2 if i==self.focus_action else 1)
        return "break"

    def activate_focus(self,_event):
        if not self.dialog and self.page!=3 and 0<=self.focus_action<len(self.actions):
            self.actions[self.focus_action][1]()

    def nav_icon(self,x,y,index,color):
        if index==0:
            for a,b in ((0,0),(10,0),(0,10),(10,10)):
                self.rect(x+a,y+b,6,6,color,2)
        elif index==1:
            self.rect(x+2,y+4,13,15,color,3)
            self.rect(x+5,y,7,6,color,2)
        elif index==2:
            self.circle(x+9,y+9,8,NAV,color,1.5)
            self.line(x+9,y+4,x+9,y+9,color,1.5)
            self.line(x+9,y+9,x+13,y+11,color,1.5)
        else:
            self.circle(x+9,y+9,8,NAV,color,2)
            self.circle(x+9,y+9,3,color)

    def render(self):
        if self.closed:
            return
        self.resize_job=None
        w=max(self.canvas.winfo_width(),1)
        h=max(self.canvas.winfo_height(),1)
        self.scale=min(w/1280,h/850)
        self.content_stretch=max(1,(w/self.scale-210)/1070)
        self.ox=0
        self.oy=(h-850*self.scale)/2
        native_font=self.font(11,scaled=True)
        self.root.option_add('*Font',native_font)
        self.style.configure('TCheckbutton',font=native_font,padding=max(3,round(7*self.scale)))
        self.style.configure('TCombobox',font=native_font,padding=max(3,round(7*self.scale)))
        for widget in self.widgets:
            widget.destroy()
        self.widgets=[]
        self.canvas.delete("all")
        self.canvas.create_rectangle(0,0,w,h,fill=BG,outline=BG)
        self.actions=[]
        self.focus_action=-1
        self.canvas.create_rectangle(0,0,210*self.scale,h,fill=NAV,outline=NAV,tags='sidebar-background')
        self.canvas.create_image(*self.point(24,25),image=self.brand_image(),anchor='nw')
        self.text(72,46,"OpenInk",23,WHITE,"bold")
        self.text(29,87,"L’ENCRE, EN TOUTE CLARTÉ",8,"#8C98B0","bold")
        for index,title in enumerate(PAGES):
            y=139+54*index
            selected=index==self.page
            first=len(self.canvas.find_all())
            area=self.rect(16,y-17,178,42,"#293248" if selected else NAV,9)
            if selected:
                self.rect(16,y-9,3,25,"#A99AFF",2)
            color=WHITE if selected else "#9BA8C0"
            self.nav_icon(31,y-7,index,color)
            label=self.text(62,y+2,title,11,color,"bold" if selected else "normal")
            tag=f"nav{index}"
            for item in self.canvas.find_all()[first:]:
                self.canvas.addtag_withtag(tag,item)
            self.canvas.tag_bind(tag,"<Button-1>",lambda _e,i=index:self.navigate(i))
            self.canvas.tag_bind(tag,"<Enter>",lambda _e:self.canvas.configure(cursor="hand2"))
            self.canvas.tag_bind(tag,"<Leave>",lambda _e:self.canvas.configure(cursor=""))
            self.actions.append((area,lambda i=index:self.navigate(i)))
        self.rect(18,698,174,92,"#222D43",12)
        self.circle(35,719,3,"#63D5AE" if self.online else "#97A0B6")
        self.text(47,720,"IMPRIMANTE",8,"#B0BAD0","bold")
        self.text(33,746,"Epson XP-2200",12,WHITE,"bold")
        connection='USB · XP-2200' if self.snapshot and self.snapshot.transport=='USB' else 'Wi-Fi · '+self.host
        self.text(33,769,connection,8,"#9FAAC0")
        self.text(29,822,f"OpenInk  /  v{__version__}",8,"#8390AA")
        self.text(247,42,"ESPACE IMPRIMANTE   /   "+PAGES[self.page].upper(),8,MUTED,"bold")
        self.text(246,85,PAGES[self.page],27,INK,"bold")
        captions=("Un regard sur votre imprimante. Le contrôle sur votre encre.",
                  "Un suivi indépendant pour chacune de vos quatre couleurs.",
                  "Les impressions et les remplissages, au fil du temps.",
                  "Une connexion locale. Des estimations à votre mesure.",
                  "OpenFlow : un firmware, un suivi indépendant de l’encre.")
        self.text(247,117,captions[self.page],11,MUTED)
        from .firmware_ui import operation
        from .firmware import SAFE_PHASES
        firmware_state=operation(self)
        updating=bool(firmware_state and firmware_state['phase']not in SAFE_PHASES)
        self.circle(970,45,3,AMBER if updating else"#32B98B" if self.online else "#A1A9B9")
        self.text(982,45,"Mise à jour"if updating else"Connectée" if self.online else "Hors ligne",9,MUTED)
        from .print_ui import show as show_test_page
        self.button(782,28,164,36,'Page de test',None if updating else lambda:show_test_page(self))
        self.button(1100,28,143,36,"Actualisation…" if self.busy else "↻  Actualiser",self.refresh if not self.busy else None)
        if self.page==0:
            self.dashboard()
        elif self.page==1:
            self.cartridges_page()
        elif self.page==2:
            self.history_page()
        elif self.page==3:
            self.settings_page()
        else:
            from .firmware_ui import page
            page(self)
        self.text(247,832,"●  Vos données restent sur cet ordinateur.",8,MUTED)
        last=local_date(self.snapshot.observed_at,"%H:%M:%S") if self.snapshot else "—"
        footer=tr(self.notice or ("Dernière lecture  "+last))
        self.text(1242,832,footer[:112],8,"#C06C51" if self.notice else MUTED,anchor="e")

    def printer_drawing(self,x,y):
        self.circle(x+66,y+43,53,"#F0EEFE")
        self.rect(x+26,y-3,78,64,WHITE,5,LINE)
        for yy in (13,21,29):
            self.line(x+38,y+yy,x+88,y+yy,"#D5D9E6",2)
        self.rect(x+3,y+30,127,59,"#303A53",12)
        self.rect(x+10,y+37,112,20,"#48536F",7)
        self.circle(x+112,y+47,2,"#74DCC4")
        self.rect(x+26,y+62,80,26,"#1E283F",4)
        self.rect(x+38,y+72,58,28,WHITE,3,LINE)
        for k,c in enumerate((INKS["cyan"],INKS["magenta"],INKS["yellow"])):
            self.rect(x+46+k*14,y+83,10,4,c,1)

    def dashboard(self):
        self.rect(246,147,997,126,WHITE,15,LINE)
        self.text(271,169,"VOTRE IMPRIMANTE",8,MUTED,"bold")
        self.text(270,200,"Epson XP-2200",22,INK,"bold")
        state="Connexion en cours…" if self.busy and not self.snapshot else (self.snapshot.status if self.snapshot and self.online else "Connexion à établir")
        state_color=("#4C856F" if self.snapshot and self.snapshot.ready else AMBER) if self.online else MUTED
        self.circle(275,235,3,state_color)
        self.text(288,235,state,10,state_color)
        self.rect(674,185,180,45,"#F7F8FC",10)
        self.text(688,198,"CONNEXION LOCALE",7,MUTED,"bold")
        self.text(688,216,'USB' if self.snapshot and self.snapshot.transport=='USB' else self.host,11,INK,"bold")
        self.printer_drawing(1040,164)
        s=self.snapshot
        for x,title,value,color,small in (
                (246,"Pages imprimées",s.total_pages if s else None,PURPLE,"COMPTEUR IMPRIMANTE"),
                (586,"Pages couleur",s.color_pages if s else None,INKS["cyan"],"COULEUR"),
                (926,"Pages noir et blanc",s.mono_pages if s else None,INKS["black"],"MONOCHROME")):
            self.rect(x,290,317,100,WHITE,14,LINE)
            self.text(x+22,312,title,10,MUTED)
            self.text(x+21,353,number(value),28,INK,"bold")
            self.circle(x+267,343,19,"#F0EEFE" if color==PURPLE else "#F0F7FA")
            self.line(x+259,350,x+259,341,color,3)
            self.line(x+267,350,x+267,335,color,3)
            self.line(x+275,350,x+275,330,color,3)
        self.text(247,423,"Niveaux indicatifs",17,INK,"bold")
        self.button(1000,405,243,33,"+  Mettre à jour mes niveaux",self.reset_dialog,subtle=True)
        estimates=self.store.estimates(s) if s else {c:None for c in COLORS}
        for index,color in enumerate(COLORS):
            self.ink_card(246+index*255,451,232,181,color,estimates[color])
        self.safety_banner(246,645,997,45)
        self.activity_card(246,704,642,109)
        self.rect(906,704,337,109,"#EDE9FF",14)
        self.text(928,726,"AVANT LA RÉSERVE · ESTIMATION",8,"#8273BA","bold")
        colors=[estimates[c]["usable_pages"] for c in COLORS if estimates[c] is not None]
        remaining=min(colors) if len(colors)==4 else None
        self.text(927,761,number(remaining),29,"#6651CB","bold")
        self.text(1038,761,"pages en couleur",10,"#8175A9")
        action="Configurer mes cartouches  →" if remaining is None else "Ajuster mon estimation  →"
        target=self.text(928,796,action,9,"#7260BB","bold")
        self.canvas.tag_bind(target,"<Button-1>",lambda _e:self.reset_dialog())

    def ink_card(self,x,y,w,h,color,estimate):
        severity=estimate["state"] if estimate else "unknown"
        shade=RED if severity=="reserve" else AMBER if severity=="low" else MUTED
        border="#EDC8C8" if severity=="reserve" else "#ECD9B4" if severity=="low" else LINE
        self.rect(x,y,w,h,WHITE,14,border)
        self.circle(x+27,y+27,12,TINTS[color])
        self.circle(x+27,y+27,4,INKS[color])
        self.text(x+47,y+28,NAMES[color],12,INK,"bold")
        self.text(x+w-20,y+28,estimate["profile"] if estimate else "604",8,MUTED,anchor="e")
        if estimate:
            percent=estimate["percent"]
            self.text(x+22,y+77,"< 1" if 0<percent<1 else str(int(percent)),30,INK,"bold")
            self.text(x+86,y+84,"%",15,MUTED)
            self.text(x+22,y+149,"≈ "+number(estimate["usable_pages"])+" pages avant réserve",9,shade)
            state_label={"ok":"Estimation par pages", "low":"À surveiller", "reserve":"Remplir / remplacer"}[severity]
            self.text(x+22,y+100,state_label,9,shade,"bold" if severity!="ok" else "normal")
            self.text(x+22,y+168,f"Réserve de précaution : {estimate['reserve_percent']:g} %",7,MUTED)
        else:
            self.text(x+22,y+82,"—",30,"#C4CADA","bold")
            self.text(x+22,y+149,"Suivi à initialiser",10,MUTED)
            self.text(x+22,y+168,"Déclarer le niveau réellement estimé",7,MUTED)
        self.rect(x+22,y+115,w-44,9,TINTS[color],4)
        if estimate and estimate["percent"]>0:
            self.rect(x+22,y+115,max(4,(w-44)*estimate["percent"]/100),9,INKS[color],4)
            marker=x+22+(w-44)*estimate["reserve_percent"]/100
            self.line(marker,y+112,marker,y+127,shade)
        elif not estimate:
            self.circle(x+w-25,y+119,2,"#D7DCE8")
        self.canvas.tag_bind(self.text(x+w-23,y+82,"↗",13,"#C3C9D8",anchor="e"),"<Button-1>",lambda _e,c=color:self.reset_dialog(c))

    def safety_banner(self,x,y,w,h):
        alerts=self.store.alerts(self.snapshot) if self.snapshot else []
        critical=[a for a in alerts if a["state"]=="reserve"]
        active=critical or alerts
        fill="#FBECEC" if critical else "#FFF4DF" if alerts else "#ECEFFC"
        shade=RED if critical else AMBER if alerts else "#68658A"
        self.rect(x,y,w,h,fill,9)
        if active:
            title=("Réserve atteinte : " if critical else "Encre à surveiller : ")+", ".join(NAMES[a["color"]] for a in active)
            detail="Remplir ou remplacer avant de poursuivre." if critical else "Préparer de l’encre ou des cartouches de remplacement."
        else:
            title="Une marge pour anticiper le remplissage"
            detail="Les pages indiquées s’arrêtent à la réserve. Un reset sans ajout d’encre conserve l’estimation."
        if not self.online and self.snapshot:
            title="Dernière estimation · "+title
        self.text(x+15,y+14,title,9,shade,"bold")
        self.text(x+15,y+32,detail,8,shade)

    def activity_card(self,x,y,w,h):
        self.rect(x,y,w,h,WHITE,14,LINE)
        self.text(x+22,y+23,"Activité des 7 derniers jours",12,INK,"bold")
        self.circle(x+w-158,y+22,3,INKS["cyan"])
        self.text(x+w-148,y+22,"Couleur",8,MUTED)
        self.circle(x+w-73,y+22,3,INKS["black"])
        self.text(x+w-63,y+22,"N&B",8,MUTED)
        data=self.store.activity(self.snapshot.printer_id) if self.snapshot else []
        total=sum(v["color"]+v["mono"] for _,v in data)
        maximum=max([v["color"]+v["mono"] for _,v in data]+[1])
        left=x+28
        self.line(left,y+h-29,x+w-25,y+h-29)
        for i,(day,values) in enumerate(data):
            xx=left+30+i*(w-105)/6
            for dx,key,shade in ((-7,"color",INKS["cyan"]),(5,"mono",INKS["black"])):
                amount=values[key]
                if amount:
                    height=max(3,amount/maximum*(h-65))
                    self.rect(xx+dx,y+h-29-height,8,height,shade,3)
                else:
                    self.circle(xx+dx+4,y+h-31,1,"#DCE1EB")
            daylabel=datetime.fromisoformat(day).strftime("%d/%m")
            self.text(xx+3,y+h-15,daylabel,7,MUTED,anchor="center")
        if total==0:
            self.text(x+w/2,y+63,"Votre suivi commence ici.",10,"#A1A9B9",anchor="center")

    def cartridges_page(self):
        s=self.snapshot
        estimates=self.store.estimates(s) if s else {c:None for c in COLORS}
        for i,color in enumerate(COLORS):
            self.ink_card(246+i*255,157,232,187,color,estimates[color])
        self.rect(246,365,997,280,WHITE,14,LINE)
        self.text(270,394,"Diagnostic par cartouche",16,INK,"bold")
        self.text(270,422,"Valeurs signalées et état interprété, séparés de l’estimation locale.",10,MUTED)
        self.text(463,449,"CODE / NIVEAU EPSON",7,MUTED,"bold")
        self.text(648,449,"DIAGNOSTIC SIGNALÉ",7,MUTED,"bold")
        self.line(270,461,1219,461)
        diagnostics=cartridge_diagnostics(s) if s else {}
        for i,color in enumerate(COLORS):
            y=487+43*i
            e=estimates[color]
            self.circle(280,y,5,INKS[color])
            self.text(299,y,NAMES[color],11,INK,"bold")
            d=diagnostics.get(color,{})
            code=d.get('raw_code')
            value='—' if code is None else (f'{code} %' if 0<=code<=100 else f'Code {code}')
            self.text(463,y,value,10,MUTED)
            self.text(648,y,d.get('label','État indisponible'),9,AMBER if d.get('state')not in {'reported'} else MUTED,width=355)
            self.button(1038,y-16,177,32,"Ajuster le suivi",lambda c=color:self.reset_dialog(c))
        self.rect(246,662,997,135,"#EDE9FF",14)
        self.text(269,689,"V2 : contournement global, suivi par couleur",13,"#6753B4","bold")
        self.text(269,722,"OpenFlow s’installe une seule fois. Après un remplissage, mets à jour les niveaux concernés. Un flash sans ajout d’encre conserve l’estimation.",10,"#7D719D",width=700)
        self.button(1013,727,206,35,"Ouvrir OpenFlow",lambda:self.navigate(4))
        self.text(269,777,"V2 ne réécrit pas les puces. Le reset matériel sélectif reste distinct du suivi indicatif.",9,"#7D719D")

    def history_page(self):
        self.activity_card(246,154,997,190)
        self.rect(246,363,997,432,WHITE,14,LINE)
        self.text(269,393,"Journal de votre imprimante",16,INK,"bold")
        self.button(1055,377,163,33,"↓  Exporter le suivi",self.export)
        rows=self.store.events(self.snapshot.printer_id,5) if self.snapshot else []
        if not rows:
            self.text(745,560,"Votre historique apparaîtra après la première connexion.",12,MUTED,anchor="center")
        for i,row in enumerate(rows):
            y=451+i*66
            self.circle(279,y,5,PURPLE if "cartouche" in row["title"] else INKS["cyan"])
            if i<len(rows)-1:
                self.line(279,y+9,279,y+55,"#ECEAF5",2)
            self.text(301,y-1,row["title"],11,INK,"bold")
            self.text(301,y+23,row["detail"],9,MUTED)
            self.text(1215,y,local_date(row["at"]),9,MUTED,anchor="e")

    def entry(self,x,y,w,variable):
        widget=tk.Entry(self.canvas,textvariable=variable,relief="flat",bg=WHITE,fg=INK,
                        insertbackground=PURPLE,highlightthickness=1,highlightbackground=LINE,
                        highlightcolor=PURPLE,font=self.font(12,scaled=True))
        self.canvas.create_window(*self.point(x,y),anchor="nw",window=widget,width=w*self.scale*self.content_stretch,height=38*self.scale)
        self.widgets.append(widget)
        return widget

    def settings_page(self):
        self.rect(246,154,997,132,WHITE,14,LINE)
        self.text(270,183,"Connexion à l’imprimante",16,INK,"bold")
        self.text(270,214,"Adresse IPv4 de l’Epson sur votre réseau local",10,MUTED)
        self.entry(270,231,325,self.host_var)
        combo=ttk.Combobox(self.canvas,textvariable=self.transport_var,state='readonly',values=('Wi-Fi','USB','Auto'))
        self.canvas.create_window(*self.point(611,231),anchor='nw',window=combo,width=173*self.scale*self.content_stretch,height=38*self.scale)
        self.widgets.append(combo)
        self.button(807,231,204,38,"Enregistrer et connecter",self.save_connection)
        self.text(1030,214,"Langue de l’interface",9,MUTED)
        from .i18n import LANGUAGES
        language=ttk.Combobox(self.canvas,textvariable=self.language_var,state='readonly',values=tuple(LANGUAGES.values()))
        language.bind('<<ComboboxSelected>>',lambda _:self.save_language())
        self.canvas.create_window(*self.point(1030,231),anchor='nw',window=language,width=189*self.scale*self.content_stretch,height=38*self.scale)
        self.widgets.append(language)
        self.rect(246,303,997,139,WHITE,14,LINE)
        self.text(270,331,"Estimer selon votre usage",16,INK,"bold")
        combo=ttk.Combobox(self.canvas,textvariable=self.coverage_var,state="readonly",
                          values=("Documents courants","Documents chargés","Photos / aplats"))
        self.canvas.create_window(*self.point(270,352),anchor="nw",window=combo,width=514*self.scale*self.content_stretch,height=38*self.scale)
        self.widgets.append(combo)
        self.button(807,352,204,38,"Appliquer cet usage",self.save_coverage)
        self.text(270,418,"La consommation déjà enregistrée reste acquise. Les nouvelles pages utilisent le nouvel usage.",9,MUTED,width=930)
        self.rect(246,458,997,211,WHITE,14,LINE)
        self.text(270,486,"Prévoir le remplissage",16,INK,"bold")
        self.text(270,518,"Alerte à (%)",10,MUTED)
        self.text(545,518,"Réserve de précaution (%)",10,MUTED)
        self.entry(270,533,235,self.warning_var)
        self.entry(545,533,235,self.reserve_var)
        self.button(807,533,204,38,"Enregistrer les seuils",self.save_safety)
        self.text(270,596,"30 % : préparer le remplacement. 20 % : réserve atteinte. Seuils indicatifs et réglables.",9,MUTED)
        check=ttk.Checkbutton(self.canvas,text="Notifications sur le bureau, même fenêtre fermée",
                              variable=self.notifications_var,command=self.save_safety)
        self.canvas.create_window(*self.point(263,613),anchor="nw",window=check,width=690*self.scale*self.content_stretch,height=42*self.scale)
        self.widgets.append(check)
        reminder=ttk.Combobox(self.canvas,textvariable=self.reminder_var,state='readonly',values=('Rappel : aucun','Rappel : 1 h','Rappel : 4 h'))
        reminder.bind('<<ComboboxSelected>>',lambda _:self.save_safety())
        self.canvas.create_window(*self.point(975,618),anchor='nw',window=reminder,width=245*self.scale*self.content_stretch,height=32*self.scale)
        self.widgets.append(reminder)
        self.rect(246,686,997,110,WHITE,14,LINE)
        self.text(270,714,"Surveillance de session",15,INK,"bold")
        self.text(270,742,"Fermer la fenêtre conserve l’icône et le suivi dans le panneau.",9,MUTED,width=680)
        checkbox=ttk.Checkbutton(self.canvas,text='Démarrer en mode icône à la connexion',variable=self.startup_var,
                                 command=lambda:self.store.set_setting('autostart',self.startup_var.get()))
        self.canvas.create_window(*self.point(263,750),anchor='nw',window=checkbox,width=650*self.scale*self.content_stretch,height=42*self.scale)
        self.widgets.append(checkbox)
        self.button(997,728,222,37,"Quitter et arrêter le suivi",self.stop_and_quit)

    def navigate(self,page):
        self.page=page
        self.notice=""
        self.render()

    def save_language(self):
        from .i18n import LANGUAGES,set_language
        if self.dialog:
            self.language_var.set(LANGUAGES.get(self.store.setting('language','auto'),'Automatique'))
            self.notice='Ferme le dialogue avant de changer de langue.'
            focus_existing(self);self.render();return
        code=next((key for key,label in LANGUAGES.items()if label==self.language_var.get()),'auto')
        self.store.set_setting('language',code);set_language(code)
        self.root.title(f'OpenInk {__version__} · Epson XP-2200')
        self.notice='Langue enregistrée.'
        self.render()
        if self.managed:self.service_refresh(True)

    def save_connection(self):
        try:
            address=ipaddress.ip_address(self.host_var.get().strip())
            if address.version!=4 or address.is_unspecified or address.is_multicast:
                raise ValueError
        except ValueError:
            self.notice="Adresse IPv4 invalide. Exemple : 192.168.1.55"
            self.render()
            return
        self.host=str(address)
        self.store.set_setting("host",self.host)
        self.store.set_setting('transport',{'Wi-Fi':'network','USB':'usb','Auto':'auto'}[self.transport_var.get()])
        self.online=False
        self.notice="Adresse enregistrée."
        self.refresh()

    def save_coverage(self):
        self.store.set_setting("coverage",{"Documents courants":1.0,"Documents chargés":1.8,"Photos / aplats":5.0}[self.coverage_var.get()])
        self.notice="Usage enregistré pour les nouvelles pages. La consommation passée est conservée."
        self.render()

    def save_safety(self):
        try:
            self.store.set_safety(float(self.warning_var.get().replace(",",".")),
                                  float(self.reserve_var.get().replace(",",".")),self.notifications_var.get())
            self.store.set_setting('reminder_minutes',{'Rappel : aucun':0,'Rappel : 1 h':60,'Rappel : 4 h':240}[self.reminder_var.get()])
        except ValueError as exc:
            self.notice=str(exc)
        else:
            self.notice="Seuils enregistrés. Les jauges et les pages avant réserve sont actualisées."
            if self.snapshot and self.online:
                self.announce_alerts(self.store.check_alerts(self.snapshot))
        self.render()

    def announce_alerts(self, alerts):
        if not alerts or self.demo or self.managed or not self.store.setting("notifications", True):
            return
        title="OpenInk · "+("Réserve d’encre atteinte" if any(a["state"]=="reserve" for a in alerts) else "Encre à surveiller")
        detail="\n".join(a["title"]+" : "+a["detail"] for a in alerts)
        self.root.bell()
        threading.Thread(target=send_notification,args=(title,detail),daemon=True,name="OpenInk-notification").start()

    def reset_dialog(self,color=None):
        if not self.demo:
            from .firmware import require_monitoring_allowed
            try:require_monitoring_allowed()
            except ValueError as exc:
                self.notice=str(exc);self.render();return
        if focus_existing(self):return
        if not self.snapshot or not self.online:
            self.notice="Connectez l’imprimante avant d’initialiser le suivi."
            self.render()
            return
        age=(datetime.now().astimezone()-datetime.fromisoformat(self.snapshot.observed_at)).total_seconds()
        if age>120 and not self.demo:
            self.notice="Actualisez l’imprimante avant de réinitialiser le suivi."
            self.refresh()
            return
        win=register_dialog(self,tk.Toplevel(self.root),modal=True)
        win.title("Remplissage ou reset déclaré · OpenInk")
        win.configure(bg=WHITE)
        win.resizable(False,False)
        win.transient(self.root)
        scale=max(.8,self.scale)
        width=min(round(640*scale),self.monitor_geometry[0]-40)
        height=min(round(740*scale),self.monitor_geometry[1]-80)
        win.geometry(f"{width}x{height}+{self.root.winfo_rootx()+max(0,(self.root.winfo_width()-width)//2)}+{self.root.winfo_rooty()+max(0,(self.root.winfo_height()-height)//2)}")
        frame,actions=scrollable_content(win,WHITE)
        tk.Label(frame,text="Que s’est-il passé pour votre encre ?",font=self.font(18,"bold",scaled=True),fg=INK,bg=WHITE).pack(anchor="w")
        tk.Label(frame,text="Un reset seul n’ajoute pas d’encre. Déclarez l’opération réelle.",font=self.font(10,scaled=True),fg=MUTED,bg=WHITE,wraplength=round(550*scale)).pack(anchor="w",pady=(8,13))
        operations=("Remplissage / remplacement plein", "Cartouche déjà utilisée · niveau estimé", "Reset déjà effectué · aucun ajout d’encre")
        operation=tk.StringVar(value=operations[0])
        operation_box=ttk.Combobox(frame,textvariable=operation,state="readonly",values=operations)
        operation_box.pack(fill="x",pady=(0,12))
        checks=tk.Frame(frame,bg=WHITE)
        checks.pack(fill="x")
        selected={c:tk.BooleanVar(value=(c==color if color else False)) for c in COLORS}
        for i,c in enumerate(COLORS):
            ttk.Checkbutton(checks,text=NAMES[c],variable=selected[c]).grid(row=0,column=i,sticky="w",padx=(0,9))
        def label(text):
            tk.Label(frame,text=text,fg=INK,bg=WHITE,font=self.font(10,"bold",scaled=True)).pack(anchor="w",pady=(14,6))
        label("Format / rendement")
        current=self.store.estimates(self.snapshot).get(color) if color else None
        profile=tk.StringVar(value=current["profile"] if current else self.store.setting("cartridge_profile","604"))
        profile_box=ttk.Combobox(frame,textvariable=profile,state="readonly",values=("604","604XL","Personnalisé"),width=45)
        profile_box.pack(fill="x")
        label("Niveau de départ estimé (%)")
        start=tk.StringVar(value="100")
        start_box=tk.Spinbox(frame,from_=0,to=100,textvariable=start,font=self.font(12,scaled=True),bg=WHITE,fg=INK,relief="solid",borderwidth=1)
        start_box.pack(fill="x",ipady=5)
        label("Rendement personnalisé (pages, seulement si choisi ci-dessus)")
        capacity=tk.StringVar(value=str(current["capacity"]) if current else "130")
        cap_entry=tk.Entry(frame,textvariable=capacity,font=self.font(12,scaled=True),relief="solid",borderwidth=1,fg=INK)
        cap_entry.pack(fill="x",ipady=6)
        confirmed=tk.BooleanVar(value=False)
        confirmation=ttk.Checkbutton(frame,text="J’ai réellement rempli ou remplacé les cartouches sélectionnées.",variable=confirmed)
        confirmation.pack(anchor="w",pady=(13,0))
        note=tk.StringVar()
        tk.Label(actions,textvariable=note,fg=MUTED,bg=WHITE,font=self.font(9,scaled=True),wraplength=round(550*scale),justify="left").pack(side='top',anchor='w',pady=(0,10))
        button_row=tk.Frame(actions,bg=WHITE);button_row.pack(side='bottom',fill='x');actions=button_row
        def dismiss():
            self.dialog=None
            win.destroy()
        def save():
            try:
                if not self.demo:
                    from .firmware import require_monitoring_allowed
                    require_monitoring_allowed()
                if not self.online or not self.snapshot:
                    raise ValueError("Reconnectez l’imprimante avant d’enregistrer.")
                age=(datetime.now().astimezone()-datetime.fromisoformat(self.snapshot.observed_at)).total_seconds()
                if age>120 and not self.demo:
                    self.refresh()
                    raise ValueError("Lecture trop ancienne : actualisation en cours. Réessayez ensuite.")
                colors=[c for c in COLORS if selected[c].get()]
                if operation.get()==operations[2]:
                    self.store.record_chip_reset(self.snapshot,colors)
                else:
                    if operation.get()==operations[0] and not confirmed.get():
                        raise ValueError("Confirmez le remplissage réel, ou choisissez « Reset déjà effectué ».")
                    amount=float(start.get().replace(",","."))
                    custom=int(capacity.get()) if profile.get()=="Personnalisé" else None
                    self.store.calibrate(self.snapshot,colors,profile.get(),amount,custom)
                    self.store.set_setting("cartridge_profile",profile.get())
            except (ValueError,OverflowError) as exc:
                note.set(str(exc))
                return
            dismiss()
            self.notice=("Reset déclaré : niveaux estimés conservés." if operation.get()==operations[2]
                         else "Niveau de départ enregistré pour les couleurs choisies.")
            self.announce_alerts(self.store.check_alerts(self.snapshot))
            self.render()
        save_button=tk.Button(actions,text="Enregistrer le remplissage",command=save,bg=PURPLE,fg=WHITE,activebackground="#6852DC",activeforeground=WHITE,relief="flat",padx=18,pady=10,cursor="hand2")
        save_button.pack(side="right")
        tk.Button(actions,text="Annuler",command=dismiss,bg="#F0F2F7",fg=INK,relief="flat",padx=18,pady=10,cursor="hand2").pack(side="right",padx=12)
        win.protocol("WM_DELETE_WINDOW",dismiss)
        win.bind("<Escape>",lambda _e:dismiss())
        def changed(_event=None):
            reset=operation.get()==operations[2]
            refill=operation.get()==operations[0]
            profile_box.configure(state="disabled" if reset else "readonly")
            start_box.configure(state="disabled" if reset else "normal")
            cap_entry.configure(state="normal" if not reset and profile.get()=="Personnalisé" else "disabled")
            confirmation.configure(state="normal" if refill else "disabled")
            if _event is not None and getattr(_event,"widget",None)==operation_box:
                start.set("100" if refill else "")
                confirmed.set(False)
            if reset:
                note.set("Cette déclaration conserve le niveau local. Elle n’envoie aucun reset à l’imprimante et n’ajoute pas d’encre au suivi.")
            elif refill:
                note.set("100 % suppose une cartouche réellement pleine. Le suivi sera remis à jour uniquement pour les couleurs choisies.")
            else:
                note.set("Renseignez une estimation prudente de l’encre réellement présente. Les photos et nettoyages peuvent réduire l’autonomie.")
            save_button.configure(text="Conserver les niveaux" if reset else "Enregistrer le remplissage" if refill else "Enregistrer l’estimation")
        operation_box.bind("<<ComboboxSelected>>",changed)
        profile_box.bind("<<ComboboxSelected>>",changed)
        changed()

    def export(self):
        if not self.snapshot:
            self.notice="Connectez l’imprimante pour commencer le suivi."
            self.render()
            return
        path=filedialog.asksaveasfilename(parent=self.root,title=tr("Exporter le suivi OpenInk"),defaultextension=".json",initialfile="OpenInk-suivi.json",filetypes=[(tr("Rapport JSON"),"*.json")])
        if path:
            try:
                self.store.export(self.snapshot.printer_id,path)
                self.notice="Suivi exporté."
            except OSError as exc:
                self.notice="Export impossible : "+str(exc)
            self.render()

    def refresh(self):
        if self.closed or self.busy:
            return
        if self.managed:
            self.service_refresh(True)
            return
        if self.demo:
            self.online=True
            self.render()
            return
        self.busy=True
        self.notice=""
        self.render()
        host=self.host
        def worker():
            try:
                self.messages.put((host,read_printer(host),None))
            except (OSError,ValueError) as exc:
                self.messages.put((host,None,str(exc)))
            except Exception as exc:
                self.messages.put((host,None,"Lecture interrompue : "+str(exc)))
        threading.Thread(target=worker,daemon=True,name="OpenInk-printer-read").start()

    def poll(self):
        if self.closed:
            return
        try:
            while True:
                host,snapshot,error=self.messages.get_nowait()
                if host=='@agent':
                    self.busy=False;self.service_polling=False
                    previous=(self.snapshot.observed_at if self.snapshot else None,self.online,self.notice)
                    if error:
                        self.online=False
                        from .firmware_ui import operation
                        from .firmware import SAFE_PHASES
                        state=operation(self)
                        self.notice='Suivi en pause pendant l’opération firmware.'if state and state['phase']not in SAFE_PHASES else error
                    else:
                        self.online=bool(snapshot.get('online'))
                        self.notice=snapshot.get('error','')
                        self.snapshot=self.store.latest(snapshot.get('printer_id')) or self.snapshot
                    current=(self.snapshot.observed_at if self.snapshot else None,self.online,self.notice)
                    if current!=previous and self.page!=3 and not self.dialog:self.render()
                    continue
                self.busy=False
                if host!=self.host:
                    self.refresh()
                    continue
                if snapshot:
                    try:
                        alerts=self.store.observe(snapshot)
                        self.announce_alerts(alerts)
                    except Exception as exc:
                        self.notice="Historique non enregistré : "+str(exc)
                    self.snapshot,self.online=snapshot,True
                else:
                    self.online=False
                    self.notice="Imprimante injoignable. Vérifiez l’alimentation, le Wi-Fi et l’adresse."
                self.render()
        except queue.Empty:
            pass
        if self.window_lock and self.window_lock.path.exists():
            self.window_lock.path.unlink(missing_ok=True)
            self.root.deiconify();self.root.lift();self.root.focus_force()
        if self.window_lock and self.window_lock.quit_path.exists():
            self.window_lock.quit_path.unlink(missing_ok=True)
            self.close();return
        if self.managed and not self.service_polling and time.monotonic()-self.last_service_poll>=2:
            self.service_refresh(False)
        self.root.after(100,self.poll)

    def auto_refresh(self):
        if self.closed:
            return
        if not self.managed and self.page!=3 and not self.dialog:
            self.refresh()
        self.root.after(15000,self.auto_refresh)

    def close(self):
        self.closed=True
        for identifier in self.root.tk.call('after','info'):
            try:self.root.after_cancel(identifier)
            except tk.TclError:pass
        if self.window_lock:self.window_lock.close()
        self.store.close()
        self.root.destroy()

    def service_refresh(self,force):
        if self.service_polling:return
        self.service_polling=True;self.last_service_poll=time.monotonic()
        if force:self.busy=True
        def worker():
            from .service import request
            try:self.messages.put(('@agent',request(self.store.path,'refresh' if force else 'ping'),None))
            except (OSError,ValueError) as exc:self.messages.put(('@agent',None,'Agent indisponible : '+str(exc)))
        threading.Thread(target=worker,daemon=True,name='OpenInk-agent-status').start()

    def stop_and_quit(self):
        if self.managed:
            from .service import stop_desktop
            stop_desktop(self.store.path)
        self.close()

    def hardware_reset_dialog(self):
        if focus_existing(self):return
        win=register_dialog(self,tk.Toplevel(self.root))
        win.title('Reset matériel · compatibilité');win.configure(bg=WHITE)
        win.geometry('620x390');win.transient(self.root)
        frame=tk.Frame(win,bg=WHITE,padx=24,pady=20);frame.pack(fill='both',expand=True)
        tk.Label(frame,text='Quelle cartouche veux-tu réinitialiser ?',bg=WHITE,fg=INK,font=self.font(17,'bold')).pack(anchor='w')
        selected={c:tk.BooleanVar(value=False)for c in COLORS}
        row=tk.Frame(frame,bg=WHITE);row.pack(fill='x',pady=15)
        for i,c in enumerate(COLORS):ttk.Checkbutton(row,text=NAMES[c],variable=selected[c]).grid(row=0,column=i,padx=5)
        note=tk.StringVar(value=capability(self.snapshot)['reason'])
        tk.Label(frame,textvariable=note,bg=WHITE,fg=MUTED,font=self.font(11),wraplength=560,justify='left').pack(fill='x',pady=8)
        def verify():
            try:
                result=request_reset(self.snapshot,[c for c in COLORS if selected[c].get()])
                note.set('Non tenté : '+', '.join(NAMES[c] for c in result['selected'])+'\n'+result['reason'])
            except ValueError as exc:note.set(str(exc))
        def dismiss():self.dialog=None;win.destroy()
        tk.Button(frame,text='Vérifier la compatibilité',command=verify,bg=PURPLE,fg=WHITE,relief='flat',padx=16,pady=9).pack(side='left',anchor='s')
        tk.Button(frame,text='Fermer',command=dismiss,relief='flat',padx=16,pady=9).pack(side='right',anchor='s')
        win.protocol('WM_DELETE_WINDOW',dismiss);win.bind('<Escape>',lambda _:dismiss())
