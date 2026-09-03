"""
Anmelde-Endpunkte
=================

Was diese Etappe (17.08.2026) an dieser Datei geändert hat:

* ``/auth/refresh``, ``/auth/logout``, ``/auth/logout-all`` und die
  Sitzungsübersicht sind **neu**. Vorher gab es keinen dieser Endpunkte: Das
  Frontend legte den Refresh-Token ab und benutzte ihn nie, und bei jedem
  401 landete der Benutzer auf der Anmeldeseite. Praktisch bedeutete das
  einen Zwangs-Abmelden alle 30 Minuten, mitten in der Arbeit — und es gab
  keine Möglichkeit, eine Anmeldung von außen zu beenden.
* Der Refresh-Token kommt als ``httpOnly``-Cookie und nicht mehr im
  Antwort-Text.
* Kontosperre nach Fehlversuchen, Prüfpfad, einheitliche Meldungen gegen das
  Ausspähen vorhandener E-Mail-Adressen.
* ``/auth/password/forgot`` und ``/auth/password/reset`` sind neu — die Seite
  ``ForgotPasswordPage.jsx`` existierte im Frontend und lief bisher ins Leere.
* Das TOTP-Secret wird nicht mehr als Query-Parameter durchgereicht.
* WebAuthn nimmt getypte Schemas statt ``dict`` und gibt keine internen
  Fehlertexte mehr nach außen.
"""
import asyncio
import base64
import json
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import (APIRouter, Depends, HTTPException, Request, Response,
                     status)
from starlette.concurrency import run_in_threadpool
from slowapi import Limiter
from sqlalchemy.orm import Session

from app.core import auth_events as EV
from app.core import passwort as pw_regeln
from app.core.config import settings
from app.core.netz import echte_ip
from app.core.security import verify_password
from app.db.base import get_db
from app.api.deps import get_current_user
from app.models.settings import Setting
from app.models.user import User, WebAuthnCredential
from app.schemas.user import (AuthEventResponse, LoginRequest,
                              PasswordChangeRequest, PasswordForgotRequest,
                              PasswordResetRequest, RecoveryCodesResponse,
                              RecoveryStatusResponse, RefreshResponse,
                              SessionResponse, TOTPSetupResponse,
                              TOTPVerifyRequest, TokenResponse, UserResponse,
                              WebAuthnLoginBegin, WebAuthnLoginComplete,
                              WebAuthnRegisterComplete)
from app.services.auth_service import (RECOVERY_ANZAHL, REFRESH_COOKIE_NAME,
                                       REFRESH_COOKIE_PATH,
                                       RESET_TOKEN_GUELTIG_MINUTEN, SPERRE_AB,
                                       auth_service)

logger = logging.getLogger(__name__)
# Eigene Limiter-Instanz für die Anmelde-Endpunkte (strengere Grenzwerte als
# die App-Vorgabe). Schlüssel ist die echte Absenderadresse — mit
# ``get_remote_address`` wäre es hinter nginx die Adresse des Proxys, und dann
# teilten sich alle Benutzer die zehn Anmeldungen pro Minute.
limiter = Limiter(key_func=echte_ip)
limiter.enabled = settings.RATE_LIMIT_AKTIV

router = APIRouter(prefix="/auth", tags=["Authentifizierung"])

#: Eine einzige Meldung für „Konto unbekannt", „Passwort falsch" und
#: „Konto deaktiviert". Jede Unterscheidung wäre eine Auskunft darüber,
#: welche Adressen im System existieren und welche Konten aktiv sind.
FEHLER_ANMELDUNG = "E-Mail oder Passwort falsch"


# ═════════════════════════════════════════════════════════════════════════════
# Hilfsfunktionen
# ═════════════════════════════════════════════════════════════════════════════

def absender_meta(request: Request) -> dict:
    """Absender-Angaben für Prüfpfad und Sitzung.

    Die Ermittlung der Adresse steht seit 18.08.2026 in ``core/netz.echte_ip``
    — dieselbe Frage stellt sich beim Rate-Limiting, und zwei Auswertungen
    derselben Header laufen mit der Zeit auseinander. Ein Prüfpfad, in den sich
    jeder seine Wunschadresse schreiben kann, wäre schlimmer als keiner: Er
    sieht belastbar aus, ohne es zu sein. Die Begründung der Reihenfolge steht
    dort.
    """
    ip = echte_ip(request)
    if ip == "unbekannt":
        ip = ""

    return {
        "user_agent": request.headers.get("user-agent"),
        "ip_address": ip[:45] or None,
    }


def _cookie_sicher() -> bool:
    """``Secure``-Flag setzen, sobald die Anwendung über HTTPS läuft.

    Wird aus ``FRONTEND_URL`` abgeleitet statt über eine eigene Einstellung:
    ein zusätzlicher Schalter, den man in der Produktion vergessen kann, wäre
    hier die schlechtere Lösung. Lokal (``http://localhost``) muss das Flag
    ausbleiben, sonst schickt der Browser den Cookie nie und die Anmeldung
    funktioniert in der Entwicklung nicht.
    """
    return settings.FRONTEND_URL.lower().startswith("https")


