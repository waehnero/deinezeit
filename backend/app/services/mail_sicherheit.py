"""
Sicherheitsregeln für Mailverbindungen (Mail-Import)
====================================================

Hintergrund: Bis Oktober 2026 konnte ein Mitarbeiter ein persönliches
IMAP-Konto mit „zentralen Zugangsdaten" anlegen und dabei den Zielserver frei
wählen. Das Backend meldete sich dann mit dem zentralen SMTP-Benutzer und
-Passwort bei diesem Server an — die Zugangsdaten landeten beim Angreifer
(Sicherheitsbefund zu Commit 1a5787e). Ebenso ließen sich die zentralen
Microsoft-Anwendungsrechte mit einer frei gewählten Mailbox auf fremde
Postfächer des Tenants richten.

Dieses Modul bündelt die Regeln, die seither für JEDE Mailverbindung gelten —
Verbindungstest, manueller Scan, Hintergrund-Scan und Outlook-Flagge laufen
alle über ``mail_ingest._imap_connect`` bzw. ``mail_ingest._graph_token`` und
damit hier durch. Eine Sperre nur in der Oberfläche reicht nicht.

1. **Zentrale Zugangsdaten nur für zentrale Konten.** ``use_central_credentials``
   ist ausschließlich an globalen, vom Admin verwalteten Konten
   (``owner_user_id IS NULL``) zulässig.
2. **Bindung an ein bestätigtes Ziel.** Beim Anlegen/Ändern durch den Admin
   (bzw. per „Ziel bestätigen") wird festgehalten, an welchen Server, Port,
   welche TLS-Art, Anmeldeidentität und — bei Graph — welche Mailbox die
   zentralen Zugangsdaten gehen dürfen (``MailAccount.zentral_bindung``).
   Weicht der aktuelle Stand davon ab (Host geändert, SMTP-Benutzer
   gewechselt, Mailbox anders), wird nicht verbunden, bis der Admin erneut
   bestätigt.
3. **Nur verschlüsselt, mit Zertifikats- und Hostnamenprüfung.** IMAP über
   TLS (Port 993) oder STARTTLS (Port 143) — STARTTLS ist dann Pflicht, ein
   Rückfall auf Klartext findet nicht statt. Zertifikate werden gegen die
   System-CAs und optional gegen admin-hinterlegte Firmen-CAs geprüft.
4. **Keine Verbindungen ins interne Netz.** Der Hostname wird aufgelöst; jede
   Adresse, die nicht global routbar ist (Loopback, privat, Link-Local inkl.
   Cloud-Metadaten 169.254.169.254, CGNAT, ULA, IPv4-gemappte IPv6 …), wird
   abgewiesen — außer der Admin hat das Ziel ausdrücklich freigegeben
   (``mail_interne_ziele``). Verbunden wird anschließend mit genau der
   geprüften Adresse, damit ein zweiter DNS-Abruf (DNS-Rebinding) nichts mehr
   umlenken kann.

Admin-Einstellungen (Tabelle ``settings``):
  - ``mail_interne_ziele``   Hostnamen, IP-Adressen oder Netze (CIDR), optional
                             mit ``:port``; je Zeile oder durch Komma getrennt
  - ``mail_ca_zertifikate``  zusätzliche vertrauenswürdige CA-Zertifikate (PEM)
"""

import ipaddress
import logging
import re
import socket
import ssl
from typing import Iterable, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.mailimport import MailAccount
from app.models.settings import Setting

logger = logging.getLogger(__name__)

SETTING_INTERNE_ZIELE = "mail_interne_ziele"
SETTING_CA_ZERTIFIKATE = "mail_ca_zertifikate"

GRAPH_HOST = "graph.microsoft.com"

# Hostname nach RFC 1123 (Labels aus Buchstaben, Ziffern, Bindestrich)
_HOST_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))*\.?$")
# Graph: Mailbox als E-Mail-Adresse oder Objekt-ID (GUID)
_MAILBOX_RE = re.compile(r"^[A-Za-z0-9._%+'-]{1,64}@[A-Za-z0-9.-]{1,253}$")
_GUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                      r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


class MailSicherheitsFehler(RuntimeError):
    """Verbindung aus Sicherheitsgründen abgelehnt (vor jeder Anmeldung)."""


# ── Hilfen ────────────────────────────────────────────────────────────────────
def _setting(db: Session, key: str) -> str:
    row = db.query(Setting).filter(Setting.key == key).first()
    return (row.value or "") if row else ""


