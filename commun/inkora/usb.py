"""Normal-mode, fixed read commands only. Never sends EEPROM/service commands."""
from dataclasses import replace
import subprocess
import os
import sys

from .printer import parse_status, COMMANDS


def read_usb():
    if sys.platform == 'darwin':
        from .macos_support import configure_libusb
        configure_libusb(required=True)
    from .usb_session import EpsonUsbPrinter
    if os.name == 'nt':
        from .windows_usb import normal_usb_device
        from .windows_printing import require_empty_queues
        path=normal_usb_device();require_empty_queues()
        return _read_usb_path(EpsonUsbPrinter,path,'usbprint')
    from epson_usb.backends import find_devices
    candidates=[d for d in find_devices(backend="libusb") if d.vendor_id==0x04b8]
    normal={d.path:d for d in candidates if d.product_id==0x11b1}
    if not normal and any(d.product_id==0x0007 for d in candidates):
        raise ValueError("Epson en mode de secours MFP-IPL : lecture normale suspendue, aucune écriture autorisée.")
    if len(normal)!=1:
        raise ValueError("Brancher une seule Epson XP-2200 en USB normal (04b8:11b1).")
    try:
        jobs=subprocess.run(["lpstat","-W","not-completed","-o"],capture_output=True,text=True,timeout=3)
    except (OSError,subprocess.TimeoutExpired):
        raise ValueError("État CUPS indisponible : lecture USB suspendue. Le réseau reste utilisable.") from None
    if jobs.returncode or jobs.stdout.strip():
        raise ValueError("Une file est active ou CUPS ne répond pas. Lecture USB différée sans arrêter de travail.")
    path=next(iter(normal))
    return _read_usb_path(EpsonUsbPrinter,path,'libusb')


def _read_usb_path(printer_class,path,backend):
    with printer_class(read_key=None,write_key=None,dry_run=True,backend=backend,
                       device=path,interface=1) as printer:
        def read(name):
            command,param=COMMANDS[name]
            value=printer.command(command,param)
            if not value:
                raise ValueError("Lecture USB sans réponse : "+name)
            return value
        raw=read("status")
        types=version=b""
        try:
            types=read("types")
            version=read("firmware")
        except ValueError:
            pass
        snapshot=parse_status(raw,"USB",types or None,version)
        if not snapshot.serial:
            raise ValueError("Identité USB non confirmée : arrêt du suivi pour éviter de mélanger les imprimantes.")
        return replace(snapshot,transport="USB")


def read_connected(host, transport="network"):
    from .firmware import hardware_session
    with hardware_session():
        return _read_connected(host,transport)


def _read_connected(host, transport="network"):
    from .printer import read_printer
    if transport=="usb":
        return read_usb()
    if transport not in {"network","auto"}:
        raise ValueError("Connexion inconnue.")
    if transport=="network":
        return read_printer(host)
    try:
        return read_printer(host)
    except (ValueError,OSError):
        return read_usb()