def refresh_cookie_setzen(response: Response, refresh_token: str) -> None:
    """Refresh-Token als ``httpOnly``-Cookie setzen.

    ``httponly`` schließt JavaScript aus — eine XSS-Lücke im Frontend kann den
    langlebigen Token damit nicht auslesen. ``samesite="lax"`` sorgt dafür,
    dass der Cookie bei einem POST von einer fremden Seite nicht mitgeschickt
    wird; das ist der CSRF-Schutz für ``/auth/refresh``. ``path`` begrenzt ihn
    auf die Anmelde-Endpunkte, sodass er bei normalen API-Aufrufen gar nicht
    erst mitläuft.
    """
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        httponly=True,
        secure=_cookie_sicher(),
        samesite="lax",
        path=REFRESH_COOKIE_PATH,
    )


def refresh_cookie_loeschen(response: Response) -> None:
    """Cookie entfernen. Pfad muss mit dem beim Setzen übereinstimmen."""
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=_cookie_sicher(),
        samesite="lax",
    )


def _jetzt() -> datetime:
    return datetime.now(timezone.utc)


def _tz(wert: Optional[datetime]) -> Optional[datetime]:
    """Naive Zeitstempel als UTC deuten (sonst TypeError beim Vergleich)."""
    if wert is not None and wert.tzinfo is None:
        return wert.replace(tzinfo=timezone.utc)
    return wert


def _sperre_pruefen(db: Session, request: Request, email: str,
                    user: Optional[User]) -> None:
    """Bei laufender Sperre mit 429 abbrechen.

    Für ein vorhandenes Konto zählt ``users.failed_login_count``, für eine
    unbekannte Adresse der Prüfpfad. Beide Wege führen zur gleichen Antwort —
    sonst verrät die Sperre, welche Konten es gibt (siehe
    ``auth_service.fehlversuche_fuer_email``).
    """
    if user is not None and user.is_locked:
        rest = _tz(user.locked_until) - _jetzt()
        minuten = max(1, int(rest.total_seconds() // 60) + 1)
        auth_service.ereignis(db, EV.LOGIN_BLOCKED, user=user, email=email,
                              meta=absender_meta(request),
                              detail=f"noch {minuten} Minuten gesperrt")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=("Zu viele Anmeldeversuche. Bitte versuchen Sie es in "
                    f"{minuten} Minuten erneut oder setzen Sie Ihr Passwort "
                    "über „Passwort vergessen“ zurück."),
            headers={"Retry-After": str(int(rest.total_seconds()))},
        )

    if user is None and auth_service.fehlversuche_fuer_email(db, email) >= SPERRE_AB:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Zu viele Anmeldeversuche. Bitte versuchen Sie es später erneut.",
            headers={"Retry-After": "900"},
        )


async def _bremsen(db: Session, email: str, user: Optional[User]) -> None:
    """Antwort verzögern, wenn es für diese Adresse schon Fehlversuche gab.

    Die Verzögerung greift *vor* der Antwort auf einen Fehlversuch. Für einen
    Menschen, der sich vertippt hat, sind das zwei bis acht Sekunden. Für ein
    Skript, das eine Passwortliste durchgeht, wird daraus Wartezeit, die den
    Angriff unbrauchbar langsam macht — und zwar unabhängig davon, aus wie
    vielen IP-Adressen es kommt. Genau das konnte das bisherige Rate-Limit
    (10 Anfragen pro Minute *pro IP*) nicht leisten.
    """
    versuche = (user.failed_login_count or 0) if user is not None \
        else auth_service.fehlversuche_fuer_email(db, email, fenster_minuten=15)
    wartezeit = auth_service.verzoegerung_sek(versuche)
    if wartezeit > 0:
        await asyncio.sleep(wartezeit)


def _tokens_ausliefern(db: Session, response: Response, user: User,
                       request: Request) -> TokenResponse:
    """Sitzung anlegen, Cookie setzen, Antwort bauen."""
    tokens = auth_service.create_tokens(db, user, absender_meta(request))
    refresh_cookie_setzen(response, tokens["refresh_token"])
    offene_codes = (auth_service.recovery_codes_offen(db, user)
                    if user.totp_enabled else None)
    return TokenResponse(
        access_token=tokens["access_token"],
        refresh_token="",          # bewusst leer — der Token steckt im Cookie
        recovery_codes_left=offene_codes,
    )


# ═════════════════════════════════════════════════════════════════════════════
# Anmeldung
# ═════════════════════════════════════════════════════════════════════════════

