# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The eFV tool-feature sidecar columns (TL_9_EFV_TOOL_SIDECAR; Part 9 PLAN section 9.4.5
'Tools as eFV drivers'; LANE_C.md sections 1.3 and 2.7; owner asks of 2026-10-01,
messages 1 and 2).

WHY THIS MAY RUN AT ALL. The eFV feature frontier is closed (plan Part 2; the 2026-08-14
closure, 39 arms, zero survivors) and game power failed as an eFV driver four times (the
Phase 1 partial, D-1 tool_game_pwr -0.0047, the C3 power pairs, iso_rel 0 of 11 folds;
data/xfv_arm_ledger.json). Nothing here re-runs a spent arm. The columns are NEW (a power
composite chosen on realized ISO by a registered look, a tool-implied ISO residual, the
inputs of an accuracy-weighted hit consensus) and exist on the owner's 2026-10-01 asks.
The served eFV grade does not change. Under the owner's TL-Q1 answer (a) the columns are
built now as a development sidecar; TL_16 runs the DS-06 admission diagnostic on
development folds and pre-declares the admitted ones for the next registration.

WHAT A ROW IS. One (player_key, list vintage V) row of efv_vintage_frame (lv_dev, V 2011
to 2019), hitter side. Every input is dated before the V read:

    per-source grades  each source's EARLIEST snapshot inside the row's own frame window
                       [V-01-01, min(V-05-01, debut day)) carrying the tool, for hit,
                       game_pwr and raw_pwr (snapshots.tools_json, grades in [20, 80]).
    consensus          consensus.py's per-tool rule: the unweighted mean across the
                       outlets publishing the key, rounded to 0.5.
    pwr_comp           the as-of game and raw consensus inputs only. A candidate ONLY
                       when look P served C2 with a below 1; look P served C0
                       (data/power_composite_eval.json), so the column is written and
                       marked 'not a candidate'. The served a is never read or stored: a
                       C2 a is cross-fitted per fold by TL_16 on board years up to V - 3,
                       players outside the fold.
    tip_iso_resid      the PA-shrunk pre-V MiLB ISO at the player's last usable level
                       (the frame's MiLB block level and season, at most V - 1) minus
                       tool_implied.tip_level at that level for his game_pwr consensus
                       grade. The TIP table is fit only on MLB seasons up to V - 1 of
                       players who debuted before V; the level norms and the AAA ISO
                       offset are rebuilt per V from seasons up to V - 1 through tip_level
                       with an explicit as-of date of December 31 of V - 1.
    tool_hit_w inputs  the per-source hit grades only. The weight is computed per fold by
                       BA2's estimator on players outside the fold's V frame and is never
                       stored as a value.

Missing is None and carries no flag: a consumer imputes it at the has-block TRAIN mean
(impute_at_train_mean) and no absence flag enters any head (DS-04, bug B3,
docs/efv-v2/DRIVER_SYSTEM_V2.md '## 2').

NEVER. No outcome of a frame row is read: no WAR, no W3, no label module, and nothing of
the row's own seasons at or after V. Nothing is grouped, counted or averaged by
consensus-FV level (docs/PROSPECT_ANCHOR_GATE.md): the only bins are TOOL grade bins
inside tool_implied, and the only summaries are counts by (V, side). Every input season is
at most V - 1 and before 2026 (assert_seasons_before raises otherwise).
"""
from __future__ import annotations

import efv_vintage_frame as F
import tool_implied as TI

#: The tools this sidecar reads, in row order.
TOOLS: tuple[str, ...] = ("hit", "game_pwr", "raw_pwr")
#: The grade range a tool grade must sit in to be read (the board's 20 to 80 scale).
GRADE_LO, GRADE_HI = 20.0, 80.0
#: TIP table fit rows: pooled MLB plate appearances a fit row needs (look P's hitter
#: floor, tool_accuracy_lab.PA_FLOOR).
TIP_PA_FLOOR = 300
#: Seasons of league lines handed to tip_level per V: V - 5 to V - 1. The level norms
#: inside read their own two-season window back from the as-of date; the within-player
#: AAA ISO offset reads all five.
CAREER_WINDOW = 5
#: The StatsAPI lean hitting rows carry no games field, so the level_norms cameo floor
#: (MIN_GAMES_HITTER, 10 games) is applied as plate appearances at 4 per game.
NORM_MIN_PA = 40
#: The house MiLB rate shrink (efv_dataset._K_REL_PA): w = PA / (PA + 50).
K_SHRINK_PA = 50.0
#: The first season no input may read (round 4, leakage 2; PLAN 9.7).
FIRST_FORBIDDEN_SEASON = TI.FIRST_FORBIDDEN_SEASON


class SidecarGuardError(RuntimeError):
    """A sidecar build was asked for a reserved vintage, an R-VM row or a season it
    may not read."""


def _f(v):
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def round_half(v):
    return None if v is None else round(float(v) * 2) / 2.0


# ---------------------------------------------------------------------------
# guards
# ---------------------------------------------------------------------------

def assert_vintage_allowed(vintage: int, *, rlv_record: bool = False) -> None:
    """Raise for a reserved list vintage (R-LV, 2020 and 2021) unless the R-LV record
    exists in docs/efv-v2/EFV_V2_GATE.md '## 9. Results' (`rlv_record`), and for any
    vintage at or after the first R-VM debut year."""
    v = int(vintage)
    if v in F.RESERVED_LV and not rlv_record:
        raise SidecarGuardError(
            f"list vintage {v} is reserved (R-LV); no row before the R-LV record exists "
            "in docs/efv-v2/EFV_V2_GATE.md '## 9. Results'")
    if v >= F.R_VM_FIRST_DEBUT_YEAR:
        raise SidecarGuardError(f"list vintage {v} reaches the R-VM debut cohorts")


def is_rvm(row: dict) -> bool:
    """True for a frame row whose effective debut year is R_VM_FIRST_DEBUT_YEAR or later
    (the frame's own debut field, placeholder days already handled by the frame). Such a
    row is dropped before any count."""
    dd = str(row.get("debut_date") or "")
    return dd[:4].isdigit() and int(dd[:4]) >= F.R_VM_FIRST_DEBUT_YEAR


def assert_seasons_before(vintage: int, seasons, what: str) -> None:
    """Raise when any season is at or after V, or is 2026 or later."""
    v = int(vintage)
    bad = sorted({int(s) for s in seasons if s is not None
                  and (int(s) >= v or int(s) >= FIRST_FORBIDDEN_SEASON)})
    if bad:
        raise SidecarGuardError(
            f"{what}: seasons {bad} may not enter the build for vintage {v} (every input "
            f"season must be at most {v - 1} and before {FIRST_FORBIDDEN_SEASON})")


# ---------------------------------------------------------------------------
# per-source grades and consensus
# ---------------------------------------------------------------------------

def earliest_grades(snaps, lo: str, hi: str, excl=frozenset()) -> dict:
    """{source: {tool: grade}} from `snaps`, an iterable of (source, snapshot_date,
    tools dict), each source's EARLIEST snapshot inside [lo, hi) per tool. Sources in
    `excl` (non-raters and constant anchors, as the frame excludes them) are skipped."""
    picked: dict = {}
    out: dict = {}
    for src, d, tools in snaps:
        if src in excl or not d:
            continue
        d = str(d)[:10]
        if not (lo <= d < hi) or not isinstance(tools, dict):
            continue
        for t in TOOLS:
            g = _f(tools.get(t))
            if g is None or not (GRADE_LO <= g <= GRADE_HI):
                continue
            k = (src, t)
            if k in picked and picked[k] <= d:
                continue
            picked[k] = d
            out.setdefault(src, {})[t] = g
    return out


def consensus(per_source: dict) -> dict:
    """{tool: consensus grade or None}: consensus.py's per-tool rule, the unweighted mean
    across the outlets publishing the key, rounded to 0.5."""
    out = {}
    for t in TOOLS:
        vals = [g[t] for g in per_source.values() if t in g]
        out[t] = round_half(sum(vals) / len(vals)) if vals else None
    return out


def pwr_comp_status(look_p_result: dict | None) -> dict:
    """Whether pwr_comp is an eFV candidate, read off look P's recorded verdict: only a C2
    serve with a below 1 makes it one (round 4, leakage 3). A C1 serve, or a = 1.0, is the
    spent free key D-1:tool_game_pwr:hit re-read. The served a is reported here for the
    reason line only and never enters a row."""
    r = look_p_result or {}
    serve = (r.get("verdict") or {}).get("serve")
    a = _f(r.get("served_a"))
    if serve == "C2" and a is not None and a < 1.0:
        return {"candidate": True, "look_p_serve": serve,
                "reason": "look P served C2 with a below 1; TL_16 cross-fits a per fold"}
    if serve is None:
        why = "no look P record"
    elif serve == "C2":
        why = "look P served C2 with a = 1.0, the spent key D-1:tool_game_pwr:hit"
    elif serve == "C1":
        why = "look P served C1, the spent key D-1:tool_game_pwr:hit re-read"
    else:
        why = f"look P served {serve}"
    return {"candidate": False, "look_p_serve": serve, "reason": f"not a candidate: {why}"}


# ---------------------------------------------------------------------------
# tip_iso_resid
# ---------------------------------------------------------------------------

def mlb_iso_pooled(lines_by_season: dict) -> dict | None:
    """Pooled MLB ISO over the season lines handed in: (2B + 2 x 3B + 3 x HR) / AB, with
    PA. None without at-bats."""
    ab = pa = xb = 0.0
    for _s, ln in lines_by_season.items():
        a = _f(ln.get("ab")) or 0.0
        if a <= 0:
            continue
        ab += a
        pa += _f(ln.get("pa")) or 0.0
        xb += ((_f(ln.get("doubles")) or 0.0) + 2.0 * (_f(ln.get("triples")) or 0.0)
               + 3.0 * (_f(ln.get("hr")) or 0.0))
    if ab <= 0:
        return None
    return {"iso": xb / ab, "pa": pa, "ab": ab}


def tip_fit_rows(frames_by_v: dict, vintage: int, mlb_lines) -> list[dict]:
    """The rows the V table is fit on: for each player with a frame row at a list vintage
    Y <= V - 1 carrying a game_pwr consensus grade and a frame debut year <= V - 1, his
    LATEST such row's grade and his MLB ISO pooled over seasons from the debut year to
    V - 1, at least TIP_PA_FLOOR PA. `frames_by_v` is {Y: [frame rows with 'consensus'
    attached]}; `mlb_lines(pid, season)` returns his MLB line or None. Keyed on the frame
    row's outcome-blind id."""
    V = int(vintage)
    latest: dict = {}
    for Y in sorted(frames_by_v):
        if int(Y) > V - 1:
            continue
        for r in frames_by_v[Y]:
            g = (r.get("consensus") or {}).get("game_pwr")
            pid = r.get("mlbam_id")
            if g is None or not pid:
                continue
            latest[r["player_key"]] = (int(Y), r)
    rows = []
    for pk, (Y, r) in sorted(latest.items()):
        dd = str(r.get("debut_date") or "")
        if not dd[:4].isdigit():
            continue
        dy = int(dd[:4])
        if dy > V - 1:
            continue
        seasons = list(range(dy, V))
        assert_seasons_before(V, seasons, "tip fit rows")
        lines = {s: ln for s in seasons if (ln := mlb_lines(int(r["mlbam_id"]), s))}
        pooled = mlb_iso_pooled(lines)
        if pooled is None or pooled["pa"] < TIP_PA_FLOOR:
            continue
        rows.append({"id": pk, "grade": r["consensus"]["game_pwr"], "value": pooled["iso"],
                     "season": max(lines), "debut_year": dy, "board_year": Y,
                     "pa": pooled["pa"]})
    return rows


def career_rows(league_lines, vintage: int) -> tuple[dict, dict, list[int]]:
    """({key: [season rows]}, {key: birth date}, seasons) for tip_level at V: every
    hitting line of seasons V - CAREER_WINDOW to V - 1 from `league_lines(season)`, an
    iterable of StatsAPI lean rows (mlbam, season, level, age, pa, ab, avg, slg, ...).
    One row per (player, season, level), the largest-PA one (two A-level sports share a
    label). A line under NORM_MIN_PA carries games 0 so level_norms' cameo floor drops it
    from the norms; the AAA offset still weights it by PA. The birth date is the age the
    feed prints placed at July 1 (level_norms reads it only to place the row in an age
    band); a line with no age is dropped."""
    V = int(vintage)
    seasons = [s for s in range(V - CAREER_WINDOW, V)]
    assert_seasons_before(V, seasons, "career rows")
    best: dict = {}
    bd: dict = {}
    for s in seasons:
        for ln in league_lines(s) or []:
            pid, lv = ln.get("mlbam"), ln.get("level")
            age = _f(ln.get("age"))
            if not pid or not lv or age is None:
                continue
            if int(ln.get("season") or s) != s:
                raise SidecarGuardError(f"a line for season {ln.get('season')} sits in {s}")
            key = f"m{int(pid)}"
            pa = _f(ln.get("pa")) or 0.0
            k = (key, s, lv)
            if k in best and (best[k].get("pa") or 0.0) >= pa:
                continue
            avg, slg = _f(ln.get("avg")), _f(ln.get("slg"))
            best[k] = {"season": s, "level": lv, "is_pitcher": False, "pa": pa,
                       "ab": _f(ln.get("ab")) or 0.0, "avg": ln.get("avg"),
                       "slg": ln.get("slg"), "obp": ln.get("obp"), "ops": ln.get("ops"),
                       "iso": (slg - avg) if slg is not None and avg is not None else None,
                       "games": 10 if pa >= NORM_MIN_PA else 0}
            bd.setdefault(key, f"{int(s - age):04d}-07-01")
    out: dict = {}
    for (key, _s, _lv), row in best.items():
        out.setdefault(key, []).append(row)
    return out, bd, seasons


def shrunk_iso(line: dict | None, level_norm_iso) -> dict | None:
    """The PA-shrunk ISO of one MiLB level-season line toward the as-of level norm:
    norm + w x (ISO - norm), w = PA / (PA + K_SHRINK_PA). None without a line, PA or norm."""
    if not line:
        return None
    pa = _f(line.get("pa")) or 0.0
    slg, avg = _f(line.get("slg")), _f(line.get("avg"))
    norm = _f(level_norm_iso)
    if pa <= 0 or slg is None or avg is None or norm is None:
        return None
    iso = slg - avg
    w = pa / (pa + K_SHRINK_PA)
    return {"iso_raw": iso, "pa": pa, "w": w, "norm": norm, "value": norm + w * (iso - norm)}


def tip_iso_resid(row: dict, grade_game, line: dict | None, tip_value, level_norm_iso) -> dict:
    """The residual for one frame row: shrunk pre-V ISO at the block's level minus the
    tool-implied ISO at that level. Every missing input gives value None (no flag)."""
    m = row.get("milb") or {}
    out = {"value": None, "level": m.get("milb_level"), "season": m.get("milb_season"),
           "iso_shrunk": None, "tip": _f(tip_value), "pa": None}
    if grade_game is None or not m or out["level"] is None or out["season"] is None:
        return out
    assert_seasons_before(row["vintage"], [out["season"]], "tip_iso_resid MiLB season")
    s = shrunk_iso(line, level_norm_iso)
    if s is None:
        return out
    out["iso_shrunk"] = s["value"]
    out["pa"] = s["pa"]
    if out["tip"] is not None:
        out["value"] = s["value"] - out["tip"]
    return out


# ---------------------------------------------------------------------------
# missingness and coverage
# ---------------------------------------------------------------------------

def impute_at_train_mean(values: dict, train_keys) -> dict:
    """{key: value} with every None replaced by the mean of the non-None values whose key
    is in `train_keys` (the fold's training rows). No absence flag is returned: under
    DS-04 and bug B3 none may enter a head. Raises when the training rows hold no value,
    so a fold cannot silently impute zero."""
    train = [values[k] for k in train_keys if values.get(k) is not None]
    if not train:
        raise ValueError("no has-block training row to impute from")
    m = sum(train) / len(train)
    return {k: (m if v is None else v) for k, v in values.items()}


def coverage_block(rows: list[dict], feats: dict) -> dict:
    """Counts for one (V, side) and nothing else: frame rows, rows with an outcome-blind
    id, rows per tool with at least one source grade, rows per source per tool, rows with
    a consensus per tool, rows with both pwr_comp inputs, rows with a tip_iso_resid, rows
    with one and with two or more source hit grades. No outcome, no grade value."""
    out = {"rows": len(rows),
           "id_resolved": sum(1 for r in rows if r.get("mlbam_id")),
           "with_milb_block": sum(1 for r in rows if r.get("milb")),
           "consensus": {t: 0 for t in TOOLS}, "by_source": {},
           "pwr_comp_inputs": 0, "tip_iso_resid": 0,
           "tool_hit_w_inputs": {"one_source": 0, "two_or_more": 0}}
    for r in rows:
        f = feats.get(r["player_key"])
        if not f:
            continue
        for t in TOOLS:
            if f["consensus"].get(t) is not None:
                out["consensus"][t] += 1
        for src, g in f["per_source"].items():
            blk = out["by_source"].setdefault(src, {t: 0 for t in TOOLS})
            for t in TOOLS:
                if t in g:
                    blk[t] += 1
        if f["consensus"].get("game_pwr") is not None and \
                f["consensus"].get("raw_pwr") is not None:
            out["pwr_comp_inputs"] += 1
        if (f.get("tip") or {}).get("value") is not None:
            out["tip_iso_resid"] += 1
        n_hit = sum(1 for g in f["per_source"].values() if "hit" in g)
        if n_hit == 1:
            out["tool_hit_w_inputs"]["one_source"] += 1
        elif n_hit >= 2:
            out["tool_hit_w_inputs"]["two_or_more"] += 1
    out["by_source"] = dict(sorted(out["by_source"].items()))
    return out
