"""
Modulrechte (Beschluss 2026-07-11/12)
=====================================

Der Admin kann pro Benutzer festlegen, welche Module er verwenden darf
(nur an/aus, kein Lesen/Schreiben-Split). Gespeichert als JSON-Liste in
users.allowed_modules:

  NULL  = alle Module erlaubt (Standard — kein Bruch für Bestandsbenutzer)
  []    = kein Modul erlaubt
  [...] = genau diese Module

Admins haben immer alle Module.

Wichtige Querbezüge (bewusst NICHT gesperrt):
  - Stammdaten LESEN bleibt für alle offen (Auswahlfelder in Zeiterfassung,
    Aufgaben, Verkauf, …) — nur Schreiben erfordert das Modul 'stammdaten'.
  - Datacenter: Datei-Anhänge je Datensatz (AttachmentPanel in anderen
    Modulen) bleiben offen — nur die Datacenter-Übersicht (/all, /stats)
    erfordert das Modul 'datacenter'.
  - Buchhaltung ist ein ZUSATZ zu Verkauf, kein eigenständiger Bereich:
    Verkaufsbuch, offene Posten, Kontenplan und Buchhaltungs-Export
    erfordern 'verkauf' UND 'buchhaltung'. Wer Belege schreiben darf, muss
    nicht zwangsläufig die Auswertungen und den Export sehen.
"""
from app.models.user import User

# Reihenfolge = Anzeige-Reihenfolge im Menü / in der Benutzerverwaltung
MODULES = (
    ("dashboard",     "Dashboard"),
    ("zeiterfassung", "Zeiterfassung"),
    ("aufgaben",      "Aufgaben"),
    ("projekte",      "Projekte"),
    ("verkauf",       "Verkauf"),
    ("buchhaltung",   "Buchhaltung"),
    ("postecke",      "Postecke"),
    ("stammdaten",    "Stammdaten"),
    ("datacenter",    "Datacenter"),
)
MODULE_KEYS = tuple(k for k, _ in MODULES)
MODULE_LABELS = dict(MODULES)


def user_modules(user: User) -> list[str]:
    """Module mit Lesezugriff (Admin: immer alle).

    Seit Migration 0055 kommt die Antwort aus dem Gruppen-Rechtemodell
    (``core/berechtigungen.py``). Die Funktion bleibt als Einstiegspunkt
    bestehen, weil sie an vielen Stellen aufgerufen wird — sie liest nur nicht
    mehr selbst ``allowed_modules``, sondern fragt die eine Stelle, an der die
    Rechte zusammengerechnet werden. Zwei Auswertungen desselben Modells
    laufen sonst mit der Zeit auseinander, und die Abweichung fällt genau dann
    auf, wenn jemand etwas sehen kann, was er nicht sehen soll.
    """
    from app.core.berechtigungen import module_mit_zugang
    return module_mit_zugang(user)


def user_has_module(user: User, module: str) -> bool:
    """Lesezugriff auf ein Modul.

    Entspricht dem alten Verhalten „Modul freigeschaltet". Für die Frage, ob
    jemand auch *ändern* darf, gibt es ``berechtigungen.hat_recht(user, modul,
    SCHREIBEN)``.
    """
    from app.core.berechtigungen import LESEN, hat_recht
    return hat_recht(user, module, LESEN)
