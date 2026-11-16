"""Preferences and contrast boundaries for the presentation-only themes."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'commun'))
from inkora.theme import color
from inkora.store import Store
from inkora.printer import demo_snapshot,COLORS


class ThemeTests(unittest.TestCase):
    def test_light_theme_preserves_existing_colours(self):
        for value in('#FFFFFF','#20283D','#FFF0EE','#23B8D4','white',None):
            self.assertEqual(color(value,'light'),value)

    def test_dark_foreground_white_stays_white_on_coloured_buttons(self):
        self.assertEqual(color('#FFFFFF','dark',True),'#FFFFFF')
        self.assertEqual(color('white','dark'),'#2B2D31')
        self.assertEqual(color('#20283D','dark',True),'#F2F3F5')

    def test_dark_text_contrasts_with_surfaces_and_flash_warning(self):
        def luminance(hex_):
            channels=[int(hex_[i:i+2],16)/255 for i in(1,3,5)]
            linear=[c/12.92 if c<=.04045 else((c+.055)/1.055)**2.4 for c in channels]
            return sum(c*w for c,w in zip(linear,(.2126,.7152,.0722)))
        for fg,bg in[('#20283D','#FFFFFF'),('#818A9E','#FFFFFF'),('#A52D26','#FFF0EE'),('#2563EB','#E8F1FF'),('#7560E8','#FFFFFF')]:
            a,b=sorted((luminance(color(fg,'dark',True)),luminance(color(bg,'dark'))))
            self.assertGreaterEqual((b+.05)/(a+.05),4.5,(fg,bg))

    def test_saved_preferences_preserve_ink_and_history(self):
        with tempfile.TemporaryDirectory()as temporary:
            path=Path(temporary)/'settings.sqlite3';store=Store(path);snapshot=demo_snapshot();store.observe(snapshot)
            for c in COLORS:store.calibrate(snapshot,[c],'604',65)
            before=store.estimates(snapshot);history=store.events(snapshot.printer_id)
            store.set_setting('theme','dark');store.set_setting('autostart',False)
            self.assertEqual(store.estimates(snapshot),before);self.assertEqual(store.events(snapshot.printer_id),history)
            store.close();store=Store(path)
            try:
                self.assertEqual(store.setting('theme'),'dark');self.assertIs(store.setting('autostart'),False)
                with self.assertRaises(ValueError):store.set_setting('theme','unsupported')
                with self.assertRaises(ValueError):store.set_setting('autostart','false')
                self.assertEqual(store.setting('theme'),'dark');self.assertIs(store.setting('autostart'),False)
            finally:store.close()


if __name__=='__main__':unittest.main()
