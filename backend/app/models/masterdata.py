import uuid
from datetime import datetime, timezone
from sqlalchemy import (Column, String, Boolean, DateTime, Integer, Numeric,
                        ForeignKey, Text)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.db.base import Base


class EntityType(Base):
    """
    Ein Stammdaten-Typ, z.B. 'Kunden', 'Lieferanten', 'Projekte'.
    Wird vom Admin angelegt und kann jederzeit erweitert werden.
    """
    __tablename__ = "entity_types"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)           # z.B. "Kunden"
    slug = Column(String(100), nullable=False, unique=True)  # z.B. "kunden"
    icon = Column(String(50), nullable=True)             # z.B. "Users"
    color = Column(String(20), nullable=True)            # z.B. "#3b82f6"
    description = Column(String(500), nullable=True)
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    # Geordnete Tab-Liste: ["Allgemein", "Bankdaten", "Kontakt"]
    # Leere Liste = keine Tabs (klassisches Formular ohne Reiter)
    tabs = Column(JSONB, nullable=True, default=list)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    fields = relationship("FieldDefinition", back_populates="entity_type",
                          cascade="all, delete-orphan", order_by="FieldDefinition.sort_order")
    records = relationship("EntityRecord", back_populates="entity_type",
                           cascade="all, delete-orphan")


class FieldDefinition(Base):
    """
    Definition eines Feldes innerhalb eines Stammdaten-Typs.
    z.B. 'Firmenname' (Text), 'Umsatz' (Zahl), 'Gründungsdatum' (Datum)
    """
    __tablename__ = "field_definitions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type_id = Column(UUID(as_uuid=True), ForeignKey("entity_types.id"), nullable=False)

    # Feld-Eigenschaften
    name = Column(String(100), nullable=False)         # Anzeigename: "Firmenname"
    key = Column(String(100), nullable=False)          # Technischer Key: "firmenname"
    field_type = Column(String(30), nullable=False)    # text, number, date, email, phone,
                                                       # dropdown, checkbox, textarea, url
    is_required = Column(Boolean, default=False)
    is_unique = Column(Boolean, default=False)
    show_in_list = Column(Boolean, default=True)       # In der Tabellen-Übersicht anzeigen
    sort_order = Column(Integer, default=0)
    col_span = Column(Integer, default=12)             # Rasterbreite: 3=25%, 4=33%, 6=50%, 9=75%, 12=100%

    # Tab-Zugehörigkeit: Name des Tabs (muss in EntityType.tabs enthalten sein)
    # None = kein Tab / erster Tab
    tab = Column(String(100), nullable=True)

    # Für Dropdown: Optionen als JSON-Array  ["Option A", "Option B"]
    options = Column(JSONB, nullable=True)

    # Platzhalter-Text im Eingabefeld
    placeholder = Column(String(200), nullable=True)

    # Standardwert
    default_value = Column(String(500), nullable=True)

    # Für Relation-Felder: Slug des verknüpften EntityType (z.B. "kunden")
    linked_type_slug = Column(String(100), nullable=True)

    # Für lookup-Felder: Quelle der Auswahlliste außerhalb der Stammdaten.
    # "konten" = Kontenplan (accounting_accounts), "artikelgruppen" = article_groups.
    # Abgegrenzt von ``relation``: Das zeigt auf einen EntityRecord und speichert
    # {id, display_name}; ``lookup`` speichert den fachlichen Schlüssel selbst
    # (Kontonummer, Gruppennummer), damit Belege und Export ihn direkt lesen
    # können, ohne eine zweite Abfrage.
    lookup_source = Column(String(50), nullable=True)

    # Systemfeld: von einer Migration angelegt und von anderen Modulen
    # vorausgesetzt (der Belegpicker liest z.B. preis, einheit, erloes_konto).
    # Solche Felder dürfen weder gelöscht noch umgeschlüsselt werden — sonst
    # läuft der Beleg still ins Leere, ohne dass irgendwo ein Fehler erscheint.
    # Umbenennen, verschieben und ausblenden bleibt erlaubt.
    is_system = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    entity_type = relationship("EntityType", back_populates="fields")


