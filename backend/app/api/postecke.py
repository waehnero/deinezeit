"""
API-Router für die Postecke (Social-Media-Modul, Etappe 1).

Endpunkte:
  Profile:  GET/POST       /postecke/profile
            PUT/DELETE     /postecke/profile/{id}
  Posts:    GET            /postecke/posts?status=...
            POST           /postecke/posts
            GET/PUT/DELETE /postecke/posts/{id}
            POST           /postecke/posts/{id}/status      (Workflow inkl. Planung)
            POST           /postecke/posts/{id}/generieren  (KI-Vorschlag)
  Fotos:    POST           /postecke/posts/{id}/fotos       (Upload, multipart)
            GET            /postecke/fotos/{id}             (Bild abrufen)
            DELETE         /postecke/fotos/{id}

Rechte: Profile und Posts sind persönlich — sichtbar/änderbar nur für den
Besitzer (private Social-Media-Konten).
"""

from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Response
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.postecke import SocialProfil, SocialPost, SocialPostFoto, POST_STATUS
from app.schemas.postecke import (
    ProfilCreate, ProfilUpdate, ProfilResponse,
    PostCreate, PostUpdate, PostStatusUpdate, PostResponse,
    GenerierenRequest, GenerierenResponse,
)
from app.services import storage_service
from app.services import postecke as postecke_service

router = APIRouter(prefix="/postecke", tags=["Postecke"])

ERLAUBTE_FOTO_TYPEN = ("image/jpeg", "image/png", "image/webp", "image/heic", "image/heif")
MAX_FOTO_BYTES = 25 * 1024 * 1024  # 25 MB je Foto (iPhone-Originale)
MAX_FOTOS_JE_POST = 20


# ── Hilfen ────────────────────────────────────────────────────────────────────
def _get_profil(db: Session, profil_id: UUID, user: User) -> SocialProfil:
    p = (db.query(SocialProfil)
         .filter(SocialProfil.id == profil_id,
                 SocialProfil.owner_user_id == user.id).first())
    if not p:
        raise HTTPException(404, "Profil nicht gefunden")
    return p


def _get_post(db: Session, post_id: UUID, user: User) -> SocialPost:
    p = (db.query(SocialPost)
         .filter(SocialPost.id == post_id,
                 SocialPost.owner_user_id == user.id).first())
    if not p:
        raise HTTPException(404, "Post nicht gefunden")
    return p


# ── Profile ───────────────────────────────────────────────────────────────────
@router.get("/profile", response_model=List[ProfilResponse])
def list_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (db.query(SocialProfil)
            .filter(SocialProfil.owner_user_id == current_user.id)
            .order_by(SocialProfil.created_at).all())


