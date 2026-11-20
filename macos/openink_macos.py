"""Source and frozen macOS launcher. No hardware access at import time."""
import logging
from pathlib import Path
import sys

if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'commun'))


def main():
    if sys.platform != 'darwin':
        raise SystemExit('Ce lanceur exige macOS.')
    from inkora.store import default_database
    folder = default_database().parent
    folder.mkdir(parents=True, exist_ok=True)
    if sys.stdout is None:
        sys.stdout = (folder / 'launcher.log').open('a', encoding='utf-8')
    if sys.stderr is None:
        sys.stderr = sys.stdout
    try:
        hidden = any(flag in sys.argv for flag in ('--agent', '--tray', '--background',
                     '--stop-agent', '--firmware-job', '--probe'))
        if hidden:
            from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
            NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)
        from inkora.__main__ import main as run
        run()
    except Exception:
        logging.basicConfig(filename=folder / 'launcher.log', encoding='utf-8', level=logging.INFO)
        logging.exception('OpenInk macOS')
        raise


if __name__ == '__main__':
    main()
