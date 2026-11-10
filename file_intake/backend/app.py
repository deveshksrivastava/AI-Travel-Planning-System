"""File-intake backend: chunked, size-limited, type-checked uploads.

Flow (all JSON except the chunk body):
  1. POST /api/uploads                     {filename, size, source_format}
        -> checks extension + declared size against the format limit
        -> returns {upload_id, chunk_size, total_chunks}
  2. PUT  /api/uploads/{id}/chunks/{index}  raw bytes (application/octet-stream)
        -> streamed to disk; rejected the moment it exceeds the chunk size
           or would make the file larger than declared
  3. POST /api/uploads/{id}/complete
        -> verifies byte count, sniffs magic bytes / text, computes SHA-256,
           moves the file into storage and returns its metadata
  DELETE /api/uploads/{id} aborts and cleans up.

Why chunked: reverse proxies and PaaS front doors cap a *single request*
(nginx 1 MB default, IIS/App Service ~28.6 MB, Kestrel 30 MB, API Gateway
10 MB...). Small chunks keep every request under those caps, so the per-format
limit in formats.py is the only limit users meet.

Run:  uvicorn file_intake.backend.app:app --reload   (from repo root)
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .formats import FORMATS, HARD_CAP_BYTES, MB, FileFormat

UPLOAD_ROOT = Path(os.getenv("UPLOAD_ROOT", "./file_intake_data")).resolve()
STAGING = UPLOAD_ROOT / "_staging"
CHUNK_SIZE = int(os.getenv("UPLOAD_CHUNK_SIZE", str(8 * MB)))
SESSION_TTL_SECONDS = int(os.getenv("UPLOAD_SESSION_TTL", str(24 * 3600)))
FRONTEND = Path(__file__).resolve().parent.parent / "frontend" / "index.html"

SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass
class Session:
    id: str
    filename: str
    fmt: FileFormat
    size: int
    total_chunks: int
    received: int = 0
    next_index: int = 0
    created: float = field(default_factory=time.time)
    lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def path(self) -> Path:
        return STAGING / f"{self.id}.part"


# In-memory session table. Swap for Redis/Postgres when running >1 worker.
SESSIONS: dict[str, Session] = {}

app = FastAPI(title="File Intake")


class InitRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    size: int = Field(ge=1)
    source_format: str


def _human(n: int) -> str:
    return f"{n / (1024 * MB):.1f} GB" if n >= 1024 * MB else f"{n / MB:.0f} MB"


def _get(upload_id: str) -> Session:
    s = SESSIONS.get(upload_id)
    if not s:
        raise HTTPException(404, "Unknown or expired upload_id.")
    return s


def _purge_expired() -> None:
    cutoff = time.time() - SESSION_TTL_SECONDS
    for sid in [k for k, s in SESSIONS.items() if s.created < cutoff]:
        SESSIONS.pop(sid).path.unlink(missing_ok=True)


def sniff(path: Path, fmt: FileFormat) -> str | None:
    """Return an error message if the content doesn't look like ``fmt``."""
    with path.open("rb") as fh:
        head = fh.read(8192)
        if fmt.kind == "binary":
            if not any(head.startswith(m) for m in fmt.magic):
                return f"File content is not a valid {fmt.label} (signature mismatch)."
            if fmt.value == "parquet-parquet":
                fh.seek(-4, os.SEEK_END)
                if fh.read(4) != b"PAR1":
                    return "Parquet footer missing - file is truncated or corrupt."
            return None
    # text formats
    if b"\x00" in head:
        return f"{fmt.label} must be a text file (binary content found)."
    text = head.lstrip(b"\xef\xbb\xbf")
    try:
        decoded = text.decode("utf-8")
    except UnicodeDecodeError as e:
        if e.start < len(text) - 4:  # a multibyte char cut at the 8 KB edge is fine
            return f"{fmt.label} must be UTF-8 encoded."
        decoded = text[: e.start].decode("utf-8")
    first = decoded.lstrip()[:1]
    if fmt.text_starts and first not in fmt.text_starts:
        return f"{fmt.label} should start with {' or '.join(fmt.text_starts)!r}."
    return None


