"""Regression for delayed mapping and destroyed modal windows. No display/IO."""
from pathlib import Path
import sys
from types import SimpleNamespace
import tkinter as tk
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'commun'))
from inkora.dialogs import focus_existing,register_dialog


class Scheduler:
    def __init__(self):self.jobs={};self.index=0
    def after(self,delay,callback):
        self.index+=1;self.jobs[self.index]=callback;return self.index
    def after_idle(self,callback):return self.after(0,callback)
    def after_cancel(self,identifier):self.jobs.pop(identifier,None)
    def drain(self):
        for _ in range(20):
            if not self.jobs:return
            identifier=next(iter(self.jobs));self.jobs.pop(identifier)()
        raise AssertionError('Unbounded dialog retry')


class Window:
    def __init__(self):
        self.exists=True;self.visible=False;self.bindings={};self.grabs=0;self.transient_failure=False
    def bind(self,name,callback,add=None):self.bindings[name]=callback
    def winfo_exists(self):return self.exists
    def winfo_viewable(self):return self.visible
    def deiconify(self):pass
    def lift(self):
        if not self.exists:raise tk.TclError('bad window path name')
    def grab_set(self):
        self.grabs+=1
        if not self.visible:raise AssertionError('Grab before map')
        if self.transient_failure:
            self.transient_failure=False;raise tk.TclError('grab failed: window not viewable')
    def event(self,name):self.bindings[name](SimpleNamespace(widget=self))
    def destroy(self):self.exists=False;self.event('<Destroy>')


class DialogLifecycleTests(unittest.TestCase):
    def setUp(self):self.owner=SimpleNamespace(dialog=None,closed=False,root=Scheduler())

    def test_modal_waits_for_mapping_instead_of_grabbing_immediately(self):
        win=register_dialog(self.owner,Window(),modal=True)
        self.owner.root.drain();self.assertEqual(win.grabs,0)
        win.visible=True;win.event('<Map>');self.owner.root.drain()
        self.assertEqual(win.grabs,1)

    def test_destroy_before_map_cancels_callback_and_clears_reference(self):
        win=register_dialog(self.owner,Window(),modal=True)
        win.destroy();self.owner.root.drain()
        self.assertIsNone(self.owner.dialog);self.assertEqual(win.grabs,0)

    def test_stale_reference_does_not_stop_reopening(self):
        old=Window();old.exists=False;self.owner.dialog=old
        self.assertFalse(focus_existing(self.owner));self.assertIsNone(self.owner.dialog)
        new=register_dialog(self.owner,Window());self.assertIs(self.owner.dialog,new)

    def test_old_destroy_event_cannot_clear_a_new_dialog(self):
        old=register_dialog(self.owner,Window());new=register_dialog(self.owner,Window())
        old.destroy();self.assertIs(self.owner.dialog,new)

    def test_transient_compositor_grab_failure_is_retried_without_callback_error(self):
        win=Window();win.visible=True;win.transient_failure=True
        register_dialog(self.owner,win,modal=True);self.owner.root.drain()
        self.assertEqual(win.grabs,2);self.assertIs(self.owner.dialog,win)

    def test_focus_existing_keeps_one_live_window(self):
        win=register_dialog(self.owner,Window())
        self.assertTrue(focus_existing(self.owner));self.assertIs(self.owner.dialog,win)


if __name__=='__main__':unittest.main()
