"""
Rechtegruppen verwalten (Migration 0055)
========================================

Nur für Administratoren. Wer Gruppen ändern darf, kann sich selbst alles
zuteilen — das ist keine Aufgabe, die man an ein Modulrecht hängt.

Jede Änderung landet im Anmelde-Prüfpfad (``auth_events``). Eine Rechteänderung
ist der Vorgang, bei dem man ein halbes Jahr später wissen will, wer sie
veranlasst hat.
"""
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.core import auth_events as EV
from app.core import berechtigungen as B
from app.db.base import get_db
from app.models.user import PermissionGroup, User
from app.schemas.group import (EffektiveRechteResponse, GroupCreate,
                               GroupResponse, GroupUpdate,
                               PermissionOverridesUpdate, UserGroupsUpdate)
from app.services.auth_service import auth_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/groups", tags=["Rechtegruppen"])


def _meta(request: Request) -> dict:
    from app.api.auth import absender_meta
    return absender_meta(request)


def _antwort(gruppe: PermissionGroup) -> GroupResponse:
    return GroupResponse(
        id=gruppe.id, name=gruppe.name, beschreibung=gruppe.beschreibung,
        rechte=B.blatt_bereinigen(gruppe.rechte), ist_system=gruppe.ist_system,
        sort_order=gruppe.sort_order, created_at=gruppe.created_at,
        mitglieder=[{"id": u.id, "full_name": u.full_name, "email": u.email}
                    for u in sorted(gruppe.users, key=lambda u: u.full_name or "")],
    )


def _mitglieder_setzen(db: Session, gruppe: PermissionGroup,
                       user_ids: Optional[list[UUID]]) -> None:
    if user_ids is None:
        return
    gefunden = db.query(User).filter(User.id.in_(user_ids)).all() if user_ids else []
    fehlend = set(user_ids) - {u.id for u in gefunden}
    if fehlend:
        raise HTTPException(status_code=400,
                            detail=f"{len(fehlend)} Benutzer nicht gefunden.")
    gruppe.users = gefunden


# ═════════════════════════════════════════════════════════════════════════════
# Katalog
# ═════════════════════════════════════════════════════════════════════════════

@router.get("/katalog")
async def katalog(_: User = Depends(get_current_user)):
    """Module, vergebbare Rechte und Umfangsangaben für die Oberfläche.

    Bewusst für alle angemeldeten Benutzer lesbar: Die Liste ist keine
    Auskunft über konkrete Rechte, sondern beschreibt nur, welche es gibt. Das
    Frontend braucht sie auch, um die eigenen Rechte lesbar darzustellen.
    """
    return {
        "module": B.katalog(),
        "rechte": [{"key": r, "label": B.RECHT_LABELS[r]} for r in B.RECHTE],
        "umfaenge": [{"key": u, "label": B.UMFANG_LABELS[u]} for u in B.UMFAENGE],
    }


# ═════════════════════════════════════════════════════════════════════════════
# Gruppen
# ═════════════════════════════════════════════════════════════════════════════

@router.get("/", response_model=list[GroupResponse])
async def gruppen_liste(db: Session = Depends(get_db),
                        _: User = Depends(require_admin)):
    gruppen = db.query(PermissionGroup).order_by(
        PermissionGroup.sort_order, PermissionGroup.name).all()
    return [_antwort(g) for g in gruppen]


@router.post("/", response_model=GroupResponse)
async def gruppe_anlegen(body: GroupCreate, request: Request,
                         db: Session = Depends(get_db),
                         current_user: User = Depends(require_admin)):
    if db.query(PermissionGroup).filter(PermissionGroup.name == body.name).first():
        raise HTTPException(status_code=400,
                            detail="Eine Gruppe mit diesem Namen gibt es schon.")

    gruppe = PermissionGroup(
        name=body.name,
        beschreibung=body.beschreibung,
        rechte=B.blatt_bereinigen(body.rechte),
        ist_system=False,
        sort_order=100,
    )
    db.add(gruppe)
    db.flush()
    _mitglieder_setzen(db, gruppe, body.user_ids)
    db.commit()
    db.refresh(gruppe)

    auth_service.ereignis(db, EV.ADMIN_USER_CHANGED, user=current_user,
                          meta=_meta(request),
                          detail=f"Gruppe „{gruppe.name}“ angelegt")
    return _antwort(gruppe)


