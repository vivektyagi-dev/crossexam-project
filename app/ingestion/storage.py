"""File storage: local folder for development, Cloud Storage on GCP.

Files are content-addressed (`raw/<sha256>/<name>`), so re-uploading identical bytes
overwrites with identical bytes and never creates a second copy.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Protocol

from app.config import settings


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Storage(Protocol):
    def put(self, path: str, data: bytes, content_type: str = "application/octet-stream") -> str: ...
    def get(self, path: str) -> bytes: ...


class LocalStorage:
    def __init__(self, root: str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, path: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return path

    def get(self, path: str) -> bytes:
        return (self.root / path).read_bytes()


class GCSStorage:
    def __init__(self, bucket: str):
        from google.cloud import storage  # imported lazily: not needed locally

        self.bucket = storage.Client().bucket(bucket)

    def put(self, path: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        blob = self.bucket.blob(path)
        blob.upload_from_string(data, content_type=content_type)
        return path

    def get(self, path: str) -> bytes:
        return self.bucket.blob(path).download_as_bytes()


_storage: Storage | None = None


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        if settings.storage_backend == "gcs":
            _storage = GCSStorage(settings.gcs_bucket)
        else:
            _storage = LocalStorage(settings.local_storage_dir)
    return _storage


def raw_path(file_hash: str, filename: str) -> str:
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in filename)[-120:]
    return f"raw/{file_hash}/{safe}"
