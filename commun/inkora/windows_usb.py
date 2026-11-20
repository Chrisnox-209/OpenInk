"""Select only a single normal XP-2200 through the existing USBPRINT driver."""
import re


def select_device(paths):
    groups = {}
    for path in paths:
        lower = path.lower()
        if 'vid_04b8&pid_0007' in lower:
            raise ValueError('Mode de secours MFP-IPL détecté. Aucune opération autorisée.')
        if not re.search(r'vid_04b8&pid_11b1(?=[&#])', lower):
            continue
        # The vendor enumerator expands MI_00/01/02 for the same printer.
        identity = re.sub(r'&mi_0\d', '', lower)
        groups.setdefault(identity, []).append(path)
    if len(groups) != 1:
        raise ValueError('Brancher une seule Epson XP-2200 en USB normal (04b8:11b1).')
    return min(next(iter(groups.values())), key=lambda p: ('mi_01' not in p.lower(), p))


def normal_usb_device():
    from epson_usb.backends import find_devices
    return select_device([device.path for device in find_devices(backend='usbprint')])
