"""Explicit graphical check, demo-only; requires a desktop display.

Not part of unittest discovery. Never opens the user's database or printer.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/"commun"))
from inkora.printer import COLORS, demo_snapshot
from inkora.store import Store
from inkora.ui import Application
from inkora import __version__


def children(widget):
    for child in widget.winfo_children():
        yield child
        yield from children(child)


def main():
    output = Path(__file__).resolve().parents[1]/"captures"
    output.mkdir(exist_ok=True)
    failures = []
    store = Store(":memory:")
    snapshot = demo_snapshot()
    store.observe(snapshot)
    for color, level in zip(COLORS, (78, 29, 16, 61)):
        store.calibrate(snapshot, [color], "604", level)
    root = tk.Tk()
    root.report_callback_exception = lambda kind, value, trace: failures.append(str(value))
    app = None
    try:
        with patch("inkora.ui.read_printer", side_effect=AssertionError("Network forbidden in UI check")), \
             patch("inkora.ui.send_notification", side_effect=AssertionError("Desktop notification forbidden in demo")):
            app = Application(root, store, demo=True)
            root.update()
            min_width,min_height=root.minsize()
            assert min_width*min_height/(app.monitor_geometry[0]*app.monitor_geometry[1])>=.45
            for page in range(5):
                app.navigate(page)
                root.update()
                assert len(app.canvas.find_all()) > 30
                assert app.ox==0 and app.canvas.coords('sidebar-background')[0]==0
                assert all('bêta'not in app.canvas.itemcget(item,'text').lower()for item in app.canvas.find_all()if app.canvas.type(item)=='text')
            assert any('RISQUE DE BLOCAGE'in app.canvas.itemcget(item,'text')for item in app.canvas.find_all()if app.canvas.type(item)=='text')
            original_toplevel=tk.Toplevel
            def hidden_window(parent):
                win=original_toplevel(parent);win.withdraw();return win
            with patch('inkora.ui.tk.Toplevel',side_effect=hidden_window):
                app.reset_dialog('cyan')
            delayed=app.dialog;root.update()
            assert not delayed.winfo_viewable()
            assert root.grab_current() is not delayed
            delayed.deiconify()
            deadline=time.monotonic()+2
            while time.monotonic()<deadline and root.grab_current()is not delayed:
                root.update();time.sleep(.01)
            assert delayed.winfo_viewable()and root.grab_current()is delayed
            delayed.destroy();root.update();assert app.dialog is None
            # Recreate the exact stale reference seen after the original error.
            app.dialog=delayed;app.reset_dialog('cyan');root.update()
            assert app.dialog is not delayed and app.dialog.winfo_exists()
            app.dialog.destroy();root.update();assert app.dialog is None
            app.navigate(0)
            before = store.estimates(snapshot)
            app.reset_dialog("cyan")
            root.update()
            win = app.dialog
            combos = [w for w in children(win) if isinstance(w, ttk.Combobox)]
            operation = combos[0]
            operation.current(2)
            operation.event_generate("<<ComboboxSelected>>")
            root.update()
            start = next(w for w in children(win) if isinstance(w, tk.Spinbox))
            assert str(start.cget("state")) == "disabled"
            save = next(w for w in children(win) if isinstance(w, tk.Button) and w.cget("text") == "Conserver les niveaux")
            save.invoke()
            root.update()
            assert app.dialog is None
            assert store.estimates(snapshot) == before
            app.reset_dialog("cyan")
            root.update()
            win = app.dialog
            save = next(w for w in children(win) if isinstance(w, tk.Button) and w.cget("text") == "Enregistrer le remplissage")
            save.invoke()
            root.update()
            assert app.dialog is not None, "Refill must require confirmation"
            assert store.estimates(snapshot) == before
            confirmation = next(w for w in children(win) if isinstance(w, ttk.Checkbutton) and "réellement" in w.cget("text"))
            confirmation.invoke()
            save.invoke()
            root.update()
            assert app.dialog is None
            assert store.estimates(snapshot)["cyan"]["percent"] == 100
            assert store.estimates(snapshot)["magenta"] == before["magenta"]
            app.navigate(3)
            app.warning_var.set("20")
            app.reserve_var.set("30")
            app.save_safety()
            assert store.setting("reserve_percent", 20) == 20
            app.warning_var.set("35")
            app.reserve_var.set("15")
            app.save_safety()
            assert store.setting("warning_percent") == 35
            assert store.setting("reserve_percent") == 15
            app.navigate(1)
            before=store.estimates(snapshot)
            app.hardware_reset_dialog()
            root.update()
            win=app.dialog
            select=next(w for w in children(win)if isinstance(w,ttk.Checkbutton)and w.cget('text')=='Cyan')
            select.invoke()
            verify=next(w for w in children(win)if isinstance(w,tk.Button)and w.cget('text')=='Vérifier la compatibilité')
            verify.invoke()
            assert store.estimates(snapshot)==before
            close=next(w for w in children(win)if isinstance(w,tk.Button)and w.cget('text')=='Fermer')
            close.invoke()
            root.update()
            from inkora.firmware_ui import wizard
            app.navigate(4)
            before=store.estimates(snapshot)
            from inkora.print_ui import show as show_test_page
            with patch('inkora.print_ui.cups_printers',side_effect=AssertionError('No CUPS query in demo')), \
                 patch('inkora.print_ui.submit_test_page',side_effect=AssertionError('No test print in demo')):
                show_test_page(app);root.update();win=app.dialog
                send=next(w for w in children(win)if isinstance(w,tk.Button)and w.cget('text')=='Imprimer une page')
                assert str(send.cget('state'))=='disabled'
                send.invoke();win.destroy();root.update()
            # Real dialog flow with a disabled USB queue and one available network queue.
            from dataclasses import replace
            fake_snapshot=replace(app.snapshot,demo=False)
            with patch('inkora.print_ui.cups_printers',return_value=[
                    {'name':'Epson-network','enabled':True,'confirmed':False},
                    {'name':'Epson-USB-off','enabled':False,'confirmed':True}]), \
                 patch('inkora.usb.read_connected',return_value=fake_snapshot), \
                 patch('inkora.print_ui.submit_test_page',return_value={'queue':'Epson-network','job_id':'Epson-network-1'})as submit, \
                 patch.object(app,'refresh'):
                app.demo=False
                try:
                    show_test_page(app);root.update();win=app.dialog
                    combo=next(w for w in children(win)if isinstance(w,ttk.Combobox))
                    deadline=time.monotonic()+3
                    while not combo.get()and time.monotonic()<deadline:root.update();time.sleep(.01)
                    assert combo.get()=='Epson-network'
                    send=next(w for w in children(win)if isinstance(w,tk.Button)and w.cget('text')=='Imprimer une page')
                    assert str(send.cget('state'))=='disabled'
                    confirm=next(w for w in children(win)if isinstance(w,ttk.Checkbutton))
                    confirm.invoke();assert str(send.cget('state'))=='normal';send.invoke()
                    deadline=time.monotonic()+3
                    while not submit.called and time.monotonic()<deadline:root.update();time.sleep(.01)
                    assert submit.call_count==1
                    assert submit.call_args.args[1:] == ('Epson-network',True)
                    for _ in range(20):root.update();time.sleep(.01)
                    assert str(send.cget('state'))=='disabled'
                    win.destroy();root.update()
                finally:app.demo=True
            with patch('inkora.firmware_ui.launch_job',side_effect=AssertionError('No firmware worker in demo')):
                wizard(app);root.update()
                win=app.dialog
                frame=win.winfo_children()[0]
                assert frame.winfo_reqheight()<=win.winfo_height(), 'Firmware dialog clips its content'
                assert frame.winfo_reqwidth()<=win.winfo_width(), 'Firmware dialog clips its width'
                start=next(w for w in children(win)if isinstance(w,tk.Button)and w.cget('text')=='Installer OpenFlow et démarrer le suivi')
                start.invoke();root.update()
                assert store.estimates(snapshot)==before
                cancel=next(w for w in children(win)if isinstance(w,tk.Button)and w.cget('text')=='Annuler')
                cancel.invoke();root.update()
            from inkora.firmware_ui import MODES
            with patch('inkora.firmware_ui.prepare_job',return_value='f'*32)as prepare, \
                 patch('inkora.firmware_ui.launch_job',return_value=SimpleNamespace(poll=lambda:None))as launch, \
                 patch('inkora.firmware_ui.current_operation',return_value=None):
                wizard(app);root.update();win=app.dialog
                checks=[w for w in children(win)if isinstance(w,ttk.Checkbutton)]
                next(w for w in checks if w.cget('text')=='Cyan').invoke()
                next(w for w in checks if w.cget('text')=='Magenta').invoke()
                modes=[w for w in children(win)if isinstance(w,ttk.Combobox)and tuple(w.cget('values'))==MODES]
                modes[1].current(1);modes[1].event_generate('<<ComboboxSelected>>')
                modes[2].current(2);modes[2].event_generate('<<ComboboxSelected>>');root.update()
                entries=[w for w in children(win)if w.winfo_class()=='Entry']
                entries[2].insert(0,'40')
                next(w for w in checks if 'déclarées pleines'in w.cget('text')).invoke()
                next(w for w in checks if 'j’accepte les risques'in w.cget('text')).invoke()
                next(w for w in checks if 'USB (obligatoire)'in w.cget('text')).invoke()
                start=next(w for w in children(win)if isinstance(w,tk.Button)and w.cget('text')=='Installer OpenFlow et démarrer le suivi')
                app.demo=False
                try:start.invoke()
                finally:app.demo=True
                assert prepare.call_count==launch.call_count==1
                plan=prepare.call_args.args[2]
                assert set(plan)=={'cyan','magenta'}
                assert plan['cyan']['action']=='full'and plan['cyan']['percent']==100
                assert plan['magenta']['action']=='estimate'and plan['magenta']['percent']==40
                assert prepare.call_args.args[-1]is True
                assert prepare.call_args.kwargs=={'risk_acknowledged':True,'usb_confirmed':True}
                assert store.estimates(snapshot)==before
                root.update()
            assert not failures, failures
            result = {"version": __version__, "checked_utc": datetime.now(timezone.utc).isoformat(),
                      "demo_only": True, "printer_contacted": False, "actual_user_database_used": False,
                      "all_five_views_rendered": True, "declared_reset_preserves_estimate": True,
                      "refill_requires_explicit_confirmation": True, "selected_color_only_refilled": True,
                      "invalid_thresholds_rejected": True, "valid_thresholds_saved": True,
                      "selected_reset_unavailable_without_ink_change": True,"v2_demo_does_not_launch_worker_or_change_levels":True,
                      "v2_wizard_selected_colors_and_mixed_ink_plan_verified_with_mock_worker":True,
                      "v2_dialog_content_fits":True,"delayed_window_mapping_regression_passed":True,
                      "destroyed_dialog_reference_recovery_passed":True,"callback_errors": failures}
            result['minimum_window_area_fraction']=min_width*min_height/(app.monitor_geometry[0]*app.monitor_geometry[1])
            result['selected_monitor_size']=list(app.monitor_geometry[:2])
            result['risk_and_usb_acknowledgments_in_wizard']=True
            result['demo_test_print_button_disabled_without_cups_io']=True
            result['no_left_margin']=True
            result['print_dialog_selects_enabled_queue_and_submits_once']=True
            (output/f"VALIDATION_INTERFACE_OPENINK_{__version__}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")
            print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        if app:
            app.close()
        else:
            store.close()
            root.destroy()


if __name__ == "__main__":
    main()
