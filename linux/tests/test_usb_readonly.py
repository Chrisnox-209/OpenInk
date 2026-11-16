"""USB command boundary and real captured special states; no USB device opened."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'commun'))
from inkora.printer import parse_status
from inkora import usb_session
from inkora.usb import read_usb

FIXTURE=json.loads((Path(__file__).parent/'fixtures/normal-IU05P2-status.json').read_text())
RAW=bytes.fromhex(FIXTURE['raw_hex'])


class UsbSafetyTests(unittest.TestCase):
    def test_captured_status_reports_unknown_119_and_error_114(self):
        snapshot=parse_status(RAW,'192.168.1.55',b'IA:604,604,604,604;',b'vi:04:06.58.IU05P2.FY22;')
        self.assertFalse(snapshot.ready)
        self.assertEqual((snapshot.color_pages,snapshot.mono_pages),(101,60))
        self.assertEqual(snapshot.supplies['cyan']['state'],'error')
        for color in ['black','yellow','magenta']:
            self.assertEqual(snapshot.supplies[color]['state'],'unknown')
            self.assertEqual(snapshot.supplies[color]['raw_code'],119)
            self.assertIsNone(snapshot.reported_ink[color])

    def test_recovery_mode_is_rejected_without_opening_printer(self):
        d=SimpleNamespace(vendor_id=0x04b8,product_id=0x0007,path='1:1')
        with patch('epson_usb.backends.find_devices',return_value=[d]),patch.object(usb_session,'EpsonUsbPrinter')as constructor:
            with self.assertRaisesRegex(ValueError,'secours'):read_usb()
            constructor.assert_not_called()

    def test_active_print_queue_is_not_interrupted_or_opened(self):
        d=SimpleNamespace(vendor_id=0x04b8,product_id=0x11b1,path='1:2')
        with patch('epson_usb.backends.find_devices',return_value=[d]),patch.object(usb_session,'EpsonUsbPrinter')as constructor, \
             patch('inkora.usb.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout='queue-10 owner'))as command:
            with self.assertRaisesRegex(ValueError,'file'):read_usb()
            constructor.assert_not_called()
            self.assertEqual(command.call_args.args[0],['lpstat','-W','not-completed','-o'])

    def test_only_three_standard_read_commands_are_sent(self):
        d=SimpleNamespace(vendor_id=0x04b8,product_id=0x11b1,path='1:2')
        calls=[]
        class Reader:
            def __enter__(self):return self
            def __exit__(self,*_):pass
            def command(self,name,value):
                calls.append((name,value))
                return {b'st':RAW,b'ia':b'IA:604,604,604,604;',b'vi':b'vi:04:06.58.IU05P2.FY22;'}[name]
        with patch('epson_usb.backends.find_devices',return_value=[d]),patch.object(usb_session,'EpsonUsbPrinter',return_value=Reader())as constructor, \
             patch('inkora.usb.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout='')):
            snapshot=read_usb()
            self.assertEqual(snapshot.transport,'USB')
            self.assertEqual(calls,[(b'st',b'\x01'),(b'ia',b'\x00'),(b'vi',b'\x04')])
            self.assertIsNone(constructor.call_args.kwargs['write_key'])
            self.assertEqual(constructor.call_args.kwargs['interface'],1)


if __name__=='__main__':unittest.main()
