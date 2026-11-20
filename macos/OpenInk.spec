# Native macOS build, one architecture per build host.
from pathlib import Path
import platform
import libusb_package
from PyInstaller.utils.hooks import collect_submodules

root = Path(SPECPATH).parent
library = libusb_package.get_library_path()
if not library:
    raise SystemExit('Le paquet libusb-package ne contient aucune bibliothèque native.')

a = Analysis(
    [str(root / 'macos/openink_macos.py')],
    pathex=[str(root / 'commun'), str(root / 'commun/inkora/_vendor')],
    binaries=[(str(library), 'libusb_package')],
    datas=[(str(root / 'commun/inkora/assets'), 'inkora/assets'),
           (str(root / 'commun/inkora/locales'), 'inkora/locales'),
           (str(root / 'commun/inkora/firmware_assets'), 'inkora/firmware_assets')],
    hiddenimports=collect_submodules('epson_usb') + ['pystray._darwin', 'AppKit', 'Foundation',
                                                   'Quartz', 'objc', 'libusb_package'],
    excludes=['win32api', 'win32gui', 'win32print', 'gi', 'pystray._win32',
              'pystray._appindicator', 'pystray._gtk', 'pystray._xorg'],
    noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='OpenInk',
          debug=False, strip=False, upx=False, console=False,
          target_arch=platform.machine(), codesign_identity=None)
collection = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='OpenInk')
app = BUNDLE(collection, name='OpenInk.app', icon=str(root / 'commun/inkora/assets/openink.icns'),
             bundle_identifier='io.github.Chrisnox209.OpenInk', version='1.7.0',
             info_plist={'CFBundleShortVersionString': '1.7.0', 'CFBundleVersion': '1701',
                         'LSMinimumSystemVersion': '11.0', 'NSHighResolutionCapable': True,
                         'NSRequiresAquaSystemAppearance': False})