@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")           # gegen Massenanfragen aus einer Quelle
async def login(request: Request, response: Response, body: LoginRequest,
                db: Session = Depends(get_db)):
    """Anmeldung mit E-Mail und Passwort, bei aktivem 2FA mit Code.

    Der Ablauf hält sich strikt an eine Regel: Bis alle Faktoren stimmen, ist
    die Antwort nach außen immer dieselbe. Nur der Prüfpfad hält fest, woran
    es tatsächlich lag.
    """
    email = (body.email or "").strip()
    meta = absender_meta(request)

    user = auth_service.get_user_by_email(db, email)
    _sperre_pruefen(db, request, email, user)

    # Passwort prüfen (bei unbekanntem Konto gegen einen Wegwerf-Hash, damit
    # die Antwortzeit nicht verrät, ob es das Konto gibt).
    #
    # Im Threadpool: bcrypt braucht mit Absicht rund eine Drittelsekunde. Dieser
    # Endpunkt muss ``async`` bleiben (wegen der Wartezeit in ``_bremsen``),
    # und in einem ``async``-Endpunkt hielte die Prüfung sonst alle anderen
    # Anfragen so lange an (Audit PERF-001).
    geprueft = await run_in_threadpool(auth_service.authenticate_user,
                                       db, email, body.password)

    if geprueft is None or not geprueft.is_active:
        await _bremsen(db, email, user)
        if user is not None:
            auth_service.fehlversuch_vermerken(db, user)
        auth_service.ereignis(
            db, EV.LOGIN_INACTIVE if (geprueft and not geprueft.is_active)
            else EV.LOGIN_FAIL,
            user=user, email=email, meta=meta,
            detail=None if user else "Konto unbekannt")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail=FEHLER_ANMELDUNG)

    user = geprueft

    # ── Zweiter Faktor ────────────────────────────────────────────────────────
    if user.totp_enabled:
        if not body.totp_code and not body.recovery_code:
            # Kein Fehler: Das Frontend fragt jetzt den Code ab. Es wird noch
            # kein Token ausgestellt und keine Sitzung angelegt.
            return TokenResponse(access_token="", refresh_token="",
                                 requires_totp=True)

        if body.recovery_code:
            if not auth_service.recovery_code_einloesen(db, user,
                                                        body.recovery_code):
                await _bremsen(db, email, user)
                auth_service.fehlversuch_vermerken(db, user)
                auth_service.ereignis(db, EV.TOTP_FAIL, user=user, email=email,
                                      meta=meta, detail="Einmal-Code ungültig")
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                    detail="Ungültiger Einmal-Code")
            offen = auth_service.recovery_codes_offen(db, user)
            auth_service.ereignis(db, EV.RECOVERY_USED, user=user, meta=meta,
                                  detail=f"noch {offen} Codes übrig")
        else:
            if not auth_service.verify_totp(user, body.totp_code):
                await _bremsen(db, email, user)
                auth_service.fehlversuch_vermerken(db, user)
                auth_service.ereignis(db, EV.TOTP_FAIL, user=user, email=email,
                                      meta=meta)
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                    detail="Ungültiger 2FA-Code")

    auth_service.fehlversuche_zuruecksetzen(db, user)
    antwort = _tokens_ausliefern(db, response, user, request)
    auth_service.ereignis(db, EV.LOGIN_OK, user=user, meta=meta)
    return antwort


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """Aktuell eingeloggten Benutzer abrufen."""
    return current_user


# ═════════════════════════════════════════════════════════════════════════════
# Sitzungen
# ═════════════════════════════════════════════════════════════════════════════

@router.post("/refresh", response_model=RefreshResponse)
@limiter.limit("60/minute")
def refresh(request: Request, response: Response,
                  db: Session = Depends(get_db)):
    """Sitzung verlängern — der neue Access-Token kommt zurück.

    Bewusst **ohne** ``get_current_user``: Der Aufruf erfolgt gerade dann, wenn
    der Access-Token abgelaufen ist. Ausgewiesen wird man hier allein über den
    Cookie.
    """
    token = request.cookies.get(REFRESH_COOKIE_NAME)
    meta = absender_meta(request)

    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Keine gültige Sitzung")

    ergebnis = auth_service.refresh(db, token, meta)

    if ergebnis is None:
        refresh_cookie_loeschen(response)
        auth_service.ereignis(db, EV.REFRESH_FAIL, meta=meta)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Sitzung abgelaufen. Bitte neu anmelden.")

    if ergebnis.get("reuse"):
        # Ein bereits verbrauchter Token wurde erneut eingelöst. Behandeln wir
        # als möglichen Diebstahl: Die ganze Kette ist entwertet, der Benutzer
        # muss sich einmal neu anmelden.
        refresh_cookie_loeschen(response)
        auth_service.ereignis(db, EV.REFRESH_REUSE,
                              user_id=ergebnis.get("user_id"), meta=meta,
                              detail="Sitzungskette entwertet")
        logger.warning("Verbrauchter Refresh-Token erneut verwendet "
                       "(Benutzer %s, IP %s) — Sitzungen entwertet",
                       ergebnis.get("user_id"), meta.get("ip_address"))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=("Diese Sitzung wurde aus Sicherheitsgründen beendet. "
                    "Bitte melden Sie sich neu an."))

    refresh_cookie_setzen(response, ergebnis["refresh_token"])
    auth_service.ereignis(db, EV.REFRESH_OK, user=ergebnis.get("user"),
                          meta=meta, session_id=UUID(ergebnis["session_id"]))
    return RefreshResponse(access_token=ergebnis["access_token"])


