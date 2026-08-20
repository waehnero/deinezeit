"""
Herkunftsadresse eines Aufrufs
==============================

Eine Stelle, an der bestimmt wird, von welcher Adresse eine Anfrage kommt.
Gebraucht wird das an zwei Stellen mit ganz unterschiedlicher Folge:

* **Prüfpfad** (``auth.absender_meta``) — steht dort die falsche Adresse, ist
  der Eintrag wertlos.
* **Rate-Limiting** (``main.limiter``) — steht dort die falsche Adresse, zählen
  alle Benutzer auf denselben Topf ein.

Der zweite Fall war bis 18.08.2026 offen: Der Limiter benutzte
``get_remote_address`` von slowapi, also ``request.client.host``. Hinter nginx
ist das immer der Proxy-Container. Damit galten die Grenzwerte nicht je
Benutzer, sondern für die gesamte Installation zusammen — 200 Anfragen und 10
Anmeldungen pro Minute für alle gemeinsam. In einem Betrieb mit zehn Leuten
führt das im Alltag zu „zu viele Anfragen“, ohne dass jemand etwas falsch macht.
"""
from fastapi import Request


def echte_ip(request: Request) -> str:
    """Die Adresse, von der die Anfrage tatsächlich kommt.

    Die Reihenfolge ist bewusst gewählt und **nicht** beliebig:

    1. ``X-Real-IP`` — nginx setzt den Header selbst aus ``$remote_addr`` und
       überschreibt dabei einen vom Client mitgeschickten Wert. Er ist damit
       die einzige Quelle, die ein Aufrufer nicht bestimmen kann.
    2. ``X-Forwarded-For``, und daraus der **letzte** Eintrag. Dieser Header
       ist eine Kette, an die jeder Proxy den vorherigen Absender anhängt —
       der Client kann also bereits mit einem gefüllten Header ankommen. Der
       vorderste Eintrag stammt dann von ihm selbst und ist frei erfunden;
       den letzten hat unser eigener nginx angehängt.
    3. ``request.client.host`` als Rückfall, wenn die Anwendung ohne Proxy
       läuft (Tests, direkter uvicorn-Start).

    Warum das gerade beim Rate-Limiting zählt: Nähme man den vordersten Eintrag
    aus ``X-Forwarded-For``, könnte sich jeder Aufrufer mit einem erfundenen
    Header eine eigene, leere Zählung verschaffen — die Bremse wäre wirkungslos.

    Bei mehr als einem vertrauenswürdigen Proxy vor nginx (z. B. einem
    vorgeschalteten Dienst des Hosters) müsste Punkt 2 um dessen Anzahl
    zurückzählen. Für die aktuelle Aufstellung — genau ein eigener nginx — ist
    der letzte Eintrag richtig.
    """
    ip = (request.headers.get("x-real-ip") or "").strip()

    if not ip:
        kette = request.headers.get("x-forwarded-for", "")
        teile = [t.strip() for t in kette.split(",") if t.strip()]
        ip = teile[-1] if teile else ""

    if not ip:
        ip = request.client.host if request.client else ""

    # slowapi braucht einen Schlüssel; ein leerer Wert würde alle Aufrufer
    # wieder auf denselben Topf werfen — dann lieber ein sprechender Ersatz.
    return ip or "unbekannt"
