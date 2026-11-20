"""Exercise all views, themes and languages with isolated example data."""
from pathlib import Path
import sys
import tempfile
import tkinter as tk
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'commun'))
from inkora.i18n import set_language, tr
from inkora.printer import COLORS, demo_snapshot
from inkora.store import Store
from inkora.ui import Application


def main():
    output = Path(__file__).resolve().parents[1] / 'captures'
    output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        for language in ('fr', 'en', 'es'):
            set_language(language)
            store = Store(Path(folder) / (language + '.sqlite3'))
            store.set_setting('language', language)
            store.set_setting('autostart', False)
            snapshot = demo_snapshot()
            store.observe(snapshot)
            store.calibrate(snapshot, list(COLORS), '604', 65)
            root = tk.Tk()
            errors = []
            root.report_callback_exception = lambda kind, value, trace: errors.append(str(value))
            app = None
            try:
                with patch('inkora.ui.read_printer', side_effect=AssertionError('No printer')), \
                        patch('inkora.usb.read_connected', side_effect=AssertionError('No printer')):
                    app = Application(root, store, demo=True)
                    root.geometry('1280x850')
                    root.update()
                    for theme in ('light', 'dark'):
                        app.save_theme(theme)
                        for page in range(5):
                            app.navigate(page)
                            root.update()
                            assert not errors, errors
                            if page == 3:
                                text = [app.canvas.itemcget(item, 'text') for item in app.canvas.find_all()
                                        if app.canvas.type(item) == 'text']
                                assert tr('Au démarrage d’Ubuntu') in text
                                assert not any('Ubuntu' in part for part in text)
                            if language == 'fr' and page in (0, 3):
                                from PIL import ImageGrab
                                root.lift()
                                root.attributes('-topmost', True)
                                root.update()
                                x, y = root.winfo_rootx(), root.winfo_rooty()
                                ImageGrab.grab(bbox=(x, y, x + root.winfo_width(), y + root.winfo_height())).save(
                                    output / f'windows-{theme}-{page}.png')
                    app.startup_information()
                    root.update()
                    app.dialog.destroy()
                    assert not errors, errors
            finally:
                if app:
                    app.close()
                else:
                    root.destroy()
                    store.close()
    print('Windows UI: 30 views, 3 languages, 2 themes and startup dialog OK')


if __name__ == '__main__':
    main()
