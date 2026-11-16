"""Localized Tk presentation without translating the application's stored values."""
import tkinter as native_tk
from tkinter import ttk as native_ttk
from .i18n import tr


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


class Label(TextMixin,native_tk.Label):pass
class Button(TextMixin,native_tk.Button):pass
class Checkbutton(TextMixin,native_ttk.Checkbutton):pass


class Toplevel(native_tk.Toplevel):
    def title(self,value=None):return super().title(tr(value)if value is not None else None)


class Tk(native_tk.Tk):
    def title(self,value=None):return super().title(tr(value)if value is not None else None)


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


tk=Namespace(native_tk,Tk=Tk,Toplevel=Toplevel,Label=Label,Button=Button)
ttk=Namespace(native_ttk,Checkbutton=Checkbutton,Combobox=Combobox)
