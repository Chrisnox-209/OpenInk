"""Branding, print-job boundary and passive/targeted verification. No hardware."""
from dataclasses import replace
from datetime import datetime,timezone
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'commun'))
from inkora.branding import ASSETS,TEST_PAGE,initial_geometry,migrate_legacy_shortcut,active_monitor
from inkora.firmware import atomic_json,firmware_root,load_assets
from inkora.firmware_usb import V2Usb,normal_usb_generation,normal_usb_port
from inkora.printer import demo_snapshot
from inkora.printing import cups_printers,submit_test_page


class OpenInkTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix='openink-test-');self.root=Path(self.temporary.name)
        self.env=patch.dict(os.environ,{'XDG_DATA_HOME':str(self.root)});self.env.start()
        self.snapshot=replace(demo_snapshot(),demo=False,serial='TEST220001',printer_id='TEST220001',ready=True,
                              observed_at=datetime.now(timezone.utc).isoformat())
    def tearDown(self):self.env.stop();self.temporary.cleanup()

    def test_window_minimum_area_is_at_least_45_percent_on_hd_and_4k(self):
        for width,height in[(1366,768),(1920,1080),(2560,1440),(3840,2160)]:
            start_w,start_h,min_w,min_h=initial_geometry(width,height)
            self.assertGreaterEqual(min_w*min_h/(width*height),.45)
            self.assertLessEqual(start_w,width);self.assertLessEqual(start_h,height)
            self.assertGreaterEqual(start_w,min_w);self.assertGreaterEqual(start_h,min_h)

    def test_multiple_monitors_use_one_monitor_instead_of_the_combined_desktop(self):
        monitors='Monitors: 2\n 0: +*DP-1 5120/620x2880/340+5120+0 DP-1\n 1: +DP-3 5120/620x2880/340+0+0 DP-3\n'
        with patch('inkora.branding.subprocess.run',return_value=self.response(monitors)):
            self.assertEqual(active_monitor(SimpleNamespace(winfo_pointerxy=lambda:(200,300))),(5120,2880,0,0))

    def test_vector_logo_and_pdf_test_page_are_packaged(self):
        self.assertTrue((ASSETS/'openink-logo.svg').is_file())
        self.assertTrue((ASSETS/'openink-1024.png').is_file())
        self.assertTrue(TEST_PAGE.read_bytes().startswith(b'%PDF-'))

    def test_only_known_old_shortcut_is_migrated_and_backed_up(self):
        applications=self.root/'applications';applications.mkdir();legacy=applications/'inkora.desktop'
        original='[Desktop Entry]\nName=Inkora\nComment=Suivi des cartouches Epson\nExec="/test/app/linux/Lancer-Inkora.sh"\nIcon=/test/inkora.svg\n'
        legacy.write_text(original);installed=self.root/'openink.desktop';installed.touch()
        self.assertTrue(migrate_legacy_shortcut(applications,installed))
        self.assertIn('Hidden=true',legacy.read_text())
        self.assertEqual((applications/'inkora.desktop.before-openink').read_text(),original)

    def response(self,stdout='',code=0):return SimpleNamespace(stdout=stdout,stderr='',returncode=code)

    def test_test_page_uses_explicit_queue_one_copy_and_reports_acceptance_only(self):
        with patch('inkora.printing.subprocess.run',side_effect=[
            self.response('device for Epson_XP_2200: ipp://192.168.1.55/ipp/print\n'),
            self.response(),self.response('request id is Epson_XP_2200-56 (1 file(s))')])as run:
            result=submit_test_page(self.snapshot,'Epson_XP_2200')
        self.assertEqual(run.call_args.args[0][:5],['lp','-d','Epson_XP_2200','-n','1'])
        self.assertFalse(result['printed_verified']);self.assertEqual(result['job_id'],'Epson_XP_2200-56')

    def test_firmware_operation_prevents_test_printing(self):
        atomic_json(firmware_root()/'current.json',{'phase':'waiting'})
        with patch('inkora.printing.subprocess.run')as run:
            with self.assertRaises(ValueError):submit_test_page(self.snapshot,'Epson_XP_2200')
            run.assert_not_called()

    def test_unconfirmed_mdns_queue_requires_user_confirmation(self):
        with patch('inkora.printing.subprocess.run',return_value=self.response('device for XP-2200: dnssd://EPSON-XP-2200._ipp._tcp.local/'))as run:
            with self.assertRaisesRegex(ValueError,'Confirme'):submit_test_page(self.snapshot,'XP-2200')
            self.assertEqual(run.call_count,1)

    def test_busy_queue_and_demo_never_submit_lp(self):
        with patch('inkora.printing.subprocess.run')as run:
            with self.assertRaises(ValueError):submit_test_page(replace(self.snapshot,demo=True),'Epson_XP_2200')
            run.assert_not_called()
        with patch('inkora.printing.subprocess.run',side_effect=[self.response('device for Epson_XP_2200: ipp://192.168.1.55/ipp/print'),self.response('Epson_XP_2200-55 owner')])as run:
            with self.assertRaisesRegex(ValueError,'occupée'):submit_test_page(self.snapshot,'Epson_XP_2200')
            self.assertFalse(any(call.args[0][0]=='lp'for call in run.call_args_list))

    def test_stale_or_unready_snapshot_never_queues_a_job(self):
        with patch('inkora.printing.subprocess.run')as run:
            with self.assertRaises(ValueError):submit_test_page(replace(self.snapshot,ready=False),'Epson_XP_2200')
            with self.assertRaises(ValueError):submit_test_page(replace(self.snapshot,observed_at='2000-01-01T00:00:00+00:00'),'Epson_XP_2200')
            run.assert_not_called()

    def test_passive_restart_detection_reads_only_cached_sysfs_attributes(self):
        node=self.root/'1-3';node.mkdir()
        for key,value in{'idVendor':'04b8','idProduct':'11b1','serial':'TEST220001','busnum':'001','devnum':'009'}.items():(node/key).write_text(value)
        self.assertEqual(normal_usb_generation('TEST220001',self.root),'1:9')
        self.assertIsNone(normal_usb_generation('OTHER',self.root))

    def test_restart_tracks_the_verified_physical_port_when_usb_serial_format_differs(self):
        node=self.root/'1-5';node.mkdir()
        for key,value in{'idVendor':'04b8','idProduct':'11b1','serial':'USB-DESCRIPTOR-FORMAT','busnum':'001','devnum':'009'}.items():(node/key).write_text(value)
        self.assertEqual(normal_usb_port('1:9',self.root),'1-5')
        (node/'devnum').write_text('010')
        self.assertEqual(normal_usb_generation('EEPROM-SERIAL',self.root,physical_port='1-5'),'1:10')

    def test_targeted_check_hashes_every_modified_byte_and_the_recovery_region(self):
        manifest,payload=load_assets();manifest=copy.deepcopy(manifest);boot=b'\0'*0x30000
        manifest['boot_sha256']=hashlib.sha256(boot).hexdigest()
        quick=manifest['quick_range'];offset=quick['offset']-0x2C000
        for corrupt in(False,True):
            backend=V2Usb(manifest,payload,'TEST220001');body=bytearray(payload[offset:offset+quick['length']])
            if corrupt:body[len(body)//2]^=1
            def chunks(start,count,progress):
                self.assertIn((start,count),[(quick['offset'],quick['length']),(0,0x30000)])
                yield start,bytes(body)if start else boot
            def memory(address,count):
                if address==0x20030000:return bytes.fromhex(manifest['main_header'])
                if address==0x43E45C00:return bytes.fromhex(manifest['public_key'])
                return bytes.fromhex(manifest['baselines']['V2']['code_windows'][str(address)])
            with patch.object(backend,'open'),patch.object(backend,'_flash_chunks',side_effect=chunks),patch.object(backend,'_memory',side_effect=memory),patch.object(backend,'identity',return_value=replace(self.snapshot,chipless=True)):
                if corrupt:
                    with self.assertRaisesRegex(ValueError,'secteurs modifiés'):backend.quick_verify(lambda *_:None)
                else:
                    backend.quick_verify(lambda *_:None)
                    self.assertEqual(backend.verification_scope,'modified_regions_and_boot')


if __name__=='__main__':unittest.main()
