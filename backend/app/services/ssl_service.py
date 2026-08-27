"""
SSL-Überwachung – dritte Sicherungsebene für das HTTPS-Zertifikat.

Hintergrund: Am 27.08.2026 ist das Let's-Encrypt-Zertifikat abgelaufen, obwohl
eine automatische Erneuerung eingerichtet war. Zwei Fehler wirkten zusammen —
der certbot-Container lief nach einem Server-Neustart nicht wieder an (ihm
fehlte die restart-Policy), und nginx liest ein erneuertes Zertifikat nicht von
selbst neu ein. Beides ist repariert (siehe ``docker-compose.yml``), doch beide
Fehler hatten dieselbe eigentliche Ursache: **niemand hat es bemerkt.**

Dieses Modul schließt genau diese Lücke. Es prüft zwei Dinge:

1. **Wie lange ist das Zertifikat noch gültig?**  Gelesen wird die Datei
   ``/etc/letsencrypt/live/<domain>/fullchain.pem`` (nur lesend eingebunden).
2. **Läuft die Erneuerungsautomatik überhaupt noch?**  Ein stehengebliebener
   certbot-Container ist das Frühwarnsignal — er fällt Wochen auf, bevor die
   Restlaufzeit knapp wird.

Ergebnis landet in den Einstellungen unter „System" und geht bei Bedarf als
E-Mail an alle Administratoren.
"""
import os
import subprocess
import threading
import time
from datetime import datetime, timezone, timedelta

# ── Schwellwerte ──────────────────────────────────────────────────────────────
# Let's Encrypt stellt für 90 Tage aus und erneuert ab 30 Tagen Restlaufzeit.
# Ab 21 Tagen ist also bereits mindestens neun Tage lang etwas schiefgelaufen —
# ein guter Zeitpunkt zum Warnen, mit drei Wochen Luft zum Reagieren.
WARNUNG_TAGE  = 21
KRITISCH_TAGE = 7

LETSENCRYPT_DIR = os.environ.get("LETSENCRYPT_DIR", "/etc/letsencrypt")
CERTBOT_CONTAINER = os.environ.get("CERTBOT_CONTAINER", "deinezeit_certbot")


# ── Zertifikat lesen ──────────────────────────────────────────────────────────

def _finde_zertifikat() -> tuple:
    """Sucht das aktive Zertifikat. Gibt (pfad, domain) oder (None, None).

    Liegen mehrere Zertifikate vor (z.B. nach einem Domainwechsel), gewinnt das
    zur konfigurierten Domain passende; sonst das erstbeste."""
    live = os.path.join(LETSENCRYPT_DIR, "live")
    if not os.path.isdir(live):
        return None, None

    try:
        domains = sorted(d for d in os.listdir(live)
                         if os.path.isdir(os.path.join(live, d)) and d != "README")
    except OSError:
        return None, None
    if not domains:
        return None, None

    # Bevorzugt die Domain, unter der die Anwendung tatsächlich läuft.
    bevorzugt = (os.environ.get("WEBAUTHN_RP_ID")
                 or os.environ.get("FRONTEND_URL", "").replace("https://", "")
                                                      .replace("http://", "").strip("/"))
    reihenfolge = ([d for d in domains if d == bevorzugt] +
                   [d for d in domains if d != bevorzugt])

    for domain in reihenfolge:
        pfad = os.path.join(live, domain, "fullchain.pem")
        if os.path.isfile(pfad):
            return pfad, domain
    return None, None


def _ablaufdatum(pfad: str):
    """Liest das Ablaufdatum aus einer PEM-Datei. Gibt datetime (UTC) oder None."""
    try:
        from cryptography import x509
        with open(pfad, "rb") as f:
            cert = x509.load_pem_x509_certificate(f.read())
        # not_valid_after_utc gibt es ab cryptography 42; der Rückfall hält das
        # Modul auch mit älteren Versionen lauffähig.
        try:
            return cert.not_valid_after_utc
        except AttributeError:                                   # pragma: no cover
            return cert.not_valid_after.replace(tzinfo=timezone.utc)
    except Exception:                                            # noqa: BLE001
        return None


# ── Automatik prüfen ──────────────────────────────────────────────────────────

def _automatik_laeuft():
    """Prüft, ob der certbot-Container läuft. True / False / None (unbekannt).

    None bedeutet: es ließ sich nicht feststellen (kein Docker-Socket, lokale
    Entwicklungsinstanz). Das ist ausdrücklich KEINE Warnung — sonst würde die
    lokale Instanz dauernd Alarm schlagen."""
    if not os.path.exists("/var/run/docker.sock"):
        return None
    try:
        res = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", CERTBOT_CONTAINER],
            capture_output=True, text=True, timeout=10,
        )
        if res.returncode != 0:
            return False          # Container existiert nicht (mehr)
        return res.stdout.strip() == "true"
    except Exception:                                            # noqa: BLE001
        return None


