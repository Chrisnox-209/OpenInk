"""Create README screenshots from isolated test fixtures, never a real printer."""
from dataclasses import replace
from datetime import datetime,timezone,timedelta
from pathlib import Path
import struct
import subprocess
import sys
import time
from unittest.mock import patch
import tkinter as tk
from PIL import Image

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'commun'))
from inkora.i18n import set_language,tr
from inkora.printer import demo_snapshot,COLORS
from inkora.store import Store
from inkora.ui import Application


def capture(canvas,path):
    # Capture only this application's client area, including native entry fields.
    # Canvas PostScript omits those fields and is not a faithful UI screenshot.
    canvas.update();time.sleep(.15);canvas.update()
    # Read this X11 window directly; a Wayland session can forbid root captures.
    data=subprocess.run(['xwd','-silent','-id',str(canvas.winfo_id())],
                        capture_output=True,check=True,timeout=10).stdout
    header=struct.unpack('>25I',data[:100])
    size,version,format_,depth,width,height=header[:6]
    byte_order,bits_per_pixel,stride=header[7],header[11],header[12]
    masks=header[14:17];colors=header[19]
    assert(version,format_,depth,byte_order,masks)==(7,2,24,0,(0xff0000,0xff00,0xff)),header
    mode={24:'BGR',32:'BGRX'}[bits_per_pixel]
    Image.frombytes('RGB',(width,height),data[size+12*colors:],'raw',mode,stride,1).save(path)


def main():
    output=ROOT/'docs/images';output.mkdir(exist_ok=True)
    for language in('fr','en','es'):
        set_language(language);store=Store(':memory:');now=datetime.now(timezone.utc)
        store.set_setting('language',language)
        snapshot=replace(demo_snapshot(),status='Prête à imprimer',ready=True,color_pages=824,mono_pages=1316)
        for day in range(7,0,-1):
            store.observe(replace(snapshot,color_pages=824-9*day,mono_pages=1316-7*day,
                                  observed_at=(now-timedelta(days=day)).isoformat()))
        store.observe(snapshot)
        for color,level in zip(COLORS,(78,29,16,61)):store.calibrate(snapshot,[color],'604',level)
        root=tk.Tk(className='OpenInk');app=None
        try:
            with patch('inkora.ui.read_printer',side_effect=AssertionError('No printer in screenshot capture')), \
                 patch('inkora.ui.send_notification',side_effect=AssertionError('No notification in screenshot capture')):
                app=Application(root,store,demo=True)
                root.minsize(1100,730);root.geometry('1440x960')
                root.attributes('-topmost',True);root.lift()
                for page,name in[(0,'overview'),(4,'openflow'),(3,'settings')]:
                    app.navigate(page)
                    for _ in range(4):root.update()
                    app.render();root.update_idletasks()
                    path=output/f'openink-{language}-{name}.png';capture(app.canvas,path)
                    print(path)
        finally:
            if app:app.close()
            else:store.close();root.destroy()
    set_language('fr')


if __name__=='__main__':main()
