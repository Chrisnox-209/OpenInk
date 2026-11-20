"""Local, bounded fixes for the pinned USB library used by read-only tools.

Resynchronize D4 headers after observed zero padding and close the logical
channel/session before releasing USB. No EEPROM, reset or update commands.
"""
import struct
from .filelock import fcntl
import time
from pathlib import Path
import sys
import os
sys.path.insert(0, str(Path(__file__).resolve().parent / "_vendor"))
from epson_usb import EpsonUsbPrinter as _Printer
from epson_usb.d4 import D4Session, parse_packet

_original_close = D4Session.close


def wait_packet(session, timeout_ms):
    """A USB zero-length packet is not an elapsed reply timeout."""
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        remaining = max(1, int((deadline-time.monotonic()) * 1000))
        packet = session.recv(remaining)
        if packet is not None:
            return packet
        time.sleep(0.005)
    return None


def _recv(self, timeout_ms=None):
    timeout = self.timeouts.reply_ms if timeout_ms is None else timeout_ms
    while True:
        while len(self._buf) < 6:
            if not self._fill(timeout):
                return None
        psid, ssid, length, credit, control = struct.unpack(">BBHBB", self._buf[:6])
        allowed = {(0, 0), (2, 2)} | getattr(self, "extra_socket_pairs", set())
        if (psid, ssid) not in allowed or not 6 <= length <= 4096 or control not in (0, 1, 2, 3):
            self._trace("resync_drop", self._buf[:1])
            self._buf = self._buf[1:]
            continue
        while len(self._buf) < length:
            if not self._fill(timeout):
                return None
        packet, self._buf = parse_packet(self._buf)
        self._trace("<", packet)
        return packet


def _close(self):
    try:
        if self.connected:
            # Standard IEEE-1284.4 CloseChannel and Exit, not EPSON service
            # reset commands. Only the EPSON-CTRL channel used here is closed.
            for payload, reply_opcode in ((b"\x02\x02\x02", 0x82), (b"\x08", 0x88)):
                self.send(0, 0, payload, credit=1)
                for _ in range(3):
                    packet = wait_packet(self, 300)
                    if packet is None or (packet.psid == 0 and packet.payload and packet.payload[0] == reply_opcode):
                        break
    except Exception as exc:
        self._trace("close_protocol_error", str(exc))
    finally:
        _original_close(self)


def _request(self, frame, tries=None):
    """Balance reply credits for the single-packet read commands used here.

    The vendor implementation grants 8 explicit plus 8 piggyback credits per
    one-packet reply. Its net +15 reaches the 16-bit limit near read 4,369.
    Grant one explicit reply credit and no additional piggyback credit.
    """
    tries = self.timeouts.tries if tries is None else tries
    self.send(0, 0, struct.pack(">BBBHH", 4, 2, 2, 128, 0xFFFF), credit=1)
    credit_reply = wait_packet(self, self.timeouts.credit_ms * 4)
    if (credit_reply is None or credit_reply.psid != 0 or
            credit_reply.payload[:4] != b"\x84\0\x02\x02" or
            int.from_bytes(credit_reply.payload[4:6], "big") < 1):
        return None
    self.send(0, 0, struct.pack(">BBBH", 3, 2, 2, 1), credit=1)
    acknowledged = False
    for _ in range(4):
        packet = wait_packet(self, self.timeouts.credit_ack_ms)
        if packet is None:
            break
        if packet.psid == 0 and packet.payload[:2] == b"\x83\0":
            acknowledged = True
            break
        if packet.psid == 2 and packet.payload:
            raise RuntimeError("Unexpected stale reply before a new USB request")
    if not acknowledged:
        return None
    self.send(2, 2, frame, credit=0)
    deadline = time.monotonic() + tries * self.timeouts.reply_ms / 1000
    while time.monotonic() < deadline:
        packet = wait_packet(self, max(1, int((deadline-time.monotonic()) * 1000)))
        if packet is not None and packet.psid == 2 and packet.payload:
            return packet.payload
    return None


D4Session.recv = _recv
D4Session.close = _close
D4Session.request = _request


class EpsonUsbPrinter(_Printer):
    """Serialize this project's USB readers, including the desktop panel."""
    def __init__(self, *args, **kwargs):
        self._local_lock = None
        super().__init__(*args, **kwargs)

    def open(self):
        if self.session is not None and self.session.connected:
            return self
        if os.name == 'nt':
            from .store import default_database
            lock_path = default_database().parent / 'usb.lock'
        elif sys.platform == 'darwin':
            lock_path = Path.home() / 'Library/Caches/inkora/usb.lock'
        else:
            lock_path = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home()/".cache"))) / "inkora/usb.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._local_lock = lock_path.open("a+b")
        lock_path.chmod(0o600)
        try:
            fcntl.flock(self._local_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return super().open()
        except BlockingIOError:
            self._release_lock()
            raise RuntimeError("Une autre lecture USB est en cours. Attends sa fin puis réessaie.")
        except Exception:
            self._release_lock()
            raise

    def _release_lock(self):
        if self._local_lock is not None:
            self._local_lock.close()
            self._local_lock = None

    def close(self):
        try:
            super().close()
        finally:
            self._release_lock()