@router.post("/logout")
def logout(request: Request, response: Response,
                 db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    """Nur dieses Gerät abmelden."""
    session_id = getattr(request.state, "session_id", None)
    if session_id:
        sitzung = auth_service.sitzung_laden(db, session_id)
        if sitzung is not None:
            auth_service.sitzung_widerrufen(db, sitzung, "logout")
    refresh_cookie_loeschen(response)
    auth_service.ereignis(db, EV.LOGOUT, user=current_user, meta=absender_meta(request),
                          session_id=session_id)
    return {"message": "Abgemeldet"}


@router.post("/logout-all")
def logout_all(request: Request, response: Response,
                     db: Session = Depends(get_db),
                     current_user: User = Depends(get_current_user)):
    """Von allen Geräten abmelden — auch von diesem.

    Der Fall, für den es gedacht ist: Ein Handy ist weg oder es besteht der
    Verdacht, dass jemand mitliest. Danach ist jeder ausgestellte Token
    entwertet.
    """
    anzahl = auth_service.alle_sitzungen_widerrufen(db, current_user,
                                                    "logout_all")
    refresh_cookie_loeschen(response)
    auth_service.ereignis(db, EV.LOGOUT_ALL, user=current_user,
                          meta=absender_meta(request),
                          detail=f"{anzahl} Sitzung(en) beendet")
    return {"message": f"{anzahl} Sitzung(en) beendet", "count": anzahl}


@router.get("/sessions", response_model=list[SessionResponse])
def sessions_list(request: Request, db: Session = Depends(get_db),
                        current_user: User = Depends(get_current_user)):
    """„Hier bist du angemeldet" — offene Sitzungen des eigenen Kontos."""
    aktuelle = getattr(request.state, "session_id", None)
    ergebnis = []
    for s in auth_service.sitzungen_auflisten(db, current_user):
        eintrag = SessionResponse.model_validate(s)
        eintrag.is_current = (s.id == aktuelle)
        ergebnis.append(eintrag)
    return ergebnis


@router.delete("/sessions/{session_id}")
def session_revoke(session_id: UUID, request: Request,
                         response: Response, db: Session = Depends(get_db),
                         current_user: User = Depends(get_current_user)):
    """Eine einzelne Sitzung beenden (fremdes Gerät aus der Liste werfen)."""
    sitzung = auth_service.sitzung_laden(db, session_id)
    # Gleiche Antwort für „gibt es nicht" und „gehört jemand anderem": sonst
    # ließe sich über diesen Endpunkt prüfen, welche Sitzungs-IDs existieren.
    if sitzung is None or sitzung.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Sitzung nicht gefunden")

    auth_service.sitzung_widerrufen(db, sitzung, "logout")
    auth_service.ereignis(db, EV.SESSION_REVOKED, user=current_user,
                          meta=absender_meta(request), session_id=session_id,
                          detail=sitzung.device_label)

    if session_id == getattr(request.state, "session_id", None):
        refresh_cookie_loeschen(response)

    return {"message": "Sitzung beendet"}


@router.get("/events", response_model=list[AuthEventResponse])
def events_list(limit: int = 30, db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user)):
    """Die letzten Anmelde-Ereignisse des eigenen Kontos.

    Damit ein Benutzer selbst erkennen kann, dass jemand anderes an seinem
    Konto versucht hat — ohne auf einen Administrator warten zu müssen.
    """
    eintraege = auth_service.ereignisse_lesen(db, user_id=current_user.id,
                                              limit=limit)
    return [
        AuthEventResponse(
            id=e.id, event=e.event, label=EV.label(e.event),
            email_attempted=e.email_attempted, ip_address=e.ip_address,
            user_agent=e.user_agent, detail=e.detail, created_at=e.created_at,
            suspicious=e.event in EV.VERDAECHTIG,
        )
        for e in eintraege
    ]


# ═════════════════════════════════════════════════════════════════════════════
# Passwort
# ═════════════════════════════════════════════════════════════════════════════

