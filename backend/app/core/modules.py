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
"""
from app.models.user import User, UserRole

# Reihenfolge = Anzeige-Reihenfolge im Menü / in der Benutzerverwaltung
MODULES = (
    ("dashboard",     "Dashboard"),
    ("zeiterfassung", "Zeiterfassung"),
    ("aufgaben",      "Aufgaben"),
    ("projekte",      "Projekte"),
    ("verkauf",       "Verkauf"),
    ("postecke",      "Postecke"),
    ("stammdaten",    "Stammdaten"),
    ("datacenter",    "Datacenter"),
)
MODULE_KEYS = tuple(k for k, _ in MODULES)
MODULE_LABELS = dict(MODULES)


def user_modules(user: User) -> list[str]:
    """Effektive Modul-Liste eines Benutzers (Admin: immer alle)."""
    if user.role == UserRole.admin or user.allowed_modules is None:
        return list(MODULE_KEYS)
    return [m for m in user.allowed_modules if m in MODULE_KEYS]


def user_has_module(user: User, module: str) -> bool:
    return module in user_modules(user)
