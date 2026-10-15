"""
API-Router für den Mail-Import (Aufgabenmodul, Etappe 3).

Endpunkte:
  Konten:      GET/POST        /mail-import/accounts
               PUT/DELETE      /mail-import/accounts/{id}
               GET             /mail-import/accounts/{id}/folders   (Verbindungstest)
               POST            /mail-import/accounts/{id}/scan      (manueller Scan)
  Vorschläge:  GET             /mail-import/suggestions?status=offen
               POST            /mail-import/suggestions/{id}/accept  -> erzeugt Todo
               POST            /mail-import/suggestions/{id}/dismiss
  KI:          GET/PUT         /mail-import/ki-settings              (PUT nur Admin)

  Sicherheit:  GET/PUT         /mail-import/sicherheit               (nur Admin)
               POST            /mail-import/accounts/{id}/zentral-bestaetigen (nur Admin)

Rechte:
  - Persönliche Konten: nur der Besitzer (verwalten, scannen, Vorschläge).
    Sie arbeiten ausschließlich mit eigenen Zugangsdaten.
  - Globale Konten (owner_user_id=NULL): verwaltet der Admin. Verwenden
    (sehen, scannen, Vorschläge entscheiden) dürfen Admins und die
    freigegebenen Benutzer (freigabe_alle bzw. Mitglieder von
    freigabe_gruppen). Nur globale Konten dürfen die zentralen
    Zugangsdaten nutzen — und nur an das vom Admin bestätigte Ziel
    (services/mail_sicherheit.py). Ziel, Port, TLS, Anmeldeidentität und
    Mailbox bestimmt der Server; Mitarbeiter können sie nicht verändern.
"""
import logging
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.api.deps import get_current_user, require_admin
from app.models.user import User, UserRole
from app.models.aufgaben import Todo
from app.models.mailimport import MailAccount, MailTaskSuggestion
from app.models.settings import Setting
from app.models.user import PermissionGroup
from app.schemas.mailimport import (
    MailAccountCreate, MailAccountUpdate, MailAccountResponse,
    SuggestionResponse, SuggestionAccept, ScanResult,
    KiSettingsResponse, KiSettingsUpdate,
    MailSicherheitResponse, MailSicherheitUpdate,
)
from app.services import mail_ingest, mail_sicherheit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mail-import", tags=["Mail-Import"])


# ── Hilfen ────────────────────────────────────────────────────────────────────
def _ist_admin(user: User) -> bool:
    return user.role == UserRole.admin


# Felder, die Anlegen/Ändern überhaupt setzen darf. Alles andere
# (owner_user_id, zentral_bindung, last_error, …) bestimmt der Server.
_KONTO_FELDER = (
    "name", "protocol", "imap_host", "imap_port", "imap_ssl", "imap_user",
    "graph_tenant_id", "graph_client_id", "graph_mailbox", "folder",
    "use_central_credentials", "flag_erledigt", "auto_scan",
    "scan_interval_minutes", "is_active", "freigabe_alle", "freigabe_gruppen",
)
# Änderungen an diesen Feldern verändern das Ziel der zentralen Zugangsdaten
_ZIEL_FELDER = ("protocol", "imap_host", "imap_port", "imap_ssl",
                "graph_mailbox", "use_central_credentials")
# Nur an globalen Konten und nur vom Admin
_ADMIN_FELDER = ("freigabe_alle", "freigabe_gruppen")
# Spalten ohne NULL — ein ausdrückliches null im Update bleibt unverändert
_NICHT_NULL = ("name", "protocol", "imap_ssl", "folder", "use_central_credentials",
               "flag_erledigt", "auto_scan", "scan_interval_minutes", "is_active",
               "freigabe_alle", "freigabe_gruppen")


def _gruppen_ids(user: User) -> set:
    return {str(g.id) for g in (user.groups or [])}


def _darf_verwenden(acc: MailAccount, user: User) -> bool:
    """Persönlich: nur der Besitzer. Global: Admin oder freigegeben."""
    if acc.owner_user_id:
        return acc.owner_user_id == user.id
    if _ist_admin(user) or acc.freigabe_alle:
        return True
    return bool(_gruppen_ids(user) & {str(g) for g in (acc.freigabe_gruppen or [])})


def _verwendbare_konten(db: Session, user: User) -> List[MailAccount]:
    rows = (db.query(MailAccount)
            .filter(or_(MailAccount.owner_user_id == user.id,
                        MailAccount.owner_user_id.is_(None)))
            .order_by(MailAccount.created_at).all())
    return [a for a in rows if _darf_verwenden(a, user)]


