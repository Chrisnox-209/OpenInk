"""Interpret reported states without confusing special codes with percentages."""
from .printer import COLORS, NAMES


def cartridge_state(value, simulated=False):
    if value is None:
        return {"state":"unknown", "label":"État indisponible", "raw_code":None, "source":"ST2"}
    if simulated:
        state, label = "unknown", "Valeur simulée par le firmware"
    elif value == 0:
        state, label = "empty", "Vide signalée par l’Epson"
    elif 1 <= value <= 100:
        state, label = "reported", f"Niveau signalé : {value} %"
    elif value == 110:
        state, label = "missing", "Absence signalée par l’Epson"
    elif value == 114:
        state, label = "error", "Non reconnue ou en erreur"
    else:
        state, label = "unknown", f"Code {value} non interprété"
    return {"state":state, "label":label, "raw_code":value, "source":"ST2"}


def cartridge_diagnostics(snapshot):
    if snapshot.supplies:
        return snapshot.supplies
    return {c:cartridge_state(snapshot.reported_ink.get(c), snapshot.chipless is True) for c in COLORS}


def fault_alerts(snapshot):
    return [{"color":c, "state":d["state"], "key":f"{d['state']}:{d.get('raw_code')}",
             "title":f"{NAMES[c]} · {d['label']}",
             "detail":"Ouvrir Inkora pour consulter le diagnostic. Un reset matériel n’est pas validé pour ce firmware."}
            for c,d in cartridge_diagnostics(snapshot).items() if d["state"] in {"empty","missing","error","defective"}]


def merge_supply_alerts(supplies,descriptions,alerts):
    result={c:dict(supplies.get(c,cartridge_state(None))) for c in COLORS}
    indexes={}
    for index,description in descriptions.items():
        words=description.lower()
        for color,labels in [('black',('black','noir')),('cyan',('cyan',)),('magenta',('magenta',)),('yellow',('yellow','jaune'))]:
            if any(label in words for label in labels):indexes[index]=color
    for alert in alerts:
        # Group 11 is supplies; indexes are resolved from actual descriptions,
        # never from the incompatible proprietary BK/Y/M/C order.
        if alert.get('group')!=11 or alert.get('index')not in indexes:continue
        message=alert.get('description','').lower().strip()
        known={'defective cartridge':('defective','Défaut de cartouche signalé'),
               'no cartridge':('missing','Absence de cartouche signalée'),
               'empty cartridge':('empty','Cartouche vide signalée'),
               'ink out':('empty','Encre épuisée signalée')}
        if message not in known:continue
        state,label=known[message];color=indexes[alert['index']]
        result[color].update(state=state,label=label,source='Printer MIB',reported_message=alert['description'])
    return result
