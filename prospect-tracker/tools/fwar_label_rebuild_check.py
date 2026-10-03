# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Precondition E7: rebuild the six-season fWAR label independently and check the matrices.

    python tools/fwar_label_rebuild_check.py              # both sides; prints and writes the receipt
    python tools/fwar_label_rebuild_check.py --no-write   # prints only

docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md part 3 row E7 ("An independent label rebuild
matching the new matrices on at least 99% of debuted rows") and its blocking map (E7 blocks
step F's reads, so every margin, every arm and every clause (d) cell); part 4.1 note 3 (the
`war_basis: mixed` stamp); part 7 row F. EPOCH_RUN runs this once, right after step F has
written data/xfv_hitter_matrix.json and data/xfv_pitcher_matrix.json on the fwar label.

THE TEMPLATE IS GONE. The gate names `label_shift_descriptive.py` (planning scratchpad,
plan3/R2_driver_ledger/) as the template; it is no longer on disk. This tool is written from
the label's written definitions below, not ported.

INDEPENDENCE (the point of E7). The label is recomputed from the FROZEN fWAR VINTAGE
(data/fwar_vintage.json) by MLBAM id and season. It never reads `career_war`, never goes
through `war_source` (not its fwar funnel, not `fwar_index`, not
`fwar_seasons_from_incumbent`), never imports `efv_dataset` (so never `_label_6yr`,
`_label_seasons` or `build_matrix`) and never calls `fwar_vintage.season_totals`, the totals
map the production funnel reads. What it does import: `fwar_vintage` for the vintage's path
and its hash check (`verify`, which recomputes hashes and computes no WAR), and, lazily and
only for the default id resolver, tools/rebase_career_war_to_ewar.py's player_photos and
override tables (that module imports `ewar` and `storage`, never `war_source`). The
label-join file is read here directly, because tools/rebase_career_war.py imports
`war_source`. test_fwar_label_rebuild_check.py pins all of this.

