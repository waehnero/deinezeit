"""
Öffentliche (auth-freie) Endpunkte.

Aktuell: token-gesicherter Abruf von Postecke-Medien. Instagram lädt Fotos/Videos
nicht hoch, sondern holt sie von einer öffentlich erreichbaren URL — dafür liefert
dieser Endpunkt ein Medium über einen signierten, zeitlich begrenzten Token aus
(HMAC über SECRET_KEY, siehe services/social_publish.py). Der Token IST die
Berechtigung; ein Login ist bewusst NICHT nötig, damit die Instagram-Server den
Abruf durchführen können.

Dieser Router wird in main.py OHNE Modul-/Auth-Sperre eingebunden.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.models.postecke import SocialPost, SocialProfil, SocialPostFoto, SocialPostVideo
from app.services import storage_service, social_publish
from app.services import postecke as postecke_service

router = APIRouter(prefix="/oeffentlich", tags=["Öffentlich"])


@router.get("/postecke/medien/{token}")
def postecke_medium(token: str, db: Session = Depends(get_db)):
    """
    Liefert ein Post-Medium (Foto/Video) anhand eines signierten Kurzzeit-Tokens.
    Fotos werden – wie bei der Facebook-Direktveröffentlichung – in der
    Ausspielungs-Variante des Post-Profils (Zielformat + Filter) geliefert.
    """
    geprueft = social_publish.pruefe_medien_token(token)
    if not geprueft:
        raise HTTPException(404, "Link ungültig oder abgelaufen")
    art, media_id = geprueft
    try:
        mid = UUID(media_id)
    except ValueError:
        raise HTTPException(404, "Link ungültig")

    if art == "video":
        video = db.query(SocialPostVideo).filter(SocialPostVideo.id == mid).first()
        if not video:
            raise HTTPException(404, "Nicht gefunden")
        data, content_type = storage_service.download_file(video.storage_key, db)
        return Response(content=data, media_type=content_type or video.mimetype or "video/mp4")

    if art == "foto":
        zeile = (db.query(SocialPostFoto, SocialPost)
                 .join(SocialPost, SocialPost.id == SocialPostFoto.post_id)
                 .filter(SocialPostFoto.id == mid).first())
        if not zeile:
            raise HTTPException(404, "Nicht gefunden")
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
            daten, mimetype = data, foto.mimetype or "image/jpeg"
        return Response(content=daten, media_type=mimetype)

    raise HTTPException(404, "Unbekannter Medientyp")