# ── Gesamtstatus ──────────────────────────────────────────────────────────────

def zertifikat_status() -> dict:
    """Liefert den vollständigen Zustand des HTTPS-Zertifikats.

    status:
      ``ok``               – alles in Ordnung
      ``warnung``          – Restlaufzeit unter 21 Tagen ODER Automatik steht
      ``kritisch``         – Restlaufzeit unter 7 Tagen
      ``abgelaufen``       – Zertifikat ist nicht mehr gültig
      ``nicht_konfiguriert`` – kein Zertifikat vorhanden (z.B. lokal, ohne HTTPS)
    """
    automatik = _automatik_laeuft()
    pfad, domain = _finde_zertifikat()

    if not pfad:
        return {
            "status": "nicht_konfiguriert",
            "domain": None,
            "gueltig_bis": None,
            "tage_verbleibend": None,
            "automatik_laeuft": automatik,
            "meldung": "Kein HTTPS-Zertifikat gefunden. Bei einer lokalen "
                       "Instanz ohne HTTPS ist das normal.",
        }

    ablauf = _ablaufdatum(pfad)
    if ablauf is None:
        return {
            "status": "nicht_konfiguriert",
            "domain": domain,
            "gueltig_bis": None,
            "tage_verbleibend": None,
            "automatik_laeuft": automatik,
            "meldung": f"Das Zertifikat für {domain} konnte nicht gelesen werden.",
        }

    tage = (ablauf - datetime.now(timezone.utc)).days

    if tage < 0:
        status = "abgelaufen"
        meldung = (f"Das Zertifikat für {domain} ist seit {abs(tage)} Tag(en) "
                   f"abgelaufen. Besucher sehen eine Sicherheitswarnung.")
    elif tage <= KRITISCH_TAGE:
        status = "kritisch"
        meldung = (f"Das Zertifikat für {domain} läuft in {tage} Tag(en) ab und "
                   f"wurde nicht erneuert.")
    elif tage <= WARNUNG_TAGE:
        status = "warnung"
        meldung = (f"Das Zertifikat für {domain} läuft in {tage} Tagen ab. "
                   f"Die Erneuerung hätte längst laufen müssen.")
    elif automatik is False:
        # Der wertvollste Fall: das Zertifikat ist noch lange gültig, aber die
        # Automatik ist tot. Genau so beginnt jeder Zertifikatsausfall.
        status = "warnung"
        meldung = ("Das Zertifikat ist noch gültig, aber die automatische "
                   "Erneuerung läuft nicht. Ohne Eingriff läuft es ab.")
    else:
        status = "ok"
        meldung = f"Das Zertifikat für {domain} ist noch {tage} Tage gültig."

    return {
        "status": status,
        "domain": domain,
        "gueltig_bis": ablauf.isoformat(),
        "tage_verbleibend": tage,
        "automatik_laeuft": automatik,
        "meldung": meldung,
    }


# ── E-Mail-Warnung ────────────────────────────────────────────────────────────

def _admin_empfaenger(db) -> list:
    from app.models.user import User, UserRole
    # `isnot(False)` statt `is_(True)`: bei alten Datensätzen kann die Spalte
    # NULL sein. Im Zweifel lieber eine Warnung zu viel verschicken als den
    # einen Administrator zu übergehen, der sie gebraucht hätte.
    rows = (db.query(User)
              .filter(User.role == UserRole.admin, User.is_active.isnot(False))
              .all())
    return [u.email for u in rows if u.email]


