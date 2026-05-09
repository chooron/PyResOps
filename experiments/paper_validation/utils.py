"""Common utilities for paper-validation runs."""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from subprocess import CompletedProcess, run
from typing import Any


def utc_now_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")


def sha256_file(path: str | Path) -> str:
    resolved = Path(path)
    digest = hashlib.sha256()
    with resolved.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_jsonable(payload: Any) -> str:
    if is_dataclass(payload):
        payload = asdict(payload)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def git_commit_hash(workdir: str | Path = ".") -> str | None:
    proc: CompletedProcess[str] = run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(workdir),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def write_json(path: str | Path, payload: Any) -> Path:
    resolved = Path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return resolved


def write_markdown(path: str | Path, text: str) -> Path:
    resolved = Path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(text, encoding="utf-8")
    return resolved


def load_manifest_rows(path: str | Path) -> list[dict[str, str]]:
    resolved = Path(path)
    if not resolved.exists():
        return []
    with resolved.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))
