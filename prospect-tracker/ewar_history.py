# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eWAR history: every season the data supports, stamped with its parts
(docs/ewar/EWAR_HISTORY_GATE.md, task EWAR_BACKGRADE_HISTORY; owner decisions
EW3-17 and EW3-20).

THE SERIES IS eWAR AS REGISTERED. eWAR is the frozen published fWAR vintage plus
the named, zero-sum departures of data/ewar_v3.json (EBR_GATE.md 11.10). This
module admits nothing and moves nothing: it measures which parts each season's
eWAR carries (the stamp), groups seasons with the same stamp, and computes the
CORE series (only the parts present in every season 2000 to 2026) beside FULL
(eWAR itself) so the parts later seasons add are measured against it.

    stamps()          {season: stamp}, every part measured on the season's rows
    season_groups()   maximal runs of seasons with one stamp, each with its sentence
    merged_shorts()   the sentences naming what a span of seasons lacks, for one series
    core_full(s)      per-row CORE, FULL and FULL realized for one season, with parts
    build()           the record tools/build_ewar_history.py writes to data/ewar_history.json

CORE is never a column, a sort key, a label, a driver or a model input (gate part
5): the artifact carries per-season summaries only, nothing per player.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import math
from pathlib import Path

import fwar_vintage

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data" / "ewar_history.json"
GATE_DOC = "docs/ewar/EWAR_HISTORY_GATE.md"
VERSION = "ewar_history_v1"
BUILD_CMD = "python tools/build_ewar_history.py --write"

#: The first season eWAR is shown for: the vintage's first accepted season (gate part 1).
FIRST_SEASON: int = int(fwar_vintage.FIRST_ACCEPTED_SEASON)

#: Why it stops there, said once for every surface that prints the window.
WHY_IT_STOPS = (
    "eWAR starts in 2000, the first season of the frozen FanGraphs WAR copy it is built on; "
    "that copy is never refetched, so an earlier season would need a new copy or another frame.")

#: Stamp thresholds (gate part 2), runs.
BSR_EPS = 0.005
FRM_EPS = 0.05
#: Identity tolerances (gate part 4), wins.
TOL_ROW = 1e-9
TOL_SIDE = 1e-6
#: Amendment 9.2: data/ewar_v3.json stores each departure at 6 decimals, wins per row.
STORE_ROUND = 5e-7
#: The gap report's correlation frames (gate part 4).
MIN_PA = 300
MIN_IP = 50

HIT_COMPONENTS = ("batting", "baseRunning", "fielding", "positional", "wLeague", "replacement")

#: Every part, in display order, with its label and series (gate part 2).
PARTS = (
    ("batting", "batting runs", "both"),
    ("wsb", "steal runs (wSB)", "both"),
    ("bsr_rest", "the rest of baserunning", "both"),
    ("fielding", "fielding", "both"),
    ("framing", "catcher framing", "both"),
    ("positional", "positional adjustment", "both"),
    ("league_replacement", "league and replacement terms", "both"),
    ("pitching", "pitching (FanGraphs' FIP-based)", "both"),
    ("eabs", "eABS (ABS challenges)", "both"),
    ("xhem", "xHEM+ expected batting, half weight (provisional)", "headline"),
    ("r2", "realized pitching (runs allowed)", "realized"),
)
CORE_PARTS = ("batting", "wsb", "fielding", "positional", "league_replacement", "pitching")
NON_CORE = ("bsr_rest", "framing", "eabs", "xhem", "r2")
BSR_LABEL_UBR = "UBR and wGDP double plays"
BSR_LABEL_OTHER = "FanGraphs' other baserunning runs"


class EwarHistoryRefusal(RuntimeError):
    """A build that must not write: the message names the identity that missed."""


# ---------------------------------------------------------------------------
# inputs
# ---------------------------------------------------------------------------

def _rows(block: dict) -> dict[int, dict]:
    fields = list(block.get("fields") or [])
    return {int(mid): dict(zip(fields, vals)) for mid, vals in (block.get("rows") or {}).items()}


def _num(v) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if math.isnan(f) else f


def _sha(path: Path) -> str | None:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


_MEMO: dict = {}


def _inputs(vintage: dict | None = None, v3: dict | None = None) -> tuple[dict, dict]:
    """(vintage, eWAR v3 payload): passed in, or read once per process."""
    if vintage is None:
        if "vin" not in _MEMO:
            _MEMO["vin"] = fwar_vintage.load()
        vintage = _MEMO["vin"]
    if v3 is None:
        if "v3" not in _MEMO:
            import ewar_v3
            _MEMO["v3"] = ewar_v3.load()
        v3 = _MEMO["v3"]
    return vintage, v3


