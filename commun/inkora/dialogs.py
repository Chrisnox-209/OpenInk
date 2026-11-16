"""Non-blocking Tk dialog lifecycle, including delayed Wayland mapping."""
from .widgets import tk,ttk


def focus_existing(owner):
    window=owner.dialog
    if window is None:return False
    try:
        if window.winfo_exists():
            window.deiconify();window.lift()
            return True
    except tk.TclError:
        pass
    if owner.dialog is window:owner.dialog=None
    return False


def register_dialog(owner,window,modal=False):
    owner.dialog=window
    pending=None
    failures=0

    def destroyed(event):
        nonlocal pending
        if event.widget is window:
            if pending is not None:
                try:owner.root.after_cancel(pending)
                except tk.TclError:pass
                pending=None
            if owner.dialog is window:owner.dialog=None

    def acquire_grab():
        nonlocal pending,failures
        pending=None
        if getattr(owner,'closed',False)or owner.dialog is not window:return
        try:
            if not window.winfo_exists()or not window.winfo_viewable():return
            window.grab_set()
        except tk.TclError:
            # The compositor can withdraw/destroy it between the visibility
            # check and grab. A failed grab must never break its construction.
            failures+=1
            if failures<10 and owner.dialog is window:pending=owner.root.after(20,acquire_grab)

    def mapped(event=None):
        nonlocal pending
        if event is not None and event.widget is not window:return
        if pending is None:pending=owner.root.after_idle(acquire_grab)

    window.bind('<Destroy>',destroyed,add='+')
    if modal:
        window.bind('<Map>',mapped,add='+')
        mapped()
    return window


def scrollable_content(window,background='white'):
    """Keep action buttons visible when a dialog's explanatory text grows."""
    footer=tk.Frame(window,bg=background,padx=20,pady=14);footer.pack(side='bottom',fill='x')
    container=tk.Frame(window,bg=background);container.pack(fill='both',expand=True)
    canvas=tk.Canvas(container,bg=background,highlightthickness=0)
    bar=ttk.Scrollbar(container,orient='vertical',command=canvas.yview)
    canvas.configure(yscrollcommand=bar.set);bar.pack(side='right',fill='y');canvas.pack(side='left',fill='both',expand=True)
    body=tk.Frame(canvas,bg=background,padx=24,pady=18)
    item=canvas.create_window(0,0,anchor='nw',window=body)
    body.bind('<Configure>',lambda _:canvas.configure(scrollregion=canvas.bbox('all')))
    canvas.bind('<Configure>',lambda event:canvas.itemconfigure(item,width=event.width))
    def scroll(event):
        delta=-1 if getattr(event,'num',None)==4 or getattr(event,'delta',0)>0 else 1
        canvas.yview_scroll(delta*3,'units');return 'break'
    window.bind('<MouseWheel>',scroll,add='+');window.bind('<Button-4>',scroll,add='+');window.bind('<Button-5>',scroll,add='+')
    return body,footer
