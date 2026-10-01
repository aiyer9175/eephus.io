# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Nightly retention of the SERVED provisional grade (PV-02).

WHY THIS EXISTS. data/xfv_ungraded.json, the provisional grade for roster
players no source has graded, is gitignored since 2026-07-14 and rewritten by
every nightly rebuild, and trade_value_history holds routed rows only. So the
only record of what the site served was 19 git versions and one backup
(2026-06-23 to 2026-07-25), and the next scoring of the served grade against
first source grades would again depend on a backup file
(_finalpass_2026-09-24/provisional/PROVISIONAL_V2.md, defect D8, build item
PV-02).

WHAT IT KEEPS. One snapshot per artifact build date, the served fields only:
key, mlbam, side, level, age, grade (xfv_grade) and p_bust, plus p_g6 / p_g12
when the served artifact carries a probability of a first grade (it does not
yet; provisional v2 adds them). No WAR column, no label, nothing computed.

WHERE.
  .cache/provisional_history/<YYYY>/<generated_at>.json.gz   the snapshot
      (untracked, columnar, gzip; first write wins, never rewritten)
  .cache/provisional_history/digest.jsonl                     durable digest
  data/provisional_history/digest.json                        tracked digest
      (one small row per build date: hashes, counts, grade quantiles)

WHY THERE IS A SECOND, UNTRACKED DIGEST. The deploy box runs
`git checkout -- .` before every nightly pull (deploy/nightly-build.sh), which
reverts any tracked file the previous night wrote. Every digest row is also
appended to .cache/provisional_history/digest.jsonl (untracked, survives the
checkout), and retain() merges those rows back before it writes, as
efv_progress.py does for its ledger. The tracked file is the union; nothing
is dropped from either copy. test_provisional_retention.py replays a real
`git checkout -- .` against a scratch repository to pin this.

NOT SERVED. data/provisional_history/ sits at data/ depth two, which neither
deploy consumer ships (they name their data subdirectories one by one), and
.cache/ is never deployed.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import logging
import statistics
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("provisional_history")

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
SOURCE_PATH = DATA_DIR / "xfv_ungraded.json"
CACHE_DIR = ROOT / ".cache" / "provisional_history"
DIGEST_PATH = DATA_DIR / "provisional_history" / "digest.json"
SCHEMA = 1

#: The retained columns, in order. p_g6 / p_g12 stay null until the served
#: artifact carries them.
COLUMNS = ("key", "mlbam", "side", "level", "age", "grade", "p_bust", "p_g6", "p_g12")


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def rows_from_artifact(doc: dict) -> list[dict]:
    """The served fields of every row that carries a grade, in key order."""
    out = []
    for k, e in sorted((doc.get("by_player") or {}).items()):
        if not isinstance(e, dict) or e.get("xfv_grade") is None:
            continue
        out.append({"key": k, "mlbam": e.get("mlbam_id"), "side": e.get("side"),
                    "level": e.get("level"), "age": e.get("age"),
                    "grade": e.get("xfv_grade"), "p_bust": e.get("p_bust"),
                    "p_g6": e.get("p_g6"), "p_g12": e.get("p_g12")})
    return out


