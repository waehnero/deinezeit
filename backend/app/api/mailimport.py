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

Rechte:
  - Persönliche Konten: nur der Besitzer (verwalten, scannen, Vorschläge)
  - Globale Konten (owner_user_id=NULL): verwaltet der Admin,
    Vorschläge sehen/entscheiden alle angemeldeten Benutzer
"""
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
from app.schemas.mailimport import (
    MailAccountCreate, MailAccountUpdate, MailAccountResponse,
    SuggestionResponse, SuggestionAccept, ScanResult,
    KiSettingsResponse, KiSettingsUpdate,
)
from app.services import mail_ingest

router = APIRouter(prefix="/mail-import", tags=["Mail-Import"])


# ── Hilfen ────────────────────────────────────────────────────────────────────
def _ist_admin(user: User) -> bool:
    return user.role == UserRole.admin


def _account_response(acc: MailAccount) -> MailAccountResponse:
    resp = MailAccountResponse.model_validate(acc)
    resp.has_secret = bool(acc.secret_enc)
    return resp


def _get_account_fuer_user(db: Session, account_id: UUID, user: User,
                           verwalten: bool = False) -> MailAccount:
    """
    Lädt ein Konto mit Rechteprüfung.
      verwalten=False: Besitzer ODER (globales Konto: jeder Benutzer)
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
    return acc


def _setze_felder(acc: MailAccount, payload: dict):
    for key, value in payload.items():
        if key in ("secret", "is_global"):
            continue
        setattr(acc, key, value)
    if payload.get("secret"):
        acc.secret_enc = mail_ingest.encrypt_secret(payload["secret"])


# ── Konten ────────────────────────────────────────────────────────────────────
@router.get("/accounts", response_model=List[MailAccountResponse])
def list_accounts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Eigene Konten + globale Konten."""
    rows = (db.query(MailAccount)
            .filter(or_(MailAccount.owner_user_id == current_user.id,
                        MailAccount.owner_user_id.is_(None)))
            .order_by(MailAccount.created_at).all())
    return [_account_response(a) for a in rows]


@router.post("/accounts", response_model=MailAccountResponse, status_code=201)
def create_account(
    body: MailAccountCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if body.is_global and not _ist_admin(current_user):
        raise HTTPException(403, "Globale Mail-Konten kann nur der Admin anlegen")
    payload = body.model_dump()
    acc = MailAccount(owner_user_id=None if body.is_global else current_user.id)
    _setze_felder(acc, payload)
    db.add(acc)
    db.commit()
    db.refresh(acc)
    return _account_response(acc)


@router.put("/accounts/{account_id}", response_model=MailAccountResponse)
def update_account(
    account_id: UUID,
    body: MailAccountUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    acc = _get_account_fuer_user(db, account_id, current_user, verwalten=True)
    _setze_felder(acc, body.model_dump(exclude_unset=True))
    acc.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(acc)
    return _account_response(acc)


@router.delete("/accounts/{account_id}", status_code=204)
def delete_account(
    account_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    acc = _get_account_fuer_user(db, account_id, current_user, verwalten=True)
    db.delete(acc)
    db.commit()


@router.get("/accounts/{account_id}/folders", response_model=List[str])
def list_account_folders(
    account_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Verbindungstest: liefert die Ordnerliste der Mailbox."""
    acc = _get_account_fuer_user(db, account_id, current_user, verwalten=True)
    if not acc.secret_enc and not acc.use_central_credentials:
        raise HTTPException(400, "Für dieses Konto ist kein Passwort/Secret hinterlegt")
    try:
        return mail_ingest.list_folders(db, acc)
    except Exception as e:
        raise HTTPException(400, f"Verbindung fehlgeschlagen: {e}")


@router.post("/accounts/{account_id}/scan", response_model=ScanResult)
def scan_account_now(
    account_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Manueller Scan: neue Nachrichten analysieren, Vorschläge anlegen."""
    acc = _get_account_fuer_user(db, account_id, current_user)
    if not acc.secret_enc and not acc.use_central_credentials:
        raise HTTPException(400, "Für dieses Konto ist kein Passwort/Secret hinterlegt")
    try:
        anzahl = mail_ingest.scan_account(db, acc)
    except Exception as e:
        raise HTTPException(400, f"Scan fehlgeschlagen: {e}")
    return ScanResult(account_id=acc.id, neue_vorschlaege=anzahl)


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
    rows = (db.query(MailAccount.id)
            .filter(or_(MailAccount.owner_user_id == user.id,
                        MailAccount.owner_user_id.is_(None))).all())
    return [r[0] for r in rows]


@router.get("/suggestions", response_model=List[SuggestionResponse])
def list_suggestions(
    status: Optional[str] = Query("offen"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    konten = {a.id: a.name for a in db.query(MailAccount)
              .filter(or_(MailAccount.owner_user_id == current_user.id,
                          MailAccount.owner_user_id.is_(None))).all()}
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
    if acc and acc.owner_user_id and acc.owner_user_id != user.id:
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
    return SuggestionResponse.model_validate(s)


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