def reset() -> None:
    """Drop the memoised inputs (the test seam)."""
    _MEMO.clear()


def seasons(vintage: dict | None = None) -> list[int]:
    """Every season the history serves: the vintage's frozen seasons from FIRST_SEASON."""
    vin = vintage if vintage is not None else _inputs()[0]
    return [s for s in fwar_vintage.fwar_seasons(vin) if s >= FIRST_SEASON]


def _season_rows(vin: dict, s: int) -> tuple[dict, dict]:
    sb = (vin.get("seasons") or {}).get(str(s)) or {}
    return _rows(sb.get("hitting") or {}), _rows(sb.get("pitching") or {})


def _frm(r: dict) -> float:
    """F_i: FanGraphs' RAR beyond the components the feed lists (the catcher term)."""
    return _num(r.get("rar")) - sum(_num(r.get(k)) for k in HIT_COMPONENTS)


# ---------------------------------------------------------------------------
# the stamp (gate part 2)
# ---------------------------------------------------------------------------

def _stamp(vin: dict, v3: dict, s: int) -> dict:
    hit, _pit = _season_rows(vin, s)
    bsr_rows = sum(1 for r in hit.values()
                   if abs(_num(r.get("baseRunning")) - _num(r.get("wSb"))) > BSR_EPS)
    frm_rows = sum(1 for r in hit.values() if abs(_frm(r)) > FRM_EPS)
    ubr_exact = all(abs(_num(r.get("baseRunning")) - _num(r.get("wSb")) - _num(r.get("ubr"))
                        - _num(r.get("wGdp"))) <= BSR_EPS for r in hit.values())
    chk = (v3.get("checks") or {}).get(str(s)) or {}
    has_abs = bool(chk.get("abs_receipt"))
    # EBR_GATE.md 11.11: the xHEM+ part rides the headline series only
    has_xhem = bool(int((chk.get("xhem_receipt") or {}).get("rows") or 0))
    r2_rows = int(chk.get("r2_rows") or 0)
    headline = list(CORE_PARTS)
    if bsr_rows:
        headline.append("bsr_rest")
    if frm_rows:
        headline.append("framing")
    if has_abs:
        headline.append("eabs")
    realized = list(headline) + (["r2"] if r2_rows else [])
    if has_xhem:
        headline.append("xhem")
    order = [p for p, _l, _s in PARTS]
    headline.sort(key=order.index)
    realized.sort(key=order.index)
    return {"headline": headline, "realized": realized,
            "bsr_label": (BSR_LABEL_UBR if ubr_exact else BSR_LABEL_OTHER) if bsr_rows else None,
            "measured": {"hit_rows": len(hit), "bsr_rest_rows": bsr_rows, "framing_rows": frm_rows,
                         "abs_receipt": has_abs, "r2_rows": r2_rows,
                         **({"xhem_rows": int(chk["xhem_receipt"]["rows"])} if has_xhem else {})}}


def stamps(vintage: dict | None = None, v3: dict | None = None) -> dict[int, dict]:
    """{season: stamp} for every season the history serves (memoised on the default inputs)."""
    default = vintage is None and v3 is None
    if default and "stamps" in _MEMO:
        return _MEMO["stamps"]
    vin, pay = _inputs(vintage, v3)
    out = {s: _stamp(vin, pay, s) for s in fwar_vintage.fwar_seasons(vin) if s >= FIRST_SEASON}
    if default:
        _MEMO["stamps"] = out
    return out


def _first_with(st: dict[int, dict], part: str, series: str = "realized") -> int | None:
    yrs = [s for s, v in st.items() if part in v[series]]
    return min(yrs) if yrs else None


def _span(a: int, b: int) -> str:
    return str(a) if a == b else f"{a}-{b}"


