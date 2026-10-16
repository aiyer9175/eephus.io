# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The Will drop seam: SDR (defense) and pitcher eWAR intake (W0, 2026-08-18).

WHY THIS EXISTS. The 2026-08-16 SDR/eWAR master plan gates every measurement
wave on Will's data drop. What is in the repo today is his METHOD stack
(defense-plus/ pipelines, milb-projections/ contracts + adapters + fixtures)
and NOT his data: no parquet, no raw inputs, no handoff directory, and
defense-plus has no export adapter at all (its card writes to ~/swing_plus/
on his machine). This module is the receiving end, built and tested against
his own contract fixtures BEFORE any data exists, so the day a drop lands the
census is one command and nothing is improvised.

STREAMS.
  pitcher_ewar_mlb, pitcher_ewar_milb_aaa, pitcher_ewar_milb_aa_higha:
      required columns come from Will's OWN contract
      (milb-projections/contracts/pitcher_ewar.schema.json). This module
      never restates his schema; his file is the authority and a drift in it
      is a drift we want to inherit loudly.
  sdr_defense_card:
      defense-plus publishes no contract (2026-08-18), so the contract is
      DECLARED HERE (DEFENSE_CARD_CONTRACT) and the intake request doc asks
      Will to adopt or amend it. One rule is load-bearing: a defense drop
      whose only signal is a range/OAA-class blend is REFUSED for the
      ewar_merged purpose, because the OAA/rfield blend is a settled loss and
      the w-grid re-open clause at ewar.py:806-812 names components beyond
      range (arm, framing, blocking, the DP pivot) as the condition. The
      refusal names that clause.

DROP LOCATION. data/drops/wills/<stream>__<YYYY-MM-DD>.(parquet|csv), the
cards drop-dir precedent. Acceptance never rewrites the file: it appends a
ledger row (sha256, rows, coverage, stamp) to data/sdr_intake_manifest.json
and writes the census artifact data/sdr_census.json FIRST, per the D-2
discipline (the census fixes the frame before any clause is measured).

IDENTITY. player_id is treated as mlbam and verified against prospects.db
players. Misses are REPORTED with a name-based alias suggestion; nothing is
ever auto-bound by name (the bind_player_ids trap).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sqlite3
from datetime import date
from pathlib import Path

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
DROPS_DIR = ROOT / "data" / "drops" / "wills"
MANIFEST_PATH = ROOT / "data" / "sdr_intake_manifest.json"
CENSUS_PATH = ROOT / "data" / "sdr_census.json"
WILLS_CONTRACT = (ROOT.parent / "milb-projections" / "contracts"
                  / "pitcher_ewar.schema.json")
DB_PATH = ROOT / "prospects.db"

# Streams whose schema authority is Will's contract file, keyed to the
# artifact name inside it.
EWAR_STREAMS = {
    "pitcher_ewar_mlb": "mlb_pitcher_ewar",
    "pitcher_ewar_milb_aaa": "milb_pitcher_ewar_aaa",
    "pitcher_ewar_milb_aa_higha": "milb_pitcher_ewar_aa_higha",
}

# The declared defense contract (2026-08-18). Adopt-or-amend is Will's call;
# the required core is the minimum any census or gate can stand on.
DEFENSE_CARD_CONTRACT = {
    "stream": "sdr_defense_card",
    "primary_key": ["player_id", "season", "primary_position"],
    "required_columns": [
        "player_id", "season", "primary_position", "innings", "sdr_runs",
    ],
    # Component columns: any subset may be present, but at least one
    # NON-RANGE component must exist somewhere in the file or the drop is
    # refused for the merge purpose (ewar.py:806-812).
    "component_columns": [
        "range_runs", "arm_runs", "framing_runs", "blocking_runs", "dp_runs",
    ],
    "context_columns": [
        "level", "team", "as_of_date", "sdr_runs_sd", "reliability",
        "player_name",
    ],
    "non_range_components": ["arm_runs", "framing_runs", "blocking_runs",
                             "dp_runs"],
}

STREAMS = tuple(EWAR_STREAMS) + (DEFENSE_CARD_CONTRACT["stream"],)


# ---------------------------------------------------------------------------
# contract resolution
# ---------------------------------------------------------------------------

def contract_for(stream: str) -> dict:
    """The schema authority for a stream: Will's contract file for the eWAR
    streams, the declared defense contract for the defense card."""
    if stream == DEFENSE_CARD_CONTRACT["stream"]:
        return DEFENSE_CARD_CONTRACT
    art = EWAR_STREAMS.get(stream)
    if art is None:
        raise ValueError(f"unknown stream {stream!r}; streams are {STREAMS}")
    doc = json.loads(WILLS_CONTRACT.read_text(encoding="utf-8"))
    spec = (doc.get("artifacts") or {}).get(art)
    if not spec:
        raise ValueError(
            f"Will's contract {WILLS_CONTRACT.name} carries no artifact "
            f"{art!r}; the contract file moved under us and this module "
            "must not guess")
    return {
        "stream": stream,
        "primary_key": spec.get("primary_key") or ["player_id", "season"],
        "required_columns": spec.get("required_columns") or [],
        "context_columns": (spec.get("label_columns") or [])
        + (spec.get("context_columns") or []),
        "component_columns": [],
        "non_range_components": [],
    }