@router.post("/password/forgot")
@limiter.limit("5/hour")
def password_forgot(request: Request, body: PasswordForgotRequest,
                          db: Session = Depends(get_db)):
    """Zurücksetzen anfordern.

    Die Antwort ist **immer** gleich, auch für unbekannte Adressen. Ein „diese
    E-Mail-Adresse ist nicht registriert" wäre eine bequeme Möglichkeit, von
    außen die Mitarbeiterliste eines Unternehmens abzugleichen.
    """
    email = (body.email or "").strip()
    meta = absender_meta(request)
    freundlich = {"message": ("Falls ein Konto mit dieser E-Mail-Adresse "
                              "besteht, wurde eine Nachricht mit einem Link "
                              "zum Zurücksetzen verschickt. Bitte prüfen Sie "
                              "auch den Spam-Ordner.")}

    user = auth_service.get_user_by_email(db, email)
    if user is None or not user.is_active:
        auth_service.ereignis(db, EV.RESET_REQUESTED, email=email, meta=meta,
                              detail="kein passendes Konto")
        return freundlich

    token = auth_service.reset_token_erzeugen(db, user, meta.get("ip_address"))
    if token is None:
        auth_service.ereignis(db, EV.RESET_REQUESTED, user=user, meta=meta,
                              detail="zu viele Anfragen")
        return freundlich

    link = f"{settings.FRONTEND_URL.rstrip('/')}/passwort-neu?token={token}"
    gueltig = RESET_TOKEN_GUELTIG_MINUTEN

    try:
        from app.services.email_service import send_email
        mail_einstellungen = {r.key: r.value for r in db.query(Setting).all()}
        text = (
            f"Hallo {user.full_name},\n\n"
            "für Ihr Konto wurde das Zurücksetzen des Passworts angefordert.\n\n"
            f"Link: {link}\n\n"
            f"Der Link ist {gueltig} Minuten gültig und funktioniert nur "
            "einmal.\n\n"
            "Waren Sie das nicht, können Sie diese Nachricht ignorieren — Ihr "
            "Passwort bleibt unverändert. Wenn Sie so etwas mehrfach erhalten, "
            "melden Sie es bitte Ihrem Administrator.\n\n"
            f"{settings.APP_NAME}"
        )
        html = (
            f"<p>Hallo {user.full_name},</p>"
            "<p>für Ihr Konto wurde das Zurücksetzen des Passworts "
            "angefordert.</p>"
            f'<p><a href="{link}">Passwort jetzt neu setzen</a></p>'
            f"<p>Der Link ist {gueltig} Minuten gültig und funktioniert nur "
            "einmal.</p>"
            "<p>Waren Sie das nicht, können Sie diese Nachricht ignorieren — "
            "Ihr Passwort bleibt unverändert.</p>"
            f"<p>{settings.APP_NAME}</p>"
        )
        send_email(settings=mail_einstellungen, to_email=user.email,
                   subject=f"{settings.APP_NAME}: Passwort zurücksetzen",
                   body_text=text, body_html=html)
        auth_service.ereignis(db, EV.RESET_REQUESTED, user=user, meta=meta,
                              detail="E-Mail verschickt")
    except Exception:                                          # noqa: BLE001
        # Nach außen bleibt die Antwort gleich: Ob der E-Mail-Versand
        # eingerichtet ist, muss ein Unbekannter nicht erfahren. Im Serverlog
        # steht der Fehler mit Ursache — dort sucht der Administrator.
        logger.error("Passwort-Zurücksetzung: E-Mail an %s konnte nicht "
                     "verschickt werden", user.email, exc_info=True)
        auth_service.ereignis(db, EV.RESET_FAIL, user=user, meta=meta,
                              detail="E-Mail-Versand fehlgeschlagen")

    return freundlich


@router.post("/password/reset")
@limiter.limit("10/hour")
def password_reset(request: Request, body: PasswordResetRequest,
                         db: Session = Depends(get_db)):
    """Neues Passwort mit dem Token aus der E-Mail setzen."""
    meta = absender_meta(request)
    eintrag = auth_service.reset_token_pruefen(db, body.token)

    if eintrag is None:
        auth_service.ereignis(db, EV.RESET_FAIL, meta=meta,
                              detail="Token ungültig oder abgelaufen")
        raise HTTPException(
            status_code=400,
            detail=("Dieser Link ist nicht mehr gültig. Bitte fordern Sie das "
                    "Zurücksetzen erneut an."))

    user = auth_service.get_user_by_id(db, eintrag.user_id)
    if user is None or not user.is_active:
        auth_service.ereignis(db, EV.RESET_FAIL, meta=meta,
                              detail="Konto nicht verwendbar")
        raise HTTPException(status_code=400, detail="Dieser Link ist nicht "
                                                   "mehr gültig.")

    pw_regeln.pruefen_oder_fehler(body.new_password, email=user.email,
                                  name=user.full_name)

    eintrag.used_at = _jetzt()
    db.commit()
    # Setzt das Passwort und entwertet **alle** Sitzungen: Wer das Passwort
    # zurücksetzt, tut das oft genau deshalb, weil ein Fremder Zugang hat.
    auth_service.passwort_setzen(db, user, body.new_password,
                                grund="password_reset")
    auth_service.ereignis(db, EV.RESET_DONE, user=user, meta=meta)

    return {"message": ("Passwort geändert. Sie können sich jetzt anmelden. "
                        "Alle bisherigen Anmeldungen wurden beendet.")}


