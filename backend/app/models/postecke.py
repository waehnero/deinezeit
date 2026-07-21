"""
Postecke (Social-Media-Modul, Etappe 1)
=======================================

Posts für Social-Media-Kanäle mit wenigen Klicks vorbereiten: Fotos hochladen,
kurze Beschreibung (Text/Diktat), KI erzeugt Posttext + Hashtags im Stil des
gewählten Profils. Veröffentlichung in Etappe 1 "assistiert" (Text in die
Zwischenablage, Kanal öffnen — der Benutzer macht den letzten Klick selbst;
bei privaten Facebook-Profilen ist das der einzige zulässige Weg).

Profile:
  Ein Profil = ein Social-Media-Konto (Kanal, Stil-Prompt, später Zugangs-
  daten für die Direktanbindung in Etappe 3). Profile sind persönlich
  (owner_user_id), da sie private Konten repräsentieren.

Fotos liegen im Objektspeicher (storage_service), Schlüssel-Schema:
  postecke/<post_id>/<dateiname>
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Boolean, DateTime, Integer, ForeignKey, Text
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.base import Base

# Kanäle: bestimmt Ziel-URL beim assistierten Posten und später die Anbindung
KANAELE = ("facebook_privat", "facebook_seite", "instagram", "linkedin",
           "tiktok", "youtube", "whatsapp", "x", "threads",
           "google_business", "pinterest", "sonstige")

# Bild-Ausspielung je Profil: Zielformat (Seitenverhältnis, mittiger Zuschnitt)
BILD_FORMATE = ("original", "1:1", "4:5", "16:9", "9:16")

# Vordefinierte Foto-Filter für eine gleichbleibende Anzeigequalität je Profil
BILD_FILTER = ("kein", "brillant", "warm", "kuehl", "kontrast", "sw")

# Status-Workflow eines Posts (Kanban-Spalten in Etappe 2);
# "archiviert" = aus dem Board/Kalender ausgeblendet, aber nicht gelöscht
POST_STATUS = ("entwurf", "kontrolle", "geplant", "veroeffentlicht", "archiviert")


class SocialProfil(Base):
    """Ein Social-Media-Konto inkl. Stil-Vorgaben für die KI."""

    __tablename__ = "social_profile"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_user_id = Column(UUID(as_uuid=True),
                           ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    name = Column(String(200), nullable=False)      # z.B. "Facebook privat Oliver"
    kanal = Column(String(30), nullable=False)      # siehe KANAELE

    # Beschreibt Stil und Redensart vergangener Posts — wird der KI als
    # Vorgabe mitgegeben, damit die Vorschläge zum Konto passen.
    stil_prompt = Column(Text, nullable=True)

    # Verschlüsselte Zugangsdaten/Token für die Direktanbindung (Etappe 3).
    # In Etappe 1 ungenutzt; nie im Klartext speichern (services/ki.py: Fernet).
    zugang_enc = Column(Text, nullable=True)

    # Bild-Parameter für die Ausspielung: Originale bleiben unangetastet,
    # Zuschnitt/Filter werden erst beim Teilen/Herunterladen angewendet.
    bild_format = Column(String(10), default="original", nullable=False)  # siehe BILD_FORMATE
    bild_filter = Column(String(30), default="kein", nullable=False)      # siehe BILD_FILTER

    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


class SocialPost(Base):
    """Ein vorbereiteter Social-Media-Post (ein Post = ein Zielprofil)."""

    __tablename__ = "social_posts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_user_id = Column(UUID(as_uuid=True),
                           ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Zielprofil; SET NULL, damit Posts beim Löschen eines Profils erhalten bleiben
    profil_id = Column(UUID(as_uuid=True),
                       ForeignKey("social_profile.id", ondelete="SET NULL"), nullable=True)

    titel = Column(String(300), nullable=True)      # interne Kurzbezeichnung (Board/Liste)
    beschreibung = Column(Text, nullable=True)      # Nutzereingabe an die KI ("was/wo war ich")

    # Optionaler Kontaktbezug (EntityRecord aus Stammdaten, denormalisiert wie
    # bei Attachment). Beim Archivieren wandert der Post ins Datacenter unter
    # diesen Kontakt (Unterordner "Postsarchiv"); ohne Kontakt global.
    kontakt_id = Column(UUID(as_uuid=True), nullable=True)
    kontakt_name = Column(String(300), nullable=True)

    text = Column(Text, nullable=True)              # Posttext (KI-Vorschlag, editierbar)
    hashtags = Column(Text, nullable=True)          # z.B. "#Feuerwehrfest #Ebreichsdorf"
    ort = Column(String(300), nullable=True)
    gefuehl = Column(String(100), nullable=True)    # Facebook-"Gefühl", optional

    status = Column(String(20), default="entwurf", nullable=False)  # siehe POST_STATUS
    geplant_am = Column(DateTime(timezone=True), nullable=True)
    veroeffentlicht_am = Column(DateTime(timezone=True), nullable=True)

    ki_model = Column(String(100), nullable=True)   # womit generiert (Nachvollziehbarkeit)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    fotos = relationship("SocialPostFoto", cascade="all, delete-orphan",
                         order_by="SocialPostFoto.sort_order", lazy="selectin")


class SocialPostFoto(Base):
    """Ein Foto eines Posts (Datei im Objektspeicher)."""

    __tablename__ = "social_post_fotos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    post_id = Column(UUID(as_uuid=True),
                     ForeignKey("social_posts.id", ondelete="CASCADE"), nullable=False)

    storage_key = Column(String(500), nullable=False)
    filename = Column(String(300), nullable=False)
    mimetype = Column(String(100), nullable=False)
    size_bytes = Column(Integer, nullable=True)
    sort_order = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
