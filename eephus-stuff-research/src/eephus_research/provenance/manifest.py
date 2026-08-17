"""Artifact manifests (docs/DATA_GOVERNANCE.md, Part P) and the production-boundary guard.

Every consequential output should be reproducible from upstream artifacts and
content-addressable -- do not rely on modification time alone as proof of
data identity.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ProductionPathError(RuntimeError):
    """Raised when a write is attempted against a path in the frozen production boundary."""


# Mirrors config/research.yaml's production_boundary.frozen_paths. Kept in
# code (not just YAML) so the guard works even if the caller never loaded
# config -- a hard-coded safety net, not the single source of truth for
# documentation purposes (research.yaml remains that).
_FROZEN_PATH_FRAGMENTS = (
    "defense-plus",
    "swing-plus",
    "milb-decision-plus",
    "playing-time-model",
    "xRV models",
    "advancement_pace",
    "milb-projections",
    "prospect-tracker",
    "xwoba_model.pkl",
    "NCAA 26 Averages S+.csv",
)


def assert_not_production_path(path: str | Path) -> None:
    """Raise ProductionPathError if `path` looks like it targets a frozen production path.

    This is a defensive check, not a substitute for review -- it catches the
    obvious case (a write inside a known production directory name) and
    nothing more subtle.
    """
    resolved = str(Path(path).as_posix())
    for fragment in _FROZEN_PATH_FRAGMENTS:
        if fragment in resolved:
            raise ProductionPathError(
                f"Refusing to write to '{path}': matches frozen production "
                f"path fragment '{fragment}'. See docs/DATA_GOVERNANCE.md."
            )


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def config_hash(config: dict[str, Any]) -> str:
    """Deterministic hash of a config dict, independent of key ordering."""
    canonical = json.dumps(config, sort_keys=True, default=str)
    return sha256_bytes(canonical.encode("utf-8"))


@dataclass
class ManifestEntry:
    path: str
    size_bytes: int
    modification_time: str
    sha256: str
    producer: str
    producer_version: str
    parent_artifacts: list[str] = field(default_factory=list)
    execution_timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    configuration_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_manifest_entry(
    path: str | Path,
    producer: str,
    producer_version: str,
    parent_artifacts: list[str] | None = None,
    config: dict[str, Any] | None = None,
) -> ManifestEntry:
    """Build a manifest entry for an artifact that already exists on disk.

    Does not write anything -- the caller decides where/whether to persist
    this (see write_manifest below). Refuses to build an entry for a path
    inside the production boundary.
    """
    assert_not_production_path(path)
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Cannot manifest a nonexistent artifact: {p}")
    stat = p.stat()
    return ManifestEntry(
        path=str(p.as_posix()),
        size_bytes=stat.st_size,
        modification_time=datetime.fromtimestamp(
            stat.st_mtime, tz=timezone.utc
        ).isoformat(),
        sha256=sha256_file(p),
        producer=producer,
        producer_version=producer_version,
        parent_artifacts=parent_artifacts or [],
        configuration_hash=config_hash(config) if config is not None else None,
    )


def write_manifest(entries: list[ManifestEntry], out_path: str | Path) -> None:
    assert_not_production_path(out_path)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        json.dump([e.to_dict() for e in entries], fh, indent=2, sort_keys=True)


def load_manifest(path: str | Path) -> list[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as fh:
        return json.load(fh)


def diff_against_baseline(
    current: dict[str, Any], baseline: dict[str, Any]
) -> dict[str, Any]:
    """Compare a current manifest entry against a frozen baseline (Part AY).

    Returns byte_identical plus the specific fields that changed, rather
    than a single opaque boolean -- a reviewer should be able to see *what*
    changed without re-deriving it.
    """
    byte_identical = current.get("sha256") == baseline.get("sha256")
    changed_fields = {
        key: {"baseline": baseline.get(key), "current": current.get(key)}
        for key in set(baseline) | set(current)
        if baseline.get(key) != current.get(key)
    }
    return {"byte_identical": byte_identical, "changed_fields": changed_fields}