@router.post("/password/change")
def password_change(request: Request, response: Response,
                          body: PasswordChangeRequest,
                          db: Session = Depends(get_db),
                          current_user: User = Depends(get_current_user)):
    """Passwort im Profil ändern (mit Rückfrage nach dem aktuellen)."""
    meta = absender_meta(request)

    if not verify_password(body.current_password, current_user.hashed_password):
        auth_service.ereignis(db, EV.LOGIN_FAIL, user=current_user, meta=meta,
                              detail="aktuelles Passwort falsch (Änderung)")
        raise HTTPException(status_code=400,
                            detail="Das aktuelle Passwort ist falsch.")

    if body.new_password == body.current_password:
        raise HTTPException(status_code=400,
                            detail="Das neue Passwort muss sich vom alten "
                                   "unterscheiden.")

    pw_regeln.pruefen_oder_fehler(body.new_password, email=current_user.email,
                                  name=current_user.full_name)

    # Die eigene Sitzung bleibt in jedem Fall bestehen — sonst wirft sich der
    # Benutzer mit dem Passwortwechsel selbst aus der laufenden Arbeit. Der
    # Schalter entscheidet nur über die *anderen* Geräte. Wer wirklich alles
    # beenden will, nimmt „Von allen Geräten abmelden".
    eigene = getattr(request.state, "session_id", None)
    auth_service.passwort_setzen(db, current_user, body.new_password,
                                 sitzungen_behalten=eigene)
    if not body.logout_other_devices:
        # Hinweis: Andere Geräte werden bei einer Passwortänderung immer
        # abgemeldet. Ein Passwortwechsel, der alte Anmeldungen weiterlaufen
        # lässt, schließt niemanden aus und wiegt nur in falscher Sicherheit.
        logger.info("Passwortänderung von %s: 'logout_other_devices=false' "
                    "wurde ignoriert (Sitzungen werden immer entwertet).",
                    current_user.email)

    auth_service.ereignis(db, EV.PASSWORD_CHANGED, user=current_user, meta=meta)
    return {"message": "Passwort geändert. Andere Geräte wurden abgemeldet."}


# ═════════════════════════════════════════════════════════════════════════════
# TOTP / 2FA
# ═════════════════════════════════════════════════════════════════════════════

@router.post("/totp/setup", response_model=TOTPSetupResponse)
def setup_totp(db: Session = Depends(get_db),
                     current_user: User = Depends(get_current_user)):
    """QR-Code für die Authenticator-App erzeugen.

    Das Secret wird serverseitig vorgemerkt und beim Aktivieren dort geprüft.
    Der Client schickt es nicht zurück — vorher hing es als Query-Parameter an
    ``/auth/totp/enable`` und stand damit in Zugriffslogs und im
    Browserverlauf.
    """
    import pyotp
    secret = auth_service.totp_einrichtung_starten(db, current_user)
    qr_code = auth_service.get_totp_qr(current_user, secret)
    uri = pyotp.TOTP(secret).provisioning_uri(current_user.email,
                                              issuer_name=settings.APP_NAME)
    return TOTPSetupResponse(secret=secret, qr_code_url=qr_code,
                             provisioning_uri=uri)


@router.post("/totp/enable")
def enable_totp(request: Request, body: TOTPVerifyRequest,
                      db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user)):
    """2FA aktivieren (nach QR-Code-Scan und Code-Bestätigung)."""
    if not auth_service.enable_totp(db, current_user, body.code):
        raise HTTPException(
            status_code=400,
            detail=("Der Code stimmt nicht oder die Einrichtung ist zu lange "
                    "her. Bitte erzeugen Sie den QR-Code neu."))

    auth_service.ereignis(db, EV.TOTP_ENABLED, user=current_user,
                          meta=absender_meta(request))
    codes = auth_service.recovery_codes_erzeugen(db, current_user)
    auth_service.ereignis(db, EV.RECOVERY_GENERATED, user=current_user,
                          meta=absender_meta(request), detail="bei 2FA-Aktivierung")
    # Die Einmal-Codes kommen direkt mit: Ohne sie wäre ein Benutzer beim
    # Verlust des Handys ausgesperrt, und im Nachhinein daran zu denken, tut
    # erfahrungsgemäß niemand.
    return {"message": "2FA erfolgreich aktiviert",
            "recovery_codes": codes,
            "hinweis": RecoveryCodesResponse(codes=[]).hinweis}


