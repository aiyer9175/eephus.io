# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The forward vintage of the MLB projections: the preseason file, frozen once.

Registered in docs/PROJ_FORWARD_VINTAGE_GATE.md (owner answers M15-2 and M15-3,
2026-09-25). The served projections file is gitignored and rewritten every
night, so without a freeze there is no record of what the engine said before a
season started. The freeze is that record: the served file of the last nightly
before the first regular-season game, copied byte for byte, logged with its
sha256, committed by hand, and never re-taken.

  Folder    data/proj_forward_vintage/ (below data/ depth one, so neither deploy
            consumer ships it; evidence, not a page)
  Frozen    mlb_projections_<season>_preseason.json, byte-identical to the
            served file it was taken from
  Log       FREEZE_LOG.json, {"entries": [...]}, one entry per season. A
            `frozen` entry carries the file's sha256, its source, the first
            game, `label_provider` (the WAR series the projection bundle was
            trained on at freeze time, gate section 5 "The labels"), and an
            `extract` with its own `extract_sha256`. A `no_season`
            entry (no regular-season game was played) carries the dated
            amendment that recorded it and no file.

The extract is what a reader such as the Awards preseason reader needs, so it
can verify its numbers against the hash without parsing the whole payload:
  vets          mlbam, key, war0 (war[0]), warP10_0 (warP10[0]), warP90_0
                (warP90[0]), in file order
  team_outlook  team, wins0 (byYear[0].wins), in file order

Nothing here runs in the nightly. tools/freeze_proj_forward_vintage.py is the
only writer, and proj_export.assert_first_season_flip_allowed is the reader
that refuses to roll the first projected season past an unfrozen one.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
VINTAGE_DIR = DATA_DIR / "proj_forward_vintage"
#: The serving projection bundle's meta; its war_provider is the training label
#: the freeze log records (gate section 5 "The labels").
BUNDLE_META = Path(__file__).parent / "model" / "proj_lgbm" / "meta.json"
LOG_NAME = "FREEZE_LOG.json"
#: The first season the gate freezes. Nothing before it was ever saved, so the
#: flip guard asks for nothing earlier.
FIRST_FROZEN_SEASON = 2027
STATUSES = ("frozen", "no_season")


def frozen_name(season: int) -> str:
    return f"mlb_projections_{int(season)}_preseason.json"


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def _first(seq):
    return seq[0] if isinstance(seq, list) and seq else None


def extract(payload: dict) -> dict:
    """The fields a forward reader uses, read straight out of the payload."""
    vets = []
    for v in payload.get("vets") or []:
        vets.append({"mlbam": v.get("mlbam"), "key": v.get("key"),
                     "war0": _first(v.get("war")),
                     "warP10_0": _first(v.get("warP10")),
                     "warP90_0": _first(v.get("warP90"))})
    teams = []
    for t in payload.get("team_outlook") or []:
        by = t.get("byYear") or []
        teams.append({"team": t.get("team"),
                      "wins0": (by[0] or {}).get("wins") if by else None})
    return {"vets": vets, "team_outlook": teams}


def extract_sha256(ex: dict) -> str:
    return sha256_bytes(_canon(ex))


def load_log(vintage_dir: Path | None = None) -> dict:
    p = Path(vintage_dir or VINTAGE_DIR) / LOG_NAME
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"entries": []}
    if not isinstance(doc, dict) or not isinstance(doc.get("entries"), list):
        raise ValueError(f"{p} is not a freeze log ({{'entries': [...]}})")
    return doc


def entry_problems(entry: dict, vintage_dir: Path | None = None) -> list[str]:
    """Why a log entry does not verify, or [] when it does."""
    d = Path(vintage_dir or VINTAGE_DIR)
    season = entry.get("season")
    status = entry.get("status")
    if status not in STATUSES:
        return [f"{season}: status {status!r} is not one of {STATUSES}"]
    if status == "no_season":
        amend = entry.get("amendment")
        return [] if isinstance(amend, str) and amend.strip() else [
            f"{season}: a no_season entry must name its dated amendment"]
    out = []
    f = d / str(entry.get("file") or "")
    if entry.get("file") != frozen_name(season):
        out.append(f"{season}: file {entry.get('file')!r} is not {frozen_name(season)!r}")
    if not f.is_file():
        return out + [f"{season}: frozen file {f.name} is missing"]
    raw = f.read_bytes()
    if sha256_bytes(raw) != entry.get("sha256"):
        out.append(f"{season}: {f.name} does not match its logged sha256")
    ex = entry.get("extract")
    if extract_sha256(ex or {}) != entry.get("extract_sha256"):
        out.append(f"{season}: the extract does not match its logged extract_sha256")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except ValueError:
        return out + [f"{season}: {f.name} is not JSON"]
    if extract(payload) != ex:
        out.append(f"{season}: the extract differs from the fields of {f.name}")
    if payload.get("first_season") != season:
        out.append(f"{season}: {f.name} has first_season {payload.get('first_season')}")
    return out


