from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from uuid import UUID
from app.db.base import get_db
from app.core.security import decode_token
from app.models.user import User, UserRole

security = HTTPBearer()

#: Einheitliche Antwort bei jedem Token-Problem. Absichtlich unspezifisch:
#: Ob das Token abgelaufen, gefälscht oder die Sitzung beendet ist, muss der
#: Aufrufer nicht erfahren — das Frontend reagiert auf jeden dieser Fälle
#: gleich (Sitzung still erneuern, sonst zur Anmeldung).
_UNGUELTIG = "Ungültiges oder abgelaufenes Token"


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """Angemeldeten Benutzer aus dem Access-Token ermitteln.

    Seit Migration 0054 wird zusätzlich die **Sitzung** geprüft (``sid`` im
    Token). Das ist der Unterschied zwischen „abmelden" und „Token aus dem
    Browser löschen": Vorher blieb ein einmal ausgestelltes Token bis zum
    Ablauf gültig, auch nach einem Abmelden, einem Passwortwechsel oder wenn
    ein Gerät verloren ging. Es gab keinen Weg, es zu entwerten.

    Token ohne ``sid`` werden abgelehnt. Beim Einspielen dieser Etappe werden
    alle Benutzer damit einmal abgemeldet — das ist gewollt, denn für die alten
    Token existiert keine überprüfbare Sitzung.
    """
    from app.services.auth_service import auth_service

    payload = decode_token(credentials.credentials)

    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail=_UNGUELTIG)

    try:
        user_id = UUID(payload.get("sub", ""))
        session_id = UUID(payload.get("sid", ""))
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail=_UNGUELTIG)

    sitzung = auth_service.sitzung_laden(db, session_id)
    if not auth_service.sitzung_gueltig(sitzung) or sitzung.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail=_UNGUELTIG)

    user = db.query(User).filter(User.id == user_id,
                                 User.is_active == True).first()  # noqa: E712
    if not user:
        # Deaktiviertes oder gelöschtes Konto: Sitzung gleich mit entwerten,
        # damit das Refresh-Token nicht weiterlebt.
        auth_service.sitzung_widerrufen(db, sitzung, "user_inactive")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail=_UNGUELTIG)

    auth_service.zugriff_vermerken(db, sitzung)

    # Für Endpunkte, die wissen müssen, aus welcher Sitzung der Aufruf kommt
    # (Abmelden, Sitzungsübersicht) — ohne das Token erneut zu zerlegen.
    request.state.session_id = session_id
    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administratorrechte erforderlich",
        )
    return current_user


def require_module(module: str):
    """Dependency-Factory: Zugriff nur mit Lesezugriff auf das Modul.

    Prüft seit Migration 0055 das Leserecht aus dem Gruppenmodell. Der Name und
    das Verhalten bleiben, damit die Router-Einbindung in ``main.py``
    unverändert weiterläuft:

        app.include_router(r, dependencies=[Depends(require_module("verkauf"))])

    Für schreibende und löschende Endpunkte ist ``require_permission`` das
    richtige Werkzeug — ``require_module`` allein lässt jeden durch, der das
    Modul ansehen darf.
    """
    def _check(current_user: User = Depends(get_current_user)) -> User:
        from app.core.modules import user_has_module, MODULE_LABELS
        if not user_has_module(current_user, module):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Kein Zugriff — das Modul "
                       f"„{MODULE_LABELS.get(module, module)}“ ist für diesen "
                       "Benutzer nicht freigeschaltet",
            )
        return current_user
    return _check


