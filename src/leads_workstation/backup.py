from __future__ import annotations

import hashlib
import os
import sqlite3
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .secrets import resolve_secret
from .storage import is_postgres_target

MAGIC = b"CLWV2ENC1"
NONCE_BYTES = 12


def _key(secret_ref: str) -> bytes:
    secret = resolve_secret(secret_ref)
    return hashlib.sha256(secret.encode("utf-8")).digest()


def encrypt_file(source: str | Path, destination: str | Path, secret_ref: str) -> dict:
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as exc:
        raise RuntimeError("encrypted backups require the production/crypto extra") from exc
    src = Path(source)
    dst = Path(destination)
    data = src.read_bytes()
    nonce = os.urandom(NONCE_BYTES)
    encrypted = AESGCM(_key(secret_ref)).encrypt(nonce, data, MAGIC)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(MAGIC + nonce + encrypted)
    return {
        "path": str(dst.resolve()),
        "bytes": dst.stat().st_size,
        "sha256": hashlib.sha256(dst.read_bytes()).hexdigest(),
        "encrypted": True,
    }


def decrypt_file(source: str | Path, destination: str | Path, secret_ref: str) -> dict:
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as exc:
        raise RuntimeError("encrypted backups require the production/crypto extra") from exc
    src = Path(source)
    blob = src.read_bytes()
    if not blob.startswith(MAGIC) or len(blob) <= len(MAGIC) + NONCE_BYTES:
        raise ValueError("not a Leads Workstation V2 encrypted backup")
    offset = len(MAGIC)
    nonce = blob[offset : offset + NONCE_BYTES]
    ciphertext = blob[offset + NONCE_BYTES :]
    clear = AESGCM(_key(secret_ref)).decrypt(nonce, ciphertext, MAGIC)
    dst = Path(destination)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(clear)
    return {
        "path": str(dst.resolve()),
        "bytes": dst.stat().st_size,
        "sha256": hashlib.sha256(clear).hexdigest(),
        "encrypted": False,
    }


def _sqlite_snapshot(db_path: str | Path, output: Path) -> None:
    source = sqlite3.connect(Path(db_path))
    try:
        target = sqlite3.connect(output)
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()


def _postgres_dump(dsn: str, output: Path) -> None:
    parsed = urlsplit(dsn)
    if not parsed.hostname or not parsed.path.lstrip("/"):
        raise ValueError("invalid PostgreSQL DSN")
    env = os.environ.copy()
    if parsed.password:
        env["PGPASSWORD"] = unquote(parsed.password)
    command = [
        "pg_dump",
        "--format=custom",
        "--no-owner",
        "--no-acl",
        "--host",
        parsed.hostname,
        "--port",
        str(parsed.port or 5432),
        "--username",
        unquote(parsed.username or ""),
        "--file",
        str(output),
        parsed.path.lstrip("/"),
    ]
    subprocess.run(command, check=True, env=env, stdout=subprocess.DEVNULL)


def create_encrypted_backup(
    db_target: str | Path,
    destination: str | Path,
    secret_ref: str,
) -> dict:
    with tempfile.TemporaryDirectory() as td:
        clear = Path(td) / ("database.dump" if is_postgres_target(db_target) else "database.sqlite")
        if is_postgres_target(db_target):
            _postgres_dump(str(db_target), clear)
            kind = "postgresql-custom"
        else:
            _sqlite_snapshot(db_target, clear)
            kind = "sqlite"
        result = encrypt_file(clear, destination, secret_ref)
        result["database_kind"] = kind
        return result
