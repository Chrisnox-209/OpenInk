"""Explicit Windows spooler submission using the Epson driver's GDI output."""
from datetime import datetime, timezone
import re

from .firmware import hardware_session
from .i18n import test_page, tr


def all_printers():
    import win32print
    return win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL |
                                  win32print.PRINTER_ENUM_CONNECTIONS, None, 2)


def require_empty_queues():
    # Fail closed if any queue cannot be inspected. Never cancel a print job.
    import win32print
    for printer in all_printers():
        handle = win32print.OpenPrinter(printer['pPrinterName'])
        try:
            if win32print.GetPrinter(handle, 2)['cJobs'] or win32print.EnumJobs(handle, 0, 1, 1):
                raise ValueError('Une file d’impression est occupée. Attends sa fin puis réessaie.')
        finally:
            win32print.ClosePrinter(handle)


def cups_printers(snapshot):
    printers = []
    for printer in all_printers():
        name = printer['pPrinterName']
        model = re.sub('[^a-z0-9]', '', (name + printer.get('pDriverName', '')).lower())
        if 'xp2200' not in model or 'mfpipl' in model:
            continue
        # Windows USB/WSD port names do not establish a physical serial identity.
        printers.append({'name': name, 'confirmed': False,
                         'enabled': not bool(printer['Status'] & (1 | 2 | 0x80 | 0x1000)),
                         'uri': printer.get('pPortName', '')})
    return sorted(printers, key=lambda p: (not p['enabled'], p['name']))


def submit_test_page(snapshot, queue, confirm_destination=False):
    import win32con
    import win32gui
    import win32print
    from PIL import Image, ImageWin
    if snapshot.demo or not snapshot.ready:
        raise ValueError('L’Epson doit être prête avant d’envoyer la page de test.')
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(snapshot.observed_at)).total_seconds()
    if not 0 <= age <= 120:
        raise ValueError('Actualise l’imprimante avant d’imprimer la page de test.')
    with hardware_session():
        selected = next((p for p in cups_printers(snapshot) if p['name'] == queue), None)
        if not selected or not selected['enabled']:
            raise ValueError('Cette file Epson n’est plus disponible.')
        if not confirm_destination:
            raise ValueError('Confirme que la file choisie correspond à ton Epson.')
        handle = win32print.OpenPrinter(queue)
        dc = None
        started = False
        try:
            info = win32print.GetPrinter(handle, 2)
            if info['cJobs'] or win32print.EnumJobs(handle, 0, 1, 1):
                raise ValueError('Cette file est occupée. Attends la fin du document en cours.')
            mode = info['pDevMode']
            if mode is None:
                raise ValueError('Le pilote Epson ne fournit pas de réglages d’impression.')
            mode.Fields |= (win32con.DM_PAPERSIZE | win32con.DM_COPIES |
                            win32con.DM_DUPLEX | win32con.DM_COLOR | win32con.DM_ORIENTATION)
            mode.PaperSize = 9  # A4
            mode.Copies = 1
            mode.Duplex = 1
            mode.Color = 2
            mode.Orientation = 1
            result = win32print.DocumentProperties(0, handle, queue, mode, mode,
                                                   win32con.DM_IN_BUFFER | win32con.DM_OUT_BUFFER)
            if result < 0 or (mode.PaperSize, mode.Copies, mode.Duplex, mode.Color, mode.Orientation) != (9, 1, 1, 2, 1):
                raise ValueError('Le pilote refuse la page A4 couleur, recto seul, une copie.')
            # The raster is generated from the exact localized PDF when building.
            with Image.open(test_page().with_suffix('.png')) as source:
                image = source.convert('RGB')
            dc = win32gui.CreateDC('WINSPOOL', queue, mode)
            job = win32print.StartDoc(dc, (tr('OpenInk - page de test CMJN'), None, None, 0))
            if job <= 0:
                raise ValueError('Le spouleur Windows a refusé la page.')
            started = True
            win32print.StartPage(dc)
            width = win32print.GetDeviceCaps(dc, win32con.HORZRES)
            height = win32print.GetDeviceCaps(dc, win32con.VERTRES)
            ratio = min(width / image.width, height / image.height)
            w, h = round(image.width * ratio), round(image.height * ratio)
            x, y = (width - w) // 2, (height - h) // 2
            ImageWin.Dib(image).draw(dc, (x, y, x + w, y + h))
            win32print.EndPage(dc)
            win32print.EndDoc(dc)
            started = False
            return {'accepted': True, 'job_id': str(job), 'queue': queue,
                    'printed_verified': False, 'copies': 1}
        except BaseException:
            if dc and started:
                win32print.AbortDoc(dc)
            raise
        finally:
            if dc:
                win32gui.DeleteDC(dc)
            win32print.ClosePrinter(handle)
