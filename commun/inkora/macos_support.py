"""macOS integration that can be imported without loading Cocoa or any printer."""
import os
from pathlib import Path
import plistlib
import subprocess
import sys

AUTOSTART_LABEL = 'io.github.Chrisnox209.OpenInk'
NOTIFICATION_SCRIPT = '''on run argv
    display notification (item 2 of argv) with title (item 1 of argv)
end run'''


def runtime_paths(database, *, root=None):
    import hashlib
    # sockaddr_un on macOS is limited to 104 bytes, even for long user names.
    root = Path(root) if root is not None else Path('/tmp') / ('openink-' + str(os.getuid()))
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if root.is_symlink() or root.stat().st_uid != os.getuid():
        raise RuntimeError('Le répertoire de session OpenInk doit appartenir à cet utilisateur.')
    root.chmod(0o700)
    key = hashlib.sha256(str(Path(database).resolve()).encode()).hexdigest()[:12]
    return root / (key + '.sock'), root / (key + '.lock')


def set_autostart(database, enabled):
    from .service import launch_command, launch_environment
    folder = Path.home() / 'Library/LaunchAgents'
    path = folder / (AUTOSTART_LABEL + '.plist')
    if not enabled:
        path.unlink(missing_ok=True)
        return
    folder.mkdir(parents=True, exist_ok=True)
    value = {'Label': AUTOSTART_LABEL,
             'ProgramArguments': launch_command(database, '--background'),
             'RunAtLoad': True, 'ProcessType': 'Background',
             'EnvironmentVariables': {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin'}}
    if not getattr(sys, 'frozen', False):
        value['EnvironmentVariables']['PYTHONPATH'] = launch_environment()['PYTHONPATH']
    temporary = path.with_suffix('.plist.tmp')
    with temporary.open('wb') as stream:
        temporary.chmod(0o600)
        plistlib.dump(value, stream)
    os.replace(temporary, path)


def configure_libusb(required=False):
    if os.environ.get('EPSON_USB_LIBUSB'):
        return os.environ['EPSON_USB_LIBUSB']
    try:
        import libusb_package
        library = libusb_package.get_library_path()
        if library and Path(library).is_file():
            os.environ['EPSON_USB_LIBUSB'] = str(library)
            return str(library)
    except ImportError:
        pass
    if required:
        raise ValueError('La bibliothèque USB macOS est absente. Réinstalle les dépendances du kit OpenInk.')
    return None


def active_monitor(root):
    try:
        from AppKit import NSScreen
        screens = list(NSScreen.screens())
        primary = screens[0].frame()
        top = primary.origin.y + primary.size.height
        frames = []
        for screen in screens:
            rect = screen.visibleFrame()
            frames.append((round(rect.size.width), round(rect.size.height),
                           round(rect.origin.x), round(top - rect.origin.y - rect.size.height)))
        px, py = root.winfo_pointerxy()
        return next((rect for rect in frames if rect[2] <= px < rect[2] + rect[0]
                     and rect[3] <= py < rect[3] + rect[1]), frames[0])
    except (ImportError, AttributeError, IndexError):
        return root.winfo_screenwidth(), root.winfo_screenheight(), 0, 0


class DesktopNotifications:
    def __init__(self, database):
        self.database = database

    def poll(self):
        pass

    def send(self, title, detail, critical=False):
        from .i18n import tr
        # Arguments stay separate from the AppleScript source, including quotes
        # and newlines. No shell or interpolated AppleScript is used.
        result = subprocess.run(['/usr/bin/osascript', '-e', NOTIFICATION_SCRIPT,
                                 '--', tr(title), tr(detail)],
                                capture_output=True, text=True, timeout=10)
        if result.returncode:
            raise OSError('Notification macOS refusée : ' + result.stderr.strip())
        return 'macOS-accepted'