@router.post("/profile", response_model=ProfilResponse, status_code=201)
def create_profil(
    body: ProfilCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = SocialProfil(owner_user_id=current_user.id, **body.model_dump())
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@router.put("/profile/{profil_id}", response_model=ProfilResponse)
def update_profil(
    profil_id: UUID,
    body: ProfilUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = _get_profil(db, profil_id, current_user)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(p, key, value)
    db.commit()
    db.refresh(p)
    return p


@router.delete("/profile/{profil_id}", status_code=204)
def delete_profil(
    profil_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = _get_profil(db, profil_id, current_user)
    db.delete(p)
    db.commit()


# ── Posts ─────────────────────────────────────────────────────────────────────
@router.get("/posts", response_model=List[PostResponse])
def list_posts(
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(SocialPost).filter(SocialPost.owner_user_id == current_user.id)
    if status:
        if status not in POST_STATUS:
            raise HTTPException(422, "Ungültiger Status")
        q = q.filter(SocialPost.status == status)
    return q.order_by(SocialPost.created_at.desc()).all()


@router.post("/posts", response_model=PostResponse, status_code=201)
def create_post(
    body: PostCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if body.profil_id:
        _get_profil(db, body.profil_id, current_user)  # Rechteprüfung
    p = SocialPost(owner_user_id=current_user.id, **body.model_dump())
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@router.get("/posts/{post_id}", response_model=PostResponse)
def get_post(
    post_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _get_post(db, post_id, current_user)


@router.put("/posts/{post_id}", response_model=PostResponse)
def update_post(
    post_id: UUID,
    body: PostUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = _get_post(db, post_id, current_user)
    payload = body.model_dump(exclude_unset=True)
    if payload.get("profil_id"):
        _get_profil(db, payload["profil_id"], current_user)  # Rechteprüfung
    for key, value in payload.items():
        setattr(p, key, value)
    db.commit()
    db.refresh(p)
    return p


@router.delete("/posts/{post_id}", status_code=204)
def delete_post(
    post_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = _get_post(db, post_id, current_user)
    for foto in list(p.fotos or []):
        storage_service.delete_file(foto.storage_key, db)
    db.delete(p)
    db.commit()


@router.post("/posts/{post_id}/status", response_model=PostResponse)
def set_post_status(
    post_id: UUID,
    body: PostStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = _get_post(db, post_id, current_user)
    vorher = p.status
    p.status = body.status
    if body.status == "geplant":
        if not body.geplant_am:
            raise HTTPException(422, "Für Status 'geplant' wird geplant_am benötigt")
        p.geplant_am = body.geplant_am
    if body.status == "veroeffentlicht":
        p.veroeffentlicht_am = datetime.now(timezone.utc)

    # Datacenter-Postsarchiv: beim Archivieren spiegeln, bei Wiederherstellung
    # aufräumen. Fehler dürfen den Statuswechsel nicht scheitern lassen.
    if body.status == "archiviert" and vorher != "archiviert":
        try:
            postecke_service.archiviere_ins_datacenter(db, p, user_id=current_user.id)
        except Exception as e:
            print(f"[WARN] Postsarchiv (Datacenter) fehlgeschlagen für {p.id}: {e}")
    elif vorher == "archiviert" and body.status != "archiviert":
        try:
            postecke_service.entferne_datacenter_archiv(db, p)
        except Exception as e:
            print(f"[WARN] Postsarchiv-Aufräumen fehlgeschlagen für {p.id}: {e}")

    db.commit()
    db.refresh(p)
    return p


# ── KI-Generierung ────────────────────────────────────────────────────────────
@router.post("/posts/{post_id}/generieren", response_model=GenerierenResponse)
def generiere_post(
    post_id: UUID,
    body: GenerierenRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Erzeugt einen KI-Vorschlag aus Fotos + Beschreibung + Profil-Stil und
    speichert ihn direkt am Post (bleibt danach frei editierbar).
    """
    p = _get_post(db, post_id, current_user)
    profil = None
    if p.profil_id:
        profil = db.query(SocialProfil).filter(SocialProfil.id == p.profil_id).first()
    try:
        vorschlag = postecke_service.generiere_vorschlag(
            db, p, profil, beschreibung=body.beschreibung)
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"KI-Aufruf fehlgeschlagen: {e}")

    if body.beschreibung:
        p.beschreibung = body.beschreibung
    p.text = vorschlag["text"]
    p.hashtags = vorschlag["hashtags"]
    p.ort = vorschlag["ort"] or p.ort
    p.gefuehl = vorschlag["gefuehl"] or p.gefuehl
    if not p.titel:
        p.titel = vorschlag["titel"]
    p.ki_model = vorschlag["ki_model"]
    if p.status == "entwurf":
        p.status = "kontrolle"
    db.commit()
    return GenerierenResponse(**vorschlag)


# ── Fotos ─────────────────────────────────────────────────────────────────────
@router.post("/posts/{post_id}/fotos", response_model=PostResponse, status_code=201)
async def upload_fotos(
    post_id: UUID,
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = _get_post(db, post_id, current_user)
    vorhandene = len(p.fotos or [])
    if vorhandene + len(files) > MAX_FOTOS_JE_POST:
        raise HTTPException(422, f"Maximal {MAX_FOTOS_JE_POST} Fotos je Post")

    for i, f in enumerate(files):
        mimetype = (f.content_type or "").lower()
        if mimetype not in ERLAUBTE_FOTO_TYPEN:
            raise HTTPException(422, f"Dateityp nicht erlaubt: {f.filename}")
        data = await f.read()
        if len(data) > MAX_FOTO_BYTES:
            raise HTTPException(422, f"Foto zu groß (max. 25 MB): {f.filename}")
        # ID selbst vergeben, damit der Storage-Key VOR dem Insert feststeht
        # (storage_key ist NOT NULL — nachträgliches Setzen scheitert am Flush)
        foto_id = uuid4()
        filename = f.filename or "foto.jpg"
        storage_key = storage_service.build_storage_key(
            "postecke", str(p.id), f"{foto_id}_{filename}")
        storage_service.upload_file(storage_key, data, mimetype, db)
        db.add(SocialPostFoto(
            id=foto_id,
            post_id=p.id,
            storage_key=storage_key,
            filename=filename,
            mimetype=mimetype,
            size_bytes=len(data),
            sort_order=vorhandene + i,
        ))

    db.commit()
    db.refresh(p)
    return p


@router.get("/fotos/{foto_id}/ausspielung")
def get_foto_ausspielung(
    foto_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Foto in der Ausspielungs-Variante des Post-Profils: Zielformat
    (z.B. 1:1, mittiger Zuschnitt) und Filter angewendet, als JPEG.
    Ohne Profil bzw. bei "original"/"kein" nur vereinheitlicht.
    Wird beim Teilen und beim Foto-Download genutzt — das Original
    bleibt unverändert gespeichert.
    """
    zeile = (db.query(SocialPostFoto, SocialPost)
             .join(SocialPost, SocialPost.id == SocialPostFoto.post_id)
             .filter(SocialPostFoto.id == foto_id,
                     SocialPost.owner_user_id == current_user.id).first())
    if not zeile:
        raise HTTPException(404, "Foto nicht gefunden")
    foto, post = zeile

    bild_format, bild_filter = "original", "kein"
    if post.profil_id:
        profil = db.query(SocialProfil).filter(SocialProfil.id == post.profil_id).first()
        if profil:
            bild_format = profil.bild_format or "original"
            bild_filter = profil.bild_filter or "kein"

    data, _ct = storage_service.download_file(foto.storage_key, db)
    try:
        daten, mimetype = postecke_service.bearbeite_foto(data, bild_format, bild_filter)
    except Exception:
        # Bearbeitung fehlgeschlagen (z.B. exotisches Format) -> Original liefern
        daten, mimetype = data, foto.mimetype or "image/jpeg"
    return Response(content=daten, media_type=mimetype)


@router.get("/fotos/{foto_id}")
def get_foto(
    foto_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    foto = (db.query(SocialPostFoto)
            .join(SocialPost, SocialPost.id == SocialPostFoto.post_id)
            .filter(SocialPostFoto.id == foto_id,
                    SocialPost.owner_user_id == current_user.id).first())
    if not foto:
        raise HTTPException(404, "Foto nicht gefunden")
    data, content_type = storage_service.download_file(foto.storage_key, db)
    return Response(content=data, media_type=content_type or foto.mimetype)


@router.delete("/fotos/{foto_id}", status_code=204)
def delete_foto(
    foto_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    foto = (db.query(SocialPostFoto)
            .join(SocialPost, SocialPost.id == SocialPostFoto.post_id)
            .filter(SocialPostFoto.id == foto_id,
                    SocialPost.owner_user_id == current_user.id).first())
    if not foto:
        raise HTTPException(404, "Foto nicht gefunden")
    storage_service.delete_file(foto.storage_key, db)
    db.delete(foto)
    db.commit()
