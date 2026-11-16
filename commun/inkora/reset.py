"""Reset capability gate. No hardware write or firmware operation is implemented.

The XP-2200 official IU05P2 has no validated selective cartridge reset in this
project. A GUI selection is never accepted as proof that the device changed.
"""
from .printer import COLORS

REASON = ("Aucune méthode de reset sélectif validée sur la XP-2200 avec IU05P2. "
          "La commande testée précédemment n’avait pas modifié le compteur relu. "
          "Le profil public EWR XP-2200 ne fournit pas de carte de reset des cartouches. "
          "Inkora ne lance ni écriture expérimentale ni flash.")


def capability(snapshot=None):
    return {"supported":False,"method":None,"reason":REASON,
            "firmware":snapshot.firmware if snapshot else "Non lu", "hardware_validated":False}


def request_reset(snapshot, colors):
    selected=list(dict.fromkeys(colors))
    if not selected or any(c not in COLORS for c in selected):
        raise ValueError("Sélection de cartouches invalide.")
    return {"ok":False,"state":"unavailable","selected":selected,
            "results":{c:{"state":"not_attempted","verified":False} for c in selected},
            "hardware_commands_sent":False,"local_levels_modified":False,**capability(snapshot)}
