"""No-printer tests for cartridge diagnosis, local agent and notification queue."""
from dataclasses import replace
from datetime import datetime,timezone,timedelta
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
from unittest.mock import patch
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'commun'))
from inkora.agent import Agent
from inkora.diagnostics import cartridge_state,merge_supply_alerts
from inkora.printer import Snapshot,parse_status
from inkora.reset import request_reset
from inkora.service import request,runtime_paths
from inkora.store import Store


def sample():
    return Snapshot('test-printer','192.168.1.55',datetime.now(timezone.utc).isoformat(),'Prête',True,100,60,
                    reported_ink={'cyan':100},firmware='06.58.IU05P2.FY22')


class FakeDesktop:
    def __init__(self):self.calls=[]
    def poll(self):pass
    def send(self,title,detail,critical=False):
        self.calls.append((title,detail,critical));return len(self.calls)


class DiagnosticTests(unittest.TestCase):
    def test_special_codes_never_become_percentages(self):
        self.assertEqual(cartridge_state(119)['state'],'unknown')
        self.assertIn('119',cartridge_state(119)['label'])
        self.assertEqual(cartridge_state(114)['state'],'error')
        self.assertEqual(cartridge_state(0)['state'],'empty')
        self.assertEqual(cartridge_state(110)['state'],'missing')
        self.assertEqual(cartridge_state(100,True)['state'],'unknown')

    def test_supply_alert_indexes_use_descriptions_not_proprietary_order(self):
        source={c:cartridge_state(114)for c in ['black','cyan','magenta','yellow']}
        result=merge_supply_alerts(source,{1:'Black ink',2:'Cyan ink',3:'Magenta ink',4:'Yellow ink'},
           [{'group':11,'index':2,'description':'defective cartridge'},
            {'group':11,'index':3,'description':'no cartridge'}])
        self.assertEqual(result['cyan']['state'],'defective')
        self.assertEqual(result['magenta']['state'],'missing')
        self.assertEqual(result['yellow']['state'],'error')
        self.assertEqual(source['cyan']['state'],'error')

    def test_unknown_descriptions_or_wrong_groups_are_not_assigned(self):
        base={'cyan':cartridge_state(119)}
        result=merge_supply_alerts(base,{2:'Unknown supply'},[{'group':11,'index':2,'description':'defective cartridge'}])
        self.assertEqual(result['cyan']['state'],'unknown')
        result=merge_supply_alerts(base,{2:'Cyan'},[{'group':10,'index':2,'description':'no cartridge'}])
        self.assertEqual(result['cyan']['state'],'unknown')

    def test_selected_hardware_reset_is_unavailable_and_never_writes(self):
        with patch('socket.socket',side_effect=AssertionError('No hardware IO')):
            result=request_reset(sample(),['cyan','magenta'])
        self.assertFalse(result['ok'])
        self.assertFalse(result['hardware_commands_sent'])
        self.assertFalse(result['local_levels_modified'])
        self.assertEqual(set(result['results']),{'cyan','magenta'})
        self.assertTrue(all(r['state']=='not_attempted'for r in result['results'].values()))


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.root=Path(self.folder.name)
        self.env=patch.dict(os.environ,{'XDG_RUNTIME_DIR':str(self.root)})
        self.env.start()
        self.path=self.root/'state.sqlite3';self.base=sample();self.desktop=FakeDesktop()
        self.store=Store(self.path);self.store.observe(self.base)
        self.store.calibrate(self.base,['cyan'],start=10);self.store.check_alerts(self.base)
        self.store.close()
    def tearDown(self):self.env.stop();self.folder.cleanup()

    def run_once(self):
        return Agent(self.path,reader=lambda *_:self.base,notifier=self.desktop).run(max_cycles=1)

    def test_notification_is_delivered_without_any_gui_and_not_repeated(self):
        self.assertTrue(self.run_once());self.assertEqual(len(self.desktop.calls),1)
        self.assertTrue(self.run_once());self.assertEqual(len(self.desktop.calls),1)
        s=Store(self.path);self.assertEqual(s.pending_notifications(),[])
        self.assertEqual(s.db.execute('SELECT delivery FROM notifications').fetchone()[0],'sent');s.close()

    def test_reset_without_ink_does_not_refill_or_rearm_warning(self):
        self.run_once();s=Store(self.path)
        before=s.estimates(self.base)
        s.record_chip_reset(self.base,['cyan']);s.close()
        self.run_once();s=Store(self.path)
        self.assertEqual(s.estimates(self.base),before)
        self.assertEqual(len(self.desktop.calls),1);s.close()

    def test_refill_supersedes_unsent_warning(self):
        s=Store(self.path);s.calibrate(self.base,['cyan'],start=100);s.close()
        self.run_once();self.assertEqual(self.desktop.calls,[])

    def test_disabling_desktop_delivery_preserves_pending_record(self):
        s=Store(self.path);s.set_setting('notifications',False);s.close()
        self.run_once();self.assertEqual(self.desktop.calls,[])
        s=Store(self.path);self.assertEqual(len(s.pending_notifications()),1)
        s.set_setting('notifications',True);s.close()
        self.run_once();self.assertEqual(len(self.desktop.calls),1)

    def test_notification_failure_is_recorded_without_losing_the_warning(self):
        class Failed(FakeDesktop):
            def send(self,*_):raise RuntimeError('Desktop unavailable')
        Agent(self.path,reader=lambda *_:self.base,notifier=Failed()).run(max_cycles=1)
        s=Store(self.path)
        self.assertEqual(s.db.execute('SELECT delivery FROM notifications').fetchone()[0],'failed')
        self.assertEqual(s.estimates(self.base)['cyan']['state'],'reserve')
        self.assertEqual(s.pending_notifications(),[]);s.close()

    def test_reminders_obey_interval_and_do_not_duplicate_pending_notifications(self):
        self.run_once();s=Store(self.path)
        s.set_setting('reminder_minutes',60)
        old=(datetime.now(timezone.utc)-timedelta(hours=2)).isoformat()
        with s.db:s.db.execute('UPDATE notifications SET attempt_at=?',(old,))
        s.queue_reminders(self.base);s.queue_reminders(self.base)
        self.assertEqual(len(s.pending_notifications()),1);s.close()

    def test_local_control_and_single_agent_lock(self):
        agent=Agent(self.path,reader=lambda *_:self.base,notifier=self.desktop)
        thread=threading.Thread(target=agent.run);thread.start()
        try:
            deadline=time.monotonic()+3
            while time.monotonic()<deadline:
                try:
                    info=request(self.path);break
                except OSError:time.sleep(.02)
            else:self.fail('Agent did not start')
            self.assertTrue(info['running'])
            self.assertFalse(Agent(self.path,reader=lambda *_:self.base,notifier=self.desktop).run(max_cycles=1))
            path,_=runtime_paths(self.path)
            self.assertEqual(path.stat().st_mode&0o777,0o600)
            with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)as client:
                client.connect(str(path));client.sendall(b'[]\n')
                self.assertFalse(json.loads(client.recv(4096))['ok'])
            self.assertTrue(request(self.path,'refresh')['ok'])
            with self.assertRaises(ValueError):request(self.path,'flash')
            request(self.path,'stop');thread.join(3)
            self.assertFalse(thread.is_alive());self.assertFalse(path.exists())
        finally:
            agent.stop.set();agent.wake.set();thread.join(3)


if __name__=='__main__':unittest.main()
