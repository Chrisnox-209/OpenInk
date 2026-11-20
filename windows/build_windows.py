"""Build a portable x64 Windows application on Windows (or isolated Wine)."""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = '1.7.0-windows-beta1'


def main():
    if os.name != 'nt':
        raise SystemExit('Construire avec Python Windows 64 bits : python windows/build_windows.py')
    if sys.maxsize <= 2**32:
        raise SystemExit('Python 64 bits requis.')
    sys.path.insert(0, str(ROOT / 'commun'))
    from inkora.firmware import load_assets
    load_assets()  # Verify the pinned firmware without opening any device.
    assets = ROOT / 'commun/inkora/assets'
    for filename in ('test-page.png', 'test-page.en.png', 'test-page.es.png', 'openink.ico'):
        if not (assets / filename).is_file():
            raise SystemExit('Ressource manquante : ' + filename)
    dist = ROOT / 'windows/dist'
    subprocess.run([
        sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--windowed',
        '--name', 'OpenInk', '--icon', str(assets / 'openink.ico'),
        '--distpath', str(dist), '--workpath', str(ROOT / 'windows/build'),
        '--specpath', str(ROOT / 'windows/build'),
        '--paths', str(ROOT / 'commun'),
        '--paths', str(ROOT / 'commun/inkora/_vendor'),
        '--add-data', str(assets) + os.pathsep + 'inkora/assets',
        '--add-data', str(ROOT / 'commun/inkora/locales') + os.pathsep + 'inkora/locales',
        '--add-data', str(ROOT / 'commun/inkora/firmware_assets') + os.pathsep + 'inkora/firmware_assets',
        '--collect-submodules', 'epson_usb', '--hidden-import', 'pystray._win32',
        '--hidden-import', 'win32api', '--hidden-import', 'win32gui',
        '--hidden-import', 'win32print', '--hidden-import', 'PIL.ImageWin',
        str(ROOT / 'windows/openink_windows.py')], check=True)
    folder = dist / 'OpenInk'
    shutil.copy2(ROOT / 'windows/README.md', folder / 'LIRE-MOI.txt')
    shutil.copy2(ROOT / 'DISCLAIMER.md', folder / 'DISCLAIMER.md')
    shutil.copy2(ROOT / 'THIRD_PARTY_NOTICES.md', folder / 'THIRD_PARTY_NOTICES.md')
    vendor_license = ROOT / 'commun/inkora/_vendor/epson_usb/LICENSE'
    if vendor_license.is_file():
        shutil.copy2(vendor_license, folder / 'LICENSE-epson-usb.txt')
    (folder / 'Arreter-OpenInk.cmd').write_text('@echo off\r\n"%~dp0OpenInk.exe" --stop-agent\r\n', encoding='ascii')
    licenses=folder/'licenses';licenses.mkdir(exist_ok=True)
    python_license=Path(sys.base_prefix)/'LICENSE.txt'
    if python_license.is_file():shutil.copy2(python_license,licenses/'Python.txt')
    shutil.copy2(ROOT/'docs/licenses/Lato-copyright',licenses/'Lato.txt')
    for package in ('Pillow','pystray','pywin32','six','PyInstaller'):
        distribution=importlib.metadata.distribution(package)
        for resource in distribution.files or ():
            if any(part.lower().startswith(('license','copying')) for part in resource.parts):
                source=Path(distribution.locate_file(resource))
                if source.is_file():
                    destination=licenses/package/str(resource).replace('..','_')
                    destination.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copy2(source,destination)
    # Supply the unmodified LGPL Python library source along with its licence.
    distribution=importlib.metadata.distribution('pystray')
    for resource in distribution.files or ():
        if resource.parts[0]=='pystray' and resource.suffix=='.py':
            source=Path(distribution.locate_file(resource))
            destination=folder/'third_party_sources'/str(resource)
            destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(source,destination)
    files = sorted(p for p in folder.rglob('*') if p.is_file())
    metadata = {
        'application': 'OpenInk', 'version': VERSION, 'platform': 'Windows 10/11 x64',
        'python': sys.version, 'hardware_validation': False,
        'sha256': {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
    (folder / 'BUILD_INFO.json').write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
    target = dist / ('OpenInk-' + VERSION + '-x64.zip')
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(folder.rglob('*')):
            if path.is_file():
                archive.write(path, 'OpenInk/' + path.relative_to(folder).as_posix())
    checksum = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix('.zip.sha256').write_text(checksum + '  ' + target.name + '\n', encoding='ascii')
    print(target)
    print('SHA-256:', checksum)


if __name__ == '__main__':
    main()
