"""Panel, startup and CUPS regression checks without hardware or real desktop."""
from dataclasses import replace
from pathlib import Path
import os
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'commun'))
from inkora import __version__
from inkora.firmware import atomic_json,firmware_root
from inkora.printer import demo_snapshot
from inkora.printing import cups_printers,submit_test_page
from inkora.service import ensure_tray,stop_desktop,tray_name
from inkora.store import Store
from inkora.tray import PanelIcon,status_lines,ITEM,MENU


class PanelTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='openink-panel-')
        self.root=Path(self.temp.name)
        self.env=patch.dict(os.environ,{'XDG_DATA_HOME':str(self.root/'data'),'XDG_RUNTIME_DIR':str(self.root/'runtime')})
        self.env.start();self.database=self.root/'test.sqlite3'

    def tearDown(self):self.env.stop();self.temp.cleanup()

    def response(self,output='',code=0):return SimpleNamespace(stdout=output,stderr='',returncode=code)

    def test_panel_status_includes_real_separate_page_counters(self):
        status,pages=status_lines({'running':True,'online':True,'color_pages':104,'mono_pages':60})
        self.assertEqual(status,'Surveillance active');self.assertIn('164 pages',pages)
        self.assertIn('hors ligne',status_lines({'running':True,'online':False})[0])
        self.assertIn('Encre basse',status_lines({'running':True,'online':True,'low_colors':['cyan']})[0])

    def test_existing_panel_is_reused_without_new_process(self):
        with patch('inkora.service.tray_request',return_value=(__version__,)),patch('inkora.service.subprocess.Popen')as spawn:
            self.assertTrue(ensure_tray(self.database));spawn.assert_not_called()
        self.assertNotEqual(tray_name(self.database),tray_name(self.root/'another.sqlite3'))

    def test_panel_upgrade_waits_until_old_bus_owner_has_released_name(self):
        with patch('inkora.service.tray_request',side_effect=[('1.4.0',),(),RuntimeError('No owner'),(__version__,)])as request, \
             patch('inkora.service.subprocess.Popen')as spawn:
            self.assertTrue(ensure_tray(self.database))
            self.assertEqual(request.call_args_list[1].args,(self.database,'Quit'))
            self.assertEqual(request.call_count,4);spawn.assert_called_once()

    def test_background_starts_agent_and_panel_without_tk_or_window_lock(self):
        from inkora.__main__ import main
        with patch.object(sys,'argv',['openink','--background','--database',str(self.database)]), \
             patch('inkora.branding.migrate_legacy_shortcut'),patch('inkora.service.ensure_agent')as agent, \
             patch('inkora.service.ensure_tray')as panel,patch('inkora.service.WindowLock')as lock,patch('inkora.__main__.tk.Tk')as tk:
            main();agent.assert_called_once();panel.assert_called_once();lock.assert_not_called();tk.assert_not_called()

    def test_disabled_startup_does_not_launch_agent_panel_or_window(self):
        store=Store(self.database)
        try:store.set_setting('autostart',False)
        finally:store.close()
        from inkora.__main__ import main
        with patch.object(sys,'argv',['openink','--background','--database',str(self.database)]), \
             patch('inkora.branding.migrate_legacy_shortcut'),patch('inkora.service.ensure_agent')as agent, \
             patch('inkora.service.ensure_tray')as panel,patch('inkora.__main__.tk.Tk')as tk:
            main();agent.assert_not_called();panel.assert_not_called();tk.assert_not_called()

    def test_menu_layout_and_tooltip_have_valid_dbus_variants(self):
        icon=PanelIcon(self.database);layout=icon.layout(0,-1,[])
        value=icon.GLib.Variant('(u(ia{sv}av))',(icon.revision,layout))
        self.assertEqual(len(value.unpack()[1][2]),7)
        self.assertEqual(icon.get_property(None,None,None,ITEM,'IconPixmap').unpack()[0][:2],(32,32))
        self.assertEqual(icon.get_property(None,None,None,MENU,'Version').unpack(),4)
        with patch('inkora.tray.subprocess.Popen')as spawn:
            icon.action(2);spawn.assert_not_called()
            icon.action(1);spawn.assert_called_once()

    def test_firmware_operation_disables_refresh_and_quit_without_stopping_worker(self):
        atomic_json(firmware_root()/'current.json',{'phase':'upload'})
        icon=PanelIcon(self.database)
        self.assertFalse(icon.menu_items()[5]['enabled']);self.assertFalse(icon.menu_items()[7]['enabled'])
        with patch('inkora.tray.stop_desktop')as stop:icon.action(7);stop.assert_not_called()

    def test_stopping_desktop_only_signals_local_processes(self):
        with patch('inkora.service.request')as agent,patch('inkora.service.tray_request')as panel:
            stop_desktop(self.database)
            agent.assert_called_once_with(self.database,'stop');panel.assert_called_once_with(self.database,'Quit')

    def test_enabled_network_queue_is_ordered_before_disabled_usb_queue(self):
        snapshot=replace(demo_snapshot(),serial='TEST220001',demo=False)
        devices='device for XP-2200-Series: usb://EPSON/XP-2200?serial=TEST220001\ndevice for Epson_XP_2200: dnssd://EPSON%20XP-2200%20Series._ipp._tcp.local/\n'
        states='printer XP-2200-Series disabled since Mon\nprinter Epson_XP_2200 is idle. enabled since Mon\n'
        with patch('inkora.printing.subprocess.run',side_effect=[self.response(devices),self.response(states)]):
            queues=cups_printers(snapshot)
        self.assertEqual(queues[0]['name'],'Epson_XP_2200');self.assertTrue(queues[0]['enabled'])
        self.assertFalse(queues[1]['enabled'])

    def test_hex_usb_descriptor_serial_is_compared_with_decoded_printer_serial(self):
        snapshot=replace(demo_snapshot(),serial='TEST220001',demo=False)
        uri='device for XP-2200: usb://EPSON/XP-2200?serial='+snapshot.serial.encode().hex()
        with patch('inkora.printing.subprocess.run',side_effect=[self.response(uri),self.response('printer XP-2200 is idle. enabled')]):
            self.assertTrue(cups_printers(snapshot)[0]['confirmed'])

    def test_disabled_queue_never_receives_a_print_job(self):
        from datetime import datetime,timezone
        snapshot=replace(demo_snapshot(),demo=False,ready=True,observed_at=datetime.now(timezone.utc).isoformat())
        with patch('inkora.printing.subprocess.run',side_effect=[
            self.response('device for XP-2200: ipp://192.168.1.55/ipp/print'),self.response('printer XP-2200 disabled since Mon')])as run:
            with self.assertRaisesRegex(ValueError,'désactivée'):submit_test_page(snapshot,'XP-2200',True)
            self.assertFalse(any(c.args[0][0]=='lp'for c in run.call_args_list))


if __name__=='__main__':unittest.main()
