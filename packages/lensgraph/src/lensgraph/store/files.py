"""Blob store over any fsspec filesystem: Parquet for frames, JSON for everything else, never pickle.

See documentation/design/core.md, Artifact store and run index.
"""

import importlib
import json
import os
import uuid
from pathlib import Path
from typing import Any

import fsspec.core
import numpy as np
import pandas as pd
from fsspec.implementations.local import LocalFileSystem
from pydantic import BaseModel

from ..hashing import content_hash
from .base import BlobStore

_ENVELOPE_KEYS = {"type", "data"}


def _encode(value: Any) -> Any:
    """Turn a value into JSON-native data, wrapping each pydantic model in a type envelope.

    Raises TypeError for anything that is not a model, a JSON primitive, or a list/dict
    (with string keys) of those.
    """
    if isinstance(value, BaseModel):
        cls = type(value)
        return {"type": f"{cls.__module__}:{cls.__qualname__}", "data": value.model_dump(mode="json")}
    if isinstance(value, np.generic):
        return _encode(value.item())
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, list):
        return [_encode(v) for v in value]
    if isinstance(value, dict):
        if not all(isinstance(k, str) for k in value):
            raise TypeError("FileBlobStore: dict keys must be strings")
        return {k: _encode(v) for k, v in value.items()}
    raise TypeError(f"FileBlobStore: unsupported type {type(value).__qualname__}")


def _import_model(path: str) -> type[BaseModel]:
    """Resolve a "<module>:<QualName>" envelope type to its pydantic model class."""
    module_name, qualname = path.split(":", 1)
    obj: Any = importlib.import_module(module_name)
    for part in qualname.split("."):
        obj = getattr(obj, part)
    if not (isinstance(obj, type) and issubclass(obj, BaseModel)):
        raise TypeError(f"FileBlobStore: {path} is not a pydantic model")
    return obj


def _decode(data: Any) -> Any:
    """Inverse of `_encode`: rebuild models from their envelopes, recursing into containers."""
    if isinstance(data, list):
        return [_decode(v) for v in data]
    if isinstance(data, dict):
        if data.keys() == _ENVELOPE_KEYS and isinstance(data["type"], str) and ":" in data["type"]:
            return _import_model(data["type"]).model_validate(data["data"])
        return {k: _decode(v) for k, v in data.items()}
    return data


class FsspecBlobStore(BlobStore):
    """BlobStore keeping blobs at `<root>/<hash[:2]>/<hash>.<ext>` on any fsspec filesystem.

    `url` is anything `fsspec.core.url_to_fs` resolves: `file://...`, `memory://...`, or
    `s3://bucket/prefix` (which needs `s3fs`, or the matching fsspec backend, installed);
    `storage_options` are passed through. Frames become `.parquet` (index, dtypes and
    empty-frame columns preserved); pydantic models, JSON primitives and lists/dicts of them
    become `.json`, with models wrapped in a `{"type": "<module>:<QualName>", "data": ...}`
    envelope. Other types raise TypeError. See documentation/design/core.md, Artifact store
    and run index.
    """

    def __init__(self, url: str, **storage_options: Any) -> None:
        self.fs, root = fsspec.core.url_to_fs(url, **storage_options)
        self.root: str = str(root).rstrip("/")

    def _path(self, h: str, ext: str) -> str:
        """Location of the blob for hash `h` with extension `ext`."""
        return f"{self.root}/{h[:2]}/{h}.{ext}"

    def _find(self, h: str) -> str | None:
        """Path of the stored blob for `h`, probing the two known extensions (no listing)."""
        for ext in ("parquet", "json"):
            path = self._path(h, ext)
            if self.fs.exists(path):
                return path
        return None

    def put(self, value: Any) -> str:
        """Store `value` and return `content_hash(value)`; a no-op if already stored."""
        h = content_hash(value)
        if self.has(h):
            return h
        if isinstance(value, pd.DataFrame):
            ext = "parquet"

            def write(f: Any) -> None:
                value.to_parquet(f, engine="pyarrow")

        else:
            ext = "json"
            payload = json.dumps(_encode(value)).encode()  # raises TypeError before any write

            def write(f: Any) -> None:
                f.write(payload)

        target = self._path(h, ext)
        self.fs.makedirs(f"{self.root}/{h[:2]}", exist_ok=True)
        # Local writes go via a temp file + move so readers never see a partial blob;
        # object-store PUTs are already atomic, so other filesystems write directly.
        atomic = isinstance(self.fs, LocalFileSystem)
        dest = f"{target}.{os.getpid()}.{uuid.uuid4().hex}.tmp" if atomic else target
        try:
            with self.fs.open(dest, "wb") as f:
                write(f)
            if atomic:
                self.fs.mv(dest, target)
        except Exception as exc:
            if self.fs.exists(dest):
                self.fs.rm(dest)
            if isinstance(value, pd.DataFrame):
                raise TypeError(f"FileBlobStore: cannot store frame: {exc}") from exc
            raise
        return h

    def get(self, h: str) -> Any:
        """Load the blob for hash `h`; KeyError if absent."""
        path = self._find(h)
        if path is None:
            raise KeyError(h)
        with self.fs.open(path, "rb") as f:
            if path.endswith(".parquet"):
                return pd.read_parquet(f, engine="pyarrow")
            return _decode(json.loads(f.read()))

    def has(self, h: str) -> bool:
        """Whether a blob with hash `h` is stored."""
        return self._find(h) is not None


class FileBlobStore(FsspecBlobStore):
    """FsspecBlobStore rooted at a local directory (the default on-disk store)."""

    def __init__(self, root: Path) -> None:
        super().__init__(f"file://{Path(root).resolve()}")