# ---------------------------------------------------------------------------
# loading
# ---------------------------------------------------------------------------

def _read(path: Path):
    import pandas as pd
    p = Path(path)
    if p.suffix.lower() == ".parquet":
        return pd.read_parquet(p)
    if p.suffix.lower() == ".csv":
        return pd.read_csv(p)
    raise ValueError(f"{p.name}: only .parquet and .csv drops are accepted")


def _mlbam_set(db_path: Path = DB_PATH) -> set[int]:
    """Every mlbam the identity layer knows. Empty set when the DB is absent
    (CI), which downgrades the identity check to 'not checkable', never to a
    false pass."""
    if not Path(db_path).exists():
        return set()
    con = sqlite3.connect(str(db_path))
    try:
        # The live players table is keyed by player_key and carries no mlbam
        # column (found 2026-10-15 by the first real drop: the original query
        # raised OperationalError). The mlbam id lives in player_photos and
        # mlb_trade_players (storage.load_mlbam_player_keys reads the first);
        # a players.mlbam column, where a database has one, is read too.
        sources = (("players", "mlbam"), ("player_photos", "mlbam_id"),
                   ("mlb_trade_players", "mlbam_id"))
        out: set[int] = set()
        for table, col in sources:
            cols = {r[1] for r in con.execute(f"pragma table_info({table})")}
            if col not in cols:
                continue
            for (v,) in con.execute(
                    f"select distinct {col} from {table} where {col} is not null"):
                try:
                    out.add(int(v))
                except (TypeError, ValueError):
                    continue
        return out
    finally:
        con.close()


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------

def validate(path: Path, stream: str, *, db_path: Path = DB_PATH) -> dict:
    """Preflight one drop file. Never writes anything.

    Returns {ok, stream, rows, problems: [...], warnings: [...],
    census: {...}} where `problems` is the refusal list (any entry means the
    drop is not acceptable) and `warnings` are stated facts that do not
    block."""
    import pandas as pd
    spec = contract_for(stream)
    out: dict = {"ok": False, "stream": stream, "path": str(path),
                 "rows": 0, "problems": [], "warnings": [], "census": {}}
    try:
        df = _read(Path(path))
    except Exception as exc:  # noqa: BLE001
        out["problems"].append(f"unreadable: {exc}")
        return out
    out["rows"] = int(len(df))
    if not len(df):
        out["problems"].append("empty drop")
        return out

    missing = [c for c in spec["required_columns"] if c not in df.columns]
    if missing:
        out["problems"].append(f"missing required columns: {missing}")

    pk = [c for c in spec["primary_key"] if c in df.columns]
    if len(pk) == len(spec["primary_key"]):
        dupes = int(df.duplicated(subset=pk).sum())
        if dupes:
            out["problems"].append(
                f"{dupes} duplicate row(s) on primary key {pk}")

    if "season" in df.columns:
        seasons = pd.to_numeric(df["season"], errors="coerce")
        bad = int((~seasons.between(1990, date.today().year + 1)).sum())
        if bad:
            out["problems"].append(
                f"{bad} row(s) with implausible season values")

    # Null rates on required columns are stated facts, blocking only when a
    # required column is entirely null (present-but-empty is a schema lie).
    for c in spec["required_columns"]:
        if c in df.columns:
            nulls = int(df[c].isna().sum())
            if nulls == len(df):
                out["problems"].append(f"required column {c} is entirely null")
            elif nulls:
                out["warnings"].append(f"{c}: {nulls} null(s)")

    # The merge-purpose refusal: a defense drop with no non-range component
    # anywhere is the banned blend class in a new costume.
    if stream == DEFENSE_CARD_CONTRACT["stream"]:
        present = [c for c in spec["non_range_components"] if c in df.columns]
        live = [c for c in present if df[c].notna().any()]
        if not live:
            out["problems"].append(
                "no non-range component column carries data (need one of "
                f"{spec['non_range_components']}): a range-only blend is the "
                "settled OAA/rfield loss and cannot re-open the w-grid "
                "(ewar.py:806-812)")
        if "as_of_date" not in df.columns:
            out["warnings"].append(
                "no as_of_date column: rows cannot be vintage-stamped and "
                "any forward use must treat the file date as the vintage")

    # Identity: report, never bind.
    known = _mlbam_set(db_path)
    if "player_id" in df.columns:
        ids = pd.to_numeric(df["player_id"], errors="coerce").dropna()
        ids = ids.astype(int)
        if known:
            miss = sorted(set(ids) - known)
            out["census"]["identity"] = {
                "distinct_ids": int(ids.nunique()),
                "resolved_mlbam": int(ids.nunique() - len(miss)),
                "unresolved": len(miss),
                "unresolved_sample": miss[:20],
            }
            # Unresolved identity is a warning, not a refusal: MiLB streams
            # legitimately carry ids the players table has not seen yet.
            if miss:
                out["warnings"].append(
                    f"{len(miss)} of {ids.nunique()} distinct player_id "
                    "values do not resolve to a known mlbam (reported, "
                    "never auto-bound by name)")
        else:
            out["census"]["identity"] = {"note": "prospects.db absent, "
                                                 "identity not checkable"}

    out["census"].update(_census_frame(df, spec))
    out["ok"] = not out["problems"]
    return out