@app.get("/")
def index() -> FileResponse:
    return FileResponse(FRONTEND)


@app.get("/api/formats")
def list_formats() -> dict:
    return {
        "chunk_size": CHUNK_SIZE,
        "hard_cap_bytes": HARD_CAP_BYTES,
        "formats": [f.public() for f in FORMATS.values()],
    }


@app.post("/api/uploads", status_code=201)
def init_upload(req: InitRequest) -> dict:
    _purge_expired()
    fmt = FORMATS.get(req.source_format)
    if not fmt:
        raise HTTPException(422, "Choose a format.")
    ext = req.filename.rsplit(".", 1)[-1].lower() if "." in req.filename else ""
    if ext != fmt.extension:
        raise HTTPException(422, f"{fmt.label} expects a .{fmt.extension} file, got '.{ext or '?'}'.")
    if req.size > fmt.max_bytes:
        raise HTTPException(413, f"{fmt.label} files are limited to {_human(fmt.max_bytes)} "
                                 f"(this one is {_human(req.size)}).")
    STAGING.mkdir(parents=True, exist_ok=True)
    total = -(-req.size // CHUNK_SIZE)
    s = Session(uuid.uuid4().hex, req.filename, fmt, req.size, total)
    s.path.touch()
    SESSIONS[s.id] = s
    return {"upload_id": s.id, "chunk_size": CHUNK_SIZE, "total_chunks": total}


@app.put("/api/uploads/{upload_id}/chunks/{index}")
async def put_chunk(upload_id: str, index: int, request: Request) -> dict:
    s = _get(upload_id)
    if not s.lock.acquire(blocking=False):
        raise HTTPException(409, "Another chunk for this upload is in flight.")
    try:
        if index < s.next_index:  # client retry of a chunk we already have
            return {"received": s.received, "next_index": s.next_index}
        if index != s.next_index:
            raise HTTPException(409, f"Expected chunk {s.next_index}, got {index}.")
        expected = min(CHUNK_SIZE, s.size - index * CHUNK_SIZE)
        written = 0
        with s.path.open("r+b") as fh:
            fh.seek(index * CHUNK_SIZE)
            async for part in request.stream():
                written += len(part)
                if written > expected:
                    raise HTTPException(413, "Chunk larger than allowed.")
                fh.write(part)
            fh.truncate(index * CHUNK_SIZE + written)
        if written != expected:
            raise HTTPException(400, f"Chunk {index} incomplete ({written}/{expected} bytes); retry it.")
        s.received = index * CHUNK_SIZE + written
        s.next_index = index + 1
        return {"received": s.received, "next_index": s.next_index}
    finally:
        s.lock.release()


@app.post("/api/uploads/{upload_id}/complete")
def complete(upload_id: str) -> dict:
    s = _get(upload_id)
    if s.received != s.size:
        raise HTTPException(400, f"Upload incomplete: {s.received}/{s.size} bytes received.")
    err = sniff(s.path, s.fmt)
    if err:
        SESSIONS.pop(s.id, None)
        s.path.unlink(missing_ok=True)
        raise HTTPException(415, err)

    sha = hashlib.sha256()
    with s.path.open("rb") as fh:
        for block in iter(lambda: fh.read(MB), b""):
            sha.update(block)

    dest_dir = UPLOAD_ROOT / s.fmt.value
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{s.id}_{SAFE_NAME.sub('_', s.filename)[-150:]}"
    shutil.move(s.path, dest)
    SESSIONS.pop(s.id, None)
    return {
        "upload_id": s.id,
        "source_format": s.fmt.value,
        "filename": s.filename,
        "size": s.size,
        "sha256": sha.hexdigest(),
        "stored_at": str(dest.relative_to(UPLOAD_ROOT)),
    }


@app.delete("/api/uploads/{upload_id}", status_code=204)
def abort(upload_id: str) -> None:
    s = SESSIONS.pop(upload_id, None)
    if s:
        s.path.unlink(missing_ok=True)
