"""
Anmeldung, Sitzungen, zweiter Faktor
====================================

Gliederung dieser Datei:

* Prüfpfad (``auth_events``)
* Anmeldeschutz — Fehlversuche, Verzögerung, Kontosperre
* Passwort-Anmeldung
* Sitzungen — anlegen, erneuern (mit Rotation), widerrufen, auflisten
* TOTP (zweiter Faktor) inklusive verschlüsseltem Secret
* Einmal-Codes als Notausgang für 2FA
* Passwort-Zurücksetzung
* WebAuthn-Challenges (in der Datenbank statt im Prozessspeicher)
* Benutzerverwaltung

Grundsatz für alle Meldungen nach außen: Sie verraten nicht, *warum* eine
Anmeldung scheiterte. „E-Mail oder Passwort falsch" ist dieselbe Antwort für
ein unbekanntes Konto und ein falsches Passwort — sonst lässt sich über die
Anmeldemaske herausfinden, welche Adressen im System existieren. Für die
Nachvollziehbarkeit steht der genaue Grund im Prüfpfad, nicht in der Antwort.
"""
import base64
import hashlib
import hmac
import io
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID, uuid4

import pyotp
import qrcode
import qrcode.image.svg
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core import auth_events as EV
from app.core.config import settings
from app.core.crypto import entschluesseln, verschluesseln
from app.core.security import (create_access_token, create_refresh_token,
                               get_password_hash, verify_password)
from app.models.user import (AuthEvent, PasswordResetToken, TotpRecoveryCode,
                             User, UserSession, WebAuthnChallenge)

logger = logging.getLogger(__name__)

# ── Anmeldeschutz: Kennzahlen ────────────────────────────────────────────────
# Beschluss 17.08.2026: gestaffelte Verzögerung, dann befristete Sperre. Eine
# Sperre, die ein Administrator aufheben muss, wäre strenger — sie lässt sich
# aber missbrauchen, um fremde Konten absichtlich lahmzulegen, und erzeugt
# Supportaufwand bei jedem Tippfehler.
VERZOEGERUNG_AB = 3          # ab dem 3. Fehlversuch wird die Antwort gebremst
VERZOEGERUNG_MAX_SEK = 8.0
SPERRE_AB = 10               # ab dem 10. Fehlversuch ist das Konto gesperrt
SPERRE_MINUTEN = 15
SPERRE_MAX_MINUTEN = 24 * 60  # bei anhaltenden Versuchen wachsende Sperrdauer

# Vergleichshash für nicht existierende Konten (siehe authenticate_user).
# Wird beim ersten Bedarf berechnet, nicht beim Import: bcrypt braucht dafür
# spürbar Zeit, und beim Hochfahren des Containers ist das verschenkt.
_DUMMY_HASH: Optional[str] = None

# ── Sitzungen ────────────────────────────────────────────────────────────────
REFRESH_COOKIE_NAME = "dz_refresh"
# Der Cookie wird nur an die Anmelde-Endpunkte geschickt. Jeder andere Aufruf
# sieht ihn nicht — auch nicht versehentlich in einem Fehler-Log oder in einem
# weitergeleiteten Header.
REFRESH_COOKIE_PATH = "/api/auth"

# ── Passwort-Zurücksetzung ───────────────────────────────────────────────────
RESET_TOKEN_GUELTIG_MINUTEN = 30
RESET_ANFRAGEN_PRO_STUNDE = 5

# ── Einmal-Codes ─────────────────────────────────────────────────────────────
RECOVERY_ANZAHL = 10
RECOVERY_LAENGE = 10          # Zeichen aus einem Alphabet ohne Verwechsler

# ── WebAuthn ─────────────────────────────────────────────────────────────────
CHALLENGE_GUELTIG_SEK = 300


def _jetzt() -> datetime:
    return datetime.now(timezone.utc)


def _tz(wert: Optional[datetime]) -> Optional[datetime]:
    """Zeitstempel ohne Zeitzone als UTC deuten.

    Nötig, weil manche Treiber und Testaufbauten naive Zeitstempel liefern und
    ein Vergleich zwischen naiv und zeitzonenbehaftet in Python sofort mit
    TypeError abbricht — mitten in der Anmeldung.
    """
    if wert is not None and wert.tzinfo is None:
        return wert.replace(tzinfo=timezone.utc)
    return wert


