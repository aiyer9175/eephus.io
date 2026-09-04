# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""Rebase the career_war sqlite table from bWAR to eWAR v2 (one epoch).

    python tools/rebase_career_war_to_ewar.py            # DRY RUN, prints coverage
    python tools/rebase_career_war_to_ewar.py --apply    # backup + write, once
    python tools/rebase_career_war_to_ewar.py --reapply  # re-derive from seasons_bwar

Owner decision 2026-09-03: the site serves and labels on eWAR v2 (ewar.py),
the Baseball-Reference run frame with pitching re-priced on FIP, centred per
season x role so role totals match B-Ref; fielding swap weight 0.0, so for
position players eWAR equals bWAR season by season until the SDR defense drop
lands, and for pitchers runs are redistributed within role. This is a BASIS
decision, not an accuracy claim: the 2026-08-04 label-swap test (R3a) moved
the eFV margin over consensus by -0.0011 hit / -0.0115 pit, a floor-sized
effect left unexcluded (data/ewar_eval.json, memory).

WHAT THIS DOES. For every stored career_war row:
  1. resolve mlbam: storage's durable player_photos binding first (the same
     key -> id map storage's timeseries export uses as its last-resort id,
     keys bound to two ids excluded), then data/sources/mlbam_id_overrides.json,
     then mlbam_id_overrides_busts.json; unresolved keys are reported and the
     row is left as it is (bWAR, source bbref);
  2. transform the per-season series with the SHARED CONTRACT below;
  3. write {seasons: eWAR series, seasons_bwar: the frame, source: ewar_v2,
     ewar_coverage: receipt} through storage.upsert_career_war, whose MERGE
     unions both series and recomputes career_war / war_per_yr /
     war_seasons_count over the served one.

SHARED TRANSFORM CONTRACT (war_source ewar_v2 provider and this tool must
agree bit for bit; the funnel and the rebase produce the same row):

    for season, bwar in seasons_bwar.items():
        rec = ewar.ewar_for(mlbam, int(season))
        seasons[season] = round(rec["ewar"], 2) if rec and rec.get("ewar") is not None else round(bwar, 2)

Seasons the artifact does not carry (outside its season window, or a
player-season war_daily has and the build dropped) fall back to the bWAR
value; the receipt counts both kinds. The window is read from the artifact
at run time (2026-09-03 dry run: [2011, 2026], 0 pre-window fallbacks,
90 in-window of 11,564 seasons). If war_source exposes
`ewar_seasons_from_bwar(seasons_bwar, mlbam, payload=None) -> dict` at run
time it is called; otherwise the rule above runs inline.

IDEMPOTENCY. A row whose source is already ewar_v2 is re-derived from its
`seasons_bwar`, never from `seasons`, so apply-twice == apply-once and a
rebuilt ewar.json can be re-applied with --reapply. Plain --apply REFUSES
when the table already carries ewar_v2 rows (the once-only guard).

SAFETY. --apply first copies prospects.db to prospects.db.bak-ewar-<date>
through sqlite3's backup API (WAL-safe; a plain file copy could miss the
write-ahead log). The DEPLOY BOX must run the same --apply on its own copy
of the DB: the table is not tracked by git, so the lineage only converges if
both writers apply the same transform to the same rows.

Nothing here touches data/ or any artifact; the later wave owns the rebuild
(matrices, evals, floors, anchors, fingerprint, epoch bump).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ewar      # noqa: E402
import storage   # noqa: E402

SOURCE_EWAR = "ewar_v2"
SOURCE_LEGACY = "bbref"
OVERRIDE_FILES = (
    ROOT / "data" / "sources" / "mlbam_id_overrides.json",
    ROOT / "data" / "sources" / "mlbam_id_overrides_busts.json",
)
_HELPER_NAME = "ewar_seasons_from_bwar"