class EntityRecord(Base):
    """
    Ein einzelner Datensatz, z.B. ein Kunde oder Lieferant.
    Die eigentlichen Daten werden in 'data' als JSONB gespeichert.
    """
    __tablename__ = "entity_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type_id = Column(UUID(as_uuid=True), ForeignKey("entity_types.id"), nullable=False)

    # Alle Felder des Datensatzes in einem flexiblen JSON-Objekt
    # z.B. {"firmenname": "Muster GmbH", "email": "info@muster.at", "umsatz": 150000}
    data = Column(JSONB, nullable=False, default=dict)

    # Schnellzugriff: Anzeigename des Datensatzes (aus dem ersten Textfeld)
    display_name = Column(String(300), nullable=True)

    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    updated_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    # DSGVO-Löschung: gesetzt, wenn der Datensatz anonymisiert wurde (Tombstone).
    # Die Zeile bleibt erhalten, damit keine Verweise verwaisen — aber ohne
    # Personenbezug (data geleert, display_name = "Gelöschter Kontakt").
    anonymized_at = Column(DateTime(timezone=True), nullable=True)

    # Archivierung statt Löschung: Datensätze mit Verweisen aus anderen
    # Modulen (Zeiten, Belege, Projekte, …) dürfen nicht hart gelöscht
    # werden — sie werden archiviert. Archivierte Datensätze verschwinden
    # aus Listen und Auswahlfeldern, bleiben aber für die Historie erhalten
    # und können vom Admin wiederhergestellt werden.
    archived_at = Column(DateTime(timezone=True), nullable=True)
    archived_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    entity_type = relationship("EntityType", back_populates="records")


class ArticleGroup(Base):
    """
    Artikelgruppe (Warengruppe) — Sortimentsstruktur *und* Buchungsvorgabe.

    Bewusst eine eigene Tabelle statt eines weiteren ``EntityType``: An der
    Gruppe hängen Buchhaltungslogik (Erlös-/Aufwandskonto) und ein laufender
    Zähler für die Artikelnummer. Beides braucht feste, typisierte Spalten und
    zeilenweise Sperren beim Hochzählen — im JSONB-Baukasten der EntityRecords
    ließe sich weder das eine prüfen noch das andere sicher machen. Der
    Kontenplan (``accounting_accounts``) ist aus demselben Grund eine eigene
    Tabelle.

    Die Artikel selbst bleiben ``EntityRecord``: Sie sollen weiter frei um
    eigene Felder erweiterbar sein.
    """
    __tablename__ = "article_groups"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Kurzschlüssel, unter dem die Gruppe im Artikel steht — z.B. "DL".
    # Die Artikel speichern diesen Schlüssel, nicht die UUID: So bleibt der
    # CSV-Export lesbar und der Import kann ohne Vorabauflösung zuordnen.
    nr = Column(String(20), nullable=False, unique=True)
    name = Column(String(200), nullable=False)
    beschreibung = Column(String(500), nullable=True)

    # ── Nummernkreis ──────────────────────────────────────────────────────────
    # Präfix + laufende Nummer, z.B. "DL" + 7 + 4 Stellen → "DL-0007".
    praefix = Column(String(10), nullable=True)
    naechste_nummer = Column(Integer, nullable=False, default=1)
    stellen = Column(Integer, nullable=False, default=4)

    # ── Buchungsvorgabe ───────────────────────────────────────────────────────
    # Kontonummern, keine Fremdschlüssel: ``invoice_positions.account_nr`` führt
    # ebenfalls die Nummer, und der BMD-Export liest sie. Ein FK würde außerdem
    # das Löschen eines Kontos an dieser Stelle stillschweigend zur
    # Kettenreaktion machen — genau das war beim Löschregeln-Beschluss
    # ausgeschlossen worden. Geprüft wird stattdessen beim Speichern.
    erloes_konto_nr = Column(String(20), nullable=True)
    aufwand_konto_nr = Column(String(20), nullable=True)

    # Vorgabewerte, die der Artikel erben kann
    ust_satz = Column(Numeric(5, 2), nullable=True)      # NULL = keine Vorgabe
    artikelart = Column(String(30), nullable=True)       # ware | dienstleistung
    einheit = Column(String(30), nullable=True)          # Stk, h, m², …

    is_active = Column(Boolean, nullable=False, default=True)
    sort_order = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
