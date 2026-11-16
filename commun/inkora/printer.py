"""Fixed, read-only Epson status requests over SNMP. Standard library only.

No reset, firmware, arbitrary command or memory-writing operation is exposed.
"""
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import ipaddress
import secrets
import socket

COLORS = ("black", "cyan", "magenta", "yellow")
NAMES = {"black": "Noir", "cyan": "Cyan", "magenta": "Magenta", "yellow": "Jaune"}
STATUS = {0: "Attention requise", 1: "Impression en cours", 2: "Occupée", 3: "Prête à imprimer",
          4: "Prête à imprimer", 5: "En pause", 7: "Nettoyage en cours", 15: "Test des buses", 17: "Chargement de l’encre"}
ERRORS = {1: "Autre interface en cours d’utilisation", 2: "Capot ouvert", 4: "Bourrage papier",
          5: "Cartouche vide ou non reconnue", 6: "Ajouter du papier", 16: "Entretien nécessaire",
          26: "Compartiment des cartouches ouvert", 55: "Scanner ouvert"}
BASE = "1.3.6.1.4.1.1248.1.2.2.44.1.1.2.1"
COMMANDS = {"status": (b"st", b"\x01"), "types": (b"ia", b"\x00"), "firmware": (b"vi", b"\x04")}
STANDARD_READS = {
    **{f'supply_{i}':f'1.3.6.1.2.1.43.11.1.1.6.1.{i}' for i in range(1,5)},
    **{f'alert_{i}_{name}':f'1.3.6.1.2.1.43.18.1.1.{field}.1.{i}'
       for i in range(1,7) for name,field in [('group',4),('index',5),('description',8)]},
}


@dataclass
class Snapshot:
    printer_id: str
    host: str
    observed_at: str
    status: str
    ready: bool
    color_pages: int | None = None
    mono_pages: int | None = None
    blank_pages: int | None = None
    reported_ink: dict = field(default_factory=dict)
    chipless: bool | None = None
    firmware: str = ""
    serial: str = ""
    demo: bool = False
    supplies: dict = field(default_factory=dict)
    transport: str = "Wi-Fi"

    @property
    def total_pages(self):
        # Blank sheets are a separate counter, not part of printed pages.
        if self.color_pages is None or self.mono_pages is None:
            return None
        return self.color_pages + self.mono_pages

    def to_dict(self):
        return asdict(self)


