import argparse
from dataclasses import replace
from datetime import datetime, timezone, timedelta
import json
import subprocess
import shutil
import sys
from pathlib import Path
import tkinter as tk

from .printer import read_printer, demo_snapshot, COLORS
from .store import Store
from .ui import Application


def main():
    parser=argparse.ArgumentParser(description="OpenInk — suivi local des cartouches Epson")
    parser.add_argument("--demo",action="store_true",help="Aperçu fictif, sans contacter l’imprimante")
    parser.add_argument("--database",type=Path,help="Emplacement de la base SQLite")
    parser.add_argument("--probe",action="store_true",help="Lecture réelle en ligne de commande")
    parser.add_argument("--host",help="Adresse IPv4 de l’imprimante")
    parser.add_argument("--transport",choices=("network","usb","auto"),help="Transport de diagnostic")
    parser.add_argument("--agent",action="store_true",help="Agent de surveillance de session")
    parser.add_argument("--background",action="store_true",help="Démarrer le suivi sans fenêtre")
    parser.add_argument("--stop-agent",action="store_true",help="Arrêter le suivi de session")
    parser.add_argument('--firmware-job',help='Exécuter une opération V2 explicitement préparée par l’interface')
    parser.add_argument('--verify-firmware',action='store_true',help='Vérifier seulement une opération V2 existante')
    parser.add_argument("--screenshot",type=Path,help="Capture de cette fenêtre pour vérification visuelle (Pillow facultatif)")
    parser.add_argument("--close-after",type=int,help="Fermer après N secondes pour les contrôles de l’interface")
    parser.add_argument('--view',choices=('overview','cartridges','history','settings','firmware'),default='overview',help='Vue affichée au lancement')
    args=parser.parse_args()
    if args.demo and (args.agent or args.background or args.stop_agent or args.probe or args.firmware_job or args.verify_firmware):
        parser.error("Le mode démo ne communique pas avec le matériel ni avec l’agent réel.")
    if args.verify_firmware and not args.firmware_job:parser.error('--verify-firmware exige une opération existante.')
    if args.firmware_job:
        if args.agent or args.background or args.stop_agent or args.probe:parser.error('Modes incompatibles avec une opération firmware.')
        from .flash_worker import run_job
        raise SystemExit(run_job(args.firmware_job,args.verify_firmware))
    if args.stop_agent:
        from .service import request
        from .store import default_database
        try:print(json.dumps(request(args.database or default_database(),'stop')))
        except OSError:print('La surveillance est déjà arrêtée.')
        return
    if args.agent:
        from .agent import run_agent
        from .store import default_database
        run_agent(args.database or default_database())
        return
    if args.probe:
        from .usb import read_connected
        print(json.dumps(read_connected(args.host or "192.168.1.55",args.transport or 'network').to_dict(),indent=2,ensure_ascii=False))
        return
    store=Store(":memory:" if args.demo else args.database)
    if args.host:
        store.set_setting("host",args.host)
    if args.transport:
        store.set_setting('transport',args.transport)
    window_lock=None
    if not args.demo:
        from .branding import migrate_legacy_shortcut
        migrate_legacy_shortcut()
        from .service import ensure_agent,WindowLock
        if args.background:
            if store.setting('autostart',True):ensure_agent(store.path)
            store.close()
            return
        try:window_lock=WindowLock(store.path)
        except RuntimeError:
            store.close()
            return
        try:ensure_agent(store.path)
        except RuntimeError as exc:print(str(exc),file=sys.stderr)
    if args.demo:
        now=datetime.now(timezone.utc)
        base=demo_snapshot()
        start=replace(base,color_pages=760,mono_pages=1240,observed_at=(now-timedelta(days=7)).isoformat())
        store.observe(start)
        for i,(color,mono) in enumerate(((765,1247),(778,1253),(788,1266),(792,1272),(810,1284),(817,1302),(824,1316))):
            store.observe(replace(base,color_pages=color,mono_pages=mono,observed_at=(now-timedelta(days=6-i)).isoformat()))
        for color,level in zip(COLORS,(78,29,16,61)):
            store.calibrate(base,[color],"604",level)
        store.check_alerts(base)
    root=tk.Tk(className='OpenInk')
    app=Application(root,store,args.demo,managed=not args.demo)
    app.window_lock=window_lock
    app.navigate(('overview','cartridges','history','settings','firmware').index(args.view))
    if args.screenshot:
        def capture():
            root.update_idletasks()
            args.screenshot.parent.mkdir(parents=True,exist_ok=True)
            # Canvas export also works on Wayland, where X11 screen grabs may
            # be unavailable. It captures the actually laid-out Tk canvas.
            ps=args.screenshot.with_suffix(".ps")
            from tkinter.font import Font
            mapping=[]
            for item in app.canvas.find_all():
                if app.canvas.type(item)=="text":
                    spec=app.canvas.itemcget(item,"font")
                    actual=Font(root,font=spec)
                    face="Helvetica-Bold" if actual.actual("weight")=="bold" else "Helvetica"
                    mapping.extend((spec,(face,actual.metrics("linespace")*0.8)))
            root.tk.call("array","set","inkora_ps_fonts",tuple(mapping))
            app.canvas.postscript(file=str(ps),colormode="color",x=0,y=0,
                width=app.canvas.winfo_width(),height=app.canvas.winfo_height(),
                pagewidth=str(app.canvas.winfo_width())+"p",pageheight=str(app.canvas.winfo_height())+"p",fontmap="inkora_ps_fonts")
            if shutil.which("gs"):
                subprocess.run(["gs","-q","-dSAFER","-dBATCH","-dNOPAUSE","-dEPSCrop",
                    "-sDEVICE=png16m","-r96","-dTextAlphaBits=4","-dGraphicsAlphaBits=4",
                    "-sOutputFile="+str(args.screenshot),str(ps)],check=True,timeout=20)
            else:
                print("Export Canvas :",ps,flush=True)
            print("Capture :",args.screenshot,flush=True)
        root.after(2200,capture)
    if args.close_after:
        root.after(args.close_after*1000,app.close)
    root.mainloop()


if __name__=="__main__":
    main()
