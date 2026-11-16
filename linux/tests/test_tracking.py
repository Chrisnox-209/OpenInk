"""Behaviour tests: real counters, calibration isolation and persistence."""
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"commun"))
from inkora.printer import Snapshot, parse_status, elements, tlv, unpack_tlv
from inkora.store import Store


def sample(**kwargs):
    base=Snapshot("printer-A","192.168.1.55",datetime.now(timezone.utc).isoformat(),
                  "Prête",True,99,60,2,{"black":100,"cyan":100,"magenta":100,"yellow":100},True)
    return replace(base,**kwargs)


class TrackingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/"state.sqlite3"
        self.store=Store(self.path)
        self.base=sample()
        self.store.observe(self.base)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_fake_printer_percent_never_initializes_local_ink(self):
        self.assertTrue(all(v is None for v in self.store.estimates(self.base).values()))

    def test_color_and_mono_are_real_separate_counters(self):
        self.assertEqual(self.base.total_pages,159)

    def test_color_consumption_and_black_conservative_count(self):
        self.store.calibrate(self.base,["black","cyan","magenta","yellow"],"604XL")
        later=replace(self.base,color_pages=109,mono_pages=65)
        e=self.store.estimates(later)
        self.assertEqual(e["black"]["pages"],485)
        self.assertEqual(e["cyan"]["pages"],340)
        self.assertAlmostEqual(e["black"]["percent"],97)

    def test_reset_one_color_preserves_other_baselines(self):
        self.store.calibrate(self.base,["black","cyan"],"604XL")
        later=replace(self.base,color_pages=109,mono_pages=65)
        self.store.calibrate(later,["cyan"],"604")
        e=self.store.estimates(later)
        self.assertEqual(e["cyan"]["pages"],130)
        self.assertEqual(e["black"]["pages"],485)
        self.assertIsNone(e["magenta"])

    def test_partial_fill(self):
        self.store.calibrate(self.base,["black"],"604",50)
        self.assertEqual(self.store.estimates(self.base)["black"]["pages"],75)

    def test_ink_never_negative(self):
        self.store.calibrate(self.base,["cyan"],"604")
        self.assertEqual(self.store.estimates(replace(self.base,color_pages=1000))["cyan"]["pages"],0)

    def test_counter_rollback_invalidates_persistently(self):
        self.store.calibrate(self.base,["black","cyan"])
        self.store.observe(replace(self.base,color_pages=1,mono_pages=1))
        self.store.observe(replace(self.base,color_pages=300,mono_pages=300))
        self.assertIsNone(self.store.estimates(self.store.latest())["cyan"])
        self.assertTrue(any(e["title"]=="Compteurs réinitialisés" for e in self.store.events("printer-A")))

    def test_unknown_counters_prevent_reset(self):
        with self.assertRaises(ValueError):
            self.store.calibrate(replace(self.base,color_pages=None),["black"])

    def test_printers_are_isolated(self):
        self.store.calibrate(self.base,["cyan"])
        self.assertIsNone(self.store.estimates(replace(self.base,printer_id="printer-B"))["cyan"])

    def test_custom_yield(self):
        self.store.calibrate(self.base,["magenta"],"Personnalisé",100,600)
        self.assertEqual(self.store.estimates(replace(self.base,color_pages=109))["magenta"]["pages"],590)

    def test_usage_factor_is_explicit(self):
        self.store.calibrate(self.base,["cyan"],"604")
        self.store.set_setting("coverage",5.0)
        self.assertEqual(self.store.estimates(replace(self.base,color_pages=109))["cyan"]["pages"],16)

    def test_settings_and_calibration_survive_restart(self):
        self.store.calibrate(self.base,["black"],"604XL",88)
        self.store.set_setting("host","192.168.1.90")
        self.store.close()
        self.store=Store(self.path)
        self.assertEqual(self.store.setting("host"),"192.168.1.90")
        self.assertEqual(self.store.estimates(self.store.latest())["black"]["percent"],88)

    def test_invalid_inputs_leave_database_unchanged(self):
        for colors,profile,level,capacity in [([],"604",100,None),(["red"],"604",100,None),
                (["cyan"],"unknown",100,None),(["cyan"],"604",101,None),
                (["cyan"],"604",float("nan"),None),(["cyan"],"Personnalisé",100,0)]:
            with self.subTest(colors=colors,profile=profile,level=level):
                with self.assertRaises(ValueError):self.store.calibrate(self.base,colors,profile,level,capacity)
        self.assertIsNone(self.store.estimates(self.base)["cyan"])

    def test_export_uses_observed_values(self):
        target=Path(self.temp.name)/"export.json"
        self.store.export("printer-A",target)
        data=json.loads(target.read_text())
        self.assertEqual(data["readings"][0]["color_pages"],99)
        self.assertTrue(data["readings"][0]["chipless"])


class ProtocolTests(unittest.TestCase):
    def packet(self,ink=100):
        counters=b"\xff"*8+(99).to_bytes(4,"little")+(60).to_bytes(4,"little")+(2).to_bytes(4,"little")
        fields=b"\x01\x01\x04"+b"\x0f\x0d\x03"+bytes((1,0,ink,5,3,100,4,2,100,3,1,100))
        fields+=bytes((54,len(counters)))+counters+b"\x40\x04TEST"
        return b"\0@BDC ST2\r\n"+len(fields).to_bytes(2,"little")+fields

    def test_actual_status_layout(self):
        s=parse_status(self.packet(),"192.168.1.55",b"\0@BDC PS\r\nIA:00;,,,;\f",b"\0vi:04:06.58.IU05P2.FY22;\f")
        self.assertEqual((s.color_pages,s.mono_pages,s.blank_pages),(99,60,2))
        self.assertEqual(s.reported_ink["cyan"],100)
        self.assertTrue(s.chipless)
        self.assertTrue(s.ready)
        self.assertEqual(s.firmware,"06.58.IU05P2.FY22")

    def test_error_value_is_not_percent(self):
        self.assertIsNone(parse_status(self.packet(114),"192.168.1.55").reported_ink["black"])

    def test_missing_mode_probe_is_not_reported_as_genuine_levels(self):
        self.assertIsNone(parse_status(self.packet(),"192.168.1.55").chipless)

    def test_truncated_status_rejected(self):
        for packet in (b"bad",self.packet()[:-1],self.packet()+b"\0"):
            with self.assertRaises(ValueError):parse_status(packet,"192.168.1.55")

    def test_ber_lengths_and_truncation(self):
        data=bytes(range(255))*3
        tag,value,end=unpack_tlv(tlv(4,data))
        self.assertEqual((tag,value,end),(4,data,len(tlv(4,data))))
        with self.assertRaises(ValueError):unpack_tlv(tlv(4,data)[:-1])
        with self.assertRaises(ValueError):unpack_tlv(b"\x04\x80")


if __name__=="__main__":unittest.main()
