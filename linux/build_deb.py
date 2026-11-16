#!/usr/bin/env python3
"""Build an Ubuntu package in a temporary tree. Does not install or access USB."""
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile

VERSION='1.7.0'


def write(root,path,text,mode=0o644):
    target=root/path;target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(text,encoding='utf-8');target.chmod(mode)


def main():
    app=Path(__file__).resolve().parents[1]
    import sys
    sys.path.insert(0,str(app/'commun'))
    from inkora.firmware import load_assets
    load_assets()  # Offline integrity check only; never opens USB.
    output=app/'linux/dist';output.mkdir(exist_ok=True)
    target=output/f'openink_{VERSION}_amd64.deb'
    with tempfile.TemporaryDirectory(prefix='inkora-deb-')as temporary:
        root=Path(temporary)/'package';root.mkdir()
        shutil.copytree(app/'commun/inkora',root/'usr/lib/openink/inkora',
                        ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        launcher="#!/usr/bin/python3\nimport sys\nsys.path.insert(0, '/usr/lib/openink')\nfrom inkora.__main__ import main\nmain()\n"
        write(root,'usr/bin/openink',launcher,0o755)
        write(root,'usr/bin/inkora',launcher,0o755)
        write(root,'usr/share/applications/openink.desktop',"""[Desktop Entry]
Type=Application
Name=OpenInk
Comment=Diagnostic Epson et suivi indicatif de l'encre
Comment[en]=Epson diagnostics and estimated ink monitoring
Comment[es]=Diagnóstico Epson y seguimiento estimado de tinta
Exec=openink
Icon=openink
Terminal=false
Categories=Utility;
StartupNotify=true
StartupWMClass=OpenInk
Actions=StopMonitoring;

[Desktop Action StopMonitoring]
Name=Arrêter la surveillance
Name[en]=Stop monitoring
Name[es]=Detener el seguimiento
Exec=openink --stop-agent
""")
        write(root,'etc/xdg/autostart/openink-agent.desktop',"""[Desktop Entry]
Type=Application
Name=OpenInk - icône et surveillance
Name[en]=OpenInk - tray and monitoring
Name[es]=OpenInk - icono y seguimiento
Comment=Démarrer dans le panneau, sans fenêtre, avec suivi des impressions
Comment[en]=Start in the panel without a window and monitor printing
Comment[es]=Iniciar en el panel sin ventana y seguir las impresiones
Exec=openink --background
Icon=openink
Terminal=false
NoDisplay=true
X-GNOME-Autostart-enabled=true
""")
        icon=root/'usr/share/icons/hicolor/scalable/apps/openink.svg';icon.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(app/'linux/openink.svg',icon)
        for size in (64,128,256,512):
            icon=root/f'usr/share/icons/hicolor/{size}x{size}/apps/openink.png'
            icon.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(app/f'commun/inkora/assets/openink-{size}.png',icon)
        write(root,'usr/lib/udev/rules.d/70-openink-epson.rules',
              '# Access for the active local user, normal XP-2200 only.\nSUBSYSTEM=="usb", ATTR{idVendor}=="04b8", ATTR{idProduct}=="11b1", TAG+="uaccess"\n')
        docs=root/'usr/share/doc/openink';docs.mkdir(parents=True,exist_ok=True)
        for source in [*sorted(app.glob('README*.md')),app/'THIRD_PARTY_NOTICES.md',app/'CONTRIBUTING.md',*sorted(p for p in (app/'docs').rglob('*') if p.is_file())]:
            if source.exists():
                destination=docs/source.relative_to(app)
                destination.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(source,destination)
        write(root,'DEBIAN/control',f'''Package: openink
Version: {VERSION}
Section: utils
Priority: optional
Architecture: amd64
Maintainer: Projet OpenInk <openink@localhost>
Provides: inkora (= {VERSION})
Conflicts: inkora
Replaces: inkora
Depends: python3 (>= 3.10), python3-tk, python3-pil, python3-gi, gir1.2-glib-2.0, libusb-1.0-0, cups-client, systemd, xdg-utils, x11-xserver-utils
Description: OpenFlow et suivi indicatif de l'encre pour Epson XP-2200
 Application graphique avec agent de session et notifications natives.
 Assistant OpenFlow USB pour la XP-2200 IU05P2.
 Installation globale et suivi par couleur ; aucune écriture de puce.
 Logo CMJN, page de test et contrôle ciblé des zones modifiées.
''')
        maintenance='''#!/bin/sh
set -e
if command -v udevadm >/dev/null 2>&1; then udevadm control --reload-rules 2>/dev/null || true; fi
if command -v update-desktop-database >/dev/null 2>&1; then update-desktop-database /usr/share/applications 2>/dev/null || true; fi
exit 0
'''
        write(root,'DEBIAN/postinst',maintenance,0o755)
        write(root,'DEBIAN/postrm',maintenance,0o755)
        for path in root.rglob('*'):
            if path.is_dir():path.chmod(0o755)
            elif path.relative_to(root).as_posix()not in {'usr/bin/openink','usr/bin/inkora','DEBIAN/postinst','DEBIAN/postrm'}:path.chmod(0o644)
        write(root,'DEBIAN/md5sums',''.join(hashlib.md5(p.read_bytes()).hexdigest()+'  '+p.relative_to(root).as_posix()+'\n'
              for p in sorted(root.rglob('*'))if p.is_file()and'DEBIAN'not in p.relative_to(root).parts))
        subprocess.run(['desktop-file-validate',str(root/'usr/share/applications/openink.desktop'),str(root/'etc/xdg/autostart/openink-agent.desktop')],check=True)
        subprocess.run(['dpkg-deb','--root-owner-group','--build',str(root),str(target)],check=True)
    digest=hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix('.deb.sha256').write_text(digest+'  '+target.name+'\n')
    print(target);print('SHA-256',digest)


if __name__=='__main__':main()
