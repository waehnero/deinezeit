"""
Ereignisarten des Anmelde-Prüfpfads (Tabelle ``auth_events``)
============================================================

Zentral aufgelistet, damit in der Datenbank keine Schreibweisen auseinander
laufen und die Oberfläche für jede Art einen deutschen Text hat. Neue Arten
hier ergänzen — sonst erscheinen sie in der Übersicht als nackter Schlüssel.

Bewusst *keine* Enum-Spalte in der Datenbank: eine neue Ereignisart soll ohne
Migration möglich sein, und ein unbekannter Wert im Prüfpfad darf nie ein
Schreiben verhindern. Ein Log, das die Anmeldung blockieren kann, ist ein
Ausfallrisiko ohne Sicherheitsgewinn.
"""

# ── Anmeldung ────────────────────────────────────────────────────────────────
LOGIN_OK = "login_ok"
LOGIN_FAIL = "login_fail"                 # Passwort falsch oder Konto unbekannt
LOGIN_BLOCKED = "login_blocked"           # Konto war gesperrt
LOGIN_INACTIVE = "login_inactive"         # Konto deaktiviert
TOTP_FAIL = "totp_fail"
TOTP_OK = "totp_ok"
RECOVERY_USED = "recovery_used"           # Einmal-Code statt 2FA verwendet
PASSKEY_OK = "passkey_ok"
PASSKEY_FAIL = "passkey_fail"

# ── Sitzungen ────────────────────────────────────────────────────────────────
LOGOUT = "logout"
LOGOUT_ALL = "logout_all"
SESSION_REVOKED = "session_revoked"       # Einzelne Sitzung vom Nutzer beendet
REFRESH_OK = "refresh_ok"
REFRESH_FAIL = "refresh_fail"
REFRESH_REUSE = "refresh_reuse"           # Bereits verbrauchter Token erneut

# ── Passwort ─────────────────────────────────────────────────────────────────
PASSWORD_CHANGED = "password_changed"
RESET_REQUESTED = "reset_requested"
RESET_DONE = "reset_done"
RESET_FAIL = "reset_fail"

# ── 2FA / Passkeys verwalten ─────────────────────────────────────────────────
TOTP_ENABLED = "totp_enabled"
TOTP_DISABLED = "totp_disabled"
RECOVERY_GENERATED = "recovery_generated"
PASSKEY_ADDED = "passkey_added"
PASSKEY_REMOVED = "passkey_removed"

# ── Verwaltung ───────────────────────────────────────────────────────────────
ADMIN_UNLOCKED = "admin_unlocked"         # Sperre vom Administrator aufgehoben
ADMIN_USER_CHANGED = "admin_user_changed"

#: Deutsche Bezeichnungen für die Anzeige. Fehlt ein Schlüssel, zeigt die
#: Oberfläche ihn unverändert an — sichtbar, aber nicht kaputt.
EVENT_LABELS: dict[str, str] = {
    LOGIN_OK:           "Anmeldung erfolgreich",
    LOGIN_FAIL:         "Anmeldung fehlgeschlagen",
    LOGIN_BLOCKED:      "Anmeldung abgewiesen (Konto gesperrt)",
    LOGIN_INACTIVE:     "Anmeldung abgewiesen (Konto deaktiviert)",
    TOTP_FAIL:          "2FA-Code falsch",
    TOTP_OK:            "2FA-Code bestätigt",
    RECOVERY_USED:      "Einmal-Code verwendet",
    PASSKEY_OK:         "Passkey-Anmeldung erfolgreich",
    PASSKEY_FAIL:       "Passkey-Anmeldung fehlgeschlagen",
    LOGOUT:             "Abgemeldet",
    LOGOUT_ALL:         "Von allen Geräten abgemeldet",
    SESSION_REVOKED:    "Sitzung beendet",
    REFRESH_OK:         "Sitzung verlängert",
    REFRESH_FAIL:       "Sitzung konnte nicht verlängert werden",
    REFRESH_REUSE:      "Verbrauchter Token erneut verwendet — Sitzungen entwertet",
    PASSWORD_CHANGED:   "Passwort geändert",
    RESET_REQUESTED:    "Passwort-Zurücksetzung angefordert",
    RESET_DONE:         "Passwort zurückgesetzt",
    RESET_FAIL:         "Zurücksetzen fehlgeschlagen",
    TOTP_ENABLED:       "2FA aktiviert",
    TOTP_DISABLED:      "2FA deaktiviert",
    RECOVERY_GENERATED: "Einmal-Codes erzeugt",
    PASSKEY_ADDED:      "Passkey hinzugefügt",
    PASSKEY_REMOVED:    "Passkey entfernt",
    ADMIN_UNLOCKED:     "Sperre durch Administrator aufgehoben",
    ADMIN_USER_CHANGED: "Benutzer durch Administrator geändert",
}

#: Ereignisse, die auf einen Angriffsversuch hindeuten können. Die Oberfläche
#: hebt sie hervor; die Systemseite kann sie zählen.
VERDAECHTIG = frozenset({
    LOGIN_FAIL, LOGIN_BLOCKED, TOTP_FAIL, PASSKEY_FAIL,
    REFRESH_REUSE, RESET_FAIL,
})


def label(event: str) -> str:
    """Deutscher Text zu einer Ereignisart (unbekannte unverändert)."""
    return EVENT_LABELS.get(event, event)