def _settings(db: Session, keys: Iterable[str]) -> dict:
    rows = db.query(Setting).filter(Setting.key.in_(list(keys))).all()
    return {r.key: (r.value or "") for r in rows}


def geheimnisse_entfernen(text: str, geheimnisse: Iterable[Optional[str]]) -> str:
    """Ersetzt bekannte Geheimnisse in Fehlertexten (Log, last_error, API)."""
    text = str(text or "")
    for g in geheimnisse:
        if g and len(g) >= 3:
            text = text.replace(g, "***")
    return text


def host_gueltig(host: Optional[str]) -> bool:
    """Syntaxprüfung: Hostname oder IP-Literal, keine Pfade/Ports/Leerzeichen."""
    if not host:
        return False
    h = host.strip()
    if h.startswith("[") and h.endswith("]"):
        h = h[1:-1]
    try:
        ipaddress.ip_address(h)
        return True
    except ValueError:
        return bool(_HOST_RE.match(h))


def tenant_gueltig(tenant: Optional[str]) -> bool:
    return bool(tenant) and (bool(_GUID_RE.match(tenant)) or bool(_HOST_RE.match(tenant)))


def mailbox_gueltig(mailbox: Optional[str]) -> bool:
    return bool(mailbox) and (bool(_MAILBOX_RE.match(mailbox))
                              or bool(_GUID_RE.match(mailbox)))


# ── 1+2. Zentrale Zugangsdaten: Bindung an ein bestätigtes Ziel ───────────────
def imap_port(account: MailAccount) -> int:
    return account.imap_port or (993 if account.imap_ssl else 143)


def imap_tls_art(account: MailAccount) -> str:
    return "ssl" if account.imap_ssl else "starttls"


def aktuelle_bindung(db: Session, account: MailAccount) -> Optional[dict]:
    """
    Das Ziel, an das die zentralen Zugangsdaten bei diesem Konto JETZT gingen.
    ``None``, wenn die zentrale Konfiguration (noch) unvollständig ist.
    Enthält nie Geheimnisse — nur Server, Port, TLS-Art, Anmeldeidentität
    und Mailbox.
    """
    if account.protocol == "imap":
        identitaet = _setting(db, "smtp_user").strip().lower()
        if not identitaet or not account.imap_host:
            return None
        return {
            "protocol": "imap",
            "host": account.imap_host.strip().lower().rstrip("."),
            "port": imap_port(account),
            "tls": imap_tls_art(account),
            "identitaet": identitaet,
            "mailbox": None,
        }
    s = _settings(db, ["ms_tenant_id", "ms_client_id", "smtp_from_email"])
    tenant = (s.get("ms_tenant_id") or "").strip().lower()
    client = (s.get("ms_client_id") or "").strip().lower()
    mailbox = (account.graph_mailbox or s.get("smtp_from_email") or "").strip().lower()
    if not (tenant and client and mailbox):
        return None
    return {
        "protocol": "graph",
        "host": GRAPH_HOST,
        "port": 443,
        "tls": "ssl",
        "identitaet": f"{client}@{tenant}",
        "mailbox": mailbox,
    }


_BINDUNG_FELDER = ("protocol", "host", "port", "tls", "identitaet", "mailbox")


def _bindung_kern(b: Optional[dict]) -> Optional[tuple]:
    if not b:
        return None
    return tuple(b.get(k) for k in _BINDUNG_FELDER)


SPERRE_PERSOENLICH = (
    "Zentrale Zugangsdaten sind für persönliche Mail-Konten nicht zulässig. "
    "Bitte eigene Zugangsdaten hinterlegen oder ein vom Admin freigegebenes "
    "zentrales Konto verwenden.")
SPERRE_UNBESTAETIGT = (
    "Zentrale Zugangsdaten gesperrt: Das Ziel dieses Kontos wurde noch nicht "
    "vom Admin bestätigt (Konto bearbeiten → „Ziel bestätigen\").")
SPERRE_GEAENDERT = (
    "Zentrale Zugangsdaten gesperrt: Server, Anmeldeidentität oder Postfach "
    "haben sich seit der Bestätigung geändert. Der Admin muss das Ziel "
    "erneut bestätigen.")
SPERRE_UNVOLLSTAENDIG = (
    "Zentrale E-Mail-Zugangsdaten fehlen (Einstellungen → System → E-Mail)")