# ------------------------------------------------------------------ identity
def durable_ids_by_key() -> dict[str, int]:
    """storage's canonical player_key -> mlbam map: the player_photos binding
    (storage.load_mlbam_player_keys), a key bound to two ids dropped as
    ambiguous. Mirrors _durable_ids_by_key in storage's timeseries export."""
    out: dict[str, int] = {}
    multi: set[str] = set()
    for mid_s, pk in storage.load_mlbam_player_keys().items():
        if not pk:
            continue
        try:
            mid = int(mid_s)
        except (TypeError, ValueError):
            continue
        prior = out.get(pk)
        if prior is not None and prior != mid:
            multi.add(pk)
        out[pk] = mid
    for pk in multi:
        out.pop(pk, None)
    return out


def override_ids() -> dict[str, int]:
    """{player_key: mlbam} from the two override files, first file wins."""
    out: dict[str, int] = {}
    for path in OVERRIDE_FILES:
        if not path.exists():
            continue
        try:
            blob = json.loads(path.read_text(encoding="utf-8")) or {}
        except (OSError, ValueError):
            continue
        for k, v in blob.items():
            if k.startswith("_") or k in out:
                continue
            try:
                out[k] = int(v)
            except (TypeError, ValueError):
                continue
    return out


def resolve_mlbam(key: str, durable: dict[str, int], overrides: dict[str, int]
                  ) -> tuple[int | None, str | None]:
    """(mlbam, source) with source in {photos, override}; (None, None) if
    no table knows the key."""
    mid = durable.get(key)
    if mid is not None:
        return mid, "photos"
    mid = overrides.get(key)
    if mid is not None:
        return mid, "override"
    return None, None


# ----------------------------------------------------------------- transform
def _inline_transform(seasons_bwar: dict, mlbam: int, payload: dict | None
                      ) -> tuple[dict[str, float], dict[str, int]]:
    """The two-line rule from the module docstring, plus the receipt counts."""
    seasons: dict[str, float] = {}
    n_ewar = 0
    n_fallback_pre = 0
    n_fallback_post = 0
    lo = (payload or ewar.load()).get("seasons", [2016, 2026])[0]
    for season, bwar in sorted(seasons_bwar.items(), key=lambda kv: int(kv[0])):
        rec = ewar.ewar_for(mlbam, int(season), payload)
        if rec and rec.get("ewar") is not None:
            seasons[str(season)] = round(float(rec["ewar"]), 2)
            n_ewar += 1
        else:
            seasons[str(season)] = round(float(bwar), 2)
            if int(season) < lo:
                n_fallback_pre += 1
            else:
                n_fallback_post += 1
    return seasons, {"n_ewar": n_ewar, "n_fallback_pre": n_fallback_pre,
                     "n_fallback_post": n_fallback_post}


def transform_seasons(seasons_bwar: dict, mlbam: int, payload: dict | None = None
                      ) -> tuple[dict[str, float], dict[str, int]]:
    """bWAR series -> eWAR series. Calls war_source's shared helper when it
    exists, else the inline rule (identical arithmetic by contract)."""
    try:
        import war_source
        helper = getattr(war_source, _HELPER_NAME, None)
    except ImportError:
        helper = None
    if helper is not None:
        seasons = helper(seasons_bwar, mlbam, payload=payload)
        # the receipt is derived the same way regardless of who transformed
        _, counts = _inline_transform(seasons_bwar, mlbam, payload)
        return {str(k): round(float(v), 2) for k, v in seasons.items()}, counts
    return _inline_transform(seasons_bwar, mlbam, payload)


def bwar_frame_of(row: dict) -> dict[str, float] | None:
    """The bWAR frame a stored row is re-derived from: `seasons_bwar` when the
    row is already ewar_v2 (never its served `seasons`), else `seasons`.
    None for an ewar_v2 row that lost its frame (cannot be rebased)."""
    if row.get("source") == SOURCE_EWAR:
        frame = row.get("seasons_bwar")
        return dict(frame) if frame else None
    return dict(row.get("seasons") or {})