THE LABEL, RE-IMPLEMENTED FROM ITS WRITTEN DEFINITIONS:
  - A season's fWAR is the sum of the vintage's published `war` over its two groups
    (hitting + pitching; a group with no row, or a null war, adds nothing), rounded to
    2 decimals (fwar_vintage's docstring, "A player-season's fWAR is the sum of its groups'
    published war"; war_source's transform contract, "round(totals[(mlbam, season)], 2)").
    Only seasons whose BOTH groups are frozen serve fWAR (fwar_vintage rule 6).
  - The window is debut_year .. debut_year + TARGET_SEASONS - 1; the observed seasons are
    the window's years <= RESOLVED_THROUGH; obs_sum = round(sum of the observed seasons, 3),
    a season with no feed row counting 0.0. A window ending <= RESOLVED_THROUGH resolves:
    (obs_sum, obs_sum, censored False, weight 1.0, n_obs). Otherwise it is right-censored:
    target_censored = round(obs_sum + (TARGET_SEASONS - n_obs) * obs_sum / n_obs, 3),
    weight round(n_obs / TARGET_SEASONS, 3) (efv_dataset's module header, CENSORING).
  - ARM A1 (service-aligned window), only when the matrix's report shows it on (its
    accounting key `debuted_window_shifted`, which the builder writes only while the arm is
    on and a row shifted): a debut whose day is after 04-15 takes debut_year + 1 .. + 6 and
    carries the debut season's fWAR as a stub added to obs_sum, excluded from the tail rate
    and from n_obs. No day is read from a placeholder debut, a bust row rerouted to the
    debuted pool, or a row whose debut year was moved past a postseason-only debut (its
    debut_year differs from its cutoff's year).
  - A terminal transaction (retired or banned) resolves a censored row when its date falls
    in a year <= RESOLVED_THROUGH, or in RESOLVED_THROUGH + 1 on or before 04-01: then
    target_censored = target_resolved, censored False, weight 1.0, observed_seasons =
    TARGET_SEASONS. The date is read off the row's `terminal_resolved` field.
  - A row's `war_basis` is 'fwar' when its id resolved and every season the label reads
    (the observed window, plus A1's stub season) is a season the vintage serves as fWAR;
    else 'mixed' (gate part 4.1 note 3). It is never 'fwar' for a row with no id.

WHAT THE TOOL TAKES FROM A MATRIX ROW: its identity (player_key, mlbam_id), side, debut_year,
cutoff, debut_date_is_placeholder, rerouted_from_bust and terminal_resolved. Those are the
row's inputs; every label field (target_resolved, target_censored, censored, weight,
observed_seasons) is recomputed and compared.

DEBUTED ROWS. A matrix row is debuted when kind == "debuted" (the debuted loop and the bust
rows rerouted into it both write that kind; a never-MLB bust is kind == "bust"). The
denominator is every debuted row of the side. A row whose id does not resolve, or whose
window has no observed season, is compared and counted as a mismatch, never dropped.

THE IDS. Step C's resolver order (tools/rebase_career_war.py): the label-join file
data/sources/mlbam_id_label_join.json, then the player_photos binding (a key bound to two ids
dropped), then data/sources/mlbam_id_overrides.json and mlbam_id_overrides_busts.json; then,
last, the matrix row's own mlbam_id. The receipt counts each source and every row whose
resolved id differs from the row's own.

MATCH (default, named in the commit): a row matches when target_resolved, target_censored and
weight each agree within TOLERANCE and censored and observed_seasons agree exactly. The
documents do not fix the tolerance. The matrices write the label at 3 decimals (efv_dataset
rounds obs_sum and the censored target to 3), so TOLERANCE is half of that precision, 0.0005
WAR, inclusive. PASS needs a match share of at least PASS_SHARE (0.99) on EACH side.

REFUSALS (exit 2, nothing written): a side's report stamp is not on the fwar label (the
report's `target`, "first-6-season summed WAR (<provider>); resolved<= <year>", is the
matrix's label stamp, since the matrix file is a bare list of rows), or its accounting names
a label_seasons_key other than `seasons`; the report's counts do not describe the matrix on
disk; the vintage fails its hash check. So this tool can never certify an eWAR v2 matrix.

THE RECEIPT. data/_labs/fwar_epoch_arms/e7_receipt.json (data/_labs/ ships in neither deploy
consumer), written only by a run, with the same lines printed. A receipt path inside data/
but outside data/_labs/ is refused. This tool computes no score, no consensus, no eFV and no
statistic by consensus-FV cell; it never writes a matrix, a gate document or prospects.db.

Exit codes: 0 PASS, 1 FAIL, 2 refused.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import fwar_vintage   # noqa: E402  the E3 vintage: its path and its hash check only

SCHEMA = "fwar_label_rebuild_check/1"
GATE = "docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md"
RUN_CMD = "python tools/fwar_label_rebuild_check.py"

DATA = ROOT / "data"
SIDES: tuple[str, ...] = ("hit", "pit")
MATRIX_FILES = {"hit": "xfv_hitter_matrix.json", "pit": "xfv_pitcher_matrix.json"}
REPORT_FILES = {"hit": "xfv_dataset_report.json", "pit": "xfv_pitcher_dataset_report.json"}
LABEL_JOIN_FILE = DATA / "sources" / "mlbam_id_label_join.json"
LABS_ROOT = DATA / "_labs"
RECEIPT_PATH = LABS_ROOT / "fwar_epoch_arms" / "e7_receipt.json"

#: The label the matrices must be on (gate part 1; owner answer EPOCH-Q4: fWAR is the
#: training label).
REQUIRED_PROVIDER = "fwar"

#: The gate's E7 bar, per side.
PASS_SHARE = 0.99

#: The matrices write the label at 3 decimals; the tolerance is half of that (inclusive).
STORED_DECIMALS = 3
TOLERANCE = 0.0005
#: A float guard so that a difference of exactly TOLERANCE in decimal still matches.
_EPS = 1e-9

#: A season's fWAR is written at 2 decimals (the transform contract).
SEASON_DECIMALS = 2

#: ARM A1's service-year cut (a calendar convention) and the terminal pre-season cut.
SERVICE_YEAR_CUT_MMDD = "04-15"
TERMINAL_PRESEASON_MMDD = "04-01"

#: The report's `target` string: the matrix's label stamp.
STAMP_RE = re.compile(r"^first-(\d+)-season summed WAR \(([^)]*)\); resolved<= (\d+)$")

GROUPS: tuple[str, ...] = ("hitting", "pitching")

#: The label fields compared, and which of them compare within TOLERANCE.
NUMERIC_FIELDS: tuple[str, ...] = ("target_resolved", "target_censored", "weight")
EXACT_FIELDS: tuple[str, ...] = ("censored", "observed_seasons")

Resolver = Callable[[str, object], "tuple[int | None, str | None]"]


class CheckRefused(RuntimeError):
    """A run this tool will not do; the message names the side and the cause."""


# ------------------------------------------------------------------ the label stamp
def read_stamp(report: dict, side: str) -> dict:
    """The label stamp of one side's matrix, read off its report. Refuses an unreadable
    stamp and a non-default label_seasons_key."""
    target = str((report or {}).get("target") or "")
    m = STAMP_RE.match(target)
    if not m:
        raise CheckRefused(f"{side}: the report's label stamp is unreadable: {target!r}")
    acct = (report or {}).get("accounting") or {}
    key = acct.get("label_seasons_key")
    if key not in (None, "seasons"):
        raise CheckRefused(f"{side}: the matrix sums career_war.{key}, not the served "
                           "series; it is an arm build, not the fwar label")
    return {"target": target, "target_seasons": int(m.group(1)), "provider": m.group(2),
            "resolved_through": int(m.group(3)),
            "service_aligned": "debuted_window_shifted" in acct}


def require_fwar(stamp: dict, side: str) -> None:
    """Refuse any matrix whose stamp is not the fwar label (never certify eWAR v2)."""
    if stamp["provider"] != REQUIRED_PROVIDER:
        raise CheckRefused(f"{side}: the matrix is stamped {stamp['provider']!r}, not "
                           f"{REQUIRED_PROVIDER!r} ({stamp['target']!r}); E7 checks only the "
                           "fwar label")


def assert_report_describes(rows: list, report: dict, side: str) -> None:
    """Refuse when the report's counts are not this matrix's (a stale stamp)."""
    counts = (report or {}).get("counts") or {}
    n_deb = sum(1 for r in rows if r.get("kind") == "debuted")
    if counts.get("rows_total") != len(rows) or counts.get("debuted") != n_deb:
        raise CheckRefused(f"{side}: the report counts rows_total={counts.get('rows_total')} "
                           f"debuted={counts.get('debuted')} but the matrix holds {len(rows)} "
                           f"rows, {n_deb} debuted; the stamp does not describe this matrix")


# ------------------------------------------------------------------ the vintage, read here
def vintage_index(vintage: dict) -> dict:
    """{"values": {(mlbam, season): fWAR at 2 dp}, "fwar_years": set, "vintage_id": id},
    read straight off the frozen vintage's rows. A season serves fWAR only when both of
    its groups are frozen. Refuses a vintage whose hashes do not verify."""
    probs = fwar_vintage.verify(vintage)
    if probs:
        raise CheckRefused("the frozen vintage fails its hash check: " + "; ".join(probs[:5]))
    values: dict[tuple[int, int], float] = {}
    years: set[int] = set()
    for s_key, sb in (vintage.get("seasons") or {}).items():
        sb = sb or {}
        if not all((sb.get(g) or {}).get("status") == "frozen" for g in GROUPS):
            continue
        season = int(s_key)
        years.add(season)
        raw: dict[int, float] = {}
        for g in GROUPS:
            gb = sb.get(g) or {}
            fields = list(gb.get("fields") or [])
            if "war" not in fields:
                raise CheckRefused(f"{season} {g}: the frozen group carries no war field")
            i = fields.index("war")
            for mid_s, vals in (gb.get("rows") or {}).items():
                v = vals[i] if i < len(vals) else None
                if v is None:
                    continue
                mid = int(mid_s)
                raw[mid] = float(v) if mid not in raw else raw[mid] + float(v)
        for mid, tot in raw.items():
            values[(mid, season)] = round(tot, SEASON_DECIMALS)
    return {"values": values, "fwar_years": years, "vintage_id": vintage.get("vintage_id")}


# ------------------------------------------------------------------ the ids
def label_join_ids(path: Path = LABEL_JOIN_FILE) -> dict[str, int]:
    """{player_key: mlbam} from the epoch's label-join file; {} when absent."""
    try:
        blob = json.loads(Path(path).read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        return {}
    out: dict[str, int] = {}
    for k, e in (blob.get("entries") or {}).items():
        try:
            out[str(k)] = int(e["mlbam"])
        except (KeyError, TypeError, ValueError):
            continue
    return out


def make_resolver(label_join: dict[str, int], durable: dict[str, int],
                  overrides: dict[str, int]) -> Resolver:
    """Step C's order, then the matrix row's own id: (mlbam, source) or (None, None)."""
    def resolve(key: str, row_mlbam) -> tuple[int | None, str | None]:
        for table, source in ((label_join, "label_join"), (durable, "photos"),
                              (overrides, "override")):
            mid = table.get(key)
            if mid is not None:
                return int(mid), source
        try:
            return (int(row_mlbam), "matrix_row") if row_mlbam not in (None, "") else (None, None)
        except (TypeError, ValueError):
            return None, None
    return resolve


def default_resolver() -> Resolver:
    """The live tables. The player_photos and override readers come from the L1 rebase
    tool (imports ewar and storage only), loaded here and not at module import."""
    tools_dir = str(ROOT / "tools")
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    import rebase_career_war_to_ewar as L1
    return make_resolver(label_join_ids(), L1.durable_ids_by_key(), L1.override_ids())


# ------------------------------------------------------------------ the label
def service_window_shifts(label_date) -> bool:
    """A1: True when the debut day is after the service-year cut. No usable day, no shift."""
    if not label_date or len(str(label_date)) < 10:
        return False
    return str(label_date)[5:10] > SERVICE_YEAR_CUT_MMDD


def label_date_of(row: dict):
    """The debut day A1 may read off a matrix row, or None (placeholder, rerouted bust,
    or a debut year moved past a postseason-only debut)."""
    if row.get("debut_date_is_placeholder") or row.get("rerouted_from_bust"):
        return None
    cutoff = str(row.get("cutoff") or "")
    if len(cutoff) < 10 or not cutoff[:4].isdigit():
        return None
    if int(cutoff[:4]) != int(row.get("debut_year")):
        return None
    return cutoff


def terminal_resolves(tdate, resolved_through: int) -> bool:
    """A terminal date resolves a censored window (see the module docstring)."""
    try:
        y = int(str(tdate)[:4])
    except (TypeError, ValueError):
        return False
    return y <= resolved_through or (y == resolved_through + 1
                                     and str(tdate)[5:10] <= TERMINAL_PRESEASON_MMDD)


def rebuild_label(season_war: dict[int, float], debut_year: int, label_date=None, *,
                  resolved_through: int, target_seasons: int,
                  service_aligned: bool = False) -> dict:
    """The six-season label from {season: fWAR}. Raises ValueError when the window has
    no observed season."""
    start, stub, stub_year = int(debut_year), 0.0, None
    if service_aligned and service_window_shifts(label_date):
        start = int(debut_year) + 1
        stub_year = int(debut_year)
        stub = float(season_war.get(stub_year, 0.0) or 0.0)
    window = [start + i for i in range(target_seasons)]
    observed = [y for y in window if y <= resolved_through]
    if not observed:
        raise ValueError(f"no observed season: debut_year={debut_year} start={start} "
                         f"resolved_through={resolved_through}")
    in_window = sum(season_war.get(y, 0.0) for y in observed)
    obs_sum = round(stub + in_window, STORED_DECIMALS)
    n_obs = len(observed)
    out = {"window": window, "observed": observed, "stub_year": stub_year}
    if start + target_seasons - 1 <= resolved_through:
        out.update(target_resolved=obs_sum, target_censored=obs_sum, censored=False,
                   weight=1.0, observed_seasons=n_obs)
        return out
    rate = (obs_sum - stub) / n_obs
    out.update(target_resolved=obs_sum,
               target_censored=round(obs_sum + (target_seasons - n_obs) * rate, STORED_DECIMALS),
               censored=True, weight=round(n_obs / target_seasons, STORED_DECIMALS),
               observed_seasons=n_obs)
    return out


def apply_terminal(rebuilt: dict, tdate, *, resolved_through: int,
                   target_seasons: int) -> dict:
    """The terminal-transaction resolution, applied to a censored rebuilt label."""
    if tdate and rebuilt.get("censored") and terminal_resolves(tdate, resolved_through):
        rebuilt = dict(rebuilt, target_censored=rebuilt["target_resolved"], censored=False,
                       weight=1.0, observed_seasons=target_seasons, terminal_resolved=tdate)
    return rebuilt


# ------------------------------------------------------------------ the comparison
def fields_differing(matrix_row: dict, rebuilt: dict, tol: float = TOLERANCE) -> list[str]:
    """The label fields on which the matrix row and the rebuild disagree."""
    bad = []
    for f in NUMERIC_FIELDS:
        a, b = matrix_row.get(f), rebuilt.get(f)
        try:
            if abs(float(a) - float(b)) > tol + _EPS:
                bad.append(f)
        except (TypeError, ValueError):
            bad.append(f)
    if bool(matrix_row.get("censored")) != bool(rebuilt.get("censored")):
        bad.append("censored")
    try:
        if int(matrix_row.get("observed_seasons")) != int(rebuilt.get("observed_seasons")):
            bad.append("observed_seasons")
    except (TypeError, ValueError):
        bad.append("observed_seasons")
    return bad


def _label_of(row: dict) -> dict:
    return {f: row.get(f) for f in (*NUMERIC_FIELDS, *EXACT_FIELDS)}


def check_side(side: str, rows: list, stamp: dict, vidx: dict, resolver: Resolver,
               tol: float = TOLERANCE) -> dict:
    """Every debuted row of one side's matrix rebuilt and compared."""
    rt, ts = stamp["resolved_through"], stamp["target_seasons"]
    values, years = vidx["values"], vidx["fwar_years"]
    compared = matched = 0
    mismatches: list[dict] = []
    per_row: list[list] = []
    basis_counts = {"fwar": 0, "mixed": 0}
    id_sources: dict[str, int] = {}
    id_disagrees: list[list] = []
    for row in rows:
        if row.get("kind") != "debuted":
            continue
        compared += 1
        key = row.get("player_key")
        dy = int(row.get("debut_year"))
        mid, how = resolver(key, row.get("mlbam_id"))
        id_sources[how or "none"] = id_sources.get(how or "none", 0) + 1
        if mid is not None and row.get("mlbam_id") not in (None, "") \
                and int(row["mlbam_id"]) != int(mid):
            id_disagrees.append([key, int(row["mlbam_id"]), int(mid), how])
        rebuilt, reason, seasons = None, None, {}
        if mid is None:
            reason = "no_id"
        else:
            season_war = _season_war(values, mid, dy, ts)
            try:
                rebuilt = rebuild_label(season_war, dy, label_date_of(row), resolved_through=rt,
                                        target_seasons=ts,
                                        service_aligned=stamp["service_aligned"])
            except ValueError:
                reason = "no_observed_season"
            if rebuilt is not None:
                rebuilt = apply_terminal(rebuilt, row.get("terminal_resolved"),
                                         resolved_through=rt, target_seasons=ts)
                read = list(rebuilt["observed"]) + (
                    [rebuilt["stub_year"]] if rebuilt["stub_year"] is not None else [])
                seasons = {str(y): values.get((mid, y)) for y in sorted(read)}
        if rebuilt is not None:
            basis = "fwar" if all(int(y) in years for y in seasons) else "mixed"
            diff = fields_differing(row, rebuilt, tol)
        else:
            basis, diff = "mixed", ["label"]
        basis_counts[basis] += 1
        ok = not diff
        matched += int(ok)
        per_row.append([key, mid, dy, basis, ok])
        if not ok:
            mismatches.append({
                "key": key, "mlbam": mid, "id_source": how, "debut_year": dy,
                "reason": reason or "label_differs", "fields": diff,
                "window": (rebuilt or {}).get("window"), "seasons": seasons,
                "matrix": _label_of(row),
                "rebuilt": _label_of(rebuilt) if rebuilt is not None else None,
                "war_basis": basis})
    share = (matched / compared) if compared else 0.0
    return {"side": side, "stamp": stamp, "rows_compared": compared, "rows_matched": matched,
            "match_share": round(share, 6), "passed": bool(compared) and share >= PASS_SHARE,
            "war_basis": basis_counts, "id_sources": id_sources,
            "id_differs_from_row": id_disagrees, "mismatches": mismatches,
            "rows": per_row}


def _season_war(values: dict, mid: int, debut_year: int, target_seasons: int) -> dict:
    """{season: fWAR} for one id over every season a label from this debut can read
    (A1's stub year through the shifted window's end)."""
    out = {}
    for y in range(debut_year, debut_year + target_seasons + 1):
        v = values.get((mid, y))
        if v is not None:
            out[y] = v
    return out


# ------------------------------------------------------------------ the run
def check(sides: dict[str, tuple[list, dict]], vintage: dict, resolver: Resolver,
          tol: float = TOLERANCE, matrix_sha: dict | None = None) -> dict:
    """The receipt for both sides. `sides` is {side: (matrix rows, report)}. Raises
    CheckRefused before anything is compared when any side is not on the fwar label."""
    missing = [s for s in SIDES if s not in sides]
    if missing:
        raise CheckRefused(f"E7 reads both sides; missing {missing}")
    stamps = {}
    for side in SIDES:
        rows, report = sides[side]
        stamps[side] = read_stamp(report, side)
        require_fwar(stamps[side], side)
        assert_report_describes(rows, report, side)
    vidx = vintage_index(vintage)
    out_sides = {s: check_side(s, sides[s][0], stamps[s], vidx, resolver, tol) for s in SIDES}
    if matrix_sha:
        for s in SIDES:
            out_sides[s]["matrix_sha256"] = matrix_sha.get(s)
    passed = all(out_sides[s]["passed"] for s in SIDES)
    pass_line = (f"E7 PASS: the independent rebuild matches at least {PASS_SHARE:.0%} of "
                 "debuted rows on each side" if passed else
                 f"E7 FAIL: a side matches under {PASS_SHARE:.0%} of its debuted rows")
    return {
        "schema": SCHEMA, "producer": "tools/fwar_label_rebuild_check.py", "gate": GATE,
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "vintage_id": vidx["vintage_id"], "fwar_years": sorted(vidx["fwar_years"]),
        "tolerance": tol,
        "tolerance_rule": (f"half of the matrices' stored precision ({STORED_DECIMALS} "
                           "decimals), inclusive; censored and observed_seasons exact"),
        "pass_share": PASS_SHARE, "sides": out_sides, "passed": passed, "pass_line": pass_line,
    }


def format_lines(receipt: dict) -> list[str]:
    """The printed lines: the same content as the receipt, every mismatch included."""
    lines = [f"E7 independent fWAR label rebuild (vintage {receipt['vintage_id']}, "
             f"tolerance {receipt['tolerance']} WAR, bar {receipt['pass_share']} per side)"]
    for s in SIDES:
        r = receipt["sides"][s]
        lines.append(
            f"  {s}: compared {r['rows_compared']}  matched {r['rows_matched']}  share "
            f"{r['match_share']:.4f}  war_basis {r['war_basis']}  ids {r['id_sources']}  "
            f"id differs from row {len(r['id_differs_from_row'])}  "
            f"[{r['stamp']['target']}; A1 {'on' if r['stamp']['service_aligned'] else 'off'}]")
        for m in r["mismatches"]:
            lines.append(
                f"    MISMATCH {s} {m['key']} mlbam={m['mlbam']} ({m['id_source']}) "
                f"debut={m['debut_year']} {m['reason']} {m['fields']} seasons={m['seasons']} "
                f"matrix={m['matrix']} rebuilt={m['rebuilt']} basis={m['war_basis']}")
    lines.append(receipt["pass_line"])
    return lines


def assert_receipt_path(path: Path) -> Path:
    """A receipt inside data/ must sit under data/_labs/ (ships in neither consumer)."""
    rp = Path(path).resolve()
    data, labs = DATA.resolve(), LABS_ROOT.resolve()
    if (rp == data or data in rp.parents) and labs not in rp.parents:
        raise CheckRefused(f"refusing a receipt inside data/ outside data/_labs/: {rp}")
    return rp


def write_receipt(receipt: dict, path: Path = RECEIPT_PATH) -> Path:
    rp = assert_receipt_path(path)
    rp.parent.mkdir(parents=True, exist_ok=True)
    rp.write_text(json.dumps(receipt, indent=1) + "\n", encoding="utf-8")
    return rp


def _read_json(p: Path):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def main(argv: list[str] | None = None, *, resolver: Resolver | None = None,
         matrix_paths: dict | None = None, report_paths: dict | None = None,
         vintage_path: Path | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--no-write", action="store_true", help="print only; write no receipt")
    ap.add_argument("--receipt", type=Path, default=RECEIPT_PATH,
                    help="receipt path (inside data/, only under data/_labs/)")
    a = ap.parse_args(argv)
    mp = matrix_paths or {s: DATA / MATRIX_FILES[s] for s in SIDES}
    rp = report_paths or {s: DATA / REPORT_FILES[s] for s in SIDES}
    try:
        if not a.no_write:
            assert_receipt_path(a.receipt)
        sides, sha = {}, {}
        for s in SIDES:
            report = _read_json(rp[s])
            stamp = read_stamp(report, s)
            require_fwar(stamp, s)           # refuse before reading the matrix itself
            blob = Path(mp[s]).read_bytes()
            sha[s] = hashlib.sha256(blob).hexdigest()
            sides[s] = (json.loads(blob.decode("utf-8")), report)
        vintage = _read_json(vintage_path or fwar_vintage.VINTAGE_PATH)
        receipt = check(sides, vintage, resolver or default_resolver(), matrix_sha=sha)
    except CheckRefused as exc:
        print(f"REFUSED: {exc}")
        return 2
    for line in format_lines(receipt):
        print(line)
    if not a.no_write:
        print(f"wrote {write_receipt(receipt, a.receipt)}")
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
