"""SQLite storage and explicit, page-based ink estimates; no hardware writes."""
from datetime import datetime, timezone, timedelta
import json
import math
import os
from pathlib import Path
import sqlite3

from .printer import COLORS, NAMES, Snapshot

YIELDS = {"604": {"black": 150, "cyan": 130, "magenta": 130, "yellow": 130},
          "604XL": {"black": 500, "cyan": 350, "magenta": 350, "yellow": 350}}
DEFAULT_WARNING = 30
DEFAULT_RESERVE = 20


def default_database():
    if os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA", str(Path.home()/"AppData/Local")))
    elif __import__("sys").platform == "darwin":
        root = Path.home()/"Library/Application Support"
    else:
        root = Path(os.environ.get("XDG_DATA_HOME", str(Path.home()/".local/share")))
    return root/"inkora/inkora.sqlite3"


class Store:
    def __init__(self, path=None):
        self.path = Path(path) if path else default_database()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS readings(id INTEGER PRIMARY KEY, printer TEXT NOT NULL, at TEXT NOT NULL, payload TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS readings_printer ON readings(printer, id);
        CREATE TABLE IF NOT EXISTS cartridges(printer TEXT NOT NULL, color TEXT NOT NULL,
          at TEXT NOT NULL, profile TEXT NOT NULL, capacity INTEGER NOT NULL, start REAL NOT NULL,
          color_baseline INTEGER NOT NULL, mono_baseline INTEGER NOT NULL,
          PRIMARY KEY(printer,color));
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, printer TEXT NOT NULL, at TEXT NOT NULL,
          title TEXT NOT NULL, detail TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS ink_alerts(printer TEXT NOT NULL, color TEXT NOT NULL,
          cycle TEXT NOT NULL, severity INTEGER NOT NULL, PRIMARY KEY(printer,color));
        CREATE TABLE IF NOT EXISTS fault_state(printer TEXT NOT NULL,color TEXT NOT NULL,
          fingerprint TEXT NOT NULL,PRIMARY KEY(printer,color));
        CREATE TABLE IF NOT EXISTS firmware_followups(job TEXT PRIMARY KEY,printer TEXT NOT NULL,at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY,printer TEXT NOT NULL,
          at TEXT NOT NULL,color TEXT NOT NULL,kind TEXT NOT NULL,state TEXT NOT NULL,
          title TEXT NOT NULL,detail TEXT NOT NULL,delivery TEXT NOT NULL DEFAULT 'queued',
          attempt_at TEXT,delivery_detail TEXT);
        """)
        # Keep accumulated consumption independent of later changes of usage.
        columns = {r[1] for r in self.db.execute("PRAGMA table_info(cartridges)")}
        for name, definition in (("used_pages", "REAL NOT NULL DEFAULT 0"),
                                 ("last_color", "INTEGER"), ("last_mono", "INTEGER")):
            if name not in columns:
                self.db.execute(f"ALTER TABLE cartridges ADD COLUMN {name} {definition}")
        self.db.execute("UPDATE cartridges SET last_color=color_baseline, last_mono=mono_baseline WHERE last_color IS NULL OR last_mono IS NULL")
        for row in self.db.execute("SELECT DISTINCT printer FROM cartridges").fetchall():
            latest = self.latest(row[0])
            if latest:
                self._settle(latest)
        self.db.commit()
        try:
            self.path.chmod(0o600)
        except OSError:
            pass

    def setting(self, key, default=None):
        row = self.db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_setting(self, key, value):
        if key=='theme'and value not in('light','dark'):
            raise ValueError('Thème non pris en charge.')
        if key=='autostart'and not isinstance(value,bool):
            raise ValueError('Le démarrage automatique doit être activé ou désactivé.')
        if key=='language'and value not in('auto','fr','en','es'):
            raise ValueError('Langue non prise en charge.')
        if key=='reminder_minutes':
            value=int(value)
            if value!=0 and not 15<=value<=1440:raise ValueError('Rappel : 0 ou 15 à 1 440 minutes.')
        if key == "coverage":
            value = float(value)
            if not math.isfinite(value) or not 0 < value <= 20:
                raise ValueError("Le coefficient d’usage doit être compris entre 0 et 20, zéro exclu.")
        with self.db:
            if key == "coverage":
                # Charge already observed pages at their previous coefficient.
                for row in self.db.execute("SELECT DISTINCT printer FROM cartridges").fetchall():
                    snapshot = self.latest(row[0])
                    if snapshot:
                        self._settle(snapshot)
            self.db.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (key, json.dumps(value)))

    def set_safety(self, warning, reserve, notifications=True):
        warning, reserve = float(warning), float(reserve)
        if not (math.isfinite(warning) and math.isfinite(reserve) and 5 <= reserve < warning <= 80):
            raise ValueError("Choisis une réserve d’au moins 5 %, inférieure au seuil d’alerte (80 % maximum).")
        with self.db:
            for key, value in (("warning_percent", warning), ("reserve_percent", reserve),
                               ("notifications", bool(notifications))):
                self.db.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (key, json.dumps(value)))

    def _settle(self, snapshot):
        if snapshot.color_pages is None or snapshot.mono_pages is None:
            return
        multiplier = float(self.setting("coverage", 1.0))
        for row in self.db.execute("SELECT * FROM cartridges WHERE printer=?", (snapshot.printer_id,)).fetchall():
            color_delta = snapshot.color_pages-row["last_color"]
            mono_delta = snapshot.mono_pages-row["last_mono"]
            if color_delta < 0 or mono_delta < 0:
                continue
            used = (color_delta+(mono_delta if row["color"] == "black" else 0))*multiplier
            self.db.execute("UPDATE cartridges SET used_pages=used_pages+?, last_color=?, last_mono=? WHERE printer=? AND color=?",
                            (used, snapshot.color_pages, snapshot.mono_pages, snapshot.printer_id, row["color"]))

    def latest(self, printer=None):
        if printer:
            row = self.db.execute("SELECT payload FROM readings WHERE printer=? ORDER BY id DESC LIMIT 1", (printer,)).fetchone()
        else:
            row = self.db.execute("SELECT payload FROM readings ORDER BY id DESC LIMIT 1").fetchone()
        return Snapshot(**json.loads(row[0])) if row else None

    def observe(self, snapshot):
        old = self.latest(snapshot.printer_id)
        now = snapshot.observed_at
        with self.db:
            baselines = self.db.execute("SELECT last_color,last_mono FROM cartridges WHERE printer=?", (snapshot.printer_id,)).fetchall()
            backwards = (snapshot.total_pages is not None and (
                any(snapshot.color_pages < r["last_color"] or snapshot.mono_pages < r["last_mono"] for r in baselines)
                or (old is not None and old.total_pages is not None and
                    (snapshot.color_pages < old.color_pages or snapshot.mono_pages < old.mono_pages))))
            self.db.execute("INSERT INTO readings(printer,at,payload) VALUES(?,?,?)",
                            (snapshot.printer_id, now, json.dumps(snapshot.to_dict())))
            if old is None:
                self.event(snapshot.printer_id, "Imprimante connectée", "Début du suivi de cette imprimante.", now)
            if backwards:
                # Also catch a rollback after an intervening missing-counter
                # reading. A later increase must never revive an invalid base.
                self.db.execute("DELETE FROM cartridges WHERE printer=?", (snapshot.printer_id,))
                self.event(snapshot.printer_id, "Compteurs réinitialisés", "Les estimations doivent être recalibrées.", now)
                self._queue_notification(snapshot.printer_id,'all','tracking','unknown',
                    'Suivi d’encre à revoir',
                    'Les compteurs ont reculé. Renseigne les niveaux réellement estimés dans Cartouches ; aucun plein n’a été créé.')
            elif old is not None and old.total_pages is not None and snapshot.total_pages is not None:
                if snapshot.total_pages > old.total_pages:
                    delta = snapshot.total_pages-old.total_pages
                    self.event(snapshot.printer_id, f"{delta} page{'s' if delta>1 else ''} imprimée{'s' if delta>1 else ''}",
                               f"Compteur imprimante : {snapshot.total_pages} pages.", now)
            self._settle(snapshot)
            alerts=self._new_alerts(snapshot)
            self._fault_notifications(snapshot)
            return alerts

    def event(self, printer, title, detail, at=None):
        self.db.execute("INSERT INTO events(printer,at,title,detail) VALUES(?,?,?,?)",
                        (printer, at or datetime.now(timezone.utc).isoformat(), title, detail))

    def calibrate(self, snapshot, colors, profile="604", start=100, capacity=None):
        if not colors or any(c not in COLORS for c in colors):
            raise ValueError("Sélectionne au moins une cartouche.")
        if snapshot.color_pages is None or snapshot.mono_pages is None:
            raise ValueError("Les compteurs d’impression ne sont pas disponibles.")
        if not 0 <= float(start) <= 100 or not math.isfinite(float(start)):
            raise ValueError("Le niveau doit être compris entre 0 et 100 %.")
        if profile not in YIELDS and profile != "Personnalisé":
            raise ValueError("Format de cartouche inconnu.")
        if profile == "Personnalisé" and (capacity is None or not 1 <= int(capacity) <= 100000):
            raise ValueError("Indique un rendement entre 1 et 100 000 pages.")
        with self.db:
            for color in colors:
                size = int(capacity) if profile == "Personnalisé" else YIELDS[profile][color]
                self.db.execute("INSERT OR REPLACE INTO cartridges(printer,color,at,profile,capacity,start,color_baseline,mono_baseline,used_pages,last_color,last_mono) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (snapshot.printer_id, color, datetime.now(timezone.utc).isoformat(), profile, size,
                     float(start), snapshot.color_pages, snapshot.mono_pages, 0,
                     snapshot.color_pages, snapshot.mono_pages))
                self.db.execute("DELETE FROM ink_alerts WHERE printer=? AND color=?", (snapshot.printer_id, color))
                self.db.execute("UPDATE notifications SET delivery='superseded' WHERE printer=? AND color=? AND kind='estimate' AND delivery IN ('queued','failed')",(snapshot.printer_id,color))
            self.event(snapshot.printer_id, "Suivi des cartouches réinitialisé",
                       ", ".join(NAMES[c] for c in colors) + f" · {profile} · départ à {float(start):g} %")
            if all(value is not None for value in self.estimates(snapshot).values()):
                self.db.execute("UPDATE notifications SET delivery='superseded' WHERE printer=? AND kind='tracking' AND delivery IN ('queued','failed')",(snapshot.printer_id,))

    def record_chip_reset(self, snapshot, colors):
        """Record an externally performed reset; never refill the local estimate."""
        if not colors or any(c not in COLORS for c in colors):
            raise ValueError("Sélectionne au moins une cartouche.")
        estimates = self.estimates(snapshot)
        if any(estimates[c] is None for c in colors):
            raise ValueError("Renseigne d’abord le niveau estimé des cartouches non suivies.")
        with self.db:
            self.event(snapshot.printer_id, "Reset déclaré sans ajout d’encre",
                       ", ".join(NAMES[c] for c in colors)+" · Niveaux estimés conservés. Aucun reset envoyé à l’imprimante.")

    def apply_firmware_plan(self,snapshot,plan,job,baseline=None):
        """Apply declared physical changes once, only after verified V2 installation."""
        from .firmware import validate_plan
        plan=validate_plan(plan)
        if snapshot.demo or snapshot.chipless is not True or snapshot.total_pages is None:
            raise ValueError('V2 et compteurs non confirmés ; les niveaux restent conservés.')
        baseline=baseline or snapshot
        if baseline.printer_id!=snapshot.printer_id or baseline.total_pages is None:
            raise ValueError('Le repère de consommation avant installation est invalide.')
        if (snapshot.color_pages<baseline.color_pages or snapshot.mono_pages<baseline.mono_pages)and any(item['action']!='keep'for item in plan.values()):
            raise ValueError('Compteurs en recul : déclarer à nouveau les niveaux réels dans Cartouches.')
        with self.db:
            inserted=self.db.execute('INSERT OR IGNORE INTO firmware_followups VALUES(?,?,?)',
                (job,snapshot.printer_id,datetime.now(timezone.utc).isoformat())).rowcount
            if not inserted:return False
            for color,item in plan.items():
                if item['action']=='keep':continue
                profile=item['profile'];amount=item['percent']
                size=item['capacity']if profile=='Personnalisé'else YIELDS[profile][color]
                self.db.execute('INSERT OR REPLACE INTO cartridges(printer,color,at,profile,capacity,start,color_baseline,mono_baseline,used_pages,last_color,last_mono) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                    (snapshot.printer_id,color,datetime.now(timezone.utc).isoformat(),profile,size,amount,
                     baseline.color_pages,baseline.mono_pages,0,baseline.color_pages,baseline.mono_pages))
                self.db.execute('DELETE FROM ink_alerts WHERE printer=? AND color=?',(snapshot.printer_id,color))
                self.db.execute("UPDATE notifications SET delivery='superseded' WHERE printer=? AND color=? AND kind='estimate' AND delivery IN ('queued','failed')",(snapshot.printer_id,color))
            detail='; '.join(NAMES[c]+(' : estimation conservée'if item['action']=='keep'else f" : départ déclaré {item['percent']:g} %")for c,item in plan.items())
            self.event(snapshot.printer_id,'OpenFlow vérifié · suivi de l’encre',detail or'Estimations conservées.')
            if all(value is not None for value in self.estimates(snapshot).values()):
                self.db.execute("UPDATE notifications SET delivery='superseded' WHERE printer=? AND kind='tracking' AND delivery IN ('queued','failed')",(snapshot.printer_id,))
        return True

    def estimates(self, snapshot):
        result = {}
        multiplier = float(self.setting("coverage", 1.0))
        warning = float(self.setting("warning_percent", DEFAULT_WARNING))
        reserve = float(self.setting("reserve_percent", DEFAULT_RESERVE))
        for color in COLORS:
            row = self.db.execute("SELECT * FROM cartridges WHERE printer=? AND color=?",
                                  (snapshot.printer_id, color)).fetchone()
            if row is None or snapshot.color_pages is None or snapshot.mono_pages is None:
                result[color] = None
                continue
            color_delta = snapshot.color_pages-row["last_color"]
            mono_delta = snapshot.mono_pages-row["last_mono"]
            if color_delta < 0 or mono_delta < 0:
                result[color] = None
                continue
            used = row["used_pages"]+(color_delta + (mono_delta if color == "black" else 0))*multiplier
            remaining = max(0.0, row["capacity"]*row["start"]/100-used)
            percent = min(100, remaining/row["capacity"]*100)
            result[color] = {"percent": percent,
                             "pages": max(0, int(remaining/multiplier)), "profile": row["profile"],
                             "usable_pages": max(0, int((remaining-row["capacity"]*reserve/100)/multiplier)),
                             "reserve_percent": reserve, "warning_percent": warning,
                             "capacity": row["capacity"],
                             "state": "reserve" if percent <= reserve else "low" if percent <= warning else "ok",
                             "at": row["at"], "start": row["start"], "used": used}
        return result

    def alerts(self, snapshot):
        return [{"color": color, **estimate} for color, estimate in self.estimates(snapshot).items()
                if estimate is not None and estimate["state"] != "ok"]

    def _new_alerts(self, snapshot):
        new = []
        for alert in self.alerts(snapshot):
            severity = 2 if alert["state"] == "reserve" else 1
            row = self.db.execute("SELECT * FROM ink_alerts WHERE printer=? AND color=?",
                                  (snapshot.printer_id, alert["color"])).fetchone()
            if row and row["cycle"] == alert["at"] and row["severity"] >= severity:
                continue
            self.db.execute("INSERT OR REPLACE INTO ink_alerts VALUES(?,?,?,?)",
                            (snapshot.printer_id, alert["color"], alert["at"], severity))
            title = ("Réserve atteinte" if severity == 2 else "Encre à surveiller")+" · "+NAMES[alert["color"]]
            detail = f"Niveau estimé : {alert['percent']:.0f} %. "
            detail += ("Remplir ou remplacer avant de poursuivre." if severity == 2
                       else f"Environ {alert['usable_pages']} pages avant la réserve. Préparer le remplacement.")
            self.event(snapshot.printer_id, title, detail)
            self._queue_notification(snapshot.printer_id,alert['color'],'estimate',alert['state'],title,detail)
            new.append({**alert, "title": title, "detail": detail})
        return new

    def _queue_notification(self,printer,color,kind,state,title,detail):
        self.db.execute("UPDATE notifications SET delivery='superseded' WHERE printer=? AND color=? AND kind=? AND delivery IN ('queued','failed')",(printer,color,kind))
        self.db.execute("INSERT INTO notifications(printer,at,color,kind,state,title,detail) VALUES(?,?,?,?,?,?,?)",
                        (printer,datetime.now(timezone.utc).isoformat(),color,kind,state,title,detail))

    def _fault_notifications(self,snapshot):
        from .diagnostics import fault_alerts
        faults={a['color']:a for a in fault_alerts(snapshot)}
        for color in COLORS:
            item=faults.get(color)
            fingerprint=item['key'] if item else ''
            old=self.db.execute('SELECT fingerprint FROM fault_state WHERE printer=? AND color=?',(snapshot.printer_id,color)).fetchone()
            if item and (not old or old[0]!=fingerprint):
                self.event(snapshot.printer_id,item['title'],item['detail'])
                self._queue_notification(snapshot.printer_id,color,'diagnostic',item['state'],item['title'],item['detail'])
            elif not item:
                self.db.execute("UPDATE notifications SET delivery='superseded' WHERE printer=? AND color=? AND kind='diagnostic' AND delivery IN ('queued','failed')",(snapshot.printer_id,color))
            self.db.execute('INSERT OR REPLACE INTO fault_state VALUES(?,?,?)',(snapshot.printer_id,color,fingerprint))

    def pending_notifications(self,printer=None):
        retry=(datetime.now(timezone.utc)-timedelta(seconds=60)).isoformat()
        return [dict(r) for r in self.db.execute("SELECT * FROM notifications WHERE (delivery='queued' OR (delivery='failed' AND attempt_at<?)) AND (? IS NULL OR printer=?) ORDER BY id LIMIT 8",(retry,printer,printer))]

    def queue_reminders(self,snapshot):
        minutes=self.setting('reminder_minutes',0)
        if not minutes:return
        threshold=(datetime.now(timezone.utc)-timedelta(minutes=minutes)).isoformat()
        from .diagnostics import fault_alerts
        with self.db:
            active=[(a['color'],'estimate',a['state'],f"Rappel · {NAMES[a['color']]}",f"Niveau estimé : {a['percent']:.0f} %. Consulter la réserve dans OpenInk.") for a in self.alerts(snapshot)]
            active.extend((a['color'],'diagnostic',a['state'],'Rappel · '+a['title'],a['detail'])for a in fault_alerts(snapshot))
            for color,kind,state,title,detail in active:
                row=self.db.execute('SELECT delivery,at,attempt_at FROM notifications WHERE printer=? AND color=? AND kind=? ORDER BY id DESC LIMIT 1',(snapshot.printer_id,color,kind)).fetchone()
                if row and row['delivery']=='sent' and (row['attempt_at']or row['at'])<threshold:
                    self._queue_notification(snapshot.printer_id,color,kind,state,title,detail)

    def notification_delivery(self,identifier,state,detail=''):
        if state not in {'sent','failed'}:raise ValueError('État de livraison invalide')
        with self.db:
            self.db.execute('UPDATE notifications SET delivery=?,attempt_at=?,delivery_detail=? WHERE id=?',
                            (state,datetime.now(timezone.utc).isoformat(),detail,identifier))

    def check_alerts(self, snapshot):
        with self.db:
            return self._new_alerts(snapshot)

    def events(self, printer, limit=30):
        return [dict(r) for r in self.db.execute("SELECT * FROM events WHERE printer=? ORDER BY id DESC LIMIT ?", (printer,limit))]

    def activity(self, printer):
        today = datetime.now().astimezone().date()
        days = {today-timedelta(days=i): {"color": 0, "mono": 0} for i in reversed(range(7))}
        rows = self.db.execute("SELECT payload FROM readings WHERE printer=? ORDER BY id", (printer,))
        previous = None
        for row in rows:
            current = Snapshot(**json.loads(row[0]))
            day = datetime.fromisoformat(current.observed_at).astimezone().date()
            if previous and day in days:
                for kind, attr in (("color", "color_pages"), ("mono", "mono_pages")):
                    a, b = getattr(previous,attr), getattr(current,attr)
                    if a is not None and b is not None and b >= a:
                        days[day][kind] += b-a
            previous = current
        return [(str(day), values) for day, values in days.items()]

    def export(self, printer, path):
        readings = [json.loads(r[0]) for r in self.db.execute("SELECT payload FROM readings WHERE printer=? ORDER BY id", (printer,))]
        data = {"application": "OpenInk 1.7", "exported_at": datetime.now(timezone.utc).isoformat(),
                "printer": printer, "readings": readings, "events": self.events(printer, 100000),
                "estimation_settings": {"coverage": self.setting("coverage", 1.0),
                    "warning_percent": self.setting("warning_percent", DEFAULT_WARNING),
                    "reserve_percent": self.setting("reserve_percent", DEFAULT_RESERVE)},
                "calibrations": [dict(r) for r in self.db.execute("SELECT * FROM cartridges WHERE printer=?", (printer,))]}
        Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")

    def close(self):
        self.db.close()