def on_record(season: int, vintage_dir: Path | None = None) -> tuple[bool, str]:
    """(True, "") when `season` has a verifying frozen or no_season entry."""
    try:
        entries = [e for e in load_log(vintage_dir)["entries"]
                   if e.get("season") == int(season)]
    except ValueError as e:
        return False, str(e)
    if not entries:
        return False, f"no freeze log entry for {season}"
    if len(entries) > 1:
        return False, f"{len(entries)} freeze log entries for {season}; the freeze is write-once"
    probs = entry_problems(entries[0], vintage_dir)
    return (not probs), "; ".join(probs)


def freeze_problems(payload: dict, season: int, first_game_date: str) -> list[str]:
    """F2 preconditions 1-3 of the gate, on the payload about to be frozen."""
    out = []
    if payload.get("first_season") != season:
        out.append(f"first_season is {payload.get('first_season')}, not {season}")
    if payload.get("horizon") != 5:
        out.append(f"horizon is {payload.get('horizon')}, not 5")
    gen = str(payload.get("generated_at") or "")[:10]
    try:
        if date.fromisoformat(gen) > date.fromisoformat(first_game_date):
            out.append(f"generated_at {gen} is after the first game ({first_game_date})")
    except ValueError:
        out.append(f"generated_at {gen!r} or first game date {first_game_date!r} is not an ISO date")
    vets = payload.get("vets") or []
    if not vets:
        out.append("no vets rows")
    bad = [v.get("key") for v in vets
           if v.get("mlbam") is None or not all(
               isinstance(v.get(k), list) and v.get(k) for k in ("war", "warP10", "warP90"))]
    if bad:
        out.append(f"{len(bad)} vets rows lack mlbam, war, warP10 or warP90 (first: {bad[:3]})")
    teams = payload.get("team_outlook") or []
    if not teams:
        out.append("no team_outlook rows")
    tbad = [t.get("team") for t in teams
            if not (t.get("byYear") and (t["byYear"][0] or {}).get("wins") is not None)]
    if tbad:
        out.append(f"{len(tbad)} team_outlook rows lack byYear[0].wins ({tbad[:3]})")
    return out


def freeze(season: int, source: Path, *, first_game_pk: int, first_game_date: str,
           source_label: str, vintage_dir: Path | None = None,
           frozen_at: str | None = None, label_provider: str | None = None) -> dict:
    """Copy `source` byte for byte into the folder and append its log entry.

    `label_provider` is the WAR series the frozen projection was trained on; when
    it is not given it is read from the serving bundle's meta (BUNDLE_META
    war_provider), and the freeze refuses when neither names one.

    Write-once: refuses when the season already has any entry or file. Refuses
    on any F2 precondition. Returns the entry it appended."""
    d = Path(vintage_dir or VINTAGE_DIR)
    season = int(season)
    raw = Path(source).read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    probs = freeze_problems(payload, season, first_game_date)
    log = load_log(d)
    if any(e.get("season") == season for e in log["entries"]):
        probs.append(f"{season} already has a freeze log entry; the freeze is write-once")
    target = d / frozen_name(season)
    if target.exists():
        probs.append(f"{target.name} already exists; the freeze is write-once")
    if not label_provider:
        try:
            label_provider = json.loads(BUNDLE_META.read_text(encoding="utf-8")).get("war_provider")
        except (OSError, ValueError):
            label_provider = None
    if not label_provider:
        probs.append("no training label: pass label_provider or keep war_provider in "
                     f"{BUNDLE_META.name}")
    if probs:
        raise ValueError("freeze refused: " + "; ".join(probs))
    ex = extract(payload)
    entry = {
        "season": season,
        "status": "frozen",
        "file": target.name,
        "sha256": sha256_bytes(raw),
        "bytes": len(raw),
        "source": str(source_label),
        "source_generated_at": payload.get("generated_at"),
        "first_game": {"gamePk": int(first_game_pk), "gameDate": str(first_game_date)},
        "frozen_at": frozen_at or date.today().isoformat(),
        "gate": "docs/PROJ_FORWARD_VINTAGE_GATE.md",
        "label_provider": str(label_provider),
        "n_vets": len(ex["vets"]),
        "n_team_outlook": len(ex["team_outlook"]),
        "extract_sha256": extract_sha256(ex),
        "extract": ex,
    }
    d.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    log["entries"].append(entry)
    (d / LOG_NAME).write_bytes(
        (json.dumps(log, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
    return entry


def check(vintage_dir: Path | None = None) -> list[str]:
    """Every problem across the log; [] when every entry verifies."""
    out = []
    seen = set()
    for e in load_log(vintage_dir)["entries"]:
        if e.get("season") in seen:
            out.append(f"{e.get('season')}: more than one entry")
        seen.add(e.get("season"))
        out += entry_problems(e, vintage_dir)
    return out
