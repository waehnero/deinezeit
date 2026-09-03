from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID
from app.db.base import get_db
from app.schemas.user import (
    UserCreate, UserResponse, UserUpdate, AdminUserUpdate, DashboardConfigPayload,
)
from app.services.auth_service import auth_service
from app.api.deps import get_current_user, require_admin
from app.models.user import User, UserRole
from app.core import auth_events as EV
from app.core import passwort as pw_regeln

router = APIRouter(prefix="/users", tags=["Benutzerverwaltung"])


@router.get("/", response_model=List[UserResponse])
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Alle Benutzer anzeigen (alle eingeloggten Benutzer; Bearbeitung bleibt Admin vorbehalten)."""
    return db.query(User).all()


@router.post("/", response_model=UserResponse)
def create_user(
    body: UserCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Neuen Benutzer anlegen (nur Admin)."""
    existing = auth_service.get_user_by_email(db, body.email)
    if existing:
        raise HTTPException(status_code=400, detail="E-Mail bereits vergeben")
    # Die Passwort-Richtlinie gilt auch hier: Ein vom Administrator gesetztes
    # „start123" ist genauso angreifbar wie ein selbst gewähltes.
    pw_regeln.pruefen_oder_fehler(body.password, email=body.email,
                                  name=body.full_name)
    return auth_service.create_user(db, body.email, body.full_name, body.password, body.role, body.language)


