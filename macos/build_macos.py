"""Build and ad-hoc-sign a standalone macOS .app on the Mac itself."""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
VERSION = '1.7.0-macos-beta1'


def collect_notices(folder):
    licenses = folder / 'licenses'
    licenses.mkdir(parents=True, exist_ok=True)
    python_license = Path(sys.base_prefix) / 'LICENSE.txt'
    if python_license.is_file():
        shutil.copy2(python_license, licenses / 'Python.txt')
    shutil.copy2(ROOT / 'docs/licenses/Lato-copyright', licenses / 'Lato.txt')
    shutil.copy2(ROOT / 'commun/inkora/_vendor/epson_usb/LICENSE', licenses / 'epson-usb.txt')
    for package in ('Pillow', 'pystray', 'pyobjc-core', 'pyobjc-framework-Cocoa', 'pyobjc-framework-Quartz',
                    'libusb-package', 'six', 'PyInstaller'):
        distribution = importlib.metadata.distribution(package)
        for resource in distribution.files or ():
            if any(part.lower().startswith(('license', 'copying')) for part in resource.parts):
                source = Path(distribution.locate_file(resource))
                if source.is_file():
                    destination = licenses / package / str(resource).replace('..', '_')
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)
            if resource.parts[0] == 'pystray' and resource.suffix == '.py':
                destination = folder / 'third_party_sources' / str(resource)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(distribution.locate_file(resource), destination)


def main():
    if sys.platform != 'darwin':
        raise SystemExit('La construction de OpenInk.app exige un Mac.')
    if platform.machine() not in ('arm64', 'x86_64'):
        raise SystemExit('Architecture macOS non prise en charge.')
    for tool in ('lipo', 'install_name_tool'):
        result = subprocess.run(['/usr/bin/xcrun', '--find', tool], capture_output=True, text=True)
        if result.returncode:
            raise SystemExit('Installe les outils en ligne de commande Apple avec xcode-select --install, puis relance la construction.')
    sys.path.insert(0, str(ROOT / 'commun'))
    from inkora.firmware import load_assets, V2_SHA
    load_assets()
    dist = ROOT / 'macos/dist'
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
                    '--distpath', str(dist), '--workpath', str(ROOT / 'macos/build'),
                    str(ROOT / 'macos/OpenInk.spec')], check=True)
    app = dist / 'OpenInk.app'
    resources = app / 'Contents/Resources'
    shutil.copy2(ROOT / 'macos/README.md', resources / 'LIRE-MOI.txt')
    shutil.copy2(ROOT / 'DISCLAIMER.md', resources / 'DISCLAIMER.md')
    shutil.copy2(ROOT / 'THIRD_PARTY_NOTICES.md', resources / 'THIRD_PARTY_NOTICES.md')
    collect_notices(resources)
    metadata = {'application': 'OpenInk', 'version': VERSION,
                'platform': 'macOS', 'architecture': platform.machine(),
                'python': sys.version, 'firmware_sha256': V2_SHA,
                'hardware_validation': False,
                'dependencies': {p: importlib.metadata.version(p) for p in
                                 ('Pillow', 'pystray', 'pyobjc-core', 'pyobjc-framework-Cocoa', 'pyobjc-framework-Quartz',
                                  'libusb-package', 'PyInstaller')}}
    (resources / 'BUILD_INFO.json').write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
    # Seal the final resources too. This is a local ad-hoc signature, not Apple notarization.
    subprocess.run(['/usr/bin/codesign', '--force', '--sign', '-', str(app)], check=True)
    subprocess.run(['/usr/bin/codesign', '--verify', '--deep', '--strict', str(app)], check=True)
    target = dist / ('OpenInk-' + VERSION + '-' + platform.machine() + '.zip')
    subprocess.run(['/usr/bin/ditto', '-c', '-k', '--sequesterRsrc', '--keepParent',
                    str(app), str(target)], check=True)
    checksum = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix('.zip.sha256').write_text(checksum + '  ' + target.name + '\n', encoding='ascii')
    print('Application :', app)
    print('Archive :', target)
    print('SHA-256 :', checksum)


if __name__ == '__main__':
    main()
