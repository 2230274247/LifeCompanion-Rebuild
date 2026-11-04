"""Private, owner-scoped storage for generated moment images."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import os
from pathlib import Path
import tempfile
from uuid import uuid4

from PIL import Image, ImageOps

from .image_provider import (
    ALLOWED_FORMATS,
    ImageProviderError,
    normalize_mime,
    validate_image_bytes,
)
from .store import utc_now


THUMBNAIL_MAX_SIZE = (640, 960)
THUMBNAIL_QUALITY = 82


@dataclass(frozen=True)
class MediaContent:
    data: bytes
    mime: str
    filename: str
    sha256: str


class MomentMediaStore:
    def __init__(self, store, settings):
        self.repository = store
        root = getattr(settings, "moment_media_root", None)
        self.root = Path(root or Path(settings.database_path).parent / "moment-media").resolve()
        self.initialize()

    def initialize(self):
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.root, 0o700)
        except OSError:
            pass
        with self.repository.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS moment_media (
                    moment_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    storage_key TEXT NOT NULL,
                    thumbnail_key TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    mime TEXT NOT NULL,
                    thumbnail_mime TEXT NOT NULL,
                    width INTEGER NOT NULL,
                    height INTEGER NOT NULL,
                    bytes INTEGER NOT NULL,
                    sha256 TEXT NOT NULL,
                    thumbnail_sha256 TEXT NOT NULL,
                    trace_id TEXT,
                    created_at TEXT NOT NULL,
                    prompt_summary TEXT NOT NULL DEFAULT '',
                    policy_status TEXT NOT NULL,
                    FOREIGN KEY(moment_id) REFERENCES moments(moment_id)
                        ON DELETE CASCADE,
                    UNIQUE(user_id,storage_key),
                    UNIQUE(user_id,thumbnail_key)
                );
                CREATE INDEX IF NOT EXISTS idx_moment_media_owner
                    ON moment_media(user_id,moment_id);
                """
            )

    @staticmethod
    def _extension(mime: str) -> str:
        return {
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/webp": ".webp",
        }[mime]

    def _new_key(self, owner: str, moment_id: str, mime: str) -> str:
        owner_key = sha256(owner.encode("utf-8")).hexdigest()[:16]
        return f"{owner_key}/{moment_id}/{uuid4().hex}{self._extension(mime)}"

    def _path(self, key: str) -> Path:
        candidate = (self.root / key).resolve()
        if not candidate.is_relative_to(self.root):
            raise ValueError("MEDIA_PATH_OUTSIDE_ROOT")
        return candidate

    @staticmethod
    def _atomic_write(path: Path, data: bytes):
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix=".media-", suffix=".tmp", dir=path.parent
        )
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.chmod(temporary, 0o600)
            except OSError:
                pass
            os.replace(temporary, path)
        except BaseException:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise

    @staticmethod
    def _remove(path: Path):
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    @staticmethod
    def _thumbnail(data: bytes) -> bytes:
        with Image.open(BytesIO(data)) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
            image.thumbnail(THUMBNAIL_MAX_SIZE, Image.Resampling.LANCZOS)
            output = BytesIO()
            image.save(
                output,
                format="JPEG",
                quality=THUMBNAIL_QUALITY,
                optimize=True,
            )
            return output.getvalue()

    def store(
        self,
        owner: str,
        moment_id: str,
        data: bytes,
        *,
        declared_mime: str,
        provider: str,
        model: str,
        trace_id: str | None,
        prompt_summary: str,
        policy_status: str,
    ) -> dict:
        validated = validate_image_bytes(data, declared_mime)
        with self.repository.connect() as db:
            moment = db.execute(
                "SELECT user_id FROM moments WHERE moment_id=?", (moment_id,)
            ).fetchone()
            if moment is None or moment["user_id"] != owner:
                raise LookupError("MOMENT_NOT_FOUND")
            if db.execute(
                "SELECT 1 FROM moment_media WHERE moment_id=?", (moment_id,)
            ).fetchone():
                raise ValueError("MOMENT_MEDIA_ALREADY_EXISTS")

        thumbnail = self._thumbnail(data)
        storage_key = self._new_key(owner, moment_id, validated.mime)
        thumbnail_key = storage_key.rsplit(".", 1)[0] + ".thumb.jpg"
        original_path = self._path(storage_key)
        thumbnail_path = self._path(thumbnail_key)
        self._atomic_write(original_path, data)
        self._atomic_write(thumbnail_path, thumbnail)
        try:
            with self.repository.connect() as db:
                db.execute(
                    """INSERT INTO moment_media
                    (moment_id,user_id,storage_key,thumbnail_key,provider,model,
                     mime,thumbnail_mime,width,height,bytes,sha256,
                     thumbnail_sha256,trace_id,created_at,prompt_summary,policy_status)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        moment_id,
                        owner,
                        storage_key,
                        thumbnail_key,
                        provider,
                        model,
                        validated.mime,
                        "image/jpeg",
                        validated.width,
                        validated.height,
                        len(data),
                        validated.sha256,
                        sha256(thumbnail).hexdigest(),
                        trace_id,
                        utc_now(),
                        " ".join((prompt_summary or "").split())[:240],
                        policy_status,
                    ),
                )
        except BaseException:
            self._remove(original_path)
            self._remove(thumbnail_path)
            raise
        return self.metadata(owner, moment_id) or {}

    def metadata(self, owner: str, moment_id: str) -> dict | None:
        with self.repository.connect() as db:
            row = db.execute(
                """SELECT provider,model,mime,width,height,bytes,sha256,trace_id,
                    created_at,prompt_summary,policy_status
                    FROM moment_media WHERE user_id=? AND moment_id=?""",
                (owner, moment_id),
            ).fetchone()
        return dict(row) if row else None

    def read(self, owner: str, moment_id: str, variant: str) -> MediaContent | None:
        if variant not in ("image", "thumbnail"):
            return None
        with self.repository.connect() as db:
            row = db.execute(
                """SELECT storage_key,thumbnail_key,mime,thumbnail_mime,sha256,
                    thumbnail_sha256 FROM moment_media
                    WHERE user_id=? AND moment_id=?""",
                (owner, moment_id),
            ).fetchone()
        if not row:
            return None
        key = row["storage_key"] if variant == "image" else row["thumbnail_key"]
        mime = row["mime"] if variant == "image" else row["thumbnail_mime"]
        expected = row["sha256"] if variant == "image" else row["thumbnail_sha256"]
        path = self._path(key)
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            return None
        if sha256(data).hexdigest() != expected:
            raise ValueError("MEDIA_INTEGRITY_FAILED")
        suffix = Path(key).suffix.lower()
        return MediaContent(
            data=data,
            mime=mime,
            filename=f"{moment_id}-{variant}{suffix}",
            sha256=expected,
        )

    def _delete_rows(self, rows) -> int:
        keys = []
        for row in rows:
            keys.extend((row["storage_key"], row["thumbnail_key"]))
        for key in keys:
            self._remove(self._path(key))
        return len(rows)

    def delete_for_moment(self, owner: str, moment_id: str) -> int:
        with self.repository.connect() as db:
            rows = db.execute(
                """SELECT storage_key,thumbnail_key FROM moment_media
                WHERE user_id=? AND moment_id=?""",
                (owner, moment_id),
            ).fetchall()
            deleted = db.execute(
                "DELETE FROM moment_media WHERE user_id=? AND moment_id=?",
                (owner, moment_id),
            ).rowcount
        self._delete_rows(rows)
        return deleted

    def delete_many(self, owner: str, moment_ids: list[str]) -> int:
        deleted_total = 0
        for moment_id in dict.fromkeys(moment_ids):
            deleted_total += self.delete_for_moment(owner, moment_id)
        return deleted_total

    def delete_for_owner(self, owner: str) -> int:
        with self.repository.connect() as db:
            rows = db.execute(
                """SELECT storage_key,thumbnail_key FROM moment_media
                WHERE user_id=?""",
                (owner,),
            ).fetchall()
            deleted = db.execute(
                "DELETE FROM moment_media WHERE user_id=?", (owner,)
            ).rowcount
        self._delete_rows(rows)
        return deleted


def mime_allowed(declared_mime: str) -> bool:
    return normalize_mime(declared_mime) in ALLOWED_FORMATS.values()


__all__ = [
    "MediaContent",
    "MomentMediaStore",
    "ImageProviderError",
    "mime_allowed",
]
