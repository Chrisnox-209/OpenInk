"""V2 installation and physical ink declarations. Demo never starts a worker."""
import json
import subprocess
import tkinter as tk
from tkinter import ttk

from .firmware import (SAFE_PHASES,current_operation,hardware_busy,job_folder,launch_job,prepare_job,
                       remaining_wait)
from .printer import COLORS,NAMES
from .dialogs import focus_existing,register_dialog,scrollable_content
from .branding import RISK_NOTICE

BG='#FFFFFF';INK='#20283D';MUTED='#818A9E';PURPLE='#7560E8';LINE='#E8ECF3'
MODES=('Conserver l’estimation','Remplie / remplacée, pleine','Niveau estimé saisi')


def operation(app):
    if app.demo:return None
    try:return current_operation()
    except (OSError,ValueError):return {'phase':'journal_error','detail':'Journal de mise à jour illisible : installation suspendue.'}


def page(app):
    state=operation(app)
    app.rect(246,154,997,159,BG,14,LINE)
    app.text(270,184,'Firmware V2 · installation USB',18,INK,'bold')
    app.text(1190,184,'USB OBLIGATOIRE',9,PURPLE,'bold',anchor='e')
    app.text(270,219,'La V2 concerne les quatre couleurs. Elle s’installe une seule fois.',12,INK,'bold')
    app.text(270,253,'Après un remplissage, mets à jour uniquement les couleurs concernées dans Cartouches. Aucun nouveau flash n’est nécessaire.',11,MUTED,width=880)
    app.rect(246,331,997,146,'#FFF5E2',14)
    app.text(270,361,'Les 100 % Epson seront simulés',15,'#A16E19','bold')
    app.text(270,399,'OpenInk estime l’encre à partir des pages. Photos et nettoyages peuvent consommer davantage : la réserve aide à anticiper le remplissage sans garantir l’absence de désamorçage.',11,'#8B764D',width=900)
    app.text(270,449,'Préalerte : 30 % · Réserve : 20 % par défaut, modifiables dans Réglages.',10,'#8B764D')
    app.rect(246,495,997,196,BG,14,LINE)
    app.text(270,525,'Installation et vérification',16,INK,'bold')
    if state:
        label={'done':'V2 active · contrôle ciblé'if state.get('verification_scope')=='modified_regions_and_boot'else'V2 vérifiée · contrôle complet','restarting':'Détection du redémarrage normal','restarted':'Redémarrage USB reconnu','unchanged':'V2 non installée · programme de départ reconnu','failed_before_update':'Installation non commencée','verification_required':'Vérification nécessaire',
               'waiting':'Attente après programmation','verifying':'Vérification de la V2','backup':'Sauvegarde avant transfert',
               'upload':'Transfert du firmware','commit_requested':'Programmation demandée'}.get(state['phase'],'Opération V2')
        app.text(270,562,label,12,PURPLE,'bold')
        detail=state.get('detail','')
        app.text(270,590,detail[:235]+('…'if len(detail)>235 else''),10,MUTED,width=880)
        value=state.get('progress')
        progress=max(0,min(1,float(value)))if value is not None else 0
        app.text(1194,562,f'{round(progress*100)} %'if value is not None else'En cours',11,PURPLE,'bold',anchor='e')
        app.rect(270,627,924,7,'#EDEBF8',3)
        if progress:app.rect(270,627,924*progress,7,PURPLE,3)
        wait=remaining_wait(state)if state['phase']in {'waiting','verification_required'}else 0
        after_wait=('Si l’Epson est éteinte, appuie une fois sur Marche, puis sur Vérifier l’installation.'
                    if state['phase']=='verification_required'else'Le suivi reprend après une vérification réussie.')
        app.text(270,660,f'Attente minimale restante : {wait//60:02d}:{wait%60:02d}'if wait else after_wait,9,MUTED)
    else:
        app.text(270,562,'V2 disponible · aucune installation lancée',12,PURPLE,'bold')
        app.text(270,599,'Sauvegarde avant écriture, détection du redémarrage USB et contrôle ciblé des zones modifiées. Attente longue conservée si le résultat est incertain.',11,MUTED,width=900)
        app.text(270,661,'Aucune page ni aucun nettoyage n’est lancé par cet assistant.',9,MUTED)
    blocked=state and state['phase']not in SAFE_PHASES
    app.button(246,712,291,44,'Préparer l’installation V2',lambda:wizard(app),primary=True)if not blocked else app.button(246,712,291,44,'Nouvelle installation suspendue',None)
    if blocked:
        available=not app.demo and not remaining_wait(state)and not hardware_busy()
        app.button(555,712,291,44,'Vérifier l’installation',lambda:verify(app)if available else None,primary=False)if available else app.button(555,712,291,44,'Vérification après attente',None)
    else:app.button(555,712,291,44,'Mettre à jour mes niveaux',lambda:app.reset_dialog())
    if state and state.get('id'):
        app.button(864,712,355,44,'Ouvrir le journal et les sauvegardes',lambda:open_folder(app,state['id']))
        if state['phase']=='done'and state.get('verified'):
            app.button(864,768,355,32,'Vérification complète (plus longue)',lambda:verify(app))
    app.text(270,789,'Le flash est global. Après remplissage, ajuste seulement les niveaux.',9,MUTED)


