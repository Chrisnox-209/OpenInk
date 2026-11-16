"""OpenInk Linux entry point. Normal launches always use real monitoring."""
import argparse
import json
import sys
from pathlib import Path

from .widgets import tk
from .store import Store
from .ui import Application
from .i18n import tr,set_language,saved_language,LANGUAGES


def main():
    bootstrap=argparse.ArgumentParser(add_help=False)
    bootstrap.add_argument('--lang')
    bootstrap.add_argument('--database',type=Path)
    initial,_=bootstrap.parse_known_args()
    set_language(initial.lang or saved_language(initial.database))
    parser=argparse.ArgumentParser(description=tr('OpenInk — suivi local des cartouches Epson'),add_help=False)
    parser._optionals.title=tr('Options')
    def option(*args,**kw):
        if 'help'in kw:kw['help']=tr(kw['help'])
        return parser.add_argument(*args,**kw)
    option('-h','--help',action='help',help='Afficher cette aide et quitter')
    option('--lang',choices=tuple(LANGUAGES),help='Langue de l’interface')
    option('--database',type=Path,help='Emplacement de la base SQLite')
    option('--probe',action='store_true',help='Lecture réelle en ligne de commande')
    option('--host',help='Adresse IPv4 de l’imprimante')
    option('--transport',choices=('network','usb','auto'),help='Transport de diagnostic')
    option('--agent',action='store_true',help='Agent de surveillance de session')
    option('--background',action='store_true',help='Démarrer le suivi sans fenêtre')
    option('--tray',action='store_true',help='Icône du panneau, sans fenêtre')
    option('--stop-agent',action='store_true',help='Arrêter le suivi de session')
    option('--firmware-job',help='Exécuter une opération V2 explicitement préparée par l’interface')
    option('--verify-firmware',action='store_true',help='Vérifier seulement une opération V2 existante')
    args=parser.parse_args()
    if args.verify_firmware and not args.firmware_job:parser.error(tr('--verify-firmware exige une opération existante.'))
    if args.firmware_job:
        if args.agent or args.background or args.tray or args.stop_agent or args.probe:parser.error(tr('Modes incompatibles avec une opération firmware.'))
        from .flash_worker import run_job
        raise SystemExit(run_job(args.firmware_job,args.verify_firmware))
    if args.stop_agent:
        from .service import stop_desktop
        from .store import default_database
        stop_desktop(args.database or default_database());return
    if args.tray:
        from .tray import run_tray
        from .store import default_database
        run_tray(args.database or default_database());return
    if args.agent:
        from .agent import run_agent
        from .store import default_database
        run_agent(args.database or default_database());return
    if args.probe:
        from .usb import read_connected
        print(json.dumps(read_connected(args.host or '192.168.1.55',args.transport or 'network').to_dict(),indent=2,ensure_ascii=False));return
    store=Store(args.database)
    if args.lang:store.set_setting('language',args.lang)
    if args.host:store.set_setting('host',args.host)
    if args.transport:store.set_setting('transport',args.transport)
    from .branding import migrate_legacy_shortcut
    from .service import ensure_agent,ensure_tray,WindowLock
    migrate_legacy_shortcut()
    if args.background:
        if store.setting('autostart',True):ensure_agent(store.path);ensure_tray(store.path)
        store.close();return
    try:window_lock=WindowLock(store.path)
    except RuntimeError:store.close();return
    try:ensure_agent(store.path)
    except RuntimeError as exc:print(tr(str(exc)),file=sys.stderr)
    if not ensure_tray(store.path):print(tr('Icône du panneau indisponible ; le suivi reste actif.'),file=sys.stderr)
    root=tk.Tk(className='OpenInk')
    app=Application(root,store,managed=True);app.window_lock=window_lock
    root.mainloop()


if __name__=='__main__':main()
