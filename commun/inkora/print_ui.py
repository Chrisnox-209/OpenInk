"""Explicit, one-page CMYK test with preview and destination selection."""
import subprocess
import queue
import threading
import sqlite3
import tkinter as tk
from tkinter import ttk

from .branding import TEST_PAGE
from .dialogs import focus_existing,register_dialog,scrollable_content
from .printing import cups_printers,submit_test_page


def show(app):
    if focus_existing(app):return
    win=register_dialog(app,tk.Toplevel(app.root),modal=True)
    win.title('OpenInk · Page de test CMJN');win.configure(bg='white');win.transient(app.root)
    scale=max(.8,app.scale)
    width=min(round(730*scale),app.monitor_geometry[0]-40)
    height=min(round(520*scale),app.monitor_geometry[1]-80)
    win.geometry(f'{width}x{height}')
    frame,buttons=scrollable_content(win,'white')
    tk.Label(frame,text='Une page pour vérifier tes quatre couleurs',font=app.font(17,'bold',scaled=True),bg='white',fg='#20283D',wraplength=round(610*scale),justify='left').pack(anchor='w',pady=(0,10))
    tk.Label(frame,text='Logo OpenInk, dégradés CMJN, niveaux de gris et traits fins. Une seule page A4 en couleur.',bg='white',fg='#66748A',wraplength=round(610*scale),justify='left',font=app.font(10,scaled=True)).pack(anchor='w',pady=(0,14))
    note=tk.StringVar(value='Mode démonstration : aucune impression ne sera envoyée.'if app.demo else'Recherche des files CUPS…')
    selection=tk.StringVar(value='')
    combo=ttk.Combobox(frame,textvariable=selection,values=(),state='readonly');combo.pack(fill='x',pady=7)
    confirmed=tk.BooleanVar(value=False)
    confirmation=ttk.Checkbutton(frame,text='Je confirme que cette file correspond à mon Epson XP-2200.',variable=confirmed)
    confirmation.pack(anchor='w',pady=8)
    tk.Label(buttons,textvariable=note,bg='white',fg='#A16E19',font=app.font(10,scaled=True),wraplength=round(610*scale),justify='left').pack(side='top',anchor='w',pady=8)
    row=tk.Frame(buttons,bg='white');row.pack(side='bottom',fill='x');buttons=row
    available={};sending=False
    def preview():subprocess.Popen(['xdg-open',str(TEST_PAGE)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    def dismiss():win.destroy()
    def background(action,finish):
        results=queue.Queue()
        def worker():
            try:results.put((action(),None))
            except Exception as exc:results.put((None,str(exc)))
        def poll():
            if app.closed:return
            try:value,error=results.get_nowait()
            except queue.Empty:app.root.after(50,poll);return
            finish(value,error)
        threading.Thread(target=worker,daemon=True,name='OpenInk-test-page').start();app.root.after(50,poll)
    def queues_loaded(queues,error):
        if not win.winfo_exists():return
        if error:note.set(error);return
        available.clear();available.update({item['name']:item for item in queues})
        combo.configure(values=list(available))
        enabled=[item for item in queues if item['enabled']]
        selected=next((item['name']for item in enabled if item['confirmed']),enabled[0]['name']if len(enabled)==1 else'')
        selection.set(selected);changed()
    def changed(*_):
        if app.demo:return
        selected=available.get(selection.get())
        valid=bool(selected and selected['enabled']and(selected['confirmed']or confirmed.get()))
        print_button.configure(state='normal'if valid and not sending else'disabled')
        if not available:note.set('Aucune file Epson disponible. Ajoute l’imprimante dans les paramètres Ubuntu, puis actualise les files.')
        elif not selected:note.set('Choisis la file CUPS de ton Epson.')
        elif not selected['enabled']:note.set('Cette file est désactivée dans CUPS. Choisis une autre file disponible.')
        elif not selected['confirmed']and not confirmed.get():note.set('Vérifie la file choisie, puis coche sa confirmation pour activer l’impression.')
        else:note.set('Prêt : une seule page A4 sera envoyée à '+selection.get()+'.')
    def delivered(result,error):
        nonlocal sending
        if error:
            sending=False
            if win.winfo_exists():changed();note.set(error)
            return
        journal_error=False
        try:
            app.store.observe(result['snapshot'])
            with app.store.db:app.store.event(result['snapshot'].printer_id,'Page de test OpenInk envoyée',result['queue']+' · '+(result['job_id']or'acceptée par CUPS'))
        except sqlite3.Error:journal_error=True
        if win.winfo_exists():note.set('Page envoyée à CUPS'+(' · '+result['job_id']if result['job_id']else'')+('. Journal non enregistré.'if journal_error else'. Vérifie sa sortie sur l’Epson.'))
        app.refresh()
    def send():
        nonlocal sending
        if app.demo:return
        snapshot=app.snapshot;destination=selection.get();ack=confirmed.get()
        host=app.host;transport=app.store.setting('transport','network')
        sending=True
        print_button.configure(state='disabled');note.set('Envoi d’une seule page à CUPS…')
        def submit():
            from .usb import read_connected
            current=read_connected(host,transport)
            if snapshot and snapshot.serial and current.serial!=snapshot.serial:
                raise ValueError('L’identité de l’imprimante a changé. Vérifie la connexion avant d’imprimer.')
            result=submit_test_page(current,destination,ack);result['snapshot']=current;return result
        background(submit,delivered)
    print_button=tk.Button(buttons,text='Imprimer une page',command=send,bg='#7560E8',fg='white',relief='flat',padx=15,pady=9,state='disabled')
    print_button.pack(side='right')
    tk.Button(buttons,text='Voir la page',command=preview,relief='flat',padx=13,pady=9).pack(side='left')
    tk.Button(buttons,text='Fermer',command=dismiss,relief='flat',padx=13,pady=9).pack(side='left',padx=8)
    def reload():
        if not app.demo and not sending:background(lambda:cups_printers(app.snapshot),queues_loaded)
    tk.Button(frame,text='Actualiser les files CUPS',command=reload,relief='flat',padx=10,pady=7).pack(anchor='w',pady=8)
    combo.bind('<<ComboboxSelected>>',lambda _: (confirmed.set(False),changed()))
    confirmation.configure(command=changed)
    win.protocol('WM_DELETE_WINDOW',dismiss);win.bind('<Escape>',lambda _:dismiss())
    if not app.demo:
        reload()