def _account_response(db: Session, acc: MailAccount, user: User) -> MailAccountResponse:
    resp = MailAccountResponse.model_validate(acc)
    resp.has_secret = bool(acc.secret_enc)
    resp.zentral_sperrgrund = mail_sicherheit.zentral_sperrgrund(db, acc)
    resp.zentral_bestaetigt_am = (acc.zentral_bindung or {}).get("bestaetigt_am")
    if acc.owner_user_id is None and not _ist_admin(user):
        # Mitarbeiter sehen von zentralen Konten nur, was sie zum Arbeiten
        # brauchen — keine Anmeldeidentität, keine App-Kennungen, keine
        # Freigabeliste.
        resp.imap_user = None
        resp.graph_tenant_id = None
        resp.graph_client_id = None
        resp.freigabe_alle = None
        resp.freigabe_gruppen = None
    elif acc.owner_user_id is not None:
        resp.freigabe_alle = None
        resp.freigabe_gruppen = None
    else:
        resp.freigabe_gruppen = [str(g) for g in (acc.freigabe_gruppen or [])]
    return resp


def _get_account_fuer_user(db: Session, account_id: UUID, user: User,
                           verwalten: bool = False) -> MailAccount:
    """
    Lädt ein Konto mit Rechteprüfung.
      verwalten=False: Besitzer ODER (globales Konto: Admin oder freigegeben)
      verwalten=True : Besitzer ODER (globales Konto: nur Admin)
    """
    acc = db.query(MailAccount).filter(MailAccount.id == account_id).first()
    if not acc:
        raise HTTPException(404, "Mail-Konto nicht gefunden")
    if acc.owner_user_id:
        if acc.owner_user_id != user.id:
            raise HTTPException(403, "Kein Zugriff auf dieses Mail-Konto")
    else:
        if verwalten and not _ist_admin(user):
            raise HTTPException(403, "Globale Mail-Konten verwaltet der Admin")
        if not _darf_verwenden(acc, user):
            raise HTTPException(403, "Dieses zentrale Mail-Konto ist für dich nicht freigegeben")
    return acc


def _felder_pruefen(db: Session, acc: MailAccount, payload: dict, user: User):
    """Serverseitige Regeln für Anlegen/Ändern — unabhängig von der Oberfläche."""
    persoenlich = acc.owner_user_id is not None
    zentral = payload.get("use_central_credentials")
    if zentral is None:
        zentral = acc.use_central_credentials

    if persoenlich and payload.get("use_central_credentials"):
        raise HTTPException(403, mail_sicherheit.SPERRE_PERSOENLICH)
    if persoenlich:
        for f in _ADMIN_FELDER:
            if payload.get(f):
                raise HTTPException(400, "Freigaben gibt es nur bei zentralen Konten")
    elif not _ist_admin(user):
        raise HTTPException(403, "Globale Mail-Konten verwaltet der Admin")

    host = payload.get("imap_host", acc.imap_host)
    protocol = payload.get("protocol", acc.protocol)
    if protocol == "imap" and host and not mail_sicherheit.host_gueltig(host):
        raise HTTPException(400, "Ungültiger IMAP-Server (nur Hostname oder IP-Adresse)")
    mailbox = payload.get("graph_mailbox", acc.graph_mailbox)
    if protocol == "graph" and mailbox and not mail_sicherheit.mailbox_gueltig(mailbox):
        raise HTTPException(400, "Ungültige Mailbox (E-Mail-Adresse oder Objekt-ID erwartet)")
    tenant = payload.get("graph_tenant_id", acc.graph_tenant_id)
    if protocol == "graph" and tenant and not zentral \
            and not mail_sicherheit.tenant_gueltig(tenant):
        raise HTTPException(400, "Ungültige Tenant-ID")

    gruppen = payload.get("freigabe_gruppen")
    if gruppen:
        ids = [str(g) for g in gruppen]
        vorhanden = {str(r[0]) for r in db.query(PermissionGroup.id)
                     .filter(PermissionGroup.id.in_(ids)).all()}
        if set(ids) - vorhanden:
            raise HTTPException(400, "Unbekannte Rechtegruppe in der Freigabe")


def _setze_felder(acc: MailAccount, payload: dict):
    for key in _KONTO_FELDER:
        if key not in payload:
            continue
        value = payload[key]
        if value is None and key in _NICHT_NULL:
            continue
        if key == "freigabe_gruppen":
            value = [str(g) for g in (value or [])]
        setattr(acc, key, value)
    if payload.get("secret"):
        acc.secret_enc = mail_ingest.encrypt_secret(payload["secret"])


