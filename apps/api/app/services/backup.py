from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from .. import __version__
from ..config import get_settings
from ..models import BackupRecord


def _database_path() -> Path:
    database = make_url(get_settings().database_url).database
    if not database:
        raise RuntimeError("Backup is only available for file-backed SQLite")
    return Path(database).resolve()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def create_backup(session: Session, requested_by: str) -> BackupRecord:
    settings = get_settings()
    settings.ensure_directories()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    artifact_name = f"claim-power-house-{stamp}.cphbackup"
    artifact = (settings.data_root / "backups" / artifact_name).resolve()
    with tempfile.TemporaryDirectory(prefix="cph-backup-") as temporary:
        staging = Path(temporary)
        database_copy = staging / "claim_powerhouse.db"
        source = sqlite3.connect(_database_path())
        destination = sqlite3.connect(database_copy)
        try:
            source.backup(destination)
        finally:
            destination.close()
            source.close()
        manifest: dict[str, Any] = {
            "format": "cph-backup-1",
            "created_at": datetime.now(UTC).isoformat(),
            "application_version": __version__,
            "database_sha256": sha256_file(database_copy),
            "includes_chroma": settings.chroma_path.exists(),
        }
        (staging / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
        )
        with zipfile.ZipFile(artifact, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(database_copy, "db/claim_powerhouse.db")
            archive.write(staging / "manifest.json", "manifest.json")
            if settings.chroma_path.exists():
                for source_path in settings.chroma_path.rglob("*"):
                    if source_path.is_file():
                        archive.write(
                            source_path,
                            Path("chroma") / source_path.relative_to(settings.chroma_path),
                        )
    record = BackupRecord(
        artifact_name=artifact_name,
        artifact_hash=sha256_file(artifact),
        schema_revision="0002_operations",
        status="READY",
        size_bytes=artifact.stat().st_size,
        requested_by=requested_by,
    )
    session.add(record)
    session.commit()
    return record


def validate_backup(artifact_name: str) -> dict[str, Any]:
    settings = get_settings()
    artifact = (settings.data_root / "backups" / Path(artifact_name).name).resolve()
    backup_root = (settings.data_root / "backups").resolve()
    if artifact.parent != backup_root or not artifact.exists():
        raise FileNotFoundError("Backup not found")
    with zipfile.ZipFile(artifact) as archive:
        names = set(archive.namelist())
        if not {"manifest.json", "db/claim_powerhouse.db"}.issubset(names):
            raise ValueError("Invalid backup structure")
        manifest = json.loads(archive.read("manifest.json"))
        if manifest.get("format") != "cph-backup-1":
            raise ValueError("Unsupported backup format")
        database_bytes = archive.read("db/claim_powerhouse.db")
        actual = hashlib.sha256(database_bytes).hexdigest()
        if actual != manifest.get("database_sha256"):
            raise ValueError("Backup database hash mismatch")
    return {"artifact": artifact.name, "sha256": sha256_file(artifact), "manifest": manifest}


def restore_backup_offline(artifact_name: str) -> None:
    """Restore a validated backup. The API process must be stopped before calling this function."""
    validation = validate_backup(artifact_name)
    settings = get_settings()
    artifact = settings.data_root / "backups" / validation["artifact"]
    database_path = _database_path()
    with tempfile.TemporaryDirectory(prefix="cph-restore-") as temporary:
        staging = Path(temporary)
        with zipfile.ZipFile(artifact) as archive:
            archive.extractall(staging)
        database_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(staging / "db" / "claim_powerhouse.db", database_path)
        restored_chroma = staging / "chroma"
        if restored_chroma.exists():
            if settings.chroma_path.exists():
                shutil.rmtree(settings.chroma_path)
            shutil.copytree(restored_chroma, settings.chroma_path)