def canon_rows(rows: list[dict]) -> str:
    """sha256 of the rows, order-independent (the freeze files use the same form)."""
    return hashlib.sha256(json.dumps(sorted(rows, key=lambda r: str(r["key"])), sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def _q(vals: list[float], p: float):
    return vals[min(len(vals) - 1, int(p * (len(vals) - 1)))] if vals else None


def digest_row(rows: list[dict], *, date: str, artifact_sha256: str, snapshot: str,
               now_iso: str) -> dict:
    g = sorted(r["grade"] for r in rows)
    return {
        "date": date,
        "retained_at": now_iso,
        "artifact_sha256": artifact_sha256,
        "sha256_rows": canon_rows(rows),
        "n_rows": len(rows),
        "n_by_side": {s: sum(1 for r in rows if r.get("side") == s) for s in ("H", "P")},
        "grade": {"median": round(statistics.median(g), 1) if g else None,
                  "p90": _q(g, 0.90), "max": g[-1] if g else None},
        "n_grade_ge_35": sum(1 for x in g if x >= 35),
        "n_with_p_bust": sum(1 for r in rows if r.get("p_bust") is not None),
        "n_with_p_first_grade": sum(1 for r in rows if r.get("p_g12") is not None),
        "snapshot": snapshot,
    }


def write_snapshot(path: Path, rows: list[dict], head: dict) -> bool:
    """Columnar gzip snapshot. First write wins: an existing file is never
    rewritten. Returns True when this call wrote it."""
    path = Path(path)
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    body = dict(head, columns=list(COLUMNS), rows=[[r.get(c) for c in COLUMNS] for r in rows])
    tmp = path.with_name(path.name + ".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as fh:
        json.dump(body, fh, separators=(",", ":"))
    tmp.replace(path)
    return True


def load_snapshot(path: Path) -> tuple[dict, list[dict]]:
    """(head, rows) of a retained snapshot; refuses a file whose rows do not
    match the hash it was written with."""
    with gzip.open(Path(path), "rt", encoding="utf-8") as fh:
        body = json.load(fh)
    cols = body.pop("columns")
    rows = [dict(zip(cols, r)) for r in body.pop("rows")]
    if body.get("sha256_rows") and canon_rows(rows) != body["sha256_rows"]:
        raise ValueError(f"{path}: rows do not match their recorded hash")
    return body, rows


def _read_jsonl(path: Path) -> list[dict]:
    out = []
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return out
    for ln in text.splitlines():
        ln = ln.strip()
        if ln:
            try:
                out.append(json.loads(ln))
            except ValueError:
                log.warning("provisional_history: unreadable digest line skipped")
    return out


def _append_jsonl(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, sort_keys=True) + "\n")


def _row_id(r: dict) -> tuple:
    return (r.get("date"), r.get("sha256_rows"))


def merge_digest(tracked: list[dict], durable: list[dict]) -> list[dict]:
    """The union of both copies, one row per (date, rows hash), date order."""
    seen, out = set(), []
    for r in list(tracked) + list(durable):
        rid = _row_id(r)
        if rid in seen:
            continue
        seen.add(rid)
        out.append(r)
    return sorted(out, key=lambda r: (r.get("date") or "", r.get("retained_at") or ""))


def _write_digest(path: Path, rows: list[dict], now_iso: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "schema": SCHEMA,
        "generated_at": now_iso,
        "what": ("one row per build of data/xfv_ungraded.json (the served provisional grade); "
                 "the full rows live in the snapshot file each row names under "
                 ".cache/provisional_history/"),
        "producer": "provisional_history.py (run_monthly daily step d9a)",
        "rule": ("append-only; a row is added when a build date or its rows hash is new; the "
                 "untracked .cache/provisional_history/digest.jsonl copy is merged back so the "
                 "box's nightly git checkout cannot drop a row"),
        "columns": list(COLUMNS),
        "rows": rows,
    }
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def _paths(source, cache_dir, digest_path):
    return (Path(source) if source is not None else SOURCE_PATH,
            Path(cache_dir) if cache_dir is not None else CACHE_DIR,
            Path(digest_path) if digest_path is not None else DIGEST_PATH)


def load_digest(digest_path=None, cache_dir=None) -> list[dict]:
    """The merged digest rows (tracked file plus the durable copy)."""
    _, cache, dig = _paths(None, cache_dir, digest_path)
    try:
        tracked = json.loads(dig.read_text(encoding="utf-8")).get("rows") or []
    except (OSError, ValueError):
        tracked = []
    return merge_digest(tracked, _read_jsonl(cache / "digest.jsonl"))


def retain(source=None, *, cache_dir=None, digest_path=None, now_iso: str | None = None) -> dict:
    """Retain tonight's served artifact. Idempotent: a second run on the same
    build adds nothing. Returns a small status dict for the heartbeat."""
    src, cache, dig = _paths(source, cache_dir, digest_path)
    now_iso = now_iso or _now_iso()
    try:
        raw = src.read_bytes()
        doc = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError) as e:
        return {"status": f"no artifact: {type(e).__name__}", "appended": 0}
    date = str((doc.get("meta") or {}).get("generated_at") or "")[:10]
    if not date:
        return {"status": "artifact has no meta.generated_at", "appended": 0}
    rows = rows_from_artifact(doc)
    art_sha = hashlib.sha256(raw).hexdigest()
    rows_sha = canon_rows(rows)
    durable = _read_jsonl(cache / "digest.jsonl")
    try:
        tracked = json.loads(dig.read_text(encoding="utf-8")).get("rows") or []
    except (OSError, ValueError):
        tracked = []
    merged = merge_digest(tracked, durable)
    have = {_row_id(r) for r in merged}
    appended = []
    if (date, rows_sha) not in have:
        rel = f"{date[:4]}/{date}.json.gz"
        snap = cache / rel
        if snap.exists():
            # A second build on the same date with different rows: keep the
            # first file, name the later one by its hash prefix.
            rel = f"{date[:4]}/{date}_{rows_sha[:12]}.json.gz"
            snap = cache / rel
        write_snapshot(snap, rows, {"date": date, "artifact_sha256": art_sha,
                                    "sha256_rows": rows_sha, "retained_at": now_iso,
                                    "source": "data/xfv_ungraded.json"})
        row = digest_row(rows, date=date, artifact_sha256=art_sha, snapshot=rel, now_iso=now_iso)
        merged = merge_digest(merged, [row])
        appended.append(row)
    in_durable = {_row_id(r) for r in durable}
    _append_jsonl(cache / "digest.jsonl", [r for r in merged if _row_id(r) not in in_durable])
    _write_digest(dig, merged, now_iso)
    return {"status": "ok", "date": date, "appended": len(appended), "n_rows": len(rows),
            "n_digest_rows": len(merged)}


def summary_line(res: dict) -> str:
    if res.get("status") != "ok":
        return str(res.get("status"))[:120]
    return (f"{res.get('date')}: {res.get('n_rows')} rows, {res.get('appended')} digest row(s) "
            f"appended, {res.get('n_digest_rows')} total")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(summary_line(retain()))