def _bindung_erneuern(db: Session, acc: MailAccount, user: User):
    """Admin hat das Ziel eines zentralen Kontos gerade eingetragen/geändert."""
    if not (acc.use_central_credentials and acc.owner_user_id is None):
        return
    try:
        mail_sicherheit.bindung_setzen(db, acc, user.id, datetime.now(timezone.utc))
    except mail_sicherheit.MailSicherheitsFehler as e:
        raise HTTPException(400, str(e)) from e


def _protokollieren(aktion: str, acc: MailAccount, user: User, felder=()):
    """Sicherheitsrelevante Konfigurationsänderung — nur Feldnamen, nie Werte
    von Geheimnissen."""
    namen = sorted(("secret(neu)" if f == "secret" else f) for f in felder)
    logger.info("Mail-Konto %s: id=%s global=%s zentral=%s durch Benutzer %s; Felder: %s",
                aktion, acc.id, acc.owner_user_id is None,
                bool(acc.use_central_credentials), user.id, ", ".join(namen) or "-")


# ── Konten ────────────────────────────────────────────────────────────────────
@router.get("/accounts", response_model=List[MailAccountResponse])
def list_accounts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Eigene Konten + für mich freigegebene zentrale Konten."""
    return [_account_response(db, a, current_user)
            for a in _verwendbare_konten(db, current_user)]


@router.post("/accounts", response_model=MailAccountResponse, status_code=201)
def create_account(
    body: MailAccountCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if body.is_global and not _ist_admin(current_user):
        raise HTTPException(403, "Globale Mail-Konten kann nur der Admin anlegen")
    if body.use_central_credentials and not body.is_global:
        raise HTTPException(403, mail_sicherheit.SPERRE_PERSOENLICH)
    payload = body.model_dump()
    acc = MailAccount(owner_user_id=None if body.is_global else current_user.id)
    _felder_pruefen(db, acc, payload, current_user)
    _setze_felder(acc, payload)
    _bindung_erneuern(db, acc, current_user)
    db.add(acc)
    db.commit()
    db.refresh(acc)
    _protokollieren("angelegt", acc, current_user,
                    [k for k, v in payload.items() if v not in (None, "", False, [])])
    return _account_response(db, acc, current_user)


@router.put("/accounts/{account_id}", response_model=MailAccountResponse)
def update_account(
    account_id: UUID,
    body: MailAccountUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    acc = _get_account_fuer_user(db, account_id, current_user, verwalten=True)
    payload = body.model_dump(exclude_unset=True)
    _felder_pruefen(db, acc, payload, current_user)
    vorher = {f: getattr(acc, f) for f in _ZIEL_FELDER}
    _setze_felder(acc, payload)
    ziel_geaendert = any(getattr(acc, f) != vorher[f] for f in _ZIEL_FELDER)
    if ziel_geaendert:
        # Nur der Admin kommt bei globalen Konten bis hierher: Er hat das Ziel
        # gerade selbst eingetragen — das gilt als Bestätigung. Wird die
        # zentrale Nutzung abgeschaltet, verfällt die Bindung.
        if acc.use_central_credentials:
            _bindung_erneuern(db, acc, current_user)
        else:
            acc.zentral_bindung = None
    acc.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(acc)
    _protokollieren("geändert", acc, current_user, payload.keys())
    return _account_response(db, acc, current_user)


@router.post("/accounts/{account_id}/zentral-bestaetigen", response_model=MailAccountResponse)
def confirm_central_target(
    account_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Admin bestätigt ausdrücklich: Die zentralen Zugangsdaten dürfen an das
    derzeit eingetragene Ziel dieses globalen Kontos gehen. Nötig nach der
    Übernahme alter Konten und nach einem Wechsel der zentralen
    Anmeldeidentität (Einstellungen → System → E-Mail).
    """
    acc = _get_account_fuer_user(db, account_id, current_user, verwalten=True)
    if acc.owner_user_id is not None:
        raise HTTPException(400, mail_sicherheit.SPERRE_PERSOENLICH)
    if not acc.use_central_credentials:
        raise HTTPException(400, "Dieses Konto verwendet keine zentralen Zugangsdaten")
    _bindung_erneuern(db, acc, current_user)
    if acc.last_error in (mail_sicherheit.SPERRE_UNBESTAETIGT, mail_sicherheit.SPERRE_GEAENDERT):
        acc.last_error = None
    db.commit()
    db.refresh(acc)
    _protokollieren("Ziel bestätigt", acc, current_user)
    return _account_response(db, acc, current_user)