@router.post("/totp/disable")
def disable_totp(request: Request, body: TOTPVerifyRequest,
                       db: Session = Depends(get_db),
                       current_user: User = Depends(get_current_user)):
    """2FA deaktivieren — mit gültigem Code oder Einmal-Code."""
    ok = (auth_service.verify_totp(current_user, body.code)
          or auth_service.recovery_code_einloesen(db, current_user, body.code))
    if not ok:
        raise HTTPException(status_code=400, detail="Ungültiger 2FA-Code")

    auth_service.disable_totp(db, current_user)
    auth_service.ereignis(db, EV.TOTP_DISABLED, user=current_user,
                          meta=absender_meta(request))
    return {"message": "2FA wurde deaktiviert"}


@router.post("/recovery-codes", response_model=RecoveryCodesResponse)
def recovery_codes_neu(request: Request, body: TOTPVerifyRequest,
                             db: Session = Depends(get_db),
                             current_user: User = Depends(get_current_user)):
    """Neue Einmal-Codes erzeugen; die bisherigen verfallen dabei."""
    if not current_user.totp_enabled:
        raise HTTPException(status_code=400,
                            detail="Einmal-Codes gibt es nur bei aktivem 2FA.")
    if not auth_service.verify_totp(current_user, body.code):
        raise HTTPException(status_code=400, detail="Ungültiger 2FA-Code")

    codes = auth_service.recovery_codes_erzeugen(db, current_user)
    auth_service.ereignis(db, EV.RECOVERY_GENERATED, user=current_user,
                          meta=absender_meta(request), detail="manuell neu erzeugt")
    return RecoveryCodesResponse(codes=codes)


@router.get("/recovery-codes/status", response_model=RecoveryStatusResponse)
def recovery_codes_status(db: Session = Depends(get_db),
                                current_user: User = Depends(get_current_user)):
    return RecoveryStatusResponse(
        codes_left=auth_service.recovery_codes_offen(db, current_user),
        total=RECOVERY_ANZAHL,
    )


# ═════════════════════════════════════════════════════════════════════════════
# WebAuthn / Passkeys (Face ID, Windows Hello, Sicherheitsschlüssel)
# ═════════════════════════════════════════════════════════════════════════════
# Die Challenges liegen seit Migration 0054 in der Datenbank. Vorher standen
# sie in einem Dict im Arbeitsspeicher des Prozesses — das funktioniert nur mit
# genau einem Uvicorn-Worker und überlebt keinen Neustart. Mit mehreren Workern
# landet der zweite Aufruf oft im falschen Prozess, und die Anmeldung scheitert
# mit „Challenge abgelaufen", obwohl gerade nichts abgelaufen ist.

@router.post("/webauthn/register/begin")
def webauthn_register_begin(db: Session = Depends(get_db),
                                  current_user: User = Depends(get_current_user)):
    """Registrierung eines neuen Passkeys starten (z.B. Face ID)."""
    import webauthn

    options = webauthn.generate_registration_options(
        rp_id=settings.WEBAUTHN_RP_ID,
        rp_name=settings.WEBAUTHN_RP_NAME,
        user_id=str(current_user.id).encode(),
        user_name=current_user.email,
        user_display_name=current_user.full_name or current_user.email,
    )
    auth_service.challenge_speichern(db, f"reg:{current_user.id}",
                                     options.challenge)
    # Als Dict zurückgeben (nicht als String) damit axios es korrekt parst
    return json.loads(webauthn.options_to_json(options))


@router.post("/webauthn/register/complete")
def webauthn_register_complete(request: Request,
                                     body: WebAuthnRegisterComplete,
                                     db: Session = Depends(get_db),
                                     current_user: User = Depends(get_current_user)):
    """Passkey-Registrierung abschließen und Credential in DB speichern."""
    import webauthn

    challenge = auth_service.challenge_holen(db, f"reg:{current_user.id}")
    if not challenge:
        raise HTTPException(status_code=400,
                            detail="Challenge abgelaufen. Bitte erneut versuchen.")

    try:
        verification = webauthn.verify_registration_response(
            credential=body.credential,
            expected_challenge=challenge,
            expected_rp_id=settings.WEBAUTHN_RP_ID,
            expected_origin=settings.FRONTEND_URL,
            require_user_verification=True,
        )
    except Exception:                                          # noqa: BLE001
        # Der Ausnahmetext der Bibliothek nennt Innereien des Prüfvorgangs.
        # Nach außen genügt „hat nicht funktioniert"; die Ursache steht im Log.
        logger.warning("Passkey-Registrierung für %s fehlgeschlagen",
                       current_user.email, exc_info=True)
        raise HTTPException(status_code=400,
                            detail="Registrierung fehlgeschlagen. Bitte erneut "
                                   "versuchen.")

    db.add(WebAuthnCredential(
        user_id=current_user.id,
        credential_id=verification.credential_id.hex(),
        public_key=verification.credential_public_key.hex(),
        sign_count=str(verification.sign_count),
        device_name=body.device_name,
    ))
    db.commit()
    auth_service.ereignis(db, EV.PASSKEY_ADDED, user=current_user,
                          meta=absender_meta(request), detail=body.device_name)
    return {"message": f"'{body.device_name}' erfolgreich registriert"}


