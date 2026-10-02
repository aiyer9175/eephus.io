# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Rebase the career_war sqlite table onto a WAR provider (ewar_v2 or fwar).

    python tools/rebase_career_war.py --provider fwar              # DRY RUN: receipt, no write
    python tools/rebase_career_war.py --provider fwar --apply      # backup + write, once
    python tools/rebase_career_war.py --provider fwar --reapply    # re-derive from the kept incumbent

fWAR label epoch precondition E3 part (4) (docs/efv-2026-09-17/
FWAR_LABEL_EPOCH_GATE.md part 3 row E3, part 4.1 note 2, part 4.3, part 7 row
C). The generalisation of tools/rebase_career_war_to_ewar.py, which is LEFT
UNTOUCHED and keeps working: `--provider ewar_v2` here writes the very payload
that tool writes (it calls that tool's rebase_row), and `--provider fwar` is
the epoch's step C. Both providers report ONE receipt schema
(RECEIPT_SCHEMA, `receipt_keys()`).

RESOLVER ORDER (unchanged, imported from the L1 tool): storage's durable
player_photos binding first (keys bound to two ids excluded), then
data/sources/mlbam_id_overrides.json, then mlbam_id_overrides_busts.json. An
unresolved key is reported and its row is left exactly as it is.

THE FWAR TRANSFORM is war_source.fwar_seasons_from_incumbent, the same function
the 'fwar' funnel calls, so the funnel and the rebase agree bit for bit:
`seasons` takes the frozen vintage's fWAR (hitting war + pitching war) on every
(mlbam, fwar season), and keeps the incumbent value everywhere else.
  - The INCUMBENT of a row is what the table serves on the incumbent provider:
    its `seasons_ewar_v2` when it keeps one, else its `seasons` (an ewar_v2
    row, or a bbref row the eWAR rebase never resolved).
  - Every fwar row keeps `seasons_ewar_v2` (the incumbent, verbatim) and
    `seasons_bwar` (when the row has one), so the eWAR v2 series re-derives
    from the table itself (note 2); the sqlite backup is the cross-check, never
    the only source.
  - A pre-2011 season, or any season the vintage does not serve as fwar (a
    mixed or absent season, or one outside it), keeps the incumbent value and is
    counted as `seasons_mixed`; the row's `fwar_coverage.war_basis` is then
    'mixed', never 'fwar' (note 3).

THE ABORTS (part 4.3, CARRIED: "abort if the career_war rebase leaves any
season of any player with NEITHER an fWAR nor an eWAR v2 value"; note 2: a
rebase that cannot reconstruct the incumbent is a STOP). Both are ASSERTED on
the planned table before any write, and re-asserted on the table read back
after --apply: `neither_value()` lists every (key, season) whose served value
and kept incumbent are both missing, `incumbent_breaks()` every row whose kept
incumbent no longer equals the pre-rebase incumbent bit for bit. Either list
non-empty raises RebaseAbort before a write, or exits 3 after one (the backup
is then the restore path).

IDEMPOTENCY. A row already on the provider is re-derived from its kept
incumbent (`seasons_ewar_v2` for fwar, `seasons_bwar` for ewar_v2), never from
its served `seasons`, so apply twice equals apply once. Plain --apply REFUSES
when any row already carries the provider's source; --reapply is the way.

SAFETY. --apply first copies prospects.db to prospects.db.bak-<provider>-<date>
through sqlite3's backup API (WAL-safe). Dry run is the default. The deploy box
must run the same --apply on its own copy of the database. Nothing here
touches data/.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import math
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import storage                                   # noqa: E402
import war_source                                # noqa: E402
import rebase_career_war_to_ewar as L1           # noqa: E402

PROVIDERS: tuple[str, ...] = ("ewar_v2", "fwar")
RECEIPT_SCHEMA = "career_war_rebase/1"

#: The kept series a provider's row is re-derived from (and the incumbent it
#: must keep reconstructible).
INCUMBENT_KEY = {"ewar_v2": "seasons_bwar", "fwar": "seasons_ewar_v2"}

#: The per-row receipt key each provider writes.
COVERAGE_KEY = {"ewar_v2": "ewar_coverage", "fwar": "fwar_coverage"}


class RebaseAbort(RuntimeError):
    """A part 4.3 / note 2 abort: the message names every offending row."""


def _finite(v) -> bool:
    try:
        return v is not None and not isinstance(v, bool) and math.isfinite(float(v))
    except (TypeError, ValueError):
        return False


# ------------------------------------------------------------------ the incumbent
def incumbent_of(row: dict, provider: str) -> dict | None:
    """The series a row is rebased FROM (see the module docstring). For fwar:
    `seasons_ewar_v2` when kept, else `seasons`. For ewar_v2: the L1 rule
    (`seasons_bwar` on an ewar_v2 row, else `seasons`). None when a row on the
    provider lost its kept series (it cannot be rebased)."""
    if provider == "fwar":
        kept = row.get("seasons_ewar_v2")
        if isinstance(kept, dict) and kept:
            return dict(kept)
        if row.get("source") == "fwar":
            return None
        return dict(row.get("seasons") or {})
    return L1.bwar_frame_of(row)


def served_incumbent(row: dict, provider: str) -> dict:
    """The incumbent series as the table carries it NOW, for the reconstruct
    check: the kept map on a row already on the provider, else `seasons`."""
    key = INCUMBENT_KEY[provider]
    if row.get("source") == provider or (provider == "fwar" and row.get(key)):
        return dict(row.get(key) or {})
    return dict(row.get("seasons") or {})


# ------------------------------------------------------------------ per-row transforms
def rebase_row_fwar(row: dict, mlbam: int, idx: dict) -> dict | None:
    """One stored row -> its fwar payload, or None without a usable incumbent."""
    inc = incumbent_of(row, "fwar")
    if not inc:
        return None
    seasons, rec = war_source.fwar_seasons_from_incumbent(inc, mlbam, idx)
    # the incumbent's own source survives a re-derivation (idempotency)
    inc_src = ((row.get("fwar_coverage") or {}).get("incumbent_source")
               if row.get("source") == "fwar" else row.get("source"))
    vals = list(seasons.values())
    n = len(vals)
    out = {
        "seasons": seasons,
        "seasons_ewar_v2": inc,
        "career_war": round(sum(vals), 2),
        "war_per_yr": round(sum(vals) / n, 2) if n else 0.0,
        "war_seasons_count": n,
        "source": "fwar",
        "fwar_coverage": {"vintage_id": idx.get("vintage_id"), "mlbam": int(mlbam),
                          "incumbent_source": inc_src, **rec},
    }
    if row.get("seasons_bwar"):
        out["seasons_bwar"] = dict(row["seasons_bwar"])
    elif row.get("source") == "bbref":
        out["seasons_bwar"] = dict(row.get("seasons") or {})
    if row.get("ewar_coverage"):
        out["ewar_coverage"] = row["ewar_coverage"]
    return out


def _row_counts(provider: str, new: dict) -> dict:
    cov = new[COVERAGE_KEY[provider]]
    if provider == "fwar":
        return {"n_provider": cov["n_fwar"], "n_fallback_pre": cov["n_fallback_pre"],
                "n_fallback_post": cov["n_fallback_post"], "war_basis": cov["war_basis"]}
    pre, post = cov["n_fallback_pre"], cov["n_fallback_post"]
    return {"n_provider": cov["n_ewar"], "n_fallback_pre": pre, "n_fallback_post": post,
            "war_basis": "ewar_v2" if not (pre or post) else "mixed"}


# ------------------------------------------------------------------ the asserts
def neither_value(table: dict[str, dict]) -> list[tuple[str, str]]:
    """(key, season) for every season of every row with NEITHER a served value
    nor a kept incumbent value (part 4.3). A row's seasons are the union of
    `seasons` and `seasons_ewar_v2`."""
    bad: list[tuple[str, str]] = []
    for key in sorted(table):
        row = table[key] or {}
        served = row.get("seasons") or {}
        kept = row.get("seasons_ewar_v2") or {}
        for yr in sorted(set(served) | set(kept), key=int):
            if not (_finite(served.get(yr)) or _finite(kept.get(yr))):
                bad.append((key, str(yr)))
    return bad


def incumbent_breaks(before: dict[str, dict], after: dict[str, dict],
                     provider: str) -> list[str]:
    """Keys whose incumbent series, read from the table AFTER, no longer equals
    the incumbent BEFORE bit for bit (note 2). Only rows present before count."""
    bad: list[str] = []
    for key in sorted(before):
        want = served_incumbent(before[key], provider)
        row = after.get(key)
        got = served_incumbent(row, provider) if row is not None else None
        if got != want:
            bad.append(key)
    return bad


# ------------------------------------------------------------------ the receipt
def receipt_keys() -> tuple[str, ...]:
    """THE ONE RECEIPT SCHEMA, both providers (pinned by test)."""
    return ("schema", "provider", "artifact", "incumbent_key", "rows", "rows_rebased",
            "rows_unresolved", "rows_no_frame", "rows_already_provider", "id_from_photos",
            "id_from_override", "override_disagrees_with_photos", "seasons",
            "seasons_provider", "seasons_fallback_pre", "seasons_fallback_post",
            "seasons_mixed", "seasons_changed", "abs_delta_sum", "rows_war_basis",
            "unresolved_keys", "no_frame_keys", "neither_value", "incumbent_breaks")


def _artifact(provider: str, blob: dict) -> dict:
    if provider == "fwar":
        import fwar_vintage
        return {"provider": "fwar", "id": blob.get("vintage_id"),
                "seasons": fwar_vintage.fwar_seasons(blob),
                "non_fwar_seasons": fwar_vintage.mixed_seasons(blob),
                "schema": blob.get("schema")}
    return {"provider": "ewar_v2", "id": blob.get("generated_at"),
            "seasons": blob.get("seasons"), "model": blob.get("model")}


def load_source(provider: str, payload: dict | None = None) -> dict:
    """The artifact a provider rebases onto: the frozen vintage (fwar) or
    data/ewar.json (ewar_v2). DataUnavailable through war_source._require."""
    if payload is not None:
        return payload
    war_source._require(provider)
    if provider == "fwar":
        import fwar_vintage
        return fwar_vintage.load()
    import ewar
    return ewar.load()


def plan(rows: dict[str, dict], provider: str, payload: dict | None = None
         ) -> tuple[dict[str, dict], dict]:
    """Every rebased payload plus the receipt, no writes. Raises RebaseAbort
    when the planned table fails either assert."""
    if provider not in PROVIDERS:
        raise ValueError(f"unknown provider {provider!r}; use one of {PROVIDERS}")
    blob = load_source(provider, payload)
    idx = war_source.fwar_index(blob) if provider == "fwar" else None
    durable = L1.durable_ids_by_key()
    overrides = L1.override_ids()
    out: dict[str, dict] = {}
    rep = {k: 0 for k in receipt_keys()}
    rep.update({"schema": RECEIPT_SCHEMA, "provider": provider,
                "artifact": _artifact(provider, blob),
                "incumbent_key": INCUMBENT_KEY[provider], "rows": len(rows),
                "abs_delta_sum": 0.0, "rows_war_basis": {},
                "override_disagrees_with_photos": [], "unresolved_keys": [],
                "no_frame_keys": [], "neither_value": [], "incumbent_breaks": []})
    for key in sorted(rows):
        row = rows[key]
        if row.get("source") == provider:
            rep["rows_already_provider"] += 1
        mid, how = L1.resolve_mlbam(key, durable, overrides)
        if mid is None:
            rep["rows_unresolved"] += 1
            rep["unresolved_keys"].append(key)
            rep["seasons"] += len(row.get("seasons") or {})
            continue
        if key in durable and key in overrides and overrides[key] != durable[key]:
            rep["override_disagrees_with_photos"].append((key, durable[key], overrides[key]))
        rep["id_from_photos" if how == "photos" else "id_from_override"] += 1
        if provider == "fwar":
            new = rebase_row_fwar(row, mid, idx)
            inc = new["seasons_ewar_v2"] if new else None
        else:
            new = L1.rebase_row(row, mid, blob)
            inc = new["seasons_bwar"] if new else None
        if new is None:
            rep["rows_no_frame"] += 1
            rep["no_frame_keys"].append(key)
            continue
        c = _row_counts(provider, new)
        rep["rows_rebased"] += 1
        rep["seasons"] += len(new["seasons"])
        rep["seasons_provider"] += c["n_provider"]
        rep["seasons_fallback_pre"] += c["n_fallback_pre"]
        rep["seasons_fallback_post"] += c["n_fallback_post"]
        rep["seasons_mixed"] += c["n_fallback_pre"]
        rep["rows_war_basis"][c["war_basis"]] = rep["rows_war_basis"].get(c["war_basis"], 0) + 1
        for yr, v in new["seasons"].items():
            b = inc.get(yr)
            if _finite(b) and _finite(v) and abs(float(v) - float(b)) >= 0.005:
                rep["seasons_changed"] += 1
                rep["abs_delta_sum"] += abs(float(v) - float(b))
        out[key] = new
    planned = {**rows, **out}
    rep["neither_value"] = neither_value(planned)
    if provider == "fwar":
        rep["incumbent_breaks"] = incumbent_breaks(rows, planned, provider)
    if rep["neither_value"] or rep["incumbent_breaks"]:
        raise RebaseAbort(_abort_text(rep))
    return out, rep


def _abort_text(rep: dict) -> str:
    parts = []
    if rep["neither_value"]:
        parts.append(f"{len(rep['neither_value'])} seasons with neither a "
                     f"{rep['provider']} nor an incumbent value (first 10: "
                     f"{rep['neither_value'][:10]})")
    if rep["incumbent_breaks"]:
        parts.append(f"{len(rep['incumbent_breaks'])} rows whose incumbent no longer "
                     f"reconstructs (first 10: {rep['incumbent_breaks'][:10]})")
    return "ABORT: " + "; ".join(parts)


def format_report(rep: dict) -> str:
    s = rep["seasons"] or 1
    a = rep["artifact"]
    lines = [
        f"career_war rebase -> {rep['provider']} (artifact {a.get('id')}, seasons "
        f"{a.get('seasons')}) [{rep['schema']}]",
        f"  rows            {rep['rows']}   rebased {rep['rows_rebased']}   "
        f"unresolved {rep['rows_unresolved']}   no-frame {rep['rows_no_frame']}   "
        f"already {rep['provider']} {rep['rows_already_provider']}",
        f"  id source       photos {rep['id_from_photos']}   override {rep['id_from_override']}   "
        f"override!=photos {len(rep['override_disagrees_with_photos'])}",
        f"  seasons         {rep['seasons']}   {rep['provider']} {rep['seasons_provider']} "
        f"({rep['seasons_provider'] / s:.1%})   mixed (outside the provider's seasons) "
        f"{rep['seasons_mixed']} ({rep['seasons_mixed'] / s:.1%})   fallback in-window "
        f"{rep['seasons_fallback_post']} ({rep['seasons_fallback_post'] / s:.1%})",
        f"  rows by basis   {rep['rows_war_basis']}",
        f"  changed         {rep['seasons_changed']} seasons move by >= 0.01 WAR against "
        f"{rep['incumbent_key']}, sum |delta| = {rep['abs_delta_sum']:.1f}",
        f"  asserts         neither-value {len(rep['neither_value'])}   "
        f"incumbent breaks {len(rep['incumbent_breaks'])}",
    ]
    if rep["unresolved_keys"]:
        lines.append("  unresolved keys (first 20): " + ", ".join(rep["unresolved_keys"][:20]))
    if rep["no_frame_keys"]:
        lines.append("  rows without a kept incumbent (first 20): "
                     + ", ".join(rep["no_frame_keys"][:20]))
    return "\n".join(lines)


def backup_db(db_path: Path, provider: str) -> Path:
    """WAL-safe copy via the sqlite3 backup API, prospects.db.bak-<provider>-<date>.
    Never overwrites."""
    stamp = _dt.date.today().isoformat()
    dst = db_path.with_name(f"{db_path.name}.bak-{provider}-{stamp}")
    if dst.exists():
        dst = db_path.with_name(f"{db_path.name}.bak-{provider}-"
                                f"{_dt.datetime.now().strftime('%Y-%m-%d-%H%M%S')}")
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


def main(argv: list[str] | None = None, *, payload: dict | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--provider", required=True, choices=PROVIDERS)
    ap.add_argument("--apply", action="store_true",
                    help="back up prospects.db, then write the rebased rows (once)")
    ap.add_argument("--reapply", action="store_true",
                    help="like --apply but allowed on a table already on the provider; "
                         "rows are re-derived from the kept incumbent")
    ap.add_argument("--json", action="store_true", help="print the receipt as JSON")
    ap.add_argument("--receipt", type=Path, default=None,
                    help="also write the receipt JSON to this path")
    args = ap.parse_args(argv)

    rows = storage.load_career_war()
    if not rows:
        print("career_war table is empty or absent; nothing to rebase")
        return 1
    try:
        new, rep = plan(rows, args.provider, payload)
    except RebaseAbort as exc:
        print(str(exc))
        return 3
    text = json.dumps(rep, indent=1, default=str)
    print(text if args.json else format_report(rep))
    if args.receipt:
        Path(args.receipt).write_text(text + "\n", encoding="utf-8")

    if not (args.apply or args.reapply):
        print("\nDRY RUN: no writes. Pass --apply to rebase (backup taken first).")
        return 0
    if rep["rows_already_provider"] and not args.reapply:
        print(f"\nREFUSED: {rep['rows_already_provider']} rows already carry source "
              f"{args.provider}; this table has been rebased. Use --reapply to re-derive "
              f"from {INCUMBENT_KEY[args.provider]}.")
        return 2
    if not new:
        print("\nnothing resolvable to write")
        return 1
    bak = backup_db(Path(storage.DB_PATH), args.provider)
    print(f"\nbackup: {bak} ({bak.stat().st_size / 1e6:.0f} MB)")
    n = storage.upsert_career_war(new)
    print(f"wrote {n} rows through storage.upsert_career_war (source {args.provider})")
    after = storage.load_career_war()
    nv = neither_value(after)
    br = incumbent_breaks(rows, after, args.provider) if args.provider == "fwar" else []
    if nv or br:
        print(_abort_text({"provider": args.provider, "neither_value": nv,
                           "incumbent_breaks": br}))
        print(f"STOP: restore from {bak}")
        return 3
    print("asserts after write: neither-value 0, incumbent breaks 0")
    print("REMINDER: the deploy box must run this same --apply on its DB.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
