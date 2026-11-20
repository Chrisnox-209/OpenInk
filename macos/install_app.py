"""Install a freshly built .app for the current user; preserve any existing app."""
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    if sys.platform != 'darwin':
        raise SystemExit('Installation sur macOS uniquement.')
    source = Path(__file__).resolve().parent / 'dist/OpenInk.app'
    if not (source / 'Contents/MacOS/OpenInk').is_file():
        raise SystemExit('Construis OpenInk.app avant de l’installer.')
    target = Path.home() / 'Applications/OpenInk.app'
    if target.exists():
        print('Une application OpenInk existe déjà. La nouvelle application est prête ici :', source)
        subprocess.run(['/usr/bin/open', '-R', str(source)], check=True)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, symlinks=True)
    print('Application installée :', target)
    subprocess.run(['/usr/bin/open', str(target)], check=True)


if __name__ == '__main__':
    main()