@router.put("/{group_id}", response_model=GroupResponse)
async def gruppe_aendern(group_id: UUID, body: GroupUpdate, request: Request,
                         db: Session = Depends(get_db),
                         current_user: User = Depends(require_admin)):
    gruppe = db.query(PermissionGroup).filter(
        PermissionGroup.id == group_id).first()
    if gruppe is None:
        raise HTTPException(status_code=404, detail="Gruppe nicht gefunden")

    geaendert: list[str] = []

    if body.name is not None and body.name != gruppe.name:
        doppelt = db.query(PermissionGroup).filter(
            PermissionGroup.name == body.name,
            PermissionGroup.id != group_id).first()
        if doppelt:
            raise HTTPException(status_code=400,
                                detail="Eine Gruppe mit diesem Namen gibt es schon.")
        gruppe.name = body.name
        geaendert.append("Name")

    if body.beschreibung is not None:
        gruppe.beschreibung = body.beschreibung

    if body.rechte is not None:
        gruppe.rechte = B.blatt_bereinigen(body.rechte)
        geaendert.append("Rechte")

    if body.user_ids is not None:
        _mitglieder_setzen(db, gruppe, body.user_ids)
        geaendert.append("Mitglieder")

    # Die Administratorengruppe darf nicht in einen Zustand geraten, in dem
    # niemand mehr Benutzer und Rechte verwalten kann. Die Rolle 'admin' ist
    # zwar ein Notausgang, aber darauf sollte sich die Rechteverwaltung nicht
    # verlassen — sie ist genau das Werkzeug, mit dem man sich aussperrt.
    if gruppe.ist_system and gruppe.name.startswith("Administratoren"):
        gruppe.rechte = B.volles_rechteblatt()

    db.commit()
    db.refresh(gruppe)

    auth_service.ereignis(
        db, EV.ADMIN_USER_CHANGED, user=current_user, meta=_meta(request),
        detail=f"Gruppe „{gruppe.name}“ geändert: "
               f"{', '.join(geaendert) or 'nur Beschreibung'}")
    return _antwort(gruppe)


@router.delete("/{group_id}")
async def gruppe_loeschen(group_id: UUID, request: Request,
                          db: Session = Depends(get_db),
                          current_user: User = Depends(require_admin)):
    gruppe = db.query(PermissionGroup).filter(
        PermissionGroup.id == group_id).first()
    if gruppe is None:
        raise HTTPException(status_code=404, detail="Gruppe nicht gefunden")

    if gruppe.ist_system:
        raise HTTPException(
            status_code=400,
            detail=("Mitgelieferte Gruppen können nicht gelöscht werden. Sie "
                    "lassen sich aber umbenennen und in ihren Rechten ändern."))

    anzahl = len(gruppe.users)
    if anzahl:
        # Kein stilles Entziehen: Wer eine Gruppe mit Mitgliedern löscht, nimmt
        # diesen Personen Rechte weg, ohne es zu sehen. Beim Ändern hilft die
        # Mitgliederliste in der Oberfläche, hier braucht es die Rückfrage.
        raise HTTPException(
            status_code=400,
            detail=(f"Dieser Gruppe sind noch {anzahl} Benutzer zugeordnet. "
                    "Bitte ordnen Sie sie zuerst einer anderen Gruppe zu — "
                    "sonst verlieren sie ihre Rechte unbemerkt."))

    name = gruppe.name
    db.delete(gruppe)
    db.commit()
    auth_service.ereignis(db, EV.ADMIN_USER_CHANGED, user=current_user,
                          meta=_meta(request),
                          detail=f"Gruppe „{name}“ gelöscht")
    return {"message": f"Gruppe „{name}“ gelöscht"}


# ═════════════════════════════════════════════════════════════════════════════
# Zuordnung und Ausnahmen je Benutzer
# ═════════════════════════════════════════════════════════════════════════════

