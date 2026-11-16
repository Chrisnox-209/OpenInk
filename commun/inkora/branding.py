"""Product identity; legacy module/data paths remain for upgrade compatibility."""
from pathlib import Path
import os
import shutil
import subprocess
import re

APP_NAME='OpenInk'
FIRMWARE_NAME='OpenFlow'
ASSETS=Path(__file__).parent/'assets'
TEST_PAGE=ASSETS/'test-page.pdf'
RISK_NOTICE_VERSION='openink-flash-2026-11-v1'
RISK_NOTICE=('Flasher un appareil comporte des risques, dont un dysfonctionnement ou un blocage. '
             'OpenInk est fourni sans garantie de réussite. Les auteurs déclinent toute responsabilité '
             'pour les dommages liés au flash, dans les limites permises par la loi.')


def initial_geometry(screen_width,screen_height):
    """At least 45% of screen area, within usable screen margins."""
    width=max(320,int(screen_width));height=max(240,int(screen_height))
    available_w=max(300,width-32);available_h=max(210,height-70)
    minimum_w=min(available_w,max(1080,round(width*.68)))
    minimum_h=min(available_h,max(730,round(height*.68)))
    start_w=min(available_w,max(1280,round(width*.76),minimum_w))
    start_h=min(available_h,max(850,round(height*.76),minimum_h))
    return start_w,start_h,minimum_w,minimum_h


def active_monitor(root):
    """Tk/XWayland reports the combined desktop; choose the pointer's monitor."""
    try:
        result=subprocess.run(['xrandr','--listmonitors'],capture_output=True,text=True,timeout=2)
        monitors=[]
        for line in result.stdout.splitlines()[1:]:
            geometry=re.search(r'(\d+)/\d+x(\d+)/\d+([+-]\d+)([+-]\d+)',line)
            if geometry:
                width,height,x,y=map(int,geometry.groups());monitors.append((width,height,x,y,'*'in line.split()[1]))
        px,py=root.winfo_pointerxy()
        chosen=next((m for m in monitors if m[2]<=px<m[2]+m[0]and m[3]<=py<m[3]+m[1]),None)
        chosen=chosen or next((m for m in monitors if m[4]),None)
        if chosen:return chosen[:4]
    except (OSError,subprocess.TimeoutExpired,ValueError,IndexError):pass
    return root.winfo_screenwidth(),root.winfo_screenheight(),0,0


def migrate_legacy_shortcut(applications=None,installed_entry=Path('/usr/share/applications/openink.desktop')):
    """Update only the known source-launcher entry; keep a reversible backup."""
    root=Path(applications)if applications else Path(os.environ.get('XDG_DATA_HOME',str(Path.home()/'.local/share')))/'applications'
    legacy=root/'inkora.desktop'
    if not legacy.is_file():return False
    data=legacy.read_text()
    if 'Lancer-Inkora.sh'not in data or 'Comment=Suivi des cartouches Epson'not in data:return False
    backup=root/'inkora.desktop.before-openink'
    if not backup.exists():shutil.copy2(legacy,backup)
    if Path(installed_entry).is_file():
        legacy.write_text('[Desktop Entry]\nType=Application\nName=OpenInk\nHidden=true\n')
    else:
        data=data.replace('Name=Inkora\n','Name=OpenInk\n')
        lines=[('Icon='+str(ASSETS/'openink-logo.svg'))if line.startswith('Icon=')else line for line in data.splitlines()]
        legacy.write_text('\n'.join(lines)+'\n')
    return True
