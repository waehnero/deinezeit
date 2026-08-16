"""
Dashboard-Kennzahlen — eine Quelle für alle Kacheln
====================================================

Vorher holte sich das Dashboard seine Zahlen mit bis zu 13 einzelnen Anfragen
und rechnete einen Teil davon im Browser zusammen (das Finanz-Widget lud dazu
*alle* Rechnungen). Hier entsteht stattdessen eine einzige Antwort, die genau
die Kennzahlen der tatsächlich sichtbaren Kacheln enthält.

Grundsatz: **nichts doppelt rechnen.** Wo es bereits einen `/stats`-Endpunkt
gibt (Aufgaben, Zeiterfassung, Projekte, Datacenter), ruft dieser Service
dessen Funktion auf, statt die Logik nachzubauen. Zwei Kopien derselben
Berechnung würden sonst über kurz oder lang auseinanderlaufen — und ein
Dashboard, das andere Zahlen zeigt als die Fachansicht, meldet niemand als
Fehler, man glaubt einfach der falschen.

Neu gerechnet wird nur, was es vorher nirgends gab: die Finanz-Kennzahlen.

Modulrechte werden je Baustein geprüft (siehe `kennzahlen`); wer ein Modul
nicht hat, bekommt den Baustein schlicht nicht geliefert.
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.modules import user_has_module
from app.models.user import User, UserRole

# Belegzustände, in denen noch Geld aussteht (Beschluss 15.08.2026).
# Deckungsgleich mit services/overdue_service.py und services/dunning.py —
# „gesendet" und „teilbezahlt" sind ebenso unbeglichen wie „offen".
UNBEGLICHEN = ("gesendet", "offen", "teilbezahlt", "ueberfaellig")


# ── Finanzen ─────────────────────────────────────────────────────────────────
def finanz_kennzahlen(db: Session) -> dict:
    """Offene, überfällige und im laufenden Monat bezahlte Rechnungen.

    Rechnet in Postgres statt im Browser: die Kachel bleibt damit gleich
    schnell, ob dreißig oder dreißigtausend Belege in der Datenbank liegen.

    Der ausgewiesene Betrag ist der **offene Restbetrag** (Belegsumme minus
    bereits erfasster Zahlungen), nicht die Bruttosumme — bei teilbezahlten
    Rechnungen wäre letztere zu hoch.

    „Offen" und „überfällig" sind überschneidungsfrei: überfällige Belege
    zählen nur in der zweiten Gruppe, damit sich die Zeilen der Kachel wie
    bisher zur Gesamtzahl addieren.
    """
    from app.models.invoice import Invoice, InvoicePayment

    heute = date.today()

    # Bereits gezahlte Beträge je Beleg
    zahlungen = (
        db.query(
            InvoicePayment.invoice_id.label("invoice_id"),
            func.coalesce(func.sum(InvoicePayment.amount), 0).label("gezahlt"),
        )
        .group_by(InvoicePayment.invoice_id)
        .subquery()
    )

    offen_betrag = Invoice.total - func.coalesce(zahlungen.c.gezahlt, 0)

    # Überfällig wird aus dem Zahlungsziel abgeleitet und nicht aus dem Status:
    # den setzt ein täglicher Hintergrundlauf (services/overdue_service.py), er
    # kann also für Belege, die heute fällig wurden, noch hinterherhinken.
    ueberfaellig_bedingung = Invoice.due_date.isnot(None) & (Invoice.due_date < heute)

    unbeglichen = (
        db.query(
            func.count().label("anzahl"),
            func.coalesce(func.sum(offen_betrag), 0).label("summe"),
            ueberfaellig_bedingung.label("ist_ueberfaellig"),
        )
        .outerjoin(zahlungen, zahlungen.c.invoice_id == Invoice.id)
        .filter(
            Invoice.doc_type == "rechnung",
            Invoice.is_recurring_template.is_(False),
            Invoice.status.in_(UNBEGLICHEN),
        )
        .group_by(ueberfaellig_bedingung)
        .all()
    )

    offen = {"anzahl": 0, "summe": Decimal("0")}
    ueberfaellig = {"anzahl": 0, "summe": Decimal("0")}
    for zeile in unbeglichen:
        ziel = ueberfaellig if zeile.ist_ueberfaellig else offen
        ziel["anzahl"] = zeile.anzahl
        ziel["summe"] = Decimal(str(zeile.summe or 0))

    # Im laufenden Monat beglichen — hier zählt die volle Belegsumme, denn der
    # Beleg ist ja vollständig bezahlt.
    monatsbeginn = heute.replace(day=1)
    bezahlt = (
        db.query(
            func.count().label("anzahl"),
            func.coalesce(func.sum(Invoice.total), 0).label("summe"),
        )
        .filter(
            Invoice.doc_type == "rechnung",
            Invoice.is_recurring_template.is_(False),
            Invoice.status == "bezahlt",
            Invoice.paid_at.isnot(None),
            Invoice.paid_at >= monatsbeginn,
        )
        .one()
    )

    def geld(betrag) -> float:
        return float(Decimal(str(betrag or 0)).quantize(Decimal("0.01")))

    return {
        "offen": {"count": offen["anzahl"], "sum": geld(offen["summe"])},
        "ueberfaellig": {"count": ueberfaellig["anzahl"], "sum": geld(ueberfaellig["summe"])},
        "bezahlt_monat": {"count": bezahlt.anzahl, "sum": geld(bezahlt.summe)},
    }


# ── Offene Posten & Mahnwesen ────────────────────────────────────────────────
def offene_posten_kennzahlen(db: Session) -> dict:
    """Forderungen nach Alter gestaffelt, dazu der Stand des Mahnwesens.

    Die Staffelung (bis 30 / 31–60 / über 60 Tage überfällig) ist die übliche
    Sicht auf Außenstände: eine Forderung, die zwei Monate liegt, ist etwas
    anderes als eine, die seit drei Tagen fällig ist.

    Gerechnet wird wie in `finanz_kennzahlen` mit dem offenen Restbetrag.
    """
    from app.models.invoice import Invoice, InvoiceDunning, InvoicePayment

    heute = date.today()

    zahlungen = (
        db.query(
            InvoicePayment.invoice_id.label("invoice_id"),
            func.coalesce(func.sum(InvoicePayment.amount), 0).label("gezahlt"),
        )
        .group_by(InvoicePayment.invoice_id)
        .subquery()
    )
    offen_betrag = Invoice.total - func.coalesce(zahlungen.c.gezahlt, 0)

    faellige = (
        db.query(Invoice.due_date, offen_betrag.label("offen"))
        .outerjoin(zahlungen, zahlungen.c.invoice_id == Invoice.id)
        .filter(
            Invoice.doc_type == "rechnung",
            Invoice.is_recurring_template.is_(False),
            Invoice.status.in_(UNBEGLICHEN),
            Invoice.due_date.isnot(None),
            Invoice.due_date < heute,
        )
        .all()
    )

    staffel = {
        "bis_30":   {"count": 0, "sum": Decimal("0")},
        "bis_60":   {"count": 0, "sum": Decimal("0")},
        "ueber_60": {"count": 0, "sum": Decimal("0")},
    }
    for zeile in faellige:
        tage = (heute - zeile.due_date).days
        schlüssel = "bis_30" if tage <= 30 else ("bis_60" if tage <= 60 else "ueber_60")
        staffel[schlüssel]["count"] += 1
        staffel[schlüssel]["sum"] += Decimal(str(zeile.offen or 0))

    # Mahnstand: je noch unbeglichenem Beleg zählt seine **höchste** bereits
    # verschickte Stufe. Ohne das `max` erschiene ein dreimal gemahnter Beleg
    # in allen drei Stufen, und ohne die Einschränkung auf offene Belege
    # zählten auch längst bezahlte Forderungen mit.
    hoechste = (
        db.query(
            InvoiceDunning.invoice_id.label("invoice_id"),
            func.max(InvoiceDunning.level).label("stufe"),
        )
        .join(Invoice, Invoice.id == InvoiceDunning.invoice_id)
        .filter(Invoice.status.in_(UNBEGLICHEN))
        .group_by(InvoiceDunning.invoice_id)
        .subquery()
    )
    mahnungen = (
        db.query(hoechste.c.stufe, func.count(hoechste.c.invoice_id))
        .group_by(hoechste.c.stufe)
        .all()
    )

    return {
        "staffel": {
            k: {"count": v["count"], "sum": float(v["sum"].quantize(Decimal("0.01")))}
            for k, v in staffel.items()
        },
        "gesamt": {
            "count": sum(v["count"] for v in staffel.values()),
            "sum": float(sum((v["sum"] for v in staffel.values()),
                             Decimal("0")).quantize(Decimal("0.01"))),
        },
        "mahnstufen": [{"stufe": stufe, "belege": anzahl} for stufe, anzahl in sorted(mahnungen)],
    }


# ── Postecke ─────────────────────────────────────────────────────────────────
def postecke_kennzahlen(db: Session) -> dict:
    """Beiträge je Kanban-Spalte, die nächsten geplanten und gescheiterte Sendungen."""
    from app.models.postecke import POST_STATUS, SocialPost

    jetzt = datetime.now(timezone.utc)

    je_status = dict(
        db.query(SocialPost.status, func.count(SocialPost.id))
        .group_by(SocialPost.status)
        .all()
    )

    naechste = (
        db.query(SocialPost)
        .filter(SocialPost.status == "geplant", SocialPost.geplant_am.isnot(None),
                SocialPost.geplant_am >= jetzt)
        .order_by(SocialPost.geplant_am.asc())
        .limit(3)
        .all()
    )

    # Beiträge, deren Veröffentlichung schief ging — die fallen sonst niemandem
    # auf, weil sie im Kanban unverändert stehen bleiben.
    fehler = (
        db.query(func.count(SocialPost.id))
        .filter(SocialPost.publish_error.isnot(None))
        .scalar() or 0
    )

    return {
        "je_status": {s: je_status.get(s, 0) for s in POST_STATUS},
        "naechste": [
            {
                "id": str(p.id),
                # `titel` ist die interne Kurzbezeichnung fürs Board; fehlt sie,
                # behelfen wir uns mit dem Anfang des Beitragstexts.
                "titel": p.titel or (p.text or "")[:60] or "(ohne Text)",
                "geplant_am": p.geplant_am.isoformat() if p.geplant_am else None,
            }
            for p in naechste
        ],
        "fehler": fehler,
    }


# ── Umsatz-Verlauf ───────────────────────────────────────────────────────────
def umsatz_kennzahlen(db: Session) -> dict:
    """Monatsumsätze des laufenden Jahres mit Vorjahresvergleich.

    Nutzt `services/auswertungen.je_monat` — dieselbe Quelle wie die
    Auswertungsseite. Die Kachel kann damit gar nicht andere Zahlen zeigen als
    die Fachansicht.

    Bewusst das **Kalenderjahr** statt der letzten zwölf Monate: nur so passt
    die Kachel zur Auswertung. Im Januar ist das Diagramm dafür kurz — der
    Vorjahresbalken steht aber von Anfang an daneben.
    """
    from app.services import auswertungen

    jahr = date.today().year
    roh = auswertungen.je_monat(db, jahr)

    return {
        "jahr": roh["jahr"],
        "monate": [
            {
                "monat": m["monat"],
                "netto": float(m["netto"]),
                "vorjahr": float(m["vorjahr"]),
                "belege": m["belege"],
            }
            for m in roh["monate"]
        ],
        "netto_gesamt": float(roh["netto_gesamt"]),
        "vorjahr_gesamt": float(roh["vorjahr_gesamt"]),
    }


# ── Eingangsrechnungen & Monatsabschluss ─────────────────────────────────────
def eingangsrechnungen_kennzahlen(db: Session, user: User) -> dict:
    """Offene Eingangsrechnungen, Vorsteuer des Monats, Stand des Abschlusses.

    Die Kachel selbst hängt an „buchhaltung" — wie die Eingangsrechnungen. Der
    Monatsabschluss verlangt zusätzlich „verkauf" (siehe main.py, period.py);
    ohne dieses Recht bleibt der Abschluss-Teil deshalb weg, statt die Kachel
    ganz zu verbergen.
    """
    from app.models.period import AccountingPeriod
    from app.models.purchase import PurchaseInvoice

    heute = date.today()
    monatsbeginn = heute.replace(day=1)

    offen = (
        db.query(
            func.count(PurchaseInvoice.id),
            func.coalesce(func.sum(PurchaseInvoice.gross_total), 0),
        )
        .filter(PurchaseInvoice.status == "offen")
        .one()
    )

    # Vorsteuer nur, soweit sie abziehbar ist (§ 12 UStG) — genau dafür gibt es
    # das Feld `vat_deductible` getrennt von der Steuerart.
    vorsteuer = (
        db.query(func.coalesce(func.sum(PurchaseInvoice.tax_total), 0))
        .filter(
            PurchaseInvoice.vat_deductible.is_(True),
            PurchaseInvoice.date >= monatsbeginn,
            PurchaseInvoice.date <= heute,
        )
        .scalar() or 0
    )

    ergebnis = {
        "offen": {"count": offen[0], "sum": float(Decimal(str(offen[1] or 0)))},
        "vorsteuer_monat": float(Decimal(str(vorsteuer))),
    }

    # Ist der Vormonat schon abgeschlossen? Nur mit dem Recht auf „verkauf".
    if user_has_module(user, "verkauf"):
        vormonat = monatsbeginn - timedelta(days=1)
        periode = (
            db.query(AccountingPeriod)
            .filter(AccountingPeriod.year == vormonat.year,
                    AccountingPeriod.month == vormonat.month)
            .first()
        )
        ergebnis["vormonat"] = {
            "jahr": vormonat.year,
            "monat": vormonat.month,
            "abgeschlossen": bool(periode and periode.status == "abgeschlossen"),
        }

    return ergebnis


# ── Buchhaltung / System (bisher als Extra-Anfragen nachgeladen) ─────────────
def buchhaltung_kennzahlen(db: Session) -> dict:
    """Anzahl aktiver Buchungskonten."""
    from app.models.accounting import AccountingAccount

    anzahl = (
        db.query(func.count(AccountingAccount.id))
        .filter(AccountingAccount.is_active.is_(True))
        .scalar()
    )
    return {"konten": anzahl or 0}


def system_kennzahlen(db: Session) -> dict:
    """Benutzerzahlen und die laufende Version.

    Bewusst **ohne** Update-Prüfung: `GET /api/system/version` fragt dafür
    GitHub ab (5 s Timeout, notfalls `git fetch` mit 10 s). In diesem
    Sammelaufruf hinge daran das gesamte Dashboard. Ob eine neuere Version
    bereitsteht, lädt das Frontend deshalb weiterhin getrennt nach.
    """
    from app.core.config import settings

    gesamt = db.query(func.count(User.id)).scalar() or 0
    aktiv = (
        db.query(func.count(User.id)).filter(User.is_active.is_(True)).scalar() or 0
    )
    return {
        "benutzer_gesamt": gesamt,
        "benutzer_aktiv": aktiv,
        "version": settings.APP_VERSION,
    }


# ── Zusammenstellung ─────────────────────────────────────────────────────────
# Baustein → benötigte Module (leer = für alle sichtbar). Es sind bewusst
# *Listen*: Umsatz, Eingangsrechnungen und Monatsabschluss verlangen wie ihre
# Fachseiten „verkauf" UND „buchhaltung". Wer Belege schreiben darf, muss nicht
# zwangsläufig die Auswertungen sehen (siehe app/main.py und core/modules.py).
#
# Spiegelt die Registry im Frontend (frontend/src/data/dashboardWidgets.js);
# die Übereinstimmung prüft ein Test.
BAUSTEIN_MODUL = {
    "aufgaben": ("aufgaben",),
    "zeiterfassung": ("zeiterfassung",),
    "rechnungen": ("verkauf",),
    "projekte": ("projekte",),
    "datacenter": ("datacenter",),
    "buchhaltung": ("buchhaltung",),
    "benutzer_system": (),
    # Neu in Etappe 2. Die Rechte entsprechen genau denen der Zielseiten
    # (siehe main.py und die Routen in frontend/src/main.jsx) — eine Kachel,
    # die Zahlen zeigt, deren Fachseite gesperrt ist, wäre eine Hintertür.
    "offene_posten": ("verkauf", "buchhaltung"),
    "postecke": ("postecke",),
    "umsatz": ("verkauf", "buchhaltung"),
    "eingangsrechnungen": ("buchhaltung",),
}

# Bausteine, die nur Administratoren sehen
NUR_ADMIN = {"buchhaltung", "benutzer_system"}

# Bausteine ohne Serverdaten (rein statische Kacheln) — bewusst hier gelistet,
# damit eine Anfrage danach kein Fehler ist, sondern einfach nichts liefert.
OHNE_DATEN = {"berichte", "quick_access", "entity_type"}

VERFUEGBAR = set(BAUSTEIN_MODUL) | OHNE_DATEN


def darf_sehen(user: User, baustein: str) -> bool:
    """Darf dieser Benutzer den Baustein abrufen? Alle Module müssen passen."""
    ist_admin = user.role == UserRole.admin
    if baustein in NUR_ADMIN and not ist_admin:
        return False
    module = BAUSTEIN_MODUL.get(baustein, ())
    return all(user_has_module(user, m) for m in module)


async def kennzahlen(db: Session, user: User, bausteine: list[str]) -> dict:
    """Kennzahlen der angefragten Bausteine sammeln.

    Nicht erlaubte oder unbekannte Bausteine werden **still übergangen**, statt
    den ganzen Aufruf mit 403 abzubrechen: ein einzelner gesperrter Baustein
    würde sonst das komplette Dashboard leer lassen.

    Fällt ein einzelner Baustein mit einem Fehler aus, bleibt der Rest
    bestehen — genau wie vorher, als jede Kachel ihre eigene Anfrage mit
    eigenem `.catch()` hatte.
    """
    # Lokale Importe: diese Module ziehen ihrerseits viel nach sich, und der
    # Dashboard-Router soll den Start der Anwendung nicht verlangsamen.
    from app.api import aufgaben as aufgaben_api
    from app.api import datacenter as datacenter_api
    from app.api import projektplan as projektplan_api
    from app.api import zeiterfassung as zeiterfassung_api

    ergebnis: dict = {}

    for baustein in dict.fromkeys(bausteine):        # Reihenfolge, ohne Doppelte
        if baustein not in VERFUEGBAR or baustein in OHNE_DATEN:
            continue
        if not darf_sehen(user, baustein):
            continue

        try:
            if baustein == "aufgaben":
                stats = aufgaben_api.get_stats(
                    mine=False, limit=4, db=db, current_user=user,
                )
                ergebnis["aufgaben"] = {
                    "stats": stats,
                    "mail_vorschlaege": mail_vorschlaege_offen(db),
                }

            elif baustein == "zeiterfassung":
                ergebnis["zeiterfassung"] = {
                    "stats": await zeiterfassung_api.get_stats(
                        user_id=None, db=db, current_user=user,
                    ),
                    "laufend": await zeiterfassung_api.get_running_timer(
                        db=db, current_user=user,
                    ),
                }

            elif baustein == "rechnungen":
                ergebnis["rechnungen"] = finanz_kennzahlen(db)

            elif baustein == "projekte":
                ergebnis["projekte"] = await projektplan_api.recent_projects(
                    limit=5, db=db, _=user,
                )

            elif baustein == "datacenter":
                ergebnis["datacenter"] = await datacenter_api.get_datacenter_stats(
                    limit=3, db=db, _=user,
                )

            elif baustein == "offene_posten":
                ergebnis["offene_posten"] = offene_posten_kennzahlen(db)

            elif baustein == "postecke":
                ergebnis["postecke"] = postecke_kennzahlen(db)

            elif baustein == "umsatz":
                ergebnis["umsatz"] = umsatz_kennzahlen(db)

            elif baustein == "eingangsrechnungen":
                ergebnis["eingangsrechnungen"] = eingangsrechnungen_kennzahlen(db, user)

            elif baustein == "buchhaltung":
                ergebnis["buchhaltung"] = buchhaltung_kennzahlen(db)

            elif baustein == "benutzer_system":
                ergebnis["benutzer_system"] = system_kennzahlen(db)

        except Exception as e:                       # noqa: BLE001
            # Bewusst geschluckt, aber protokolliert: eine kaputte Kachel darf
            # das übrige Dashboard nicht mitreißen.
            import logging
            logging.getLogger(__name__).warning(
                "Dashboard-Kennzahl '%s' fehlgeschlagen: %s", baustein, e,
            )

    return ergebnis


def mail_vorschlaege_offen(db: Session) -> int:
    """Anzahl offener Mail-Vorschläge (Kennziffer der Aufgaben-Kachel)."""
    from app.models.mailimport import MailTaskSuggestion

    return db.query(func.count(MailTaskSuggestion.id)).filter(
        MailTaskSuggestion.status == "offen",
    ).scalar() or 0