def zentral_sperrgrund(db: Session, account: MailAccount) -> Optional[str]:
    """
    Warum dieses Konto die zentralen Zugangsdaten gerade NICHT verwenden darf
    — oder ``None``, wenn es darf bzw. sie gar nicht verwendet.
    """
    if not account.use_central_credentials:
        return None
    if account.owner_user_id is not None:
        return SPERRE_PERSOENLICH
    gebunden = account.zentral_bindung
    if not gebunden:
        return SPERRE_UNBESTAETIGT
    aktuell = aktuelle_bindung(db, account)
    if aktuell is None:
        return SPERRE_UNVOLLSTAENDIG
    if _bindung_kern(aktuell) != _bindung_kern(gebunden):
        return SPERRE_GEAENDERT
    return None


def zentrale_nutzung_pruefen(db: Session, account: MailAccount) -> None:
    """Wirft ``MailSicherheitsFehler``, wenn die zentrale Nutzung gesperrt ist."""
    grund = zentral_sperrgrund(db, account)
    if grund:
        raise MailSicherheitsFehler(grund)


def bindung_setzen(db: Session, account: MailAccount, admin_id, zeitpunkt) -> dict:
    """
    Hält das aktuelle Ziel als vom Admin bestätigt fest. Nur aus
    Admin-Endpunkten aufrufen.
    """
    if account.owner_user_id is not None:
        raise MailSicherheitsFehler(SPERRE_PERSOENLICH)
    b = aktuelle_bindung(db, account)
    if b is None:
        raise MailSicherheitsFehler(SPERRE_UNVOLLSTAENDIG)
    b = dict(b)
    b["bestaetigt_von"] = str(admin_id) if admin_id else None
    b["bestaetigt_am"] = zeitpunkt.isoformat() if zeitpunkt else None
    account.zentral_bindung = b
    return b


# ── 3. TLS ────────────────────────────────────────────────────────────────────
def tls_kontext(db: Session) -> ssl.SSLContext:
    """
    TLS-Kontext mit Zertifikats- UND Hostnamenprüfung. Zusätzlich zu den
    System-CAs werden die vom Admin hinterlegten Firmen-CAs vertraut
    (interne Mailserver mit eigener PKI). Ein Abschalten der Prüfung ist
    bewusst nicht vorgesehen.
    """
    ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    pem = _setting(db, SETTING_CA_ZERTIFIKATE).strip()
    if pem:
        try:
            ctx.load_verify_locations(cadata=pem)
        except (ssl.SSLError, ValueError) as e:
            # Kaputtes PEM darf nicht still zu „gar keine Firmen-CA" werden,
            # ohne dass es jemand merkt — die Verbindung schlägt dann ohnehin
            # an der Zertifikatsprüfung fehl; der Hinweis erklärt, warum.
            logger.warning("Hinterlegte Mail-CA-Zertifikate sind ungültig: %s", e)
    return ctx


def ca_pem_gueltig(pem: str) -> bool:
    if not pem.strip():
        return True
    try:
        ssl.create_default_context().load_verify_locations(cadata=pem)
        return True
    except (ssl.SSLError, ValueError):
        return False


# ── 4. Zielprüfung (Netz) ─────────────────────────────────────────────────────
def interne_ziele(db: Session) -> List[str]:
    roh = _setting(db, SETTING_INTERNE_ZIELE)
    return [z.strip().lower() for z in re.split(r"[\s,;]+", roh) if z.strip()]


_PORT_RE = re.compile(r"^(?P<ziel>[^:\[\]]+|\[[^\]]+\]):(?P<port>\d{1,5})$")


def _freigabe_zerlegen(eintrag: str) -> Tuple[str, Optional[int]]:
    """
    ``ziel`` oder ``ziel:port``. Ohne Port gelten die IMAP-Ports 143/993.
    IPv6-Netze mit Port in eckigen Klammern: ``[fd00::/64]:1143``.
    """
    m = _PORT_RE.match(eintrag)
    if m:
        return m.group("ziel").strip("[]"), int(m.group("port"))
    return eintrag, None


def interne_ziele_gueltig(eintraege: Iterable[str]) -> Tuple[bool, Optional[str]]:
    for e in eintraege:
        ziel, port = _freigabe_zerlegen(e)
        if port is not None and not (1 <= port <= 65535):
            return False, e
        try:
            ipaddress.ip_network(ziel, strict=False)
            continue
        except ValueError:
            pass
        if not _HOST_RE.match(ziel):
            return False, e
    return True, None