def _hash(wert: str) -> str:
    """SHA-256 für Token-Werte.

    Bewusst nicht bcrypt: Diese Token sind 256 Bit Zufall aus
    ``secrets.token_urlsafe``, kein vom Menschen gewähltes Passwort. Es gibt
    also nichts zu erraten, und bcrypt bei jedem Erneuern der Sitzung wäre nur
    Rechenzeit. Verglichen wird trotzdem zeitkonstant (siehe ``_hash_gleich``).
    """
    return hashlib.sha256(wert.encode("utf-8")).hexdigest()


def _hash_gleich(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)


class AuthService:

    # ═════════════════════════════════════════════════════════════════════════
    # Prüfpfad
    # ═════════════════════════════════════════════════════════════════════════

    def ereignis(
        self,
        db: Session,
        event: str,
        *,
        user: Optional[User] = None,
        user_id: Optional[UUID] = None,
        email: Optional[str] = None,
        meta: Optional[dict] = None,
        detail: Optional[str] = None,
        session_id: Optional[UUID] = None,
        commit: bool = True,
    ) -> None:
        """Einen Eintrag in den Anmelde-Prüfpfad schreiben.

        Schluckt eigene Fehler absichtlich: Der Prüfpfad ist wichtig, aber er
        darf niemals der Grund sein, warum sich jemand nicht anmelden kann.
        Ein Schreibfehler landet im Serverlog.
        """
        meta = meta or {}
        try:
            eintrag = AuthEvent(
                user_id=user.id if user is not None else user_id,
                event=event,
                email_attempted=(email or "")[:255] or None,
                ip_address=meta.get("ip_address"),
                user_agent=(meta.get("user_agent") or "")[:500] or None,
                detail=(detail or "")[:200] or None,
                session_id=session_id,
                created_at=_jetzt(),
            )
            db.add(eintrag)
            if commit:
                db.commit()
        except Exception:                                     # noqa: BLE001
            logger.warning("Prüfpfad-Eintrag '%s' konnte nicht geschrieben "
                           "werden", event, exc_info=True)
            try:
                db.rollback()
            except Exception:                                 # noqa: BLE001
                pass

    def ereignisse_lesen(
        self,
        db: Session,
        *,
        user_id: Optional[UUID] = None,
        nur_verdaechtige: bool = False,
        limit: int = 50,
    ) -> list[AuthEvent]:
        q = db.query(AuthEvent)
        if user_id is not None:
            q = q.filter(AuthEvent.user_id == user_id)
        if nur_verdaechtige:
            q = q.filter(AuthEvent.event.in_(tuple(EV.VERDAECHTIG)))
        return q.order_by(AuthEvent.created_at.desc()).limit(min(limit, 500)).all()

    # ═════════════════════════════════════════════════════════════════════════
    # Anmeldeschutz
    # ═════════════════════════════════════════════════════════════════════════

    def sperrdauer(self, fehlversuche: int) -> timedelta:
        """Sperrdauer, die mit anhaltenden Fehlversuchen wächst.

        10 Versuche → 15 Minuten, 11 → 30, 12 → 45 … bis höchstens 24 Stunden.
        Wer es weiter probiert, wartet immer länger; ein Mitarbeiter mit
        Tippfehler ist nach einer Viertelstunde wieder handlungsfähig.
        """
        stufe = max(1, fehlversuche - SPERRE_AB + 1)
        minuten = min(SPERRE_MINUTEN * stufe, SPERRE_MAX_MINUTEN)
        return timedelta(minutes=minuten)

    def verzoegerung_sek(self, fehlversuche: int) -> float:
        """Wartezeit vor der Antwort — bremst automatisiertes Durchprobieren.

        Der Wert steigt ab dem dritten Fehlversuch (2 s, 4 s, 8 s) und bleibt
        dann bei 8 Sekunden. Absicht: für einen Menschen kaum spürbar, für ein
        Skript, das Tausende Passwörter durchgeht, tödlich.
        """
        if fehlversuche < VERZOEGERUNG_AB:
            return 0.0
        return min(2.0 ** (fehlversuche - VERZOEGERUNG_AB + 1),
                   VERZOEGERUNG_MAX_SEK)

    def fehlversuch_vermerken(self, db: Session, user: User) -> None:
        """Zähler erhöhen und bei Überschreitung sperren."""
        user.failed_login_count = (user.failed_login_count or 0) + 1
        if user.failed_login_count >= SPERRE_AB:
            user.locked_until = _jetzt() + self.sperrdauer(user.failed_login_count)
        db.commit()

    def fehlversuche_zuruecksetzen(self, db: Session, user: User) -> None:
        if user.failed_login_count or user.locked_until:
            user.failed_login_count = 0
            user.locked_until = None
            db.commit()

    def fehlversuche_fuer_email(self, db: Session, email: str,
                                fenster_minuten: int = 60) -> int:
        """Fehlversuche auf eine Adresse, für die es **kein** Konto gibt.

        Klingt überflüssig, ist aber der Grund, warum die Sperre kein
        Verzeichnis der vorhandenen Konten wird: Zählen wir nur bei echten
        Benutzern, dann antwortet der Server nach zehn Versuchen bei
        existierenden Adressen „zu viele Versuche" und bei erfundenen weiterhin
        „E-Mail oder Passwort falsch". Genau daran ließe sich ablesen, welche
        Adressen im System hinterlegt sind. Mit diesem Zähler aus dem Prüfpfad
        verhalten sich beide Fälle identisch.
        """
        if not email:
            return 0
        seit = _jetzt() - timedelta(minutes=fenster_minuten)
        return db.query(AuthEvent).filter(
            AuthEvent.event == EV.LOGIN_FAIL,
            func.lower(AuthEvent.email_attempted) == email.lower(),
            AuthEvent.created_at > seit,
        ).count()

    def sperre_aufheben(self, db: Session, user: User,
                        durch: Optional[User] = None) -> None:
        """Sperre vorzeitig aufheben (Administrator)."""
        user.failed_login_count = 0
        user.locked_until = None
        db.commit()
        self.ereignis(db, EV.ADMIN_UNLOCKED, user=user,
                      detail=f"durch {durch.email}" if durch else None)

    # ═════════════════════════════════════════════════════════════════════════
    # Passwort-Anmeldung
    # ═════════════════════════════════════════════════════════════════════════

    def _dummy_hash(self) -> str:
        global _DUMMY_HASH
        if _DUMMY_HASH is None:
            _DUMMY_HASH = get_password_hash(secrets.token_urlsafe(24))
        return _DUMMY_HASH

    def authenticate_user(self, db: Session, email: str,
                          password: str) -> Optional[User]:
        """Passwort prüfen. ``None`` = Anmeldung abgelehnt.

        Für ein unbekanntes Konto wird trotzdem ein bcrypt-Vergleich gegen
        einen Wegwerf-Hash ausgeführt. Ohne das antwortet der Server bei
        unbekannten Adressen messbar schneller als bei bekannten, und über
        diesen Zeitunterschied lässt sich von außen ermitteln, welche
        E-Mail-Adressen im System hinterlegt sind — ganz ohne je ein Passwort
        zu erraten.
        """
        user = db.query(User).filter(func.lower(User.email) == email.lower()).first()
        if user is None:
            verify_password(password, self._dummy_hash())
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user

    # ═════════════════════════════════════════════════════════════════════════
    # Sitzungen
    # ═════════════════════════════════════════════════════════════════════════

    def _geraet_benennen(self, user_agent: Optional[str]) -> str:
        """Aus dem User-Agent einen für Menschen lesbaren Gerätenamen machen.

        Damit in „Hier bist du angemeldet" nicht 200 Zeichen Browserkennung
        stehen, sondern „Safari auf iPhone".
        """
        ua = (user_agent or "").lower()
        if not ua:
            return "Unbekanntes Gerät"

        if "iphone" in ua:
            geraet = "iPhone"
        elif "ipad" in ua:
            geraet = "iPad"
        elif "android" in ua:
            geraet = "Android-Gerät"
        elif "macintosh" in ua or "mac os" in ua:
            geraet = "Mac"
        elif "windows" in ua:
            geraet = "Windows-PC"
        elif "linux" in ua:
            geraet = "Linux-Rechner"
        else:
            geraet = "Unbekanntes Gerät"

        # Reihenfolge zählt: Edge und Chrome nennen sich beide „Safari" und
        # „Chrome" im User-Agent, deshalb von spezifisch nach allgemein prüfen.
        if "edg/" in ua:
            browser = "Edge"
        elif "opr/" in ua or "opera" in ua:
            browser = "Opera"
        elif "firefox" in ua:
            browser = "Firefox"
        elif "chrome" in ua or "crios" in ua:
            browser = "Chrome"
        elif "safari" in ua:
            browser = "Safari"
        else:
            browser = None

        return f"{browser} auf {geraet}" if browser else geraet

    def create_tokens(self, db: Session, user: User,
                      request_meta: Optional[dict] = None) -> dict:
        """Neue Sitzung anlegen und Token-Paar ausstellen.

        Die Sitzungs-ID steckt als ``sid`` in *beiden* Token. Erst dadurch
        lässt sich eine Anmeldung überhaupt beenden: ``get_current_user``
        prüft bei jedem Aufruf, ob die Sitzung zu ``sid`` noch lebt. Vorher
        war ein ausgestellter Token bis zum Ablaufdatum gültig, komme was
        wolle — ein Abmelden im Sinne von „dieser Token gilt nicht mehr" gab
        es nicht.
        """
        request_meta = request_meta or {}
        session_id = uuid4()

        access_token = create_access_token({
            "sub": str(user.id),
            "role": user.role.value,
            "sid": str(session_id),
        })
        refresh_token = create_refresh_token({
            "sub": str(user.id),
            "sid": str(session_id),
        })

        jetzt = _jetzt()
        sitzung = UserSession(
            id=session_id,
            user_id=user.id,
            refresh_token_hash=_hash(refresh_token),
            user_agent=(request_meta.get("user_agent") or "")[:500] or None,
            ip_address=request_meta.get("ip_address"),
            device_label=self._geraet_benennen(request_meta.get("user_agent")),
            expires_at=jetzt + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
            created_at=jetzt,
            last_used_at=jetzt,
        )
        db.add(sitzung)

        user.last_login_at = jetzt
        user.failed_login_count = 0
        user.locked_until = None
        db.commit()

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "session_id": str(session_id),
        }

    def sitzung_laden(self, db: Session,
                      session_id: UUID) -> Optional[UserSession]:
        return db.query(UserSession).filter(UserSession.id == session_id).first()

    def sitzung_gueltig(self, sitzung: Optional[UserSession]) -> bool:
        if sitzung is None or sitzung.revoked_at is not None:
            return False
        ablauf = _tz(sitzung.expires_at)
        return ablauf is None or ablauf > _jetzt()

    def zugriff_vermerken(self, db: Session, sitzung: UserSession) -> None:
        """``last_used_at`` fortschreiben — höchstens einmal pro Minute.

        Ohne die Drosselung würde jeder einzelne API-Aufruf ein UPDATE auf die
        Sitzungstabelle auslösen. Bei einem Dashboard, das mehrere Kennzahlen
        parallel holt, sind das Dutzende Schreibvorgänge pro Seitenaufruf —
        für eine Angabe, die auf die Minute genau völlig ausreicht.
        """
        letzter = _tz(sitzung.last_used_at)
        jetzt = _jetzt()
        if letzter is None or (jetzt - letzter) > timedelta(minutes=1):
            sitzung.last_used_at = jetzt
            try:
                db.commit()
            except Exception:                                 # noqa: BLE001
                db.rollback()

    def sitzung_widerrufen(self, db: Session, sitzung: UserSession,
                           grund: str, commit: bool = True) -> None:
        if sitzung.revoked_at is None:
            sitzung.revoked_at = _jetzt()
            sitzung.revoked_reason = grund[:30]
        if commit:
            db.commit()

    def alle_sitzungen_widerrufen(self, db: Session, user: User, grund: str,
                                  ausser: Optional[UUID] = None) -> int:
        """Alle lebenden Sitzungen eines Benutzers entwerten.

        ``ausser`` lässt die aktuelle Sitzung stehen — sinnvoll bei „von allen
        *anderen* Geräten abmelden" und nach einer Passwortänderung, damit der
        Benutzer nicht sich selbst aus der gerade laufenden Arbeit wirft.
        """
        q = db.query(UserSession).filter(
            UserSession.user_id == user.id,
            UserSession.revoked_at.is_(None),
        )
        if ausser is not None:
            q = q.filter(UserSession.id != ausser)
        anzahl = 0
        for sitzung in q.all():
            self.sitzung_widerrufen(db, sitzung, grund, commit=False)
            anzahl += 1
        db.commit()
        return anzahl

    def _kette_widerrufen(self, db: Session, sitzung: UserSession) -> None:
        """Einer Rotationskette folgen und alles darin entwerten.

        Wird ein bereits verbrauchter Refresh-Token ein zweites Mal eingelöst,
        gibt es zwei Erklärungen: ein Client hat ihn doppelt geschickt, oder
        jemand hat ihn kopiert. Von außen ist das nicht unterscheidbar, also
        wird der Fall wie ein Diebstahl behandelt und die gesamte Kette
        entwertet. Der echte Benutzer muss sich einmal neu anmelden — deutlich
        besser als ein Angreifer, der sich unbegrenzt weiterreicht.
        """
        gesehen: set[UUID] = set()
        aktuell: Optional[UserSession] = sitzung
        while aktuell is not None and aktuell.id not in gesehen:
            gesehen.add(aktuell.id)
            if aktuell.revoked_at is None:
                aktuell.revoked_at = _jetzt()
            # Der Grund wird auch bei bereits widerrufenen Gliedern überschrieben:
            # In der Sitzungsübersicht und bei einer späteren Aufklärung soll die
            # ganze Kette als betroffen erkennbar sein, nicht nur als „rotiert".
            aktuell.revoked_reason = "reuse_detected"
            aktuell = (self.sitzung_laden(db, aktuell.replaced_by_id)
                       if aktuell.replaced_by_id else None)
        db.commit()

    def refresh(self, db: Session, refresh_token: str,
                request_meta: Optional[dict] = None) -> Optional[dict]:
        """Sitzung verlängern und dabei den Refresh-Token austauschen.

        Rotation heißt: Der eingelöste Token gilt sofort nicht mehr, es kommt
        ein neuer zurück. Fängt jemand einen Token ab, hat er nur so lange
        etwas davon, bis der echte Client das nächste Mal erneuert — und dann
        fällt es auf (siehe ``_kette_widerrufen``).

        Rückgabe ``None`` = abgelehnt. Der Aufrufer schreibt den Prüfpfad, weil
        nur er den HTTP-Zusammenhang kennt.
        """
        from app.core.security import decode_token

        request_meta = request_meta or {}
        payload = decode_token(refresh_token)
        if not payload or payload.get("type") != "refresh":
            return None

        try:
            session_id = UUID(payload.get("sid", ""))
            user_id = UUID(payload.get("sub", ""))
        except (ValueError, TypeError):
            return None

        sitzung = self.sitzung_laden(db, session_id)
        if sitzung is None or sitzung.user_id != user_id:
            return None

        # Passt der Hash nicht, gehört der Token nicht zu dieser Sitzung —
        # gefälscht oder aus einer fremden Installation. Kein Diebstahlsverdacht
        # gegen die eigene Kette, also nur ablehnen.
        if not _hash_gleich(sitzung.refresh_token_hash, _hash(refresh_token)):
            return None

        # Der Hash stimmt, die Sitzung wurde aber bereits rotiert: Genau **das**
        # ist die Zweitverwendung. Der Token ist echt und war einmal gültig,
        # jemand löst ihn nur ein zweites Mal ein.
        #
        # Der gefährliche Ablauf dahinter: Ein Angreifer mit kopiertem Token
        # erneuert *zuerst* und besitzt danach die Nachfolge-Sitzung. Der echte
        # Benutzer kommt mit demselben, nun verbrauchten Token und würde bloß
        # abgewiesen — der Angreifer behielte seinen Zugang, und niemand hätte
        # etwas bemerkt. Deshalb fliegt hier die ganze Kette raus.
        #
        # Ein Abmelden (revoked_reason 'logout', 'logout_all', 'admin', …) ist
        # ausdrücklich **kein** solcher Fall: Da hat der Benutzer selbst
        # beendet, und ein nachlaufender Client soll nicht als Angriff gelten.
        if sitzung.revoked_reason == "rotation":
            self._kette_widerrufen(db, sitzung)
            return {"reuse": True, "user_id": user_id}

        if not self.sitzung_gueltig(sitzung):
            return None

        user = db.query(User).filter(User.id == user_id,
                                     User.is_active == True).first()  # noqa: E712
        if user is None:
            self.sitzung_widerrufen(db, sitzung, "user_inactive")
            return None

        # Neue Sitzung als Nachfolger, alte als rotiert markieren.
        neu = self.create_tokens(db, user, {
            "user_agent": request_meta.get("user_agent") or sitzung.user_agent,
            "ip_address": request_meta.get("ip_address") or sitzung.ip_address,
        })
        sitzung.replaced_by_id = UUID(neu["session_id"])
        self.sitzung_widerrufen(db, sitzung, "rotation")

        neu["user"] = user
        return neu

    def sitzungen_auflisten(self, db: Session, user: User,
                            nur_aktive: bool = True) -> list[UserSession]:
        q = db.query(UserSession).filter(UserSession.user_id == user.id)
        if nur_aktive:
            q = q.filter(UserSession.revoked_at.is_(None),
                         UserSession.expires_at > _jetzt())
        return q.order_by(UserSession.last_used_at.desc().nullslast(),
                          UserSession.created_at.desc()).all()

    def sitzungen_aufraeumen(self, db: Session, tage: int = 30) -> int:
        """Alte, längst erledigte Sitzungszeilen löschen.

        Ohne Aufräumen wächst die Tabelle mit jeder Anmeldung und jeder
        Rotation unbegrenzt — bei 30 Minuten Token-Laufzeit sind das pro
        Benutzer und Arbeitstag rund 16 Zeilen. Der Prüfpfad bleibt davon
        unberührt, die Historie geht also nicht verloren.
        """
        grenze = _jetzt() - timedelta(days=tage)
        anzahl = db.query(UserSession).filter(
            UserSession.expires_at < grenze,
        ).delete(synchronize_session=False)
        db.commit()
        return anzahl

    # ═════════════════════════════════════════════════════════════════════════
    # TOTP (zweiter Faktor)
    # ═════════════════════════════════════════════════════════════════════════

    def generate_totp_secret(self) -> str:
        return pyotp.random_base32()

    def totp_secret_lesen(self, user: User) -> Optional[str]:
        """Entschlüsseltes Secret. Immer hierüber lesen, nie über das Feld."""
        return entschluesseln(user.totp_secret)

    def get_totp_qr(self, user: User, secret: str) -> str:
        totp = pyotp.TOTP(secret)
        uri = totp.provisioning_uri(name=user.email, issuer_name=settings.APP_NAME)

        qr = qrcode.make(uri)
        buffer = io.BytesIO()
        qr.save(buffer, format="PNG")
        buffer.seek(0)
        return "data:image/png;base64," + base64.b64encode(buffer.read()).decode()

    def totp_einrichtung_starten(self, db: Session, user: User) -> str:
        """Secret erzeugen und **serverseitig** vormerken.

        Vorher gab der Server das Secret an das Frontend und erwartete es bei
        ``/auth/totp/enable`` als Query-Parameter zurück. Damit stand der
        Schlüssel zum zweiten Faktor in der URL — und URLs landen im
        Browserverlauf, in nginx-Zugriffslogs und in jedem Proxy dazwischen.
        Jetzt bleibt er hier und der Client schickt nur den sechsstelligen Code.
        """
        secret = self.generate_totp_secret()
        user.totp_secret_pending = verschluesseln(secret)
        user.totp_pending_at = _jetzt()
        db.commit()
        return secret

    def verify_totp(self, user: User, code: str) -> bool:
        secret = self.totp_secret_lesen(user)
        if not secret or not code:
            return False
        return pyotp.TOTP(secret).verify(code.strip(), valid_window=1)

    def enable_totp(self, db: Session, user: User, code: str) -> bool:
        """2FA aktivieren — geprüft gegen das vorgemerkte Secret."""
        secret = entschluesseln(user.totp_secret_pending)
        if not secret:
            return False
        # Ein vergessener Einrichtungsvorgang soll nicht ewig gültig bleiben.
        gestartet = _tz(user.totp_pending_at)
        if gestartet is None or (_jetzt() - gestartet) > timedelta(minutes=15):
            return False
        if not pyotp.TOTP(secret).verify((code or "").strip(), valid_window=1):
            return False

        user.totp_secret = verschluesseln(secret)
        user.totp_enabled = True
        user.totp_secret_pending = None
        user.totp_pending_at = None
        db.commit()
        return True

    def disable_totp(self, db: Session, user: User) -> None:
        user.totp_secret = None
        user.totp_enabled = False
        user.totp_secret_pending = None
        user.totp_pending_at = None
        db.query(TotpRecoveryCode).filter(
            TotpRecoveryCode.user_id == user.id).delete(synchronize_session=False)
        db.commit()

    # ═════════════════════════════════════════════════════════════════════════
    # Einmal-Codes (Notausgang für 2FA)
    # ═════════════════════════════════════════════════════════════════════════

    #: Alphabet ohne 0/O und 1/I/L — die Codes werden abgeschrieben, oft von
    #: einem Ausdruck, und Verwechslungen kosten unnötige Fehlversuche.
    _RECOVERY_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"

    def recovery_codes_erzeugen(self, db: Session, user: User) -> list[str]:
        """Neue Einmal-Codes erzeugen; alte verfallen dabei.

        Rückgabe im Klartext — das ist die einzige Gelegenheit, sie anzuzeigen.
        Gespeichert wird nur der Hash.
        """
        db.query(TotpRecoveryCode).filter(
            TotpRecoveryCode.user_id == user.id).delete(synchronize_session=False)

        codes: list[str] = []
        for _ in range(RECOVERY_ANZAHL):
            roh = "".join(secrets.choice(self._RECOVERY_ALPHABET)
                          for _ in range(RECOVERY_LAENGE))
            # In Blöcken darstellen: leichter vorzulesen und abzuschreiben.
            code = f"{roh[:5]}-{roh[5:]}"
            codes.append(code)
            db.add(TotpRecoveryCode(user_id=user.id,
                                    code_hash=_hash(self._recovery_norm(code))))
        db.commit()
        return codes

    def _recovery_norm(self, code: str) -> str:
        """Eingabe vereinheitlichen: Groß-/Kleinschreibung, Striche, Leerzeichen."""
        return (code or "").upper().replace("-", "").replace(" ", "")

    def recovery_code_einloesen(self, db: Session, user: User, code: str) -> bool:
        """Einmal-Code prüfen und verbrauchen."""
        if not code:
            return False
        gesucht = _hash(self._recovery_norm(code))
        for eintrag in db.query(TotpRecoveryCode).filter(
                TotpRecoveryCode.user_id == user.id,
                TotpRecoveryCode.used_at.is_(None)).all():
            if _hash_gleich(eintrag.code_hash, gesucht):
                eintrag.used_at = _jetzt()
                db.commit()
                return True
        return False

    def recovery_codes_offen(self, db: Session, user: User) -> int:
        return db.query(TotpRecoveryCode).filter(
            TotpRecoveryCode.user_id == user.id,
            TotpRecoveryCode.used_at.is_(None)).count()

    # ═════════════════════════════════════════════════════════════════════════
    # Passwort-Zurücksetzung
    # ═════════════════════════════════════════════════════════════════════════

    def reset_token_erzeugen(self, db: Session, user: User,
                             ip: Optional[str] = None) -> Optional[str]:
        """Einmal-Token für „Passwort vergessen".

        ``None`` = zu viele Anfragen in der letzten Stunde. Der Aufrufer
        antwortet nach außen trotzdem freundlich und unverändert: Wer aus der
        Antwort schließen könnte „hier wurde schon fünfmal angefragt, das Konto
        existiert also", hätte genau die Auskunft, die wir vermeiden wollen.
        """
        seit = _jetzt() - timedelta(hours=1)
        offen = db.query(PasswordResetToken).filter(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.created_at > seit).count()
        if offen >= RESET_ANFRAGEN_PRO_STUNDE:
            return None

        token = secrets.token_urlsafe(32)
        db.add(PasswordResetToken(
            user_id=user.id,
            token_hash=_hash(token),
            expires_at=_jetzt() + timedelta(minutes=RESET_TOKEN_GUELTIG_MINUTEN),
            ip_address=ip,
        ))
        db.commit()
        return token

    def reset_token_pruefen(self, db: Session,
                            token: str) -> Optional[PasswordResetToken]:
        if not token:
            return None
        eintrag = db.query(PasswordResetToken).filter(
            PasswordResetToken.token_hash == _hash(token)).first()
        if eintrag is None or eintrag.used_at is not None:
            return None
        if _tz(eintrag.expires_at) <= _jetzt():
            return None
        return eintrag

    def passwort_setzen(self, db: Session, user: User, neues_passwort: str,
                        *, sitzungen_behalten: Optional[UUID] = None,
                        grund: str = "password_change") -> None:
        """Passwort ändern und alle Sitzungen entwerten.

        Ein Passwortwechsel muss ausgesperrte Mitleser wirklich aussperren.
        Solange alte Refresh-Token weitergelten, ist die Änderung kosmetisch —
        genau das war vorher der Fall, weil es keinen Widerruf gab. Offene
        Zurücksetzungs-Token verfallen mit.
        """
        user.hashed_password = get_password_hash(neues_passwort)
        user.password_changed_at = _jetzt()
        user.failed_login_count = 0
        user.locked_until = None
        db.commit()

        self.alle_sitzungen_widerrufen(db, user, grund, ausser=sitzungen_behalten)
        db.query(PasswordResetToken).filter(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
        ).update({"used_at": _jetzt()}, synchronize_session=False)
        db.commit()

    # ═════════════════════════════════════════════════════════════════════════
    # WebAuthn-Challenges
    # ═════════════════════════════════════════════════════════════════════════

    def challenge_speichern(self, db: Session, scope: str,
                            challenge: bytes) -> None:
        """Challenge in der Datenbank ablegen (ersetzt eine vorhandene)."""
        self.challenges_aufraeumen(db)
        db.query(WebAuthnChallenge).filter(
            WebAuthnChallenge.scope == scope).delete(synchronize_session=False)
        db.add(WebAuthnChallenge(
            scope=scope[:320],
            challenge=challenge,
            expires_at=_jetzt() + timedelta(seconds=CHALLENGE_GUELTIG_SEK),
        ))
        db.commit()

    def challenge_holen(self, db: Session, scope: str) -> Optional[bytes]:
        """Challenge einmalig entnehmen (danach ist sie verbraucht)."""
        eintrag = db.query(WebAuthnChallenge).filter(
            WebAuthnChallenge.scope == scope).first()
        if eintrag is None:
            return None
        challenge = eintrag.challenge
        abgelaufen = _tz(eintrag.expires_at) <= _jetzt()
        db.delete(eintrag)
        db.commit()
        return None if abgelaufen else challenge

    def challenges_aufraeumen(self, db: Session) -> None:
        try:
            db.query(WebAuthnChallenge).filter(
                WebAuthnChallenge.expires_at < _jetzt()
            ).delete(synchronize_session=False)
            db.commit()
        except Exception:                                     # noqa: BLE001
            db.rollback()

    # ═════════════════════════════════════════════════════════════════════════
    # Benutzerverwaltung
    # ═════════════════════════════════════════════════════════════════════════

    def create_user(self, db: Session, email: str, full_name: str, password: str,
                    role: str = "employee", language: str = "de") -> User:
        user = User(
            email=email,
            full_name=full_name,
            hashed_password=get_password_hash(password),
            role=role,
            language=language,
            password_changed_at=_jetzt(),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    def get_user_by_email(self, db: Session, email: str) -> Optional[User]:
        """Benutzer über die E-Mail-Adresse, ohne Rücksicht auf Groß-/Klein.

        E-Mail-Adressen sind im Alltag nicht schreibweisenabhängig. Wer sein
        Konto als ``Oliver@…`` angelegt hat und sich als ``oliver@…`` anmeldet,
        soll nicht ratlos vor „E-Mail oder Passwort falsch" stehen.
        """
        if not email:
            return None
        return db.query(User).filter(func.lower(User.email) == email.lower()).first()

    def get_user_by_id(self, db: Session, user_id: UUID) -> Optional[User]:
        return db.query(User).filter(User.id == user_id).first()


auth_service = AuthService()