def tlv(tag, data):
    size = len(data)
    length = bytes((size,)) if size < 128 else bytes((0x80 | ((size.bit_length()+7)//8),)) + size.to_bytes((size.bit_length()+7)//8, "big")
    return bytes((tag,)) + length + data


def integer(value):
    data = value.to_bytes(max(1, (value.bit_length()+7)//8), "big")
    return tlv(2, (b"\0" if data[0] & 128 else b"") + data)


def base128(value):
    parts = [value & 127]
    value >>= 7
    while value:
        parts.append((value & 127) | 128)
        value >>= 7
    return bytes(reversed(parts))


def oid_bytes(oid):
    parts = [int(p) for p in oid.split(".")]
    return base128(40*parts[0]+parts[1]) + b"".join(base128(n) for n in parts[2:])


def unpack_tlv(data, position=0):
    if position+2 > len(data):
        raise ValueError("Réponse SNMP tronquée")
    tag, length = data[position:position+2]
    position += 2
    if length & 128:
        count = length & 127
        if not 1 <= count <= 4 or position+count > len(data):
            raise ValueError("Longueur SNMP invalide")
        length = int.from_bytes(data[position:position+count], "big")
        position += count
    end = position+length
    if end > len(data):
        raise ValueError("Réponse SNMP incomplète")
    return tag, data[position:end], end


def elements(data):
    result, position = [], 0
    while position < len(data):
        tag, value, position = unpack_tlv(data, position)
        result.append((tag, value))
    return result


def get(host, name, timeout=1.5):
    # An SNMP GET can encode mutations on Epson devices. Only these three
    # fixed read commands are ever accepted here.
    command, payload = COMMANDS[name]
    frame = command + len(payload).to_bytes(2, "little") + payload
    oid = BASE + "." + ".".join(map(str, frame))
    return _get_oid(host,oid,timeout)


def get_standard(host,name,timeout=.3):
    return _get_oid(host,STANDARD_READS[name],timeout,integer_result=True)


def _get_oid(host,oid,timeout,integer_result=False):
    rid = secrets.randbits(30)
    bindings = tlv(0x30, tlv(0x30, tlv(6, oid_bytes(oid)) + tlv(5, b"")))
    packet = tlv(0x30, integer(0) + tlv(4, b"public") + tlv(0xA0, integer(rid)+integer(0)+integer(0)+bindings))
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as conn:
        conn.settimeout(timeout)
        conn.connect((host, 161))
        conn.send(packet)
        response = conn.recv(65535)
    tag, body, end = unpack_tlv(response)
    if tag != 0x30 or end != len(response):
        raise ValueError("Enveloppe SNMP incorrecte")
    message = elements(body)
    if len(message) != 3 or message[2][0] != 0xA2:
        raise ValueError("Réponse SNMP incorrecte")
    pdu = elements(message[2][1])
    if len(pdu) != 4 or int.from_bytes(pdu[0][1], "big") != rid:
        raise ValueError("Identifiant SNMP incorrect")
    if int.from_bytes(pdu[1][1], "big"):
        raise ValueError("La lecture a été refusée par l’imprimante")
    items = elements(pdu[3][1])
    if len(items) != 1:
        raise ValueError("Nombre de valeurs SNMP incorrect")
    pair = elements(items[0][1])
    if len(pair) != 2 or pair[0] != (6, oid_bytes(oid)):
        raise ValueError("Valeur SNMP inattendue")
    if pair[1][0]==4:return pair[1][1]
    if integer_result and pair[1][0]==2:return int.from_bytes(pair[1][1],'big',signed=True)
    raise ValueError("Type SNMP indisponible ou inattendu")


def parse_status(raw, host, cartridge_types=None, firmware=b""):
    marker = b"@BDC ST2\r\n"
    start = raw.find(marker)
    if start < 0 or start+12 > len(raw):
        raise ValueError("État Epson ST2 non reconnu")
    start += len(marker)
    length = int.from_bytes(raw[start:start+2], "little")
    body = raw[start+2:]
    if len(body) != length:
        raise ValueError("État Epson ST2 incomplet")
    values, position = {}, 0
    while position < len(body):
        if position+2 > len(body):
            raise ValueError("Champ Epson tronqué")
        kind, size = body[position:position+2]
        position += 2
        if position+size > len(body):
            raise ValueError("Champ Epson incomplet")
        values[kind] = body[position:position+size]
        position += size
    code = values.get(1, b"\xff")[0]
    state = STATUS.get(code, "État non reconnu")
    if 2 in values and values[2]:
        state = ERRORS.get(values[2][0], "Attention requise")
    levels, raw_levels = {}, {}
    ink = values.get(15, b"")
    if ink:
        stride = ink[0]
        if stride < 3 or (len(ink)-1) % stride:
            raise ValueError("Niveaux d’encre invalides")
        for position in range(1, len(ink), stride):
            _cartridge, color, value = ink[position:position+3]
            if color < 4:
                levels[COLORS[color]] = value if value <= 100 else None
                raw_levels[COLORS[color]] = value
    counts = [None]*5
    if len(values.get(54, b"")) == 20:
        counts = [int.from_bytes(values[54][n:n+4], "little", signed=True) for n in range(0, 20, 4)]
        counts = [n if n >= 0 else None for n in counts]
    serial = values.get(64, values.get(31, b"")).decode("ascii", "replace").strip("\0")
    mode = None if cartridge_types is None else b"IA:00;,,,;" in cartridge_types
    version = firmware.decode("ascii", "replace").strip("\0\f;")
    if "vi:04:" in version:
        version = version.split("vi:04:", 1)[1]
    from .diagnostics import cartridge_state
    supplies={c:cartridge_state(raw_levels.get(c),mode is True) for c in COLORS}
    return Snapshot(serial or "network:"+host, host, datetime.now(timezone.utc).isoformat(), state,
                    code in (3, 4) and 2 not in values, counts[2], counts[3], counts[4],
                    levels, mode, version, serial, supplies=supplies)


def read_printer(host):
    host = host.strip()
    try:
        address = ipaddress.ip_address(host)
        if address.version != 4 or address.is_multicast or address.is_unspecified:
            raise ValueError
    except ValueError:
        raise ValueError("Indique une adresse IPv4, par exemple 192.168.1.55.") from None
    raw = get(host, "status")
    types = version = None
    try:
        types = get(host, "types")
    except (OSError, ValueError):
        pass
    try:
        version = get(host, "firmware")
    except (OSError, ValueError):
        pass
    snapshot=parse_status(raw, host, types, version or b"")
    descriptions={};alerts=[]
    try:
        for i in range(1,5):
            descriptions[i]=get_standard(host,f'supply_{i}').decode('utf-8','replace')
        for i in range(1,7):
            try:
                group=get_standard(host,f'alert_{i}_group')
                index=get_standard(host,f'alert_{i}_index')
                description=get_standard(host,f'alert_{i}_description').decode('utf-8','replace')
                alerts.append({'group':group,'index':index,'description':description})
            except (OSError,ValueError):break
    except (OSError,ValueError):pass
    from .diagnostics import merge_supply_alerts
    snapshot.supplies=merge_supply_alerts(snapshot.supplies,descriptions,alerts)
    return snapshot


def demo_snapshot():
    from .diagnostics import cartridge_state
    supplies={c:cartridge_state(v)for c,v in [('black',78),('cyan',114),('magenta',0),('yellow',61)]}
    supplies['cyan'].update(state='defective',label='Défaut de cartouche signalé',source='Exemple fictif')
    return Snapshot("DEMO-XP2200", "192.168.1.55", datetime.now(timezone.utc).isoformat(),
                    "Cartouche vide ou en erreur · démonstration", False, 824, 1316, 8,
                    {"black": 78, "cyan": None, "magenta": 0, "yellow": 61},
                    False, "06.58.IU05P2.FY22", "DEMONSTRATION", True,supplies=supplies)
