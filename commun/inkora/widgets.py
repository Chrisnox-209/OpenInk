"""Localized Tk presentation without translating the application's stored values."""
import tkinter as native_tk
from tkinter import ttk as native_ttk
from .i18n import tr
from .theme import widget_colors,color


class ColorMixin:
    def __init__(self,master=None,**kw):
        defaults={'bg':'white'}
        if isinstance(self,(native_tk.Label,native_tk.Button,native_tk.Entry,native_tk.Spinbox)):
            defaults.update(fg='#20283D',insertbackground='#20283D'if isinstance(self,(native_tk.Entry,native_tk.Spinbox))else None)
            if defaults['insertbackground']is None:defaults.pop('insertbackground')
        if isinstance(self,native_tk.Button):defaults.update(activebackground='#F0F2F7',activeforeground='#20283D',highlightbackground='white',highlightcolor='#7560E8')
        if isinstance(self,(native_tk.Entry,native_tk.Spinbox)):
            defaults.update(disabledbackground='#F0F2F7',disabledforeground='#818A9E',readonlybackground='white',
                            selectbackground='#7560E8',selectforeground='white')
        super().__init__(master,**widget_colors(master,{**defaults,**kw}))

    def configure(self,cnf=None,**kw):
        if isinstance(cnf,dict):kw={**cnf,**kw};cnf=None
        return super().configure(cnf,**widget_colors(self,kw))
    config=configure


class TextMixin:
    def __init__(self,master=None,**kw):
        self._translation_trace=None
        if 'text'in kw:kw['text']=tr(kw['text'])
        source=kw.get('textvariable')
        if isinstance(source,native_tk.Variable):
            target=native_tk.StringVar(master,value=tr(source.get()))
            self._translation_source=source;self._translation_target=target
            self._translation_trace=source.trace_add('write',lambda *_:target.set(tr(source.get())))
            kw['textvariable']=target
        super().__init__(master,**kw)
        self.bind('<Destroy>',self._translation_cleanup,add='+')

    def _translation_cleanup(self,event):
        if event.widget is self and self._translation_trace:
            try:self._translation_source.trace_remove('write',self._translation_trace)
            except native_tk.TclError:pass
            self._translation_trace=None

    def configure(self,cnf=None,**kw):
        if isinstance(cnf,dict):kw={**cnf,**kw};cnf=None
        if 'text'in kw:kw['text']=tr(kw['text'])
        return super().configure(cnf,**kw)
    config=configure


class Label(TextMixin,ColorMixin,native_tk.Label):pass
class Button(TextMixin,ColorMixin,native_tk.Button):pass
class Frame(ColorMixin,native_tk.Frame):pass
class Canvas(ColorMixin,native_tk.Canvas):pass
class Entry(ColorMixin,native_tk.Entry):pass
class Spinbox(ColorMixin,native_tk.Spinbox):pass
class Checkbutton(TextMixin,native_ttk.Checkbutton):pass


class Toplevel(ColorMixin,native_tk.Toplevel):
    def title(self,value=None):return super().title(tr(value)if value is not None else None)


class Tk(native_tk.Tk):
    def title(self,value=None):return super().title(tr(value)if value is not None else None)


class Switch(Canvas):
    """A real focusable control: mouse, Space and Return all toggle once."""
    def __init__(self,master,variable,command=None,**kw):
        self.variable=variable;self.command=command
        super().__init__(master,width=48,height=28,highlightthickness=0,takefocus=True,cursor='hand2',**kw)
        self._trace=variable.trace_add('write',lambda *_:self.draw())
        self.bind('<Configure>',lambda _:self.draw())
        self.bind('<FocusIn>',lambda _:self.draw());self.bind('<FocusOut>',lambda _:self.draw())
        self.bind('<Button-1>',lambda _:self.invoke())
        self.bind('<space>',self._key);self.bind('<Return>',self._key)
        self.bind('<Destroy>',self._destroy,add='+')
        self.draw()

    def invoke(self):
        self.focus_set();self.variable.set(not self.variable.get())
        if self.command:self.command()

    def _key(self,_):self.invoke();return 'break'

    def draw(self):
        self.delete('all')
        w=self.winfo_width();h=self.winfo_height()
        if w<=1:w=int(self.cget('width'))
        if h<=1:h=int(self.cget('height'))
        pad=h*.14;r=(h-2*pad)/2
        theme=getattr(self._root(),'_openink_theme','light')
        if self.focus_get()is self:self.create_rectangle(1,1,w-1,h-1,outline=color('#7560E8',theme),width=1)
        self.create_line(r+pad,h/2,w-r-pad,h/2,width=2*r,capstyle='round',fill=color('#7560E8'if self.variable.get()else'#CBD2E1',theme))
        cx=w-r-pad if self.variable.get()else r+pad;knob=r*.72
        self.create_oval(cx-knob,h/2-knob,cx+knob,h/2+knob,fill='#FFFFFF',outline='#FFFFFF')

    def _destroy(self,event):
        if event.widget is self:self.variable.trace_remove('write',self._trace)


class Combobox(native_ttk.Combobox):
    """Present translated choices while callbacks still receive canonical values."""
    def __init__(self,master=None,**kw):
        self.localize_values=kw.pop('localize_values',True)
        self.canonical_values=tuple(kw.pop('values',()))
        self.source=kw.pop('textvariable',None)or native_tk.StringVar(master)
        self.display=native_tk.StringVar(master)
        self._syncing=False
        super().__init__(master,textvariable=self.display,values=self._visible(),**kw)
        self._source_trace=self.source.trace_add('write',self._source_changed)
        self._display_trace=self.display.trace_add('write',self._display_changed)
        self._source_changed()
        self.bind('<Destroy>',self._cleanup,add='+')

    def _visible(self):return tuple(tr(value)if self.localize_values else value for value in self.canonical_values)

    def _source_changed(self,*_):
        if self._syncing:return
        self._syncing=True
        try:self.display.set(tr(self.source.get())if self.localize_values else self.source.get())
        finally:self._syncing=False

    def _display_changed(self,*_):
        if self._syncing:return
        self._syncing=True
        try:
            value=self.display.get();visible=self._visible()
            self.source.set(self.canonical_values[visible.index(value)]if value in visible else value)
        finally:self._syncing=False

    def get(self):return self.source.get()

    def configure(self,cnf=None,**kw):
        if isinstance(cnf,dict):kw={**cnf,**kw};cnf=None
        if 'values'in kw:
            self.canonical_values=tuple(kw['values']);kw['values']=self._visible()
        return super().configure(cnf,**kw)
    config=configure

    def _cleanup(self,event):
        if event.widget is self:
            for variable,trace in((self.source,self._source_trace),(self.display,self._display_trace)):
                try:variable.trace_remove('write',trace)
                except native_tk.TclError:pass


class Namespace:
    def __init__(self,module,**overrides):self._module=module;self.__dict__.update(overrides)
    def __getattr__(self,name):return getattr(self._module,name)


tk=Namespace(native_tk,Tk=Tk,Toplevel=Toplevel,Label=Label,Button=Button,
             Frame=Frame,Canvas=Canvas,Entry=Entry,Spinbox=Spinbox)
ttk=Namespace(native_ttk,Checkbutton=Checkbutton,Combobox=Combobox)
