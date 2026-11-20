"""Source and frozen Windows launcher; keep all application paths independent of cwd."""
import logging
import os
from pathlib import Path
import sys

if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'commun'))


def main():
    from inkora.store import default_database
    folder = default_database().parent
    folder.mkdir(parents=True, exist_ok=True)
    # pythonw / PyInstaller GUI builds have no stdout or stderr.
    if sys.stdout is None:
        sys.stdout = (folder / 'launcher.log').open('a', encoding='utf-8')
    if sys.stderr is None:
        sys.stderr = sys.stdout
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (OSError, AttributeError):
            ctypes.windll.user32.SetProcessDPIAware()
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('OpenInk.Desktop')
        from inkora.__main__ import main as run
        run()
    except Exception:
        logging.basicConfig(filename=folder / 'launcher.log', encoding='utf-8', level=logging.INFO)
        logging.exception('OpenInk Windows')
        if not any(flag in sys.argv for flag in ('--agent', '--tray', '--background', '--firmware-job')):
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, 'OpenInk ne peut pas démarrer. Consulte le journal :\n' +
                                              str(folder / 'launcher.log'), 'OpenInk', 0x10)
        raise


if __name__ == '__main__':
    main()