def require_permission(module: str, recht: str):
    """Dependency-Factory für ein bestimmtes Recht an einem Modul.

    Verwendung je Endpunkt::

        @router.delete("/{id}")
        async def loeschen(user: User = Depends(
                require_permission("verkauf", LOESCHEN))):

    Die Fehlermeldung nennt Modul und Recht im Klartext. Ein blankes „Kein
    Zugriff" führt sonst zu Rückfragen beim Administrator, die sich niemand
    beantworten kann, weil auch er nicht sieht, welches Häkchen fehlt.
    """
    def _check(current_user: User = Depends(get_current_user)) -> User:
        from app.core.berechtigungen import RECHT_LABELS, hat_recht
        from app.core.modules import MODULE_LABELS
        if not hat_recht(current_user, module, recht):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(f"Kein Zugriff — für „{MODULE_LABELS.get(module, module)}“ "
                        f"fehlt das Recht „{RECHT_LABELS.get(recht, recht)}“. "
                        "Ein Administrator kann es über die Gruppenverwaltung "
                        "vergeben."),
            )
        return current_user
    return _check


#: ``POST``-Endpunkte, die nichts verändern, und deshalb nur Lesezugriff
#: brauchen. Verglichen wird die Pfad-Endung.
#:
#: Diese Liste ist absichtlich kurz und wird eng gehalten: Wer hier etwas
#: einträgt, senkt die Anforderung für einen Endpunkt. Im Zweifel gehört ein
#: ``POST`` **nicht** hierher — die strengere Einstufung verursacht höchstens
#: eine Rückfrage beim Administrator, die zu lockere eine stille Lücke.
LESENDE_POSTS = (
    # Wertet ein Transkript per KI aus und liefert einen Vorschlag zurück;
    # gespeichert wird ausdrücklich nichts (siehe zeiterfassung.ki_nachtragen).
    "/ki-nachtragen",
    # Prüft die Zugangsdaten eines Social-Media-Profils, ohne sie zu ändern.
    "/verbindung-testen",
)


def require_modul_rechte(module: str):
    """Router-weite Rechteprüfung anhand der HTTP-Methode.

    ``GET``/``HEAD`` → Ansehen, ``POST``/``PUT``/``PATCH`` → Ändern,
    ``DELETE`` → Löschen.

    Warum nach Methode und nicht je Endpunkt: Die neun Module haben zusammen
    124 schreibende Endpunkte. Jeden einzeln zu versehen heißt, an 124 Stellen
    daran zu denken — und ein vergessener bleibt unbemerkt offen, weil nichts
    kaputt aussieht. Die Methode sagt in einer sauber geschnittenen API
    ohnehin, was der Aufruf tut. Für die wenigen Fälle, in denen das nicht
    zutrifft, gibt es ``LESENDE_POSTS``; wo eine feinere Regel nötig ist
    (etwa „stornieren nur mit Löschrecht"), kommt zusätzlich
    ``require_permission`` an den einzelnen Endpunkt — die strengere von beiden
    Prüfungen gewinnt, weil beide durchlaufen werden.

    Einbindung wie bisher beim Router:

        app.include_router(r, dependencies=[Depends(require_modul_rechte("verkauf"))])
    """
    def _check(request: Request,
               current_user: User = Depends(get_current_user)) -> User:
        from app.core.berechtigungen import (LESEN, LOESCHEN, RECHT_LABELS,
                                             SCHREIBEN, hat_recht)
        from app.core.modules import MODULE_LABELS

        methode = request.method.upper()
        pfad = request.url.path.rstrip("/")

        if methode in ("GET", "HEAD", "OPTIONS"):
            recht = LESEN
        elif methode == "DELETE":
            recht = LOESCHEN
        elif any(pfad.endswith(endung) for endung in LESENDE_POSTS):
            recht = LESEN
        else:
            recht = SCHREIBEN

        if not hat_recht(current_user, module, recht):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(f"Kein Zugriff — für „{MODULE_LABELS.get(module, module)}“ "
                        f"fehlt das Recht „{RECHT_LABELS.get(recht, recht)}“. "
                        "Ein Administrator kann es über die Gruppenverwaltung "
                        "vergeben."),
            )
        return current_user
    return _check


def require_schreiben(module: str):
    """Kurzform für Anlegen und Ändern."""
    from app.core.berechtigungen import SCHREIBEN
    return require_permission(module, SCHREIBEN)


def require_loeschen(module: str):
    """Kurzform für Löschen."""
    from app.core.berechtigungen import LOESCHEN
    return require_permission(module, LOESCHEN)