def _census_frame(df, spec: dict) -> dict:
    """Coverage by season / level / position: the frame every later gate is
    derived on. Expect tracking-era cliffs; a has-SDR indicator is an era
    indicator and inadmissible in any trainable use (stated in the gates)."""
    c: dict = {}
    if "season" in df.columns:
        c["rows_by_season"] = {
            str(int(k)): int(v)
            for k, v in df["season"].value_counts().sort_index().items()
            if str(k) != "nan"}
    if "level" in df.columns:
        c["rows_by_level"] = {
            str(k): int(v) for k, v in df["level"].value_counts().items()}
    if "primary_position" in df.columns:
        c["rows_by_position"] = {
            str(k): int(v)
            for k, v in df["primary_position"].value_counts().items()}
    comp = [col for col in spec.get("component_columns", [])
            if col in df.columns]
    if comp:
        c["component_coverage"] = {
            col: int(df[col].notna().sum()) for col in comp}
    return c


# ---------------------------------------------------------------------------
# acceptance (census FIRST, then the ledger row; the file itself is never
# rewritten)
# ---------------------------------------------------------------------------

def accept(path: Path, stream: str, *, db_path: Path = DB_PATH,
           manifest_path: Path = MANIFEST_PATH,
           census_path: Path = CENSUS_PATH) -> dict:
    v = validate(path, stream, db_path=db_path)
    if not v["ok"]:
        return v
    sha = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    census_doc = {"generated_at": date.today().isoformat(), "streams": {}}
    if Path(census_path).exists():
        try:
            census_doc = json.loads(Path(census_path).read_text(
                encoding="utf-8"))
        except Exception:  # noqa: BLE001
            log.warning("sdr_intake: census artifact unreadable, rebuilding")
    census_doc["generated_at"] = date.today().isoformat()
    census_doc.setdefault("streams", {})[stream] = {
        "path": str(Path(path).name), "rows": v["rows"],
        "census": v["census"], "warnings": v["warnings"],
    }
    Path(census_path).parent.mkdir(parents=True, exist_ok=True)
    Path(census_path).write_text(
        json.dumps(census_doc, indent=1) + "\n", encoding="utf-8")

    ledger = []
    if Path(manifest_path).exists():
        try:
            ledger = json.loads(Path(manifest_path).read_text(
                encoding="utf-8"))
        except Exception:  # noqa: BLE001
            log.warning("sdr_intake: manifest unreadable, starting fresh")
    ledger.append({
        "accepted_on": date.today().isoformat(), "stream": stream,
        "file": str(Path(path).name), "sha256": sha, "rows": v["rows"],
    })
    Path(manifest_path).write_text(
        json.dumps(ledger, indent=1) + "\n", encoding="utf-8")
    v["accepted"] = True
    return v


def newest_accepted(stream: str, *, manifest_path: Path = MANIFEST_PATH,
                    drops_dir: Path = DROPS_DIR) -> Path | None:
    """The newest accepted drop for a stream, or None. W1 loads through this
    so nothing ever reads an unvalidated file by accident."""
    if not Path(manifest_path).exists():
        return None
    try:
        ledger = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    rows = [r for r in ledger if r.get("stream") == stream]
    if not rows:
        return None
    p = Path(drops_dir) / rows[-1]["file"]
    return p if p.exists() else None


# ---------------------------------------------------------------------------
if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description="Will drop intake (SDR + eWAR)")
    ap.add_argument("--stream", required=True, choices=STREAMS)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--validate", metavar="FILE")
    g.add_argument("--census", metavar="FILE")
    g.add_argument("--accept", metavar="FILE")
    a = ap.parse_args()
    target = a.validate or a.census or a.accept
    if a.accept:
        res = accept(Path(target), a.stream)
    else:
        res = validate(Path(target), a.stream)
        if a.census:
            res = res["census"]
    print(json.dumps(res, indent=1, default=str))
    ok = res.get("ok", True) if isinstance(res, dict) else True
    raise SystemExit(0 if ok else 1)
