"""
MinIO Storage Service
Verwaltet alle Dateioperationen mit dem MinIO Objektspeicher.
"""
import os
import io
import secrets
from datetime import timedelta
from typing import Optional

from minio import Minio
from minio.error import S3Error

ENDPOINT  = os.environ.get("MINIO_ENDPOINT", "minio:9000")
ACCESS    = os.environ.get("MINIO_ROOT_USER", "minioadmin")
SECRET    = os.environ.get("MINIO_ROOT_PASSWORD", "minioadmin123")
BUCKET    = os.environ.get("MINIO_BUCKET", "deinezeit-files")


def _client() -> Minio:
    return Minio(ENDPOINT, access_key=ACCESS, secret_key=SECRET, secure=False)


def ensure_bucket():
    """Stellt sicher dass der Bucket existiert (beim Start aufrufen)."""
    c = _client()
    if not c.bucket_exists(BUCKET):
        c.make_bucket(BUCKET)


def upload_file(storage_key: str, data: bytes, mimetype: str) -> None:
    """Datei in MinIO hochladen."""
    c = _client()
    ensure_bucket()
    c.put_object(
        BUCKET,
        storage_key,
        io.BytesIO(data),
        length=len(data),
        content_type=mimetype,
    )


def download_file(storage_key: str) -> tuple[bytes, str]:
    """Datei aus MinIO herunterladen. Gibt (bytes, content_type) zurück."""
    c = _client()
    response = c.get_object(BUCKET, storage_key)
    try:
        data = response.read()
        content_type = response.headers.get("Content-Type", "application/octet-stream")
    finally:
        response.close()
        response.release_conn()
    return data, content_type


def delete_file(storage_key: str) -> None:
    """Datei aus MinIO löschen."""
    c = _client()
    try:
        c.remove_object(BUCKET, storage_key)
    except S3Error:
        pass  # Datei existiert nicht mehr – kein Fehler


def generate_presigned_url(storage_key: str, expires_hours: int = 24) -> str:
    """Öffentlichen Download-Link generieren (wie SeaDrive Share-Link)."""
    c = _client()
    url = c.presigned_get_object(
        BUCKET,
        storage_key,
        expires=timedelta(hours=expires_hours),
    )
    return url


def generate_share_token() -> str:
    """Sicheres zufälliges Token für Share-Links."""
    return secrets.token_urlsafe(32)


def build_storage_key(entity_type: str, entity_id: str, filename: str) -> str:
    """Einheitlicher Pfad im Bucket: z.B. kontakte/uuid/dokument.pdf"""
    # Dateinamen sichern (Sonderzeichen entfernen)
    safe_name = "".join(c for c in filename if c.isalnum() or c in "._- ")
    return f"{entity_type}/{entity_id}/{safe_name}"