@router.put("/me", response_model=UserResponse)
def update_me(
    body: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Eigenes Profil aktualisieren (Sprache, Name).

    **Das Passwort wird hier nicht mehr geändert.** Vorher genügte ein
    gültiger Access-Token, um es zu überschreiben — ohne Kenntnis des alten
    Passworts. Wer ein unbeaufsichtigtes Gerät vorfand oder einen Token
    abgriff, konnte damit das Konto übernehmen und den rechtmäßigen Benutzer
    aussperren. Zudem blieben alle bestehenden Anmeldungen weiter gültig, die
    Änderung sperrte also niemanden aus.

    Für Passwortänderungen gibt es ``POST /api/auth/password/change`` — dort
    wird das aktuelle Passwort abgefragt, die Richtlinie geprüft und andere
    Geräte werden abgemeldet.
    """
    if body.full_name is not None:
        current_user.full_name = body.full_name
    if body.language is not None:
        current_user.language = body.language
    if body.password is not None:
        raise HTTPException(
            status_code=400,
            detail=("Das Passwort wird über „Passwort ändern“ in den "
                    "Sicherheitseinstellungen geändert — dort wird zur "
                    "Sicherheit das aktuelle Passwort abgefragt."))
    db.commit()
    db.refresh(current_user)
    return current_user


@router.get("/me/dashboard", response_model=DashboardConfigPayload)
def get_my_dashboard(
    current_user: User = Depends(get_current_user),
):
    """Persönliche Dashboard-Konfiguration abrufen (None = Standard)."""
    return DashboardConfigPayload(config=current_user.dashboard_config)


@router.put("/me/dashboard", response_model=DashboardConfigPayload)
def save_my_dashboard(
    body: DashboardConfigPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Persönliche Dashboard-Konfiguration speichern.

    config = None setzt auf das Standard-Dashboard zurück.
    """
    current_user.dashboard_config = body.config
    db.commit()
    db.refresh(current_user)
    return DashboardConfigPayload(config=current_user.dashboard_config)


@router.put("/{user_id}", response_model=UserResponse)
def update_user_by_admin(
    user_id: UUID,
    body: AdminUserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Benutzer bearbeiten (nur Admin): Name, Passwort, Rolle, 2FA, Modulrechte.

    Änderungen mit Sicherheitswirkung ziehen jetzt Folgen nach sich, die vorher
    fehlten: Ein neues Passwort und ein Deaktivieren beenden die bestehenden
    Anmeldungen des Benutzers. Ohne das lief ein deaktiviertes Konto bis zum
    Ablauf des Tokens weiter — „Zugang entziehen" hatte also bis zu sieben Tage
    keine Wirkung. Jeder Eingriff landet außerdem im Prüfpfad.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")

    # Gemeinsame Auswertung der Weiterleitungs-Header (siehe dort, warum nicht
    # einfach request.client.host): sonst steht im Prüfpfad die Adresse des
    # nginx-Containers statt der des Administrators.
    from app.api.auth import absender_meta
    meta = absender_meta(request)
    geaendert: list[str] = []

    if body.full_name is not None:
        user.full_name = body.full_name
        geaendert.append("Name")

    if body.password is not None:
        pw_regeln.pruefen_oder_fehler(body.password, email=user.email,
                                      name=user.full_name)
        # passwort_setzen() entwertet alle Sitzungen des Benutzers — genau das
        # ist bei einem vom Administrator zurückgesetzten Passwort gewollt.
        auth_service.passwort_setzen(db, user, body.password,
                                     grund="admin_reset")
        geaendert.append("Passwort")

    if body.role is not None and body.role != user.role:
        # Sich selbst die Adminrechte zu nehmen ist der einfachste Weg, sich
        # aus der eigenen Verwaltung auszuschließen — und wenn es der letzte
        # Administrator war, kommt niemand mehr hinein.
        if user.id == current_user.id and body.role != UserRole.admin:
            raise HTTPException(
                status_code=400,
                detail=("Sie können sich die eigenen Administratorrechte nicht "
                        "entziehen. Bitte lassen Sie das von einem anderen "
                        "Administrator machen."))
        if user.role == UserRole.admin and body.role != UserRole.admin:
            weitere = db.query(User).filter(
                User.role == UserRole.admin, User.is_active == True,  # noqa: E712
                User.id != user.id).count()
            if weitere == 0:
                raise HTTPException(
                    status_code=400,
                    detail=("Das ist der letzte Administrator. Bitte legen Sie "
                            "zuerst einen weiteren an, sonst kann niemand mehr "
                            "Benutzer und Rechte verwalten."))
        user.role = body.role
        geaendert.append(f"Rolle → {body.role.value}")

    if body.language is not None:
        user.language = body.language

    if body.is_active is not None and body.is_active != user.is_active:
        if user.id == current_user.id and not body.is_active:
            raise HTTPException(status_code=400,
                                detail="Das eigene Konto kann man nicht "
                                       "deaktivieren.")
        user.is_active = body.is_active
        geaendert.append("aktiviert" if body.is_active else "deaktiviert")
        if not body.is_active:
            db.commit()
            auth_service.alle_sitzungen_widerrufen(db, user, "admin")

    if body.disable_totp:
        auth_service.disable_totp(db, user)
        auth_service.ereignis(db, EV.TOTP_DISABLED, user=user, meta=meta,
                              detail=f"durch Administrator {current_user.email}")
        geaendert.append("2FA deaktiviert")

    if body.allowed_modules is not None:
        # Seit Teiletappe 2c vergibt die Benutzerverwaltung Rechte über
        # Gruppen. Dieses Feld kommt nur noch von einer zwischengespeicherten,
        # älteren Oberfläche (PWA-Cache).
        #
        # Es wird ausdrücklich abgelehnt statt still ignoriert: Ein Häkchen,
        # das gesetzt aussieht und nichts bewirkt, hat hier schon einmal Zeit
        # gekostet. Und es wird nicht mehr in Ausnahmen übersetzt — dieser
        # Übergangsweg hat für jedes abweichende Modul volle Rechte gesetzt und
        # damit Gruppeneinstellungen unbemerkt ausgehebelt.
        raise HTTPException(
            status_code=400,
            detail=("Modulrechte werden jetzt über Rechtegruppen vergeben "
                    "(Benutzerverwaltung → Rechtegruppen). Falls Sie diese "
                    "Meldung in der Oberfläche sehen, laden Sie die Seite bitte "
                    "neu — Ihr Browser zeigt eine ältere Fassung."))

    db.commit()
    db.refresh(user)

    auth_service.ereignis(
        db, EV.ADMIN_USER_CHANGED, user=user, meta=meta,
        detail=f"durch {current_user.email}: {', '.join(geaendert) or 'keine'}")
    return user


@router.post("/{user_id}/unlock", response_model=UserResponse)
def unlock_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Kontosperre vorzeitig aufheben (nur Admin).

    Die Sperre nach Fehlversuchen läuft nach 15 Minuten von selbst ab. Dieser
    Weg ist für den Fall gedacht, dass jemand nicht warten kann — etwa wenn ein
    Mitarbeiter vor einem Kundentermin steht.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")
    auth_service.sperre_aufheben(db, user, durch=current_user)
    db.refresh(user)
    return user


def fachdaten_des_benutzers(db: Session, user_id: UUID) -> dict:
    """Was im System auf diesen Benutzer verweist — mit Anzahl je Art.

    Grundlage für die Entscheidung „löschen oder deaktivieren". Aufgeführt
    wird nur, was fachlich zählt: Zeiteinträge, angelegte Stammdaten und
    Projekte, zugewiesene Aufgaben, Postecke-Inhalte, Mail-Konten. Sitzungen,
    Passkeys, Einmal-Codes und der Prüfpfad hängen am Konto und gehen mit
    (bzw. bleiben anonymisiert erhalten) — sie sind kein Grund, ein Konto zu
    behalten."""
    from app.models.zeiterfassung import TimeEntry, Stundenkonto
    from app.models.masterdata import EntityRecord
    from app.models.projektplan import (PlanningProject, Task, ChecklistItem)
    from app.models.aufgaben import Todo
    from app.models.postecke import SocialProfil, SocialPost
    from app.models.mailimport import MailAccount, MailTaskSuggestion

    def n(query) -> int:
        return query.count()

    pruefungen = {
        "Zeiteinträge":            n(db.query(TimeEntry).filter(TimeEntry.user_id == user_id)),
        "angelegte Stammdaten":    n(db.query(EntityRecord).filter(
            (EntityRecord.created_by == user_id) | (EntityRecord.updated_by == user_id)
            | (EntityRecord.archived_by == user_id))),
        "Stundenkonten":           n(db.query(Stundenkonto).filter(Stundenkonto.created_by == user_id)),
        "Projekte":                n(db.query(PlanningProject).filter(PlanningProject.created_by == user_id)),
        "Projektaufgaben":         n(db.query(Task).filter(
            (Task.assignee_id == user_id) | (Task.created_by == user_id))),
        "Checklistenpunkte":       n(db.query(ChecklistItem).filter(
            (ChecklistItem.assignee_user_id == user_id) | (ChecklistItem.created_by == user_id))),
        "Aufgaben":                n(db.query(Todo).filter(
            (Todo.assignee_id == user_id) | (Todo.created_by == user_id))),
        "Postecke-Profile":        n(db.query(SocialProfil).filter(SocialProfil.owner_user_id == user_id)),
        "Postecke-Beiträge":       n(db.query(SocialPost).filter(SocialPost.owner_user_id == user_id)),
        "Mail-Konten":             n(db.query(MailAccount).filter(MailAccount.owner_user_id == user_id)),
        "Mail-Vorschläge":         n(db.query(MailTaskSuggestion).filter(
            MailTaskSuggestion.decided_by == user_id)),
    }
    return {k: v for k, v in pruefungen.items() if v}


@router.delete("/{user_id}")
def delete_user(
    user_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Benutzer endgültig löschen (nur Admin) — nur, wenn nichts an ihm hängt.

    Bis 02.09.2026 löschte dieser Endpunkt bedingungslos. Über die
    Löschkaskade an ``time_entries.user_id`` verschwanden dabei sämtliche
    Zeiteinträge des Benutzers — auch abgerechnete —, ohne Rückfrage. Hatte
    der Benutzer dagegen Stammdaten oder Projekte angelegt, scheiterte das
    Löschen an einem Fremdschlüssel mit einem nackten HTTP 500 (Audit
    DATA-003).

    Jetzt gilt: Verweist noch irgendetwas Fachliches auf das Konto, wird der
    Aufruf mit 409 und einer Aufstellung abgelehnt — der richtige Weg ist dann
    „Deaktivieren" (PUT /users/{id} mit ``is_active=false``): Das Konto kann
    sich nicht mehr anmelden, alle Sitzungen enden, die Daten bleiben
    zuordenbar. Nur ein Konto ohne Spuren (z. B. eine Fehlanlage) wird wirklich
    gelöscht.
    """
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Den eigenen Account kann man nicht löschen")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")

    spuren = fachdaten_des_benutzers(db, user_id)
    if spuren:
        aufstellung = ", ".join(f"{anzahl} {art}" for art, anzahl in spuren.items())
        raise HTTPException(
            status_code=409,
            detail=(f"„{user.full_name}“ kann nicht gelöscht werden, weil noch "
                    f"Daten auf das Konto verweisen: {aufstellung}. Bitte "
                    "deaktivieren Sie den Benutzer stattdessen — er kann sich "
                    "dann nicht mehr anmelden, seine Einträge bleiben erhalten."))

    from app.api.auth import absender_meta
    auth_service.alle_sitzungen_widerrufen(db, user, "admin")
    auth_service.ereignis(db, EV.LOGOUT_ALL, user=None, email=user.email,
                          meta=absender_meta(request),
                          detail=f"Konto gelöscht durch Administrator {current_user.email}")
    db.delete(user)
    db.commit()
    return {"message": "Benutzer gelöscht"}