def open_folder(app,identifier):
    if app.demo:return
    subprocess.Popen(['xdg-open',str(job_folder(identifier))],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)


def wizard(app):
    if focus_existing(app):return
    if not app.snapshot or not app.online:
        app.notice='Connecte l’Epson avant de préparer la V2.';app.render();return
    win=register_dialog(app,tk.Toplevel(app.root))
    win.title('Installer V2 et préparer le suivi · OpenInk');win.configure(bg=BG);win.transient(app.root)
    scale=max(.8,app.scale)
    width=min(round(920*scale),app.monitor_geometry[0]-40)
    height=min(round(940*scale),app.monitor_geometry[1]-80)
    win.geometry(f'{width}x{height}');win.minsize(min(width,round(820*scale)),min(height,round(620*scale)))
    frame,actions=scrollable_content(win,BG)
    def label(text,size=11,bold=False):
        widget=tk.Label(frame,text=text,bg=BG,fg=INK if bold else MUTED,font=app.font(size,'bold'if bold else'normal',scaled=True),wraplength=round(830*scale),justify='left')
        widget.pack(anchor='w',pady=(0,10));return widget
    label('Installer V2, puis suivre l’encre réellement présente',18,True)
    label('Le flash modifie toute l’imprimante. La sélection ci-dessous concerne uniquement le suivi d’encre : elle ne réécrit pas les puces et ne limite pas le flash à une couleur.')
    label('Connexion directe par câble USB obligatoire. Le Wi-Fi sert au suivi, jamais au flash.',11,True)
    estimates=app.store.estimates(app.snapshot)
    table=tk.Frame(frame,bg=BG);table.pack(fill='x',pady=(2,12))
    for column,text in enumerate(('Cartouche','Niveau actuel','Déclaration pour le suivi','Départ (%)')):
        tk.Label(table,text=text,bg=BG,fg=MUTED,font=app.font(10,'bold',scaled=True)).grid(row=0,column=column,sticky='w',padx=(0,12),pady=6)
    rows={}
    def toggle(color):
        item=rows[color];enabled=item['selected'].get()
        item['combo'].configure(state='readonly'if enabled else'disabled')
        item['entry'].configure(state='normal'if enabled and item['mode'].get()==MODES[2]else'disabled')
    for row,color in enumerate(COLORS,1):
        estimate=estimates[color]
        selected=tk.BooleanVar(value=False);mode=tk.StringVar(value=MODES[0]if estimate else MODES[2]);amount=tk.StringVar(value='')
        check=ttk.Checkbutton(table,text=NAMES[color],variable=selected,command=lambda c=color:toggle(c))
        check.grid(row=row,column=0,sticky='w',padx=(0,8),pady=6)
        tk.Label(table,text=f"{estimate['percent']:.0f} % estimés"if estimate else'À initialiser',bg=BG,fg=INK,font=app.font(10,scaled=True)).grid(row=row,column=1,sticky='w',padx=(0,12))
        combo=ttk.Combobox(table,textvariable=mode,values=MODES,state='disabled',width=29)
        combo.grid(row=row,column=2,sticky='ew',padx=(0,12));combo.bind('<<ComboboxSelected>>',lambda _,c=color:toggle(c))
        entry=tk.Entry(table,textvariable=amount,width=7,state='disabled',font=app.font(11,scaled=True))
        entry.grid(row=row,column=3,sticky='w')
        rows[color]={'selected':selected,'mode':mode,'percent':amount,'combo':combo,'entry':entry}
    table.columnconfigure(2,weight=1)
    options=tk.Frame(frame,bg=BG);options.pack(fill='x',pady=(0,12))
    tk.Label(options,text='Format pour les niveaux déclarés :',bg=BG,fg=INK,font=app.font(10,scaled=True)).pack(side='left')
    profile=tk.StringVar(value=app.store.setting('cartridge_profile','604'))
    if profile.get()not in('604','604XL'):profile.set('604')
    ttk.Combobox(options,textvariable=profile,values=('604','604XL'),state='readonly',width=12).pack(side='left',padx=12)
    added=tk.BooleanVar(value=False);risk=tk.BooleanVar(value=False);usb=tk.BooleanVar(value=False)
    ttk.Checkbutton(frame,text='Les couleurs déclarées pleines ont réellement été remplies ou remplacées.',variable=added).pack(anchor='w',pady=5)
    label('Sans ajout d’encre, conserve l’estimation. Une couleur inconnue doit recevoir un niveau de départ saisi : OpenInk ne la supposera jamais pleine.',10)
    label('Avertissement avant flash',12,True)
    label(RISK_NOTICE,10)
    ttk.Checkbutton(frame,text='J’ai lu l’avertissement et j’accepte les risques du flash.',variable=risk).pack(anchor='w',pady=7)
    ttk.Checkbutton(frame,text='L’Epson est reliée directement par câble USB (obligatoire).',variable=usb).pack(anchor='w',pady=7)
    label('Ne pas imprimer, débrancher ni couper l’alimentation avant la fin indiquée. En cas de réponse incertaine, l’attente prudente peut durer quinze minutes.',10)
    note=tk.StringVar(value='Démonstration : aucune communication matérielle.'if app.demo else'Les niveaux seront mis à jour uniquement après vérification réussie de V2.')
    tk.Label(actions,textvariable=note,bg=BG,fg='#A16E19',font=app.font(10,scaled=True),wraplength=round(830*scale),justify='left').pack(side='top',anchor='w',pady=(0,8))
    button_row=tk.Frame(actions,bg=BG);button_row.pack(side='bottom',fill='x');actions=button_row
    def dismiss():app.dialog=None;win.destroy()
    def start():
        if app.demo:note.set('Démonstration : aucun flash envoyé et aucun niveau modifié.');return
        try:
            plan={}
            for color,item in rows.items():
                if not item['selected'].get():continue
                action=MODES.index(item['mode'].get())
                plan[color]=({'action':'keep'}if action==0 else{'action':'full'if action==1 else'estimate',
                    'percent':100 if action==1 else float(item['percent'].get().replace(',','.')),
                    'profile':profile.get(),'ink_added':added.get()})
            identifier=prepare_job(app.store.path,app.snapshot,plan,app.store.estimates(app.snapshot),True,
                                   risk_acknowledged=risk.get(),usb_confirmed=usb.get())
            process=launch_job(identifier)
        except (ValueError,OSError)as exc:note.set(str(exc));return
        app.flash_process=process;app.flash_identifier=identifier;dismiss()
        app.navigate(4)
        app.notice='Assistant V2 démarré. Les sauvegardes et contrôles précèdent tout transfert.'
    tk.Button(actions,text='Installer V2 et démarrer le suivi',command=start,bg=PURPLE,fg=BG,relief='flat',padx=18,pady=10).pack(side='right')
    tk.Button(actions,text='Annuler',command=dismiss,bg='#F0F2F7',fg=INK,relief='flat',padx=18,pady=10).pack(side='right',padx=10)
    win.protocol('WM_DELETE_WINDOW',dismiss);win.bind('<Escape>',lambda _:dismiss())