def _warnung_versenden(db, zustand: dict) -> int:
    """Verschickt die Warnung an alle Administratoren. Gibt die Anzahl zurück."""
    from app.models.settings import Setting
    from app.services.email_service import send_email
    from app.core.config import settings as cfg

    empfaenger = _admin_empfaenger(db)
    if not empfaenger:
        return 0

    mail_einstellungen = {r.key: r.value for r in db.query(Setting).all()}
    domain = zustand.get("domain") or "der Server"
    tage = zustand.get("tage_verbleibend")

    if zustand["status"] == "abgelaufen":
        betreff = f"{cfg.APP_NAME}: HTTPS-Zertifikat ist ABGELAUFEN"
    else:
        betreff = f"{cfg.APP_NAME}: HTTPS-Zertifikat läuft in {tage} Tagen ab"

    text = (
        f"{zustand['meldung']}\n\n"
        "Was zu tun ist — bitte auf dem Server ausführen:\n\n"
        "    cd /opt/deinezeit\n"
        "    sudo bash scripts/ssl-renew.sh\n\n"
        "Das Skript erneuert das Zertifikat, startet eine ausgefallene\n"
        "Erneuerungsautomatik wieder und lässt nginx das neue Zertifikat\n"
        "einlesen. Den aktuellen Stand sehen Sie jederzeit in der Anwendung\n"
        "unter Einstellungen → System.\n\n"
        f"{cfg.APP_NAME}"
    )
    html = (
        f"<p>{zustand['meldung']}</p>"
        "<p><strong>Was zu tun ist</strong> — bitte auf dem Server ausführen:</p>"
        "<pre style=\"background:#f3f4f6;padding:10px;border-radius:6px\">"
        "cd /opt/deinezeit\nsudo bash scripts/ssl-renew.sh</pre>"
        "<p>Das Skript erneuert das Zertifikat, startet eine ausgefallene "
        "Erneuerungsautomatik wieder und lässt nginx das neue Zertifikat "
        "einlesen. Den aktuellen Stand sehen Sie jederzeit in der Anwendung "
        "unter <em>Einstellungen → System</em>.</p>"
        f"<p>{cfg.APP_NAME}</p>"
    )

    verschickt = 0
    for adresse in empfaenger:
        try:
            send_email(settings=mail_einstellungen, to_email=adresse,
                       subject=betreff, body_text=text, body_html=html)
            verschickt += 1
        except Exception as e:                                   # noqa: BLE001
            print(f"[WARN] SSL-Warnung an {adresse} fehlgeschlagen: {e}")
    return verschickt


def pruefen_und_warnen(db) -> dict:
    """Einmalige Prüfung samt E-Mail-Versand, wenn nötig.

    Wird vom Hintergrund-Worker aufgerufen und ist auch für einen Test direkt
    aufrufbar. Damit im Ernstfall nicht täglich dieselbe Mail eintrudelt,
    greift eine Sperre: bei Restlaufzeit über 7 Tagen höchstens alle 3 Tage
    eine Mail, darunter täglich — dann ist Nerven wichtiger als Ruhe."""
    from app.models.settings import Setting
    from app.api.settings import _save

    zustand = zertifikat_status()
    zustand["mails_verschickt"] = 0

    if zustand["status"] in ("ok", "nicht_konfiguriert"):
        return zustand

    # Wie lange ist die letzte Warnung her?
    letzte = db.query(Setting).filter(Setting.key == "ssl_warn_last_at").first()
    abstand_tage = 1 if zustand["status"] in ("kritisch", "abgelaufen") else 3
    if letzte and letzte.value:
        try:
            zuletzt = datetime.fromisoformat(letzte.value)
            if zuletzt.tzinfo is None:
                zuletzt = zuletzt.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) - zuletzt < timedelta(days=abstand_tage):
                return zustand          # noch in der Sperrfrist
        except ValueError:
            pass

    anzahl = _warnung_versenden(db, zustand)
    if anzahl:
        # _save committet selbst.
        _save(db, "ssl_warn_last_at", datetime.now(timezone.utc).isoformat())
    zustand["mails_verschickt"] = anzahl
    return zustand


# ── Hintergrund-Worker ────────────────────────────────────────────────────────
_worker_started = False


def _worker_loop():
    from app.db.base import SessionLocal
    # Beim Start kurz warten, damit Datenbank und Migrationen fertig sind.
    time.sleep(120)
    while True:
        try:
            db = SessionLocal()
            try:
                ergebnis = pruefen_und_warnen(db)
                if ergebnis["status"] not in ("ok", "nicht_konfiguriert"):
                    # WARNING, damit es im Serverlog auch wirklich auftaucht:
                    # info-Meldungen werden nicht ausgegeben.
                    print(f"[WARN] SSL: {ergebnis['meldung']}")
            finally:
                db.close()
        except Exception as e:                                   # noqa: BLE001
            print(f"[WARN] SSL-Worker: {e}")
        time.sleep(6 * 60 * 60)      # alle 6 Stunden


def start_ssl_worker():
    """Startet die Zertifikatsüberwachung (einmalig; in Tests deaktiviert)."""
    global _worker_started
    if _worker_started:
        return
    if os.environ.get("TEST_DATABASE_URL") or os.environ.get("DISABLE_SSL_WORKER") == "1":
        return
    _worker_started = True
    threading.Thread(target=_worker_loop, daemon=True, name="ssl-watch").start()