@router.post("/webauthn/login/begin")
@limiter.limit("20/minute")
def webauthn_login_begin(request: Request, body: WebAuthnLoginBegin,
                               db: Session = Depends(get_db)):
    """Passkey-Login starten — Challenge erzeugen.

    Die E-Mail-Adresse steht jetzt im Anfragetext statt im Query-String (sie
    gehörte nie in eine URL, die in Logs landet). Und die Antwort ist für
    unbekannte Konten dieselbe wie für bekannte ohne Passkey: Vorher meldete
    dieser Endpunkt „Benutzer nicht gefunden" mit 404 und war damit ein
    bequemes Werkzeug, um vorhandene Konten aufzulisten — ganz ohne Passwort.
    """
    import webauthn

    email = (body.email or "").strip()
    user = auth_service.get_user_by_email(db, email)
    credentials = []
    if user is not None and user.is_active:
        credentials = db.query(WebAuthnCredential).filter(
            WebAuthnCredential.user_id == user.id).all()

    if not credentials:
        auth_service.ereignis(db, EV.PASSKEY_FAIL, user=user, email=email,
                              meta=absender_meta(request), detail="kein Passkey")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=("Für diese E-Mail-Adresse ist keine Anmeldung per Passkey "
                    "möglich. Bitte melden Sie sich mit Ihrem Passwort an."))

    options = webauthn.generate_authentication_options(
        rp_id=settings.WEBAUTHN_RP_ID,
        allow_credentials=[
            webauthn.helpers.structs.PublicKeyCredentialDescriptor(
                id=bytes.fromhex(c.credential_id)
            )
            for c in credentials
        ],
    )
    auth_service.challenge_speichern(db, f"auth:{email.lower()}",
                                     options.challenge)
    return json.loads(webauthn.options_to_json(options))


@router.post("/webauthn/login/complete", response_model=TokenResponse)
@limiter.limit("20/minute")
def webauthn_login_complete(request: Request, response: Response,
                                  body: WebAuthnLoginComplete,
                                  db: Session = Depends(get_db)):
    """Passkey-Login abschließen — Assertion prüfen und Sitzung anlegen."""
    import webauthn

    email = (body.email or "").strip()
    meta = absender_meta(request)
    abgelehnt = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                              detail="Anmeldung mit Passkey fehlgeschlagen.")

    challenge = auth_service.challenge_holen(db, f"auth:{email.lower()}")
    if not challenge:
        raise HTTPException(status_code=400,
                            detail="Challenge abgelaufen. Bitte erneut versuchen.")

    user = auth_service.get_user_by_email(db, email)
    if user is None or not user.is_active:
        auth_service.ereignis(db, EV.PASSKEY_FAIL, email=email, meta=meta,
                              detail="Konto unbekannt oder inaktiv")
        raise abgelehnt

    # Credential-ID (base64url) → hex für DB-Lookup
    cred_id_b64 = body.credential.get("id", "")
    try:
        missing = (4 - len(cred_id_b64) % 4) % 4
        cred_id_hex = base64.urlsafe_b64decode(cred_id_b64 + "=" * missing).hex()
    except Exception:                                          # noqa: BLE001
        raise HTTPException(status_code=400, detail="Ungültige Credential-ID")

    db_cred = db.query(WebAuthnCredential).filter(
        WebAuthnCredential.user_id == user.id,
        WebAuthnCredential.credential_id == cred_id_hex,
    ).first()
    if not db_cred:
        auth_service.ereignis(db, EV.PASSKEY_FAIL, user=user, meta=meta,
                              detail="Passkey nicht erkannt")
        raise abgelehnt

    try:
        verification = webauthn.verify_authentication_response(
            credential=body.credential,
            expected_challenge=challenge,
            expected_rp_id=settings.WEBAUTHN_RP_ID,
            expected_origin=settings.FRONTEND_URL,
            credential_public_key=bytes.fromhex(db_cred.public_key),
            credential_current_sign_count=int(db_cred.sign_count),
            require_user_verification=True,
        )
    except Exception:                                          # noqa: BLE001
        logger.warning("Passkey-Anmeldung für %s fehlgeschlagen", email,
                       exc_info=True)
        auth_service.ereignis(db, EV.PASSKEY_FAIL, user=user, meta=meta,
                              detail="Prüfung fehlgeschlagen")
        raise abgelehnt

    db_cred.sign_count = str(verification.new_sign_count)
    db_cred.last_used_at = _jetzt()
    db.commit()

    antwort = _tokens_ausliefern(db, response, user, request)
    auth_service.ereignis(db, EV.PASSKEY_OK, user=user, meta=meta,
                          detail=db_cred.device_name)
    return antwort