@router.delete("/accounts/{account_id}", status_code=204)
def delete_account(
    account_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    acc = _get_account_fuer_user(db, account_id, current_user, verwalten=True)
    _protokollieren("gelöscht", acc, current_user)
    db.delete(acc)
    db.commit()


def _verbindungsfehler(db: Session, acc: MailAccount, praefix: str, e: Exception) -> HTTPException:
    return HTTPException(400, f"{praefix}: {mail_ingest.fehlertext(db, acc, e)}")


@router.get("/accounts/{account_id}/folders", response_model=List[str])
def list_account_folders(
    account_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Verbindungstest: liefert die Ordnerliste der Mailbox."""
    acc = _get_account_fuer_user(db, account_id, current_user, verwalten=True)
    grund = mail_sicherheit.zentral_sperrgrund(db, acc)
    if grund:
        raise HTTPException(403, grund)
    if not acc.secret_enc and not acc.use_central_credentials:
        raise HTTPException(400, "Für dieses Konto ist kein Passwort/Secret hinterlegt")
    try:
        return mail_ingest.list_folders(db, acc)
    except Exception as e:
        raise _verbindungsfehler(db, acc, "Verbindung fehlgeschlagen", e) from e


@router.post("/accounts/{account_id}/scan", response_model=ScanResult)
def scan_account_now(
    account_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Manueller Scan: neue Nachrichten analysieren, Vorschläge anlegen."""
    acc = _get_account_fuer_user(db, account_id, current_user)
    grund = mail_sicherheit.zentral_sperrgrund(db, acc)
    if grund:
        raise HTTPException(403, grund)
    if not acc.secret_enc and not acc.use_central_credentials:
        raise HTTPException(400, "Für dieses Konto ist kein Passwort/Secret hinterlegt")
    try:
        anzahl = mail_ingest.scan_account(db, acc)
    except Exception as e:
        raise _verbindungsfehler(db, acc, "Scan fehlgeschlagen", e) from e
    return ScanResult(account_id=acc.id, neue_vorschlaege=anzahl)


# ── Sicherheit: Vertrauens- und Zielregeln (nur Admin) ────────────────────────
def _setting_schreiben(db: Session, key: str, value: str):
    row = db.query(Setting).filter(Setting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(Setting(key=key, value=value))


@router.get("/sicherheit", response_model=MailSicherheitResponse)
def get_mail_security(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    pem = (db.query(Setting).filter(Setting.key == mail_sicherheit.SETTING_CA_ZERTIFIKATE)
           .first())
    return MailSicherheitResponse(
        interne_ziele=mail_sicherheit.interne_ziele(db),
        ca_zertifikate=(pem.value or "") if pem else "",
    )


@router.put("/sicherheit", response_model=MailSicherheitResponse)
def update_mail_security(
    body: MailSicherheitUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    ziele = [z.strip().lower() for z in body.interne_ziele if z.strip()]
    ok, falsch = mail_sicherheit.interne_ziele_gueltig(ziele)
    if not ok:
        raise HTTPException(400, f"Ungültiger Eintrag bei internen Zielen: {falsch}")
    if not mail_sicherheit.ca_pem_gueltig(body.ca_zertifikate):
        raise HTTPException(400, "Die CA-Zertifikate sind kein gültiges PEM")
    _setting_schreiben(db, mail_sicherheit.SETTING_INTERNE_ZIELE, "\n".join(ziele))
    _setting_schreiben(db, mail_sicherheit.SETTING_CA_ZERTIFIKATE, body.ca_zertifikate.strip())
    db.commit()
    logger.info("Mail-Sicherheitsregeln geändert durch Benutzer %s: %d interne Ziele, "
                "Firmen-CA %s", current_user.id, len(ziele),
                "hinterlegt" if body.ca_zertifikate.strip() else "keine")
    return get_mail_security(db, current_user)


# ── KI-Einstellungen (global, PUT nur Admin) ──────────────────────────────────
@router.get("/ki-settings", response_model=KiSettingsResponse)
def get_ki_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ki = mail_ingest.load_ki_settings(db)
    return KiSettingsResponse(
        provider=ki.get("provider") or "anthropic",
        model=ki.get("model"),
        has_api_key=bool(ki.get("api_key_enc")),
    )


@router.put("/ki-settings", response_model=KiSettingsResponse)
def update_ki_settings(
    body: KiSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    mail_ingest.save_ki_settings(db, body.provider, body.api_key, body.model)
    ki = mail_ingest.load_ki_settings(db)
    return KiSettingsResponse(
        provider=ki.get("provider") or "anthropic",
        model=ki.get("model"),
        has_api_key=bool(ki.get("api_key_enc")),
    )


# ── Vorschläge ────────────────────────────────────────────────────────────────
def _sichtbare_konten_ids(db: Session, user: User) -> List[UUID]:
    return [a.id for a in _verwendbare_konten(db, user)]


@router.get("/suggestions", response_model=List[SuggestionResponse])
def list_suggestions(
    status: Optional[str] = Query("offen"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    konten = {a.id: a.name for a in _verwendbare_konten(db, current_user)}
    query = (db.query(MailTaskSuggestion)
             .filter(MailTaskSuggestion.account_id.in_(list(konten.keys()) or [UUID(int=0)])))
    if status:
        query = query.filter(MailTaskSuggestion.status == status)
    # "(keine Aufgabe erkannt)"-Marker nie anzeigen
    query = query.filter(MailTaskSuggestion.title != "(keine Aufgabe erkannt)")
    rows = query.order_by(MailTaskSuggestion.received_at.desc().nullslast(),
                          MailTaskSuggestion.created_at.desc()).all()
    result = []
    for r in rows:
        item = SuggestionResponse.model_validate(r)
        item.account_name = konten.get(r.account_id)
        result.append(item)
    return result


def _get_suggestion_fuer_user(db: Session, suggestion_id: UUID, user: User) -> MailTaskSuggestion:
    s = db.query(MailTaskSuggestion).filter(MailTaskSuggestion.id == suggestion_id).first()
    if not s:
        raise HTTPException(404, "Vorschlag nicht gefunden")
    acc = db.query(MailAccount).filter(MailAccount.id == s.account_id).first()
    if acc and not _darf_verwenden(acc, user):
        raise HTTPException(403, "Kein Zugriff auf diesen Vorschlag")
    return s


@router.post("/suggestions/{suggestion_id}/accept", response_model=SuggestionResponse)
def accept_suggestion(
    suggestion_id: UUID,
    body: SuggestionAccept,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Vorschlag übernehmen -> Todo mit source='email' anlegen."""
    s = _get_suggestion_fuer_user(db, suggestion_id, current_user)
    if s.status != "offen":
        raise HTTPException(400, "Vorschlag wurde bereits entschieden")

    assignee_name = None
    assignee_id = body.assignee_id
    if assignee_id:
        user = db.query(User).filter(User.id == assignee_id).first()
        if not user:
            raise HTTPException(404, "Zugewiesener Benutzer nicht gefunden")
        assignee_name = user.full_name

    todo = Todo(
        title=(body.title or s.title)[:500],
        description=body.description if body.description is not None else s.description,
        priority=body.priority or s.priority or "mittel",
        due_date=body.due_date if body.due_date is not None else s.due_date,
        assignee_id=assignee_id,
        assignee_name=assignee_name,
        source="email",
        source_meta={
            "account_id": str(s.account_id),
            "message_id": s.message_id,
            "subject": s.subject,
            "sender": s.sender,
            "received_at": s.received_at.isoformat() if s.received_at else None,
        },
        created_by=current_user.id,
        created_by_name=current_user.full_name,
    )
    db.add(todo)
    db.flush()

    s.status = "uebernommen"
    s.todo_id = todo.id
    s.decided_at = datetime.now(timezone.utc)
    s.decided_by = current_user.id
    db.commit()
    db.refresh(s)
    resp = SuggestionResponse.model_validate(s)

    # Ursprungs-Mail in Outlook als erledigt kennzeichnen (nur Graph-Konten
    # mit aktivierter Option; best-effort — Fehler blockieren die Übernahme
    # nicht, werden aber am Konto vermerkt und dem Frontend gemeldet).
    acc = db.query(MailAccount).filter(MailAccount.id == s.account_id).first()
    if acc and acc.protocol == "graph" and acc.flag_erledigt:
        try:
            mail_ingest.graph_set_flag(db, acc, s.message_id, "complete")
            resp.mail_flagged = True
        except Exception as e:
            resp.mail_flagged = False
            acc.last_error = f"Erledigt-Flag fehlgeschlagen: {mail_ingest.fehlertext(db, acc, e)[:500]}"
            db.commit()

    return resp


@router.post("/suggestions/{suggestion_id}/dismiss", response_model=SuggestionResponse)
def dismiss_suggestion(
    suggestion_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    s = _get_suggestion_fuer_user(db, suggestion_id, current_user)
    if s.status != "offen":
        raise HTTPException(400, "Vorschlag wurde bereits entschieden")
    s.status = "verworfen"
    s.decided_at = datetime.now(timezone.utc)
    s.decided_by = current_user.id
    db.commit()
    db.refresh(s)
    return SuggestionResponse.model_validate(s)