def rebase_row(row: dict, mlbam: int, payload: dict | None = None,
               generated_at: str | None = None) -> dict | None:
    """One stored career_war row -> the ewar_v2 payload upsert_career_war
    expects. None when the row has no usable frame."""
    frame = bwar_frame_of(row)
    if not frame:
        return None
    seasons, counts = transform_seasons(frame, mlbam, payload)
    vals = list(seasons.values())
    n = len(vals)
    blob = payload or ewar.load()
    return {
        "seasons": seasons,
        "seasons_bwar": {str(k): round(float(v), 2) for k, v in frame.items()},
        "career_war": round(sum(vals), 2),
        "war_per_yr": round(sum(vals) / n, 2) if n else 0.0,
        "war_seasons_count": n,
        "source": SOURCE_EWAR,
        "ewar_coverage": {
            "model": blob.get("model", ewar.MODEL),
            "artifact_generated_at": generated_at or blob.get("generated_at"),
            "mlbam": int(mlbam),
            "n_seasons": n,
            **counts,
        },
    }


# --------------------------------------------------------------------- driver
def plan(rows: dict[str, dict], payload: dict | None = None) -> tuple[dict[str, dict], dict]:
    """Compute every rebased payload plus the coverage report, no writes."""
    durable = durable_ids_by_key()
    overrides = override_ids()
    blob = payload or ewar.load()
    out: dict[str, dict] = {}
    rep = {
        "rows": len(rows), "rows_rebased": 0, "rows_unresolved": 0,
        "rows_no_frame": 0, "rows_already_ewar": 0,
        "id_from_photos": 0, "id_from_override": 0,
        "seasons": 0, "seasons_ewar": 0, "seasons_fallback_pre": 0,
        "seasons_fallback_post": 0, "seasons_changed": 0,
        "abs_delta_sum": 0.0, "unresolved_keys": [], "no_frame_keys": [],
        "override_disagrees_with_photos": [],
        "artifact": {"model": blob.get("model"), "seasons": blob.get("seasons"),
                     "generated_at": blob.get("generated_at")},
    }
    for key in sorted(rows):
        row = rows[key]
        if row.get("source") == SOURCE_EWAR:
            rep["rows_already_ewar"] += 1
        mid, how = resolve_mlbam(key, durable, overrides)
        if mid is None:
            rep["rows_unresolved"] += 1
            rep["unresolved_keys"].append(key)
            rep["seasons"] += len(row.get("seasons") or {})
            continue
        if key in durable and key in overrides and overrides[key] != durable[key]:
            rep["override_disagrees_with_photos"].append(
                (key, durable[key], overrides[key]))
        rep["id_from_photos" if how == "photos" else "id_from_override"] += 1
        new = rebase_row(row, mid, blob)
        if new is None:
            rep["rows_no_frame"] += 1
            rep["no_frame_keys"].append(key)
            continue
        cov = new["ewar_coverage"]
        rep["rows_rebased"] += 1
        rep["seasons"] += cov["n_seasons"]
        rep["seasons_ewar"] += cov["n_ewar"]
        rep["seasons_fallback_pre"] += cov["n_fallback_pre"]
        rep["seasons_fallback_post"] += cov["n_fallback_post"]
        for yr, v in new["seasons"].items():
            b = new["seasons_bwar"].get(yr)
            if b is not None and abs(float(v) - float(b)) >= 0.005:
                rep["seasons_changed"] += 1
                rep["abs_delta_sum"] += abs(float(v) - float(b))
        out[key] = new
    return out, rep