def _join(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _sentence(first: int, last: int, stp: dict, st: dict[int, dict]) -> dict:
    """The sentences of one group, every fact read off the stamps:
    text           what the season's eWAR and eWAR realized carry
    text_headline  the same for eWAR alone (the boards print eWAR only)
    missing        the part ids the newest season carries and this group does not
                   (eABS is never missing before its first season: there was nothing)
    short          one sentence naming the missing parts, "" when none is missing
    short_headline the same, eWAR's parts only (every one of them a hitting-side part)
    short_realized the same, eWAR realized's own part only (pitching)
    reason_*       the short sentences without their span, so a reader can join
                   neighbouring groups that lack the same parts."""
    head = stp["headline"]
    if "bsr_rest" not in head:
        bsr = "baserunning from wSB steals only"
    elif stp["bsr_label"] == BSR_LABEL_UBR:
        bsr = "baserunning (wSB steals, UBR and wGDP double plays)"
    else:
        bsr = f"baserunning (wSB steals and {stp['bsr_label']})"
    fld = "fielding and catcher framing" if "framing" in head else "fielding"
    parts = ["batting", bsr, fld, "the positional, league and replacement terms", "pitching"]
    text_h = f"{_span(first, last)}: FanGraphs' " + _join(parts)
    extras = (["eABS (ABS challenges)"] if "eabs" in head else []) + (
        ["half of xHEM+ expected batting (provisional)"] if "xhem" in head else [])
    if extras:
        text_h += ", plus " + _join(extras)
    keeps = " and keeps FanGraphs' batting" if "xhem" in head else ""
    text = text_h + ((f"; eWAR realized prices pitchers on runs allowed{keeps}") if "r2" in stp["realized"]
                     else (f"; eWAR realized keeps FanGraphs' batting" if keeps else "; eWAR realized equals eWAR")) + "."
    newest = st[max(st)]
    missing, why_h, why_r = [], [], []
    if "bsr_rest" in newest["headline"] and "bsr_rest" not in head:
        missing.append("bsr_rest")
        why_h.append("baserunning is steals only (FanGraphs published no UBR or double-play runs "
                     "for these seasons)")
    if "framing" in newest["headline"] and "framing" not in head:
        fr = _first_with(st, "framing", "headline")
        missing.append("framing")
        why_h.append(f"no catcher framing (FanGraphs' WAR carries it from {fr})")
    if "xhem" in newest["headline"] and "xhem" not in head:
        xf = _first_with(st, "xhem", "headline")
        missing.append("xhem")
        why_h.append(f"batting is FanGraphs' alone (the xHEM+ part starts in {xf})")
    if "r2" in newest["realized"] and "r2" not in stp["realized"]:
        r2 = _first_with(st, "r2")
        missing.append("r2")
        why_r.append(f"eWAR realized equals eWAR (its runs-allowed pitching starts in {r2})")
    span = _span(first, last)
    why = why_h + why_r
    return {"text": text, "text_headline": text_h + ".", "missing": missing,
            "short": (f"{span}: " + "; ".join(why) + ".") if why else "",
            "short_headline": (f"{span}: " + "; ".join(why_h) + ".") if why_h else "",
            "short_realized": (f"{span}: " + "; ".join(why_r) + ".") if why_r else "",
            "reason_headline": "; ".join(why_h), "reason_realized": "; ".join(why_r)}


def season_groups(vintage: dict | None = None, v3: dict | None = None) -> list[dict]:
    """Maximal runs of consecutive seasons with one stamp (gate part 2), oldest first:
    {"first", "last", "headline", "realized", "bsr_label", "text", "text_headline",
    "missing", "short", "short_headline", "short_realized", "reason_headline",
    "reason_realized"}."""
    default = vintage is None and v3 is None
    if default and "groups" in _MEMO:
        return _MEMO["groups"]
    st = stamps(vintage, v3)
    out: list[dict] = []
    key = None
    for s in sorted(st):
        k = (tuple(st[s]["headline"]), tuple(st[s]["realized"]), st[s]["bsr_label"])
        if out and k == key and out[-1]["last"] == s - 1:
            out[-1]["last"] = s
        else:
            out.append({"first": s, "last": s, "headline": list(k[0]), "realized": list(k[1]),
                        "bsr_label": k[2]})
            key = k
    for g in out:
        g.update(_sentence(g["first"], g["last"], st[g["first"]], st))
    if default:
        _MEMO["groups"] = out
    return out


def merged_shorts(groups: list[dict], seasons, series: str) -> list[str]:
    """The `short` sentences for one series ("headline" or "realized"), with
    neighbouring groups that lack the same parts joined into one span, kept where
    the span holds any of `seasons`: oldest first, [] when none lacks a part."""
    key = "reason_" + series
    runs: list[list] = []
    for g in groups:
        why = g.get(key) or ""
        if not why:
            continue
        if runs and runs[-1][2] == why and runs[-1][1] == g["first"] - 1:
            runs[-1][1] = g["last"]
        else:
            runs.append([g["first"], g["last"], why])
    held = [int(y) for y in seasons]
    return [f"{_span(a, b)}: {why}." for a, b, why in runs if any(a <= y <= b for y in held)]


def group_for(season: int, groups: list[dict] | None = None) -> dict | None:
    for g in (season_groups() if groups is None else groups):
        if g["first"] <= int(season) <= g["last"]:
            return g
    return None


# ---------------------------------------------------------------------------
# CORE and FULL (gate part 3, amendment 9.1)
# ---------------------------------------------------------------------------

def rpw_fg(hit: dict) -> float:
    """FanGraphs' own per-season runs per win: sum rar / sum war over hitting rows with
    abs(war) >= 0.5 (gate part 3)."""
    rows = [r for r in hit.values() if abs(_num(r.get("war"))) >= 0.5]
    num = sum(_num(r.get("rar")) for r in rows)
    den = sum(_num(r.get("war")) for r in rows)
    if not rows or den == 0:
        raise EwarHistoryRefusal("no hitting row with abs(war) >= 0.5 to read FanGraphs' conversion from")
    return num / den


def _recentre(raw: dict[int, float], expo: dict[int, float]) -> dict[int, float]:
    tot_raw = sum(raw.get(k, 0.0) for k in expo)
    tot_expo = sum(max(0.0, v) for v in expo.values())
    if tot_expo <= 0:
        return {k: raw.get(k, 0.0) for k in expo}
    rate = tot_raw / tot_expo
    return {k: raw.get(k, 0.0) - max(0.0, expo[k]) * rate for k in expo}


def core_full(season: int, vintage: dict | None = None, v3: dict | None = None,
              stamp: dict | None = None) -> dict:
    """{"rpw_fg", "bat": {mlbam: row}, "pit": {mlbam: row}} for one season, each row
    {"war", "core", "full", "real", "bsr_rest", "framing", "eabs", "xhem", "r2", "pa"/"ip"}.
    xhem is the headline-only xHEM+ part (EBR_GATE.md 11.11; hitting side), read from the
    block's parts; eabs is the rest of the headline departure."""
    vin, pay = _inputs(vintage, v3)
    s = int(season)
    stp = stamp or _stamp(vin, pay, s)
    hit, pit = _season_rows(vin, s)
    rpw = rpw_fg(hit)
    pa = {m: _num(r.get("plateAppearances")) for m, r in hit.items()}
    b_raw = ({m: _num(r.get("baseRunning")) - _num(r.get("wSb")) for m, r in hit.items()}
             if "bsr_rest" in stp["headline"] else {})
    f_raw = {m: _frm(r) for m, r in hit.items()} if "framing" in stp["headline"] else {}
    B = _recentre(b_raw, pa)
    Fr = _recentre(f_raw, pa)
    players = pay.get("players") or {}

    def _dep(mid: int) -> dict:
        return (players.get(str(mid)) or {}).get(str(s)) or {}

    bat, pitd = {}, {}
    for m, r in hit.items():
        if r.get("war") is None:
            continue
        war = _num(r.get("war"))
        b, fr = B.get(m, 0.0) / rpw, Fr.get(m, 0.0) / rpw
        blk = _dep(m)
        dh = _num((blk.get("dh") or {}).get("bat"))
        dr = _num((blk.get("dr") or {}).get("bat"))
        x = _num(((blk.get("parts") or {}).get("xhem") or {}).get("wins"))
        core = war - (b + fr)
        bat[m] = {"war": war, "core": core, "full": war + dh, "real": war + dr,
                  "bsr_rest": b, "framing": fr, "eabs": dh - x, "xhem": x, "r2": dr - (dh - x),
                  "pa": pa.get(m, 0.0)}
    for m, r in pit.items():
        if r.get("war") is None:
            continue
        war = _num(r.get("war"))
        blk = _dep(m)
        dh = _num((blk.get("dh") or {}).get("pit"))
        dr = _num((blk.get("dr") or {}).get("pit"))
        pitd[m] = {"war": war, "core": war, "full": war + dh, "real": war + dr,
                   "bsr_rest": 0.0, "framing": 0.0, "eabs": dh, "xhem": 0.0, "r2": dr - dh,
                   "ip": _num(r.get("outs")) / 3.0}
    return {"rpw_fg": rpw, "bat": bat, "pit": pitd}


# ---------------------------------------------------------------------------
# the agreement check (gate part 4)
# ---------------------------------------------------------------------------

def _check_identities(s: int, cf: dict, stp: dict, chk: dict) -> dict:
    worst = {"row_headline": 0.0, "row_realized": 0.0}
    for side in ("bat", "pit"):
        for m, r in cf[side].items():
            e1 = abs(r["full"] - r["core"] - (r["bsr_rest"] + r["framing"] + r["eabs"] + r["xhem"]))
            e2 = abs(r["real"] - r["core"] - (r["bsr_rest"] + r["framing"] + r["eabs"] + r["r2"]))
            worst["row_headline"] = max(worst["row_headline"], e1)
            worst["row_realized"] = max(worst["row_realized"], e2)
            if e1 > TOL_ROW or e2 > TOL_ROW:
                raise EwarHistoryRefusal(f"{s} {side} {m}: FULL - CORE is not the sum of the named parts "
                                         f"({e1:.3g}, {e2:.3g} wins)")
    # Amendment 9.2: the artifact stores each departure at 6 decimals, so a side's
    # stored departures sum to zero within STORE_ROUND per listed row.
    r2_bound = _num(chk.get("r2_rounding_bound")) + TOL_SIDE
    sums = {}
    for side in ("bat", "pit"):
        rows = cf[side].values()
        w = sum(r["war"] for r in rows)
        c = sum(r["core"] for r in rows)
        f = sum(r["full"] for r in rows)
        z = sum(r["real"] for r in rows)
        tol_f = TOL_SIDE + STORE_ROUND * sum(1 for r in rows if (r["eabs"] + r["xhem"]) != 0.0)
        tol_z = TOL_SIDE + STORE_ROUND * sum(1 for r in rows if (r["eabs"] + r["r2"]) != 0.0)
        if side == "pit":
            tol_z = max(tol_z, r2_bound)
        sums[side] = {"fwar": w, "core_minus_fwar": c - w, "full_minus_fwar": f - w,
                      "realized_minus_fwar": z - w, "tol_full": tol_f, "tol_realized": tol_z}
        if abs(c - w) > TOL_SIDE:
            raise EwarHistoryRefusal(f"{s} {side}: CORE sums {c - w:+.3g} wins off published fWAR")
        if abs(f - w) > tol_f:
            raise EwarHistoryRefusal(f"{s} {side}: FULL sums {f - w:+.3g} wins off published fWAR")
        if abs(z - w) > tol_z:
            raise EwarHistoryRefusal(f"{s} {side}: FULL realized sums {z - w:+.3g} wins off published fWAR")
    bare = not any(p in stp["realized"] or p in stp["headline"] for p in NON_CORE)
    if bare:
        for side in ("bat", "pit"):
            for m, r in cf[side].items():
                if not (r["core"] == r["full"] == r["real"]):
                    raise EwarHistoryRefusal(f"{s} {side} {m}: a season with no non-core part has CORE "
                                             "different from FULL")
    return {"max_row_error": worst, "side_sums": sums, "core_equals_full_exactly": bare}


def _spearman(a: list[float], b: list[float]) -> float | None:
    if len(a) < 3:
        return None
    from scipy.stats import spearmanr
    rho = spearmanr(a, b).correlation
    return None if rho is None or math.isnan(rho) else round(float(rho), 4)


def _sd(xs: list[float]) -> float:
    if not xs:
        return 0.0
    mu = sum(xs) / len(xs)
    return math.sqrt(sum((x - mu) ** 2 for x in xs) / len(xs))


def _gap(rows: list[dict], term, frame, target="full") -> dict:
    """One part's (or the total's) gap block over one side's rows (gate part 4)."""
    vals = [term(r) for r in rows]
    moved = sum(1 for r, v in zip(rows, vals) if round(r["core"], 1) != round(r["core"] + v, 1))
    fr = [r for r in rows if frame(r)]
    return {"rows": len(rows), "nonzero": sum(1 for v in vals if abs(v) > 1e-12),
            "sd": round(_sd(vals), 4), "mean_abs": round(sum(abs(v) for v in vals) / len(vals), 4) if vals else 0.0,
            "max_abs": round(max((abs(v) for v in vals), default=0.0), 4),
            "cells_moved_1dp": moved, "share_moved_1dp": round(moved / len(rows), 4) if rows else 0.0,
            "spearman_core_full": _spearman([r["core"] for r in fr], [r["core"] + term(r) for r in fr]),
            "frame_n": len(fr)}


def gap_report(s: int, cf: dict, stp: dict) -> dict:
    bat, pit = list(cf["bat"].values()), list(cf["pit"].values())
    hit_frame = lambda r: r.get("pa", 0.0) >= MIN_PA    # noqa: E731
    pit_frame = lambda r: r.get("ip", 0.0) >= MIN_IP    # noqa: E731
    out: dict = {"bat": {}, "pit": {}}
    for p in ("bsr_rest", "framing", "eabs", "xhem"):
        if p in stp["headline"]:
            out["bat"][p] = _gap(bat, lambda r, p=p: r[p], hit_frame)
    if "eabs" in stp["headline"]:
        out["pit"]["eabs"] = _gap(pit, lambda r: r["eabs"], pit_frame)
    if "r2" in stp["realized"]:
        out["pit"]["r2"] = _gap(pit, lambda r: r["r2"], pit_frame)
    out["bat"]["total_headline"] = _gap(bat, lambda r: r["full"] - r["core"], hit_frame)
    out["pit"]["total_headline"] = _gap(pit, lambda r: r["full"] - r["core"], pit_frame)
    out["pit"]["total_realized"] = _gap(pit, lambda r: r["real"] - r["core"], pit_frame)
    return out


def build(vintage: dict | None = None, v3: dict | None = None, log=print) -> dict:
    """The record of data/ewar_history.json: stamps, groups, the identities' results and
    the gap report per season and part. Nothing per player (gate part 5)."""
    vin, pay = _inputs(vintage, v3)
    st = stamps(vin, pay)
    if not st:
        raise EwarHistoryRefusal("the vintage has no frozen season from the first season on")
    groups = season_groups(vin, pay)
    per: dict[str, dict] = {}
    for s in sorted(st):
        chk = (pay.get("checks") or {}).get(str(s)) or {}
        cf = core_full(s, vin, pay, st[s])
        ident = _check_identities(s, cf, st[s], chk)
        per[str(s)] = {"stamp": st[s], "rpw_fg": round(cf["rpw_fg"], 4), "identities": ident,
                       "gap": gap_report(s, cf, st[s])}
        on = set(st[s]["realized"]) | set(st[s]["headline"])
        log(f"  {s}: parts {'+'.join(p for p, _l, _s in PARTS if p in NON_CORE and p in on) or 'core only'}; "
            f"rpw_fg {cf['rpw_fg']:.4f}; identities hold")
    return {
        "schema": 1,
        "model": "ewar_history",
        "version": VERSION,
        "generated_at": _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat(),
        "registration": GATE_DOC,
        "first_season": min(st), "last_season": max(st),
        "why_it_stops": WHY_IT_STOPS,
        "fwar_vintage_id": vin.get("vintage_id"),
        "fwar_vintage_sha256": _sha(fwar_vintage.VINTAGE_PATH),
        "ewar_v3_generated_at": pay.get("generated_at"),
        "ewar_v3_sha256": _sha(ROOT / "data" / "ewar_v3.json"),
        # the xHEM+ part is listed only when a season carries it (EBR_GATE.md 11.11)
        "parts": [{"id": p, "label": lab, "series": ser, "core": p in CORE_PARTS} for p, lab, ser in PARTS
                  if p != "xhem" or any("xhem" in v["headline"] for v in st.values())],
        "groups": groups,
        "constants": {"bsr_eps_runs": BSR_EPS, "framing_eps_runs": FRM_EPS, "tol_row_wins": TOL_ROW,
                      "tol_side_wins": TOL_SIDE, "frame_min_pa": MIN_PA, "frame_min_ip": MIN_IP},
        "field_key": {
            "stamp": "the parts each series carries in the season, measured on its rows (gate part 2)",
            "gap": ("per side and part, in wins: rows, nonzero rows, sd, mean_abs, max_abs, cells whose "
                    "CORE and CORE plus the part differ at one decimal, and the Spearman correlation of "
                    "CORE with CORE plus the part over hitters with 300+ PA or pitchers with 50+ IP; "
                    "descriptive, it decides nothing (gate part 4)"),
            "identities": "the hard checks of gate part 4; a miss refuses the build",
        },
        "seasons": per,
        "note": ("CORE is eWAR from the parts present in every season 2000 to 2026; FULL is eWAR as "
                 "served. CORE is recorded here as per-season summaries only and is never displayed."),
    }


def write(payload: dict, path: Path | None = None) -> Path:
    import os
    path = Path(path or OUT)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    tmp.write_text(json.dumps(payload, indent=1, ensure_ascii=True, allow_nan=False) + "\n",
                   encoding="utf-8")
    os.replace(tmp, path)
    return path
