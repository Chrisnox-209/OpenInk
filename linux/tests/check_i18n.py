"""Graphical checks in all three languages, isolated from printer and user data."""
from pathlib import Path
import sys
import tkinter as tk
from tkinter import ttk
from unittest.mock import patch
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'commun'))
from inkora.i18n import set_language,tr,get_language
from inkora.printer import demo_snapshot,COLORS
from inkora.store import Store
from inkora.ui import Application
from inkora.widgets import Combobox,Label


def children(widget):
    for child in widget.winfo_children():yield child;yield from children(child)


def main():
    for language in('fr','en','es'):
        set_language(language);store=Store(':memory:');snapshot=demo_snapshot();store.observe(snapshot)
        for color in COLORS:store.calibrate(snapshot,[color],'604',70)
        root=tk.Tk();errors=[];root.report_callback_exception=lambda kind,value,trace:errors.append(str(value))
        app=None
        try:
            with patch('inkora.ui.read_printer',side_effect=AssertionError('No printer')),patch('inkora.ui.send_notification',side_effect=AssertionError('No notifications')):
                app=Application(root,store,demo=True);root.minsize(1100,730);root.geometry('1440x960');root.update()
                for page in range(5):app.navigate(page);root.update();assert app.ox==0
                app.navigate(3);root.update()
                coverage=next(w for w in app.widgets if isinstance(w,ttk.Combobox)and 'Documents courants'in w.canonical_values)
                coverage.current(1);coverage.event_generate('<<ComboboxSelected>>');app.save_coverage()
                assert store.setting('coverage')==1.8
                before=store.estimates(snapshot)
                app.language_var.set('Español'if language!='es'else'English');app.save_language();root.update()
                assert store.estimates(snapshot)==before
                assert get_language()==('es'if language!='es'else'en')
                set_language(language);app.navigate(4);root.update()
                from inkora.firmware_ui import wizard
                wizard(app);root.update();win=app.dialog
                texts=[w.cget('text')for w in children(win)if isinstance(w,(tk.Label,tk.Button,ttk.Checkbutton))]
                assert tr('J’ai lu l’avertissement et j’accepte les risques du flash.')in texts
                assert tr('L’Epson est reliée directement par câble USB (obligatoire).')in texts
                assert tr('Installer OpenFlow et démarrer le suivi')in texts
                win.destroy();root.update()
                variable=tk.StringVar(root,value='Conserver l’estimation')
                combo=Combobox(root,textvariable=variable,values=('Conserver l’estimation','Niveau estimé saisi'))
                assert combo.display.get()==tr('Conserver l’estimation')
                combo.current(1);assert variable.get()=='Niveau estimé saisi'
                combo.destroy();assert not variable.trace_info()
                source=tk.StringVar(root,value='Choisis la file CUPS de ton Epson.');label=Label(root,textvariable=source)
                source.set('Code 114 non interprété');assert label._translation_target.get()==tr(source.get())
                label.destroy();assert not source.trace_info()
                assert not errors,errors
                print(language+': cinq vues, préférences, valeurs canoniques, avertissements et nettoyage OK')
        finally:
            if app:app.close()
            else:store.close();root.destroy()
    set_language('fr')


if __name__=='__main__':main()