@router.put("/users/{user_id}/groups", response_model=EffektiveRechteResponse)
async def benutzer_gruppen_setzen(user_id: UUID, body: UserGroupsUpdate,
                                  request: Request,
                                  db: Session = Depends(get_db),
                                  current_user: User = Depends(require_admin)):
    """Gruppenzugehörigkeit eines Benutzers ersetzen."""
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")

    gruppen = (db.query(PermissionGroup).filter(
        PermissionGroup.id.in_(body.group_ids)).all() if body.group_ids else [])
    if len(gruppen) != len(set(body.group_ids)):
        raise HTTPException(status_code=400,
                            detail="Mindestens eine Gruppe wurde nicht gefunden.")

    user.groups = gruppen
    db.commit()
    db.refresh(user)

    auth_service.ereignis(
        db, EV.ADMIN_USER_CHANGED, user=user, meta=_meta(request),
        detail=f"Gruppen durch {current_user.email} gesetzt: "
               f"{', '.join(g.name for g in gruppen) or 'keine'}")
    return _rechte_antwort(user)


@router.put("/users/{user_id}/overrides", response_model=EffektiveRechteResponse)
async def benutzer_ausnahmen_setzen(user_id: UUID,
                                    body: PermissionOverridesUpdate,
                                    request: Request,
                                    db: Session = Depends(get_db),
                                    current_user: User = Depends(require_admin)):
    """Individuelle Abweichungen von den Gruppenrechten setzen.

    Format: nur die abweichenden Angaben, z. B.
    ``{"verkauf": {"loeschen": false}}``. Ein Entzug gewinnt gegen jede Gruppe.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")

    if body.overrides is None:
        user.permission_overrides = None
    else:
        # Auf das erlaubte Raster ziehen, aber nur die genannten Angaben
        # behalten — eine Ausnahme soll nicht unbemerkt zum vollständigen
        # Rechteblatt werden und damit die Gruppen aushebeln.
        sauber: dict = {}
        from app.core.modules import MODULE_KEYS
        for modul, werte in body.overrides.items():
            if modul not in MODULE_KEYS or not isinstance(werte, dict):
                continue
            eintrag = {}
            for recht in B.rechte_fuer_modul(modul):
                if recht in werte:
                    eintrag[recht] = bool(werte[recht])
            if werte.get("umfang") in B.UMFAENGE:
                eintrag["umfang"] = werte["umfang"]
            if eintrag:
                sauber[modul] = eintrag
        user.permission_overrides = sauber or None

    db.commit()
    db.refresh(user)

    auth_service.ereignis(
        db, EV.ADMIN_USER_CHANGED, user=user, meta=_meta(request),
        detail=f"Rechte-Ausnahmen durch {current_user.email} geändert")
    return _rechte_antwort(user)


def _rechte_antwort(user: User) -> EffektiveRechteResponse:
    return EffektiveRechteResponse(
        user_id=user.id,
        rechte=B.effektive_rechte(user),
        role=user.role.value,
        gruppen=[g.name for g in user.groups or []],
        ausnahmen=user.permission_overrides,
        module=B.module_mit_zugang(user),
    )


@router.get("/users/{user_id}/rechte", response_model=EffektiveRechteResponse)
async def benutzer_rechte(user_id: UUID, db: Session = Depends(get_db),
                          current_user: User = Depends(get_current_user)):
    """Die maßgeblichen Rechte eines Benutzers samt Herkunft.

    Die eigenen Rechte darf jeder abrufen — sie zu kennen ist kein Risiko, und
    die Oberfläche braucht sie, um Schaltflächen auszublenden, statt den
    Benutzer in eine Fehlermeldung laufen zu lassen. Fremde Rechte sieht nur
    ein Administrator.
    """
    from app.models.user import UserRole
    if user_id != current_user.id and current_user.role != UserRole.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Administratorrechte erforderlich")

    user = (current_user if user_id == current_user.id
            else db.query(User).filter(User.id == user_id).first())
    if user is None:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")
    return _rechte_antwort(user)


@router.get("/me/rechte", response_model=EffektiveRechteResponse)
async def eigene_rechte(current_user: User = Depends(get_current_user)):
    """Kurzform für die eigenen Rechte — was die Oberfläche beim Start braucht."""
    return _rechte_antwort(current_user)