def _ip_normalisieren(ip: ipaddress._BaseAddress) -> ipaddress._BaseAddress:
    # ::ffff:127.0.0.1 und Co. wie die eingebettete IPv4-Adresse behandeln
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped:
            return ip.ipv4_mapped
        if ip.sixtofour:
            return ip.sixtofour
    return ip


def _ip_oeffentlich(ip: ipaddress._BaseAddress) -> bool:
    ip = _ip_normalisieren(ip)
    if (ip.is_loopback or ip.is_link_local or ip.is_private or ip.is_multicast
            or ip.is_reserved or ip.is_unspecified):
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.is_site_local:
        return False  # veraltetes fec0::/10, in Altnetzen noch intern genutzt
    if isinstance(ip, ipaddress.IPv4Address) and ip in ipaddress.ip_network("100.64.0.0/10"):
        return False  # Carrier-Grade-NAT / Shared Address Space
    return ip.is_global


def _intern_freigegeben(host: str, ip: ipaddress._BaseAddress, port: int,
                        freigaben: List[str]) -> bool:
    """Passt ein Freigabe-Eintrag (Hostname oder IP/Netz, optional mit Port)?"""
    ip = _ip_normalisieren(ip)
    for eintrag in freigaben:
        ziel, f_port = _freigabe_zerlegen(eintrag)
        if (port != f_port) if f_port is not None else (port not in INTERNE_PORTS):
            continue
        if ziel == host:
            return True
        try:
            if ip in ipaddress.ip_network(ziel, strict=False):
                return True
        except (ValueError, TypeError):
            continue
    return False


# Interne (freigegebene) Ziele nur auf den IMAP-Ports — eine Freigabe soll
# einen Mailserver öffnen, nicht jeden Dienst auf diesem Rechner.
INTERNE_PORTS = (143, 993)

_NICHT_ERREICHBAR = ("Mailserver '{h}' ist nicht erreichbar oder nicht freigegeben. "
                     "Mailserver im internen Netz muss der Admin ausdrücklich "
                     "freigeben (Einstellungen → KI & Mail-Import → Sicherheit der Mailverbindungen).")


def ziel_adressen(db: Session, host: str, port: int) -> List[str]:
    """
    Prüft Host und Port und liefert die IP-Adressen (in Auflösungsreihenfolge),
    zu denen verbunden werden darf. Wirft ``MailSicherheitsFehler`` vor jedem
    Verbindungsaufbau.

    Freigabe eines internen Ziels durch den Admin: per Hostname (dann sind
    alle Adressen erlaubt, zu denen er auflöst) oder per IP/Netz — ohne
    Portangabe nur auf den IMAP-Ports 143/993, sonst genau auf dem
    angegebenen Port (``exchange.firma.local:1993``).

    Die Fehlermeldung ist für „nicht auflösbar" und „intern" bewusst gleich
    und nennt keine Adresse: Sonst könnte jeder Mitarbeiter über den
    Verbindungstest interne Namen und Adressen auskundschaften. Details
    stehen nur im Serverlog.
    """
    if not host_gueltig(host):
        raise MailSicherheitsFehler("Ungültiger Mailserver-Name")
    if not isinstance(port, int) or not (1 <= port <= 65535):
        raise MailSicherheitsFehler("Ungültiger Port")
    h = host.strip().strip("[]").lower().rstrip(".")
    fehler = MailSicherheitsFehler(_NICHT_ERREICHBAR.format(h=h))
    freigaben = interne_ziele(db)

    try:
        infos = socket.getaddrinfo(h, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError) as e:
        logger.info("Mailserver %s nicht auflösbar", h)
        raise fehler from e

    adressen = []
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0].split("%")[0])
        except (ValueError, IndexError):
            continue
        if ip not in adressen:
            adressen.append(ip)
    if not adressen:
        raise fehler

    # ALLE Adressen müssen zulässig sein — sonst entschiede der Zufall der
    # Reihenfolge, ob eine interne Adresse erreicht wird.
    for ip in adressen:
        if _ip_oeffentlich(ip):
            continue
        if _intern_freigegeben(h, ip, port, freigaben):
            continue
        logger.warning("Mailverbindung zu %s (%s, Port %s) abgewiesen: interne Adresse "
                       "ohne Freigabe", h, ip, port)
        raise fehler
    return [str(ip) for ip in adressen]


def ziel_aufloesen(db: Session, host: str, port: int) -> str:
    """Erste zulässige Adresse (Kurzform von ``ziel_adressen``)."""
    return ziel_adressen(db, host, port)[0]