def verify(app):
    if app.demo:return
    try:
        state=current_operation()
        if not state or not state.get('id'):raise ValueError('Aucune opération à vérifier.')
        if remaining_wait(state):raise ValueError('Le délai après programmation n’est pas terminé ; laisse l’Epson branchée.')
        if hardware_busy():raise ValueError('L’assistant fonctionne encore. Attends la fin de l’opération.')
        if getattr(app,'flash_process',None)and app.flash_process.poll()is None:
            raise ValueError('L’assistant fonctionne encore. Attends la fin de l’opération.')
        app.flash_process=launch_job(state['id'],verify_only=True);app.flash_identifier=state['id']
        app.notice='Vérification seule démarrée ; aucun nouveau flash.'
    except (ValueError,OSError)as exc:app.notice=str(exc)
    app.render()


def poll(app):
    if app.closed:return
    state=operation(app)
    digest=json.dumps(state,sort_keys=True)
    process=getattr(app,'flash_process',None)
    if process and process.poll()is not None:
        if process.returncode and (not state or state.get('id')!=getattr(app,'flash_identifier',None)):
            app.notice='Assistant non démarré. Consulte worker.log ; aucun transfert confirmé.'
        app.flash_process=None
    if app.page==4 and not app.dialog and digest!=getattr(app,'flash_digest',None):app.render()
    app.flash_digest=digest
    if app.page==4 and state and remaining_wait(state)and not app.dialog:app.render()
    app.root.after(1000,lambda:poll(app))
