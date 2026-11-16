"""Firmware failure boundaries and ink semantics. Never opens real hardware."""
from dataclasses import replace
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'commun'))
from inkora.firmware import (COOLDOWN_SECONDS,V2_SHA,atomic_json,current_operation,firmware_root,
    boot_id,hardware_session,job_folder,load_assets,prepare_job,remaining_wait,require_monitoring_allowed)
from inkora.flash_worker import FlashJob
from inkora.firmware_usb import V2Usb,normal_usb_device,require_empty_queues
from inkora.printer import COLORS,demo_snapshot
from inkora.store import Store


class Clock:
    def __init__(self):self.now=1000000;self.sleeps=[];self.observer=None
    def __call__(self):return self.now
    def sleep(self,seconds):
        if self.observer:
            observer=self.observer;self.observer=None;observer()
        self.sleeps.append(seconds);self.now+=seconds


class FirmwareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.manifest,cls.payload=load_assets()

    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix='inkora-firmware-test-')
        self.root=Path(self.temporary.name)
        self.environment=patch.dict('os.environ',{'XDG_DATA_HOME':str(self.root/'data')})
        self.environment.start()
        self.store=Store(self.root/'test.sqlite3')
        self.before=replace(demo_snapshot(),printer_id='TEST220001',serial='TEST220001',demo=False,chipless=False)
        self.after=replace(self.before,chipless=True)
        self.store.observe(self.before);self.store.calibrate(self.before,list(COLORS),'604',60)
        self.clock=Clock();self.calls=[];self.restart=[]
        self.failure=None;self.baseline='official'
        self.verification_baseline='V2'
        self.fast_restart=False
        self.commit_reply=b'fl:03:OK;\x0c'

    def tearDown(self):
        self.store.close();self.environment.stop();self.temporary.cleanup()

    def prepare(self,plan=None):
        return prepare_job(self.store.path,self.before,plan or {'cyan':{'action':'keep'}},
                           self.store.estimates(self.before),True,risk_acknowledged=True,usb_confirmed=True)

    def worker(self,identifier):
        test=self
        class Backend:
            def __init__(self,*_):pass
            def open(self):test.calls.append(('open',test.clock()));return test.before
            def backup(self,path,progress):
                test.calls.append(('backup',test.clock()))
                if test.failure=='backup':raise ValueError('Unknown baseline')
                path.write_bytes(b'FAKE backup, never restore');progress(1,1)
                return {'baseline':test.baseline,'size':16*1024*1024,'sha256':'test-only'}
            def stage(self,progress,before_update):
                before_update();test.calls.append(('stage',test.clock()));progress(1,1)
                if test.failure=='stage':raise ValueError('Upload interrupted')
            def commit(self,before_commit):
                before_commit();test.calls.append(('commit',test.clock()))
                if test.failure=='commit':raise ValueError('Reply lost after send')
                return test.commit_reply
            def restarted_device(self):
                sent=next((at for name,at in test.calls if name=='commit'),test.clock())
                return '1:99'if test.fast_restart and test.clock()-sent>=11 else None
            def quick_verify(self,progress):
                test.calls.append(('quick_verify',test.clock()))
                if test.failure=='verify':raise ValueError('Not reachable')
                self.verified_baseline='V2';self.verification_scope='modified_regions_and_boot'
                progress(1,1);return test.after
            def verify(self,progress,allow_unchanged=False):
                test.calls.append(('verify',test.clock()))
                if any(name=='commit'for name,_ in test.calls):
                    sent=next(at for name,at in test.calls if name=='commit')
                    test.assertGreaterEqual(test.clock()-sent,COOLDOWN_SECONDS)
                if test.failure=='verify':raise ValueError('Not reachable')
                self.verified_baseline=test.verification_baseline
                self.verification_scope='full'
                progress(1,1);return test.after
            def close(self,protocol=True):test.calls.append(('close_protocol'if protocol else'close_host_only',test.clock()))
        return FlashJob(identifier,Backend,self.clock,self.clock.sleep,
                        lambda _:self.calls.append(('stop_monitor',self.clock())),lambda _:self.restart.append(True),monotonic=self.clock)

    def test_v2_pinned_payload_and_no_warning_prototype(self):
        self.assertEqual(self.manifest['payload_sha256'],V2_SHA)
        self.assertFalse(self.manifest['warning_prototype_included'])
        with patch('inkora.firmware_usb.EpsonUsbPrinter')as connection:
            with self.assertRaises(ValueError):V2Usb(self.manifest,self.payload[:-1]+b'X','TEST220001')
            connection.assert_not_called()

    def test_install_requires_explicit_confirmation_and_known_remaining_ink(self):
        with self.assertRaises(ValueError):prepare_job(self.store.path,self.before,{},self.store.estimates(self.before),False)
        self.store.db.execute('DELETE FROM cartridges WHERE color=?',('yellow',));self.store.db.commit()
        with self.assertRaisesRegex(ValueError,'Jaune'):self.prepare()
        self.assertIsNone(current_operation())

    def test_full_cartridge_requires_actual_ink_confirmation(self):
        with self.assertRaises(ValueError):self.prepare({'cyan':{'action':'full','percent':100,'ink_added':False}})
        self.assertIsNone(current_operation())

    def test_failed_backup_never_stages_or_changes_levels(self):
        before=self.store.estimates(self.before);identifier=self.prepare();self.failure='backup'
        self.assertFalse(self.worker(identifier).run())
        self.assertFalse(any(name in {'stage','commit'}for name,_ in self.calls))
        self.assertEqual(self.store.estimates(self.before),before)
        self.assertEqual(current_operation()['phase'],'failed_before_update')
        require_monitoring_allowed();self.assertEqual(self.restart,[True])

    def test_selected_full_refill_applies_only_after_wait_and_successful_verification(self):
        before=self.store.estimates(self.before)
        identifier=self.prepare({'cyan':{'action':'full','percent':100,'ink_added':True,'profile':'604'},'black':{'action':'keep'}})
        self.assertTrue(self.worker(identifier).run())
        names=[name for name,_ in self.calls]
        self.assertLess(names.index('backup'),names.index('stage'));self.assertLess(names.index('commit'),names.index('verify'))
        estimates=self.store.estimates(self.after)
        self.assertEqual(estimates['cyan']['percent'],100)
        for color in ['black','magenta','yellow']:self.assertEqual(estimates[color],before[color])
        self.assertEqual(sum(name=='commit'for name,_ in self.calls),1)
        self.assertTrue(current_operation()['verified']);self.assertTrue(self.clock.sleeps)

    def test_flash_without_added_ink_preserves_all_estimates(self):
        before=self.store.estimates(self.before);identifier=self.prepare()
        self.assertTrue(self.worker(identifier).run())
        self.assertEqual(self.store.estimates(self.after),before)

    def test_pages_printed_between_declaration_and_verification_are_not_free_ink(self):
        identifier=self.prepare({'cyan':{'action':'full','percent':100,'ink_added':True,'profile':'604'}})
        self.after=replace(self.after,color_pages=self.before.color_pages+10)
        self.assertTrue(self.worker(identifier).run())
        self.assertAlmostEqual(self.store.estimates(self.after)['cyan']['percent'],100-10/130*100)

    def test_counter_rollback_keeps_firmware_success_and_requests_manual_tracking_review(self):
        identifier=self.prepare({'cyan':{'action':'full','percent':100,'ink_added':True}})
        self.after=replace(self.after,color_pages=1,mono_pages=1)
        self.assertTrue(self.worker(identifier).run())
        self.assertTrue(current_operation()['verified'])
        self.assertFalse(current_operation()['levels_applied'])
        self.assertIsNone(self.store.estimates(self.after)['cyan'])
        self.assertTrue(any(item['kind']=='tracking'for item in self.store.pending_notifications()))

    def test_lost_commit_reply_blocks_monitoring_and_never_retries_or_refills(self):
        before=self.store.estimates(self.before)
        identifier=self.prepare({'cyan':{'action':'full','percent':100,'ink_added':True}});self.failure='commit'
        def during_wait():
            with self.assertRaisesRegex(ValueError,'quinze minutes'):self.worker(identifier).run(verify_only=True)
            with self.assertRaises(ValueError):require_monitoring_allowed()
        self.clock.observer=during_wait
        self.assertFalse(self.worker(identifier).run())
        self.assertEqual(current_operation()['phase'],'verification_required')
        self.assertEqual(self.store.estimates(self.before),before)
        with self.assertRaises(ValueError):require_monitoring_allowed()
        with self.assertRaises(ValueError):self.worker(identifier).run()
        self.assertEqual(sum(name=='commit'for name,_ in self.calls),1)
        self.assertGreaterEqual(sum(self.clock.sleeps),COOLDOWN_SECONDS)
        self.assertFalse(self.restart)

    def test_manual_verification_after_interruption_applies_plan_once(self):
        identifier=self.prepare({'cyan':{'action':'estimate','percent':45,'profile':'604'}})
        self.failure='commit';self.worker(identifier).run()
        self.clock.now+=COOLDOWN_SECONDS+1;self.failure=None
        self.assertTrue(self.worker(identifier).run(verify_only=True))
        first=self.store.estimates(self.after)
        self.assertEqual(first['cyan']['percent'],45)
        self.assertTrue(self.worker(identifier).run(verify_only=True))
        self.assertEqual(self.store.estimates(self.after),first)
        self.assertEqual(sum(name=='commit'for name,_ in self.calls),1)

    def test_already_v2_does_not_send_another_flash(self):
        self.baseline='V2';identifier=self.prepare()
        self.assertTrue(self.worker(identifier).run())
        self.assertFalse(any(name in {'stage','commit'}for name,_ in self.calls))
        self.assertFalse(current_operation()['commit_attempted'])

    def test_upload_failure_keeps_ink_and_journal_across_process_restart(self):
        before=self.store.estimates(self.before);identifier=self.prepare();self.failure='stage'
        self.worker(identifier).run()
        self.assertTrue(current_operation()['update_mode_attempted'])
        self.assertFalse(current_operation()['commit_attempted'])
        self.assertEqual(self.store.estimates(self.before),before)
        self.assertTrue(self.worker(identifier).state['update_mode_attempted'])
        with self.assertRaises(ValueError):require_monitoring_allowed()
        self.assertGreaterEqual(sum(self.clock.sleeps),COOLDOWN_SECONDS)

    def test_failed_postflash_verification_cannot_apply_full_gauge(self):
        before=self.store.estimates(self.before)
        identifier=self.prepare({'cyan':{'action':'full','percent':100,'ink_added':True}});self.failure='verify'
        self.assertFalse(self.worker(identifier).run())
        self.assertEqual(self.store.estimates(self.before),before)
        self.assertFalse(current_operation()['levels_applied'])

    def test_exclusive_lease_and_malformed_journal_fail_closed(self):
        with hardware_session(firmware=True):
            with self.assertRaises(ValueError):
                with hardware_session():pass
        atomic_json(firmware_root()/'current.json',{'bad':'journal'})
        with self.assertRaises(ValueError):require_monitoring_allowed()

    def test_normal_device_guard_refuses_recovery_even_with_normal_connected(self):
        devices=[SimpleNamespace(vendor_id=0x04b8,product_id=pid,path=str(pid))for pid in(0x11b1,0x0007)]
        with patch('epson_usb.backends.find_devices',return_value=devices),patch('inkora.firmware_usb.EpsonUsbPrinter')as opener:
            with self.assertRaisesRegex(ValueError,'secours'):normal_usb_device()
            opener.assert_not_called()

    def test_busy_queue_is_never_cancelled(self):
        with patch('inkora.firmware_usb.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout='Epson-10 owner'))as command:
            with self.assertRaises(ValueError):require_empty_queues()
            self.assertEqual(command.call_count,1)
            self.assertEqual(command.call_args.args[0],['lpstat','-W','not-completed','-o'])

    def test_memory_reads_outside_pinned_regions_are_rejected(self):
        backend=V2Usb(self.manifest,self.payload,'TEST220001')
        backend.printer=SimpleNamespace(command=lambda *_:self.fail('USB command must not be sent'))
        with self.assertRaises(ValueError):backend._memory(0x1000,64)

    def test_commit_timeout_closes_only_host_handle_and_is_not_retried(self):
        backend=V2Usb(self.manifest,self.payload,'TEST220001');session=SimpleNamespace(connected=True)
        calls=[]
        class Printer:
            def __init__(self):self.session=session
            def command(self,*args,**kwargs):calls.append((args,kwargs));raise TimeoutError('Lost reply')
            def close(self):calls.append(('host_closed',session.connected))
        backend.printer=Printer();backend.staged=True;backend.metadata=b'checked'
        with patch('inkora.firmware_usb.require_empty_queues'),patch.object(backend,'_verify_staged'),patch.object(backend,'_memory',return_value=b'checked'):
            with self.assertRaises(TimeoutError):backend.commit(lambda:calls.append('journal_saved'))
        self.assertEqual(calls[0],'journal_saved')
        self.assertEqual(calls[1],((b'gm',b'\x03'),{'tries':1}))
        self.assertEqual(calls[2],('host_closed',False))

    def memory_data(self,address,count):
        if address==0x43E45C00:return bytes.fromhex(self.manifest['public_key'])
        return bytes.fromhex(self.manifest['baselines']['V2']['code_windows'][str(address)])

    def test_postflash_requires_entire_main_and_boot_hashes_not_only_samples(self):
        manifest=copy.deepcopy(self.manifest);boot=b'\0'*0x30000
        manifest['boot_sha256']=hashlib.sha256(boot).hexdigest()
        for corrupt in (False,True):
            backend=V2Usb(manifest,self.payload,'TEST220001')
            main=bytearray(self.payload[0x4000:])
            if corrupt:main[0x123456]^=1
            def chunks(start,count,progress):yield start,bytes(main)if start==0x30000 else boot
            with patch.object(backend,'open'),patch.object(backend,'identity',return_value=self.after), \
                 patch.object(backend,'_flash_chunks',side_effect=chunks),patch.object(backend,'_memory',side_effect=self.memory_data):
                if corrupt:
                    with self.assertRaisesRegex(ValueError,'principal V2'):backend.verify(lambda *_:None)
                else:self.assertEqual(backend.verify(lambda *_:None).serial,'TEST220001')

    def test_unknown_flash_baseline_cannot_authorize_staging(self):
        manifest=copy.deepcopy(self.manifest);boot=b'\0'*0x30000
        manifest['boot_sha256']=hashlib.sha256(boot).hexdigest()
        data=bytearray(boot+self.payload[0x4000:]+b'\xff'*(0x1000000-0xC90000))
        data[0x654321]^=1
        backend=V2Usb(manifest,self.payload,'TEST220001');backend.printer=object()
        with patch.object(backend,'_flash_chunks',return_value=iter([(0,bytes(data))])):
            with self.assertRaisesRegex(ValueError,'inconnu'):backend.backup(self.root/'bad-baseline.bin',lambda *_:None)
        self.assertFalse(backend.backup_confirmed)
        with self.assertRaises(ValueError):backend.stage(lambda *_:self.fail('No upload'),lambda:self.fail('No update command'))

    def test_staged_metadata_change_refuses_commit(self):
        backend=V2Usb(self.manifest,self.payload,'TEST220001');backend.staged=True
        backend.metadata=b'original metadata'
        manager=bytearray(32);manager[5]=2;manager[8:10]=b'\x01\x06'
        with patch.object(backend,'_memory',side_effect=[bytes(manager),b'\x01'+b'\0'*15,b'changed metadata']):
            with self.assertRaisesRegex(ValueError,'métadonnées'):backend._verify_staged()

    def test_wall_clock_jump_cannot_skip_postflash_wait(self):
        state={'boot_id':boot_id(),'no_contact_before':1000,'no_contact_before_uptime':1000}
        self.assertEqual(remaining_wait(state,clock=lambda:100000,uptime=lambda:100),900)

    def test_manual_check_of_intact_original_unlocks_monitoring_without_applying_refill(self):
        before=self.store.estimates(self.before)
        identifier=self.prepare({'cyan':{'action':'full','percent':100,'ink_added':True}})
        self.failure='stage';self.worker(identifier).run()
        self.clock.now+=COOLDOWN_SECONDS+1;self.failure=None;self.verification_baseline='official'
        self.assertFalse(self.worker(identifier).run(verify_only=True))
        self.assertEqual(current_operation()['phase'],'unchanged')
        require_monitoring_allowed()
        self.assertEqual(self.store.estimates(self.before),before)
        self.assertNotEqual(self.prepare(),identifier)

    def test_normal_confirmed_restart_uses_targeted_check_without_fifteen_minute_delay(self):
        self.fast_restart=True;identifier=self.prepare()
        self.assertTrue(self.worker(identifier).run())
        self.assertLess(sum(self.clock.sleeps),60)
        self.assertTrue(any(name=='quick_verify'for name,_ in self.calls))
        self.assertFalse(any(name=='verify'for name,_ in self.calls))
        self.assertEqual(current_operation()['verification_scope'],'modified_regions_and_boot')
        self.assertEqual(current_operation()['no_contact_before'],0)

    def test_risk_and_usb_acknowledgments_are_required_before_preparing_an_install(self):
        estimates=self.store.estimates(self.before)
        with self.assertRaisesRegex(ValueError,'risques'):
            prepare_job(self.store.path,self.before,{},estimates,True)
        with self.assertRaisesRegex(ValueError,'USB'):
            prepare_job(self.store.path,self.before,{},estimates,True,risk_acknowledged=True)

    def test_missing_commit_ack_keeps_long_wait_even_if_normal_device_returns(self):
        self.fast_restart=True;self.commit_reply=None;identifier=self.prepare()
        self.assertTrue(self.worker(identifier).run())
        self.assertGreaterEqual(sum(self.clock.sleeps),COOLDOWN_SECONDS)
        self.assertFalse(any(name=='quick_verify'for name,_ in self.calls))


if __name__=='__main__':unittest.main()
