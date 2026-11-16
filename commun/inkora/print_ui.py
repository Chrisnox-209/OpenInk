"""Explicit, one-page CMYK test with preview and destination selection."""
import subprocess
import queue
import threading
import sqlite3
import tkinter as tk
from tkinter import ttk

from .branding import TEST_PAGE
from .dialogs import focus_existing,register_dialog
from .printing import cups_printers,submit_test_page


def show(app):
    if focus_existing(app):return
    win=register_dialog(app,tk.Toplevel(app.root),modal=True)
    win.title('OpenInk · Page de test CMJN');win.configure(bg='white');win.transient(app.root)
    scale=max(.8,app.scale);win.geometry(f'{round(680*scale)}x{round(410*scale)}')
    frame=tk.Frame(win,bg='white',padx=24,pady=20);frame.pack(fill='both',expand=True)
    tk.Label(frame,text='Une page pour vérifier tes quatre couleurs',font=app.font(17,'bold',scaled=True),bg='white',fg='#20283D',wraplength=round(610*scale),justify='left').pack(anchor='w',pady=(0,10))
    tk.Label(frame,text='Logo OpenInk, dégradés CMJN, niveaux de gris et traits fins. Une seule page A4 en couleur.',bg='white',fg='#66748A',wraplength=round(610*scale),justify='left',font=app.font(10,scaled=True)).pack(anchor='w',pady=(0,14))
    note=tk.StringVar(value='Mode démonstration : aucune impression ne sera envoyée.'if app.demo else'Choisis la file de ton Epson.')
    selection=tk.StringVar(value='')
    combo=ttk.Combobox(frame,textvariable=selection,values=(),state='readonly');combo.pack(fill='x',pady=7)
    confirmed=tk.BooleanVar(value=False)
    ttk.Checkbutton(frame,text='Je confirme que cette file correspond à mon Epson XP-2200.',variable=confirmed).pack(anchor='w',pady=8)
    tk.Label(frame,textvariable=note,bg='white',fg='#A16E19',font=app.font(10,scaled=True),wraplength=round(610*scale),justify='left').pack(anchor='w',pady=8)
    buttons=tk.Frame(frame,bg='white');buttons.pack(side='bottom',fill='x')
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
        combo.configure(values=[item['name']for item in queues])
        selection.set(next((item['name']for item in queues if item['confirmed']),''))
        note.set('Choisis la file de ton Epson.'if queues else'Aucune file Epson XP-2200 disponible dans CUPS.')
    def delivered(result,error):
        if error:
            if win.winfo_exists():note.set(error);print_button.configure(state='normal')
            return
        journal_error=False
        try:
            with app.store.db:app.store.event(submitted_printer,'Page de test OpenInk envoyée',result['queue']+' · '+(result['job_id']or'acceptée par CUPS'))
        except sqlite3.Error:journal_error=True
        if win.winfo_exists():note.set('Page envoyée à CUPS'+(' · '+result['job_id']if result['job_id']else'')+('. Journal non enregistré.'if journal_error else'. Vérifie sa sortie sur l’Epson.'))
        app.refresh()
    submitted_printer=None
    def send():
        nonlocal submitted_printer
        if app.demo:return
        if not app.snapshot or not app.online:note.set('Connecte l’Epson et actualise son état.');return
        snapshot=app.snapshot;destination=selection.get();ack=confirmed.get()
        submitted_printer=snapshot.printer_id
        print_button.configure(state='disabled');note.set('Envoi d’une seule page à CUPS…')
        background(lambda:submit_test_page(snapshot,destination,ack),delivered)
    print_button=tk.Button(buttons,text='Imprimer une page',command=send,bg='#7560E8',fg='white',relief='flat',padx=15,pady=9,state='disabled'if app.demo else'normal')
    print_button.pack(side='right')
    tk.Button(buttons,text='Voir la page',command=preview,relief='flat',padx=13,pady=9).pack(side='left')
    tk.Button(buttons,text='Fermer',command=dismiss,relief='flat',padx=13,pady=9).pack(side='left',padx=8)
    win.protocol('WM_DELETE_WINDOW',dismiss);win.bind('<Escape>',lambda _:dismiss())
    if not app.demo:
        snapshot=app.snapshot
        background(lambda:cups_printers(snapshot)if snapshot else[],queues_loaded)