def format_report(rep: dict) -> str:
    s = rep["seasons"] or 1
    lines = [
        f"career_war rebase -> {rep['artifact']['model']} "
        f"(artifact {rep['artifact']['seasons']}, generated {rep['artifact']['generated_at']})",
        f"  rows            {rep['rows']}   rebased {rep['rows_rebased']}   "
        f"unresolved {rep['rows_unresolved']}   no-frame {rep['rows_no_frame']}   "
        f"already ewar_v2 {rep['rows_already_ewar']}",
        f"  id source       photos {rep['id_from_photos']}   override {rep['id_from_override']}   "
        f"override!=photos {len(rep['override_disagrees_with_photos'])}",
        f"  seasons         {rep['seasons']}   eWAR {rep['seasons_ewar']} "
        f"({rep['seasons_ewar'] / s:.1%})   fallback pre-artifact {rep['seasons_fallback_pre']} "
        f"({rep['seasons_fallback_pre'] / s:.1%})   fallback in-window {rep['seasons_fallback_post']} "
        f"({rep['seasons_fallback_post'] / s:.1%})",
        f"  changed         {rep['seasons_changed']} seasons move by >= 0.01 WAR, "
        f"sum |eWAR - bWAR| = {rep['abs_delta_sum']:.1f}",
    ]
    if rep["unresolved_keys"]:
        lines.append("  unresolved keys (first 20): " + ", ".join(rep["unresolved_keys"][:20]))
    if rep["no_frame_keys"]:
        lines.append("  ewar_v2 rows without seasons_bwar (first 20): "
                     + ", ".join(rep["no_frame_keys"][:20]))
    if rep["override_disagrees_with_photos"]:
        lines.append("  override disagrees with player_photos (photos wins): "
                     + ", ".join(f"{k} photos={a} override={b}"
                                 for k, a, b in rep["override_disagrees_with_photos"][:10]))
    return "\n".join(lines)


def backup_db(db_path: Path) -> Path:
    """WAL-safe copy via the sqlite3 backup API. Never overwrites."""
    stamp = _dt.date.today().isoformat()
    dst = db_path.with_name(f"{db_path.name}.bak-ewar-{stamp}")
    if dst.exists():
        dst = db_path.with_name(
            f"{db_path.name}.bak-ewar-{_dt.datetime.now().strftime('%Y-%m-%d-%H%M%S')}")
    src = sqlite3.connect(str(db_path))
    try:
        out = sqlite3.connect(str(dst))
        try:
            src.backup(out)
        finally:
            out.close()
    finally:
        src.close()
    return dst


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true",
                    help="back up prospects.db, then write the rebased rows (once)")
    ap.add_argument("--reapply", action="store_true",
                    help="like --apply but allowed on a table already on ewar_v2; "
                         "rows are re-derived from seasons_bwar")
    ap.add_argument("--json", action="store_true", help="print the report as JSON")
    args = ap.parse_args(argv)

    rows = storage.load_career_war()
    if not rows:
        print("career_war table is empty or absent; nothing to rebase")
        return 1
    new, rep = plan(rows)
    print(json.dumps(rep, indent=1, default=str) if args.json else format_report(rep))

    if not (args.apply or args.reapply):
        print("\nDRY RUN: no writes. Pass --apply to rebase (backup taken first).")
        return 0
    if rep["rows_already_ewar"] and not args.reapply:
        print(f"\nREFUSED: {rep['rows_already_ewar']} rows already carry source "
              f"{SOURCE_EWAR}; this table has been rebased. Use --reapply to "
              f"re-derive from seasons_bwar (e.g. after rebuilding data/ewar.json).")
        return 2
    if not new:
        print("\nnothing resolvable to write")
        return 1
    db_path = Path(storage.DB_PATH)
    bak = backup_db(db_path)
    print(f"\nbackup: {bak} ({bak.stat().st_size / 1e6:.0f} MB)")
    n = storage.upsert_career_war(new)
    print(f"wrote {n} rows through storage.upsert_career_war (source {SOURCE_EWAR})")
    print("REMINDER: the deploy box must run this same --apply on its DB.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
