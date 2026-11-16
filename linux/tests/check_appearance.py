"""Exercise real preference controls in both themes and all languages, offline."""
from pathlib import Path
import sys
import tkinter as tk
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'commun'))
from inkora.i18n import set_language,tr,get_language,LANGUAGES
from inkora.printer import demo_snapshot,COLORS
from inkora.store import Store
from inkora.ui import Application
from inkora.widgets import Switch,Combobox


def children(widget):
    for child in widget.winfo_children():yield child;yield from children(child)


def main(capture_images=False):
    for language in('fr','en','es'):
        set_language(language);store=Store(':memory:');store.set_setting('language',language)
        snapshot=demo_snapshot();store.observe(snapshot)
        for c in COLORS:store.calibrate(snapshot,[c],'604',65)
        root=tk.Tk();app=None;errors=[]
        root.report_callback_exception=lambda kind,value,trace:errors.append(str(value))
        try:
            with patch('inkora.ui.read_printer',side_effect=AssertionError('No printer')),patch('inkora.ui.send_notification',side_effect=AssertionError('No notification')):
                app=Application(root,store,demo=True);root.minsize(1100,730);root.geometry('1440x960');root.update()
                before=store.estimates(snapshot);history=store.events(snapshot.printer_id)
                for theme,label in(('dark','Sombre'),('light','Clair')):
                    app.navigate(3);root.update()
                    choice=next(w for w in app.widgets if isinstance(w,tk.Button)and w.cget('text')==tr(label))
                    choice.invoke();root.update()
                    assert store.setting('theme')==theme and app.theme==theme
                    for page in range(5):
                        app.navigate(page);root.update()
                        assert app.ox==0 and not errors,errors
                    if capture_images and language=='fr'and theme=='dark':
                        from capture_readme import capture
                        output=Path(__file__).resolve().parents[1]/'captures';output.mkdir(exist_ok=True)
                        root.attributes('-topmost',True);root.lift()
                        for page,name in((0,'overview'),(4,'openflow')):
                            app.navigate(page);root.update();capture(app.canvas,output/f'OpenInk-1.7-dark-{name}.png')
                    app.navigate(3);root.update()
                    canvas_text=[app.canvas.itemcget(i,'text')for i in app.canvas.find_all()if app.canvas.type(i)=='text']
                    assert tr('Apparence')in canvas_text
                    next(w for w in app.widgets if isinstance(w,tk.Button)and w.cget('text')=='?').invoke()
                    root.update();win=app.dialog
                    assert win.cget('background')==app.color('#FFFFFF')
                    assert any(tr('Garder votre historique à jour')==w.cget('text')for w in children(win)if isinstance(w,tk.Label))
                    if capture_images and language=='fr'and theme=='dark':capture(win,output/'OpenInk-1.7-dark-help.png')
                    win.destroy();root.update()
                    switch=next(w for w in app.widgets if isinstance(w,Switch));switch.invoke();root.update()
                    assert store.setting('autostart')is False
                    switch=next(w for w in app.widgets if isinstance(w,Switch));switch.focus_force();root.update()
                    switch.event_generate('<space>');root.update()
                    assert store.setting('autostart')is True
                    # Real combobox event, not a direct call of the save method.
                    selector=next(w for w in app.widgets if isinstance(w,Combobox)and w.canonical_values==tuple(LANGUAGES.values()))
                    target='en'if language!='en'else'es'
                    selector.current(tuple(LANGUAGES).index(target));selector.event_generate('<<ComboboxSelected>>');root.update()
                    assert get_language()==target and store.setting('theme')==theme
                    app.language_var.set(LANGUAGES[language]);app.save_language();root.update()
                    app.reset_dialog('cyan');root.update();win=app.dialog
                    assert win.cget('background')==app.color('#FFFFFF');win.destroy();root.update()
                    from inkora.firmware_ui import wizard
                    wizard(app);root.update();win=app.dialog
                    assert win.cget('background')==app.color('#FFFFFF')
                    assert any(tr('J’ai lu l’avertissement et j’accepte les risques du flash.')==w.cget('text')for w in children(win)if hasattr(w,'cget')and'text'in w.keys())
                    win.destroy();root.update()
                    assert store.estimates(snapshot)==before and store.events(snapshot.printer_id)==history
                    assert not errors,errors
                    print(language+'/'+theme+': cinq vues, thèmes, langue, switch clavier, aide et dialogues OK')
        finally:
            if app:app.close()
            else:store.close();root.destroy()
    set_language('fr')


if __name__=='__main__':main('--capture'in sys.argv)
