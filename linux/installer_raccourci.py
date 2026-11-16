#!/usr/bin/env python3
"""Install a user-only launcher pointing at this folder. No sudo required."""
from pathlib import Path
import os


def main():
    folder=Path(__file__).resolve().parent
    launcher=folder/"Lancer-OpenInk.sh"
    launcher.chmod(launcher.stat().st_mode|0o111)
    applications=Path(os.environ.get("XDG_DATA_HOME",str(Path.home()/".local/share")))/"applications"
    applications.mkdir(parents=True,exist_ok=True)
    def quoted(value):
        return '"'+str(value).replace('\\','\\\\').replace('"','\\"').replace('%','%%').replace('`','\\`').replace('$','\\$')+'"'
    entry=applications/"openink.desktop"
    entry.write_text("[Desktop Entry]\nType=Application\nName=OpenInk\nComment=Suivi des cartouches Epson\n"
        "Comment[en]=Epson cartridge monitoring\nComment[es]=Seguimiento de cartuchos Epson\nExec="+quoted(launcher)+
        "\nIcon="+str(folder/"openink.svg")+"\nTerminal=false\nCategories=Utility;\nStartupNotify=true\n",encoding="utf-8")
    print("Raccourci installé :",entry)


if __name__=="__main__":main()
