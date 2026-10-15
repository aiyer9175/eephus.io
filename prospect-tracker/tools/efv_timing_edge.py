# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The eFV timing-edge read (EFV_BEAT_TIMING_EDGE; owner EW3-11, 2026-10-15; method
docs/efv-v2/EFV_BEAT_TIMING_EDGE.md, committed before this module existed).

WHAT IT MEASURES. Every earlier eFV read froze eFV and consensus at the same preseason
point. Here, at six read dates inside each development season (the last day of April to
September), eFV v5 COMBINED is re-read with its minor league block through the read date
(the season to date, the way the live board reads the current season) and scored against
consensus AS PUBLISHED on or before the read date (the latest board point, never a later
one). Statistic: within (side, year, read date) Spearman, eFV minus consensus, pooled over
read dates by row count; player-clustered bootstrap, B 2000, seed 20261015, one-sided 95
percent lower bound; club-clustered sensitivity.

THE MODELS ARE NOT REFITTED. The development read's fold models (efv5_combined.Fits on
efv5_combined.build_dev, and the V2 fold models the frame carries) are applied to each
row re-read at the read date. Only the anchor (consensus as published), the prior block at
that point and the minor league block move; every candidate column and sidecar keeps its
preseason value (the document, section 5, default D-2).

TO-DATE MINOR LEAGUE LINES. StatsAPI stats=byDateRange from S-01-01 to the read date, per
affiliated minor league sport id and group, cached under .cache/efv_timing_edge/milb_todate
(this tool's own folder; .cache/milb_stats is never written). season_todate() swaps season
S of milb_history.season_splits for those lines inside a block, computes season S's level
norms from them blended with season S-1 by qualified count (milb_history.league_norms' live
rule) and skips the AAA Statcast and park line adjustments on season S.

NO LOOK-AHEAD (asserted): every point read is dated on or before d (every per-source date
too); every to-date file carries its end date d; every kept row debuts after d; candidate
columns and sidecars are the preseason read (dated before S-05-01).

RESERVED FRAMES. Only the development frames are built (efv5_combined.build_dev raises on
list vintages 2020 and 2021 and stops before the 2025 cohort). The spent frames are opened
only on a development PASS (the document, section 9), by a later run.

GATE COMPLIANCE (docs/PROSPECT_ANCHOR_GATE.md): consensus enters as a within-group
percentile and as a rater score; the only groups are side, year, read date and read month.
Nothing here groups, counts or averages rows by consensus-FV level;
test_efv_timing_edge.py scans this source.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import efv_dataset as D  # noqa: E402
import efv_model as V1  # noqa: E402
import efv_v2_model as H  # noqa: E402
import efv_v2_stat as S  # noqa: E402
import efv_vintage_frame as F  # noqa: E402
import milb_history as mh  # noqa: E402
import source_backtest as SB  # noqa: E402

TOOL = "tools/efv_timing_edge.py"
ITEM = "EFV_BEAT_TIMING_EDGE"
DOC = "docs/efv-v2/EFV_BEAT_TIMING_EDGE.md"
REGISTRATION_COMMIT = "d9820e84"
OUT_PATH = ROOT / "data" / "_labs" / "efv5" / "efv_timing_edge.json"
CACHE_DIR = ROOT / ".cache" / "efv_timing_edge" / "milb_todate"

#: The read dates: the last day of each month April to September (D-1).
READ_MMDD: tuple[str, ...] = ("04-30", "05-31", "06-30", "07-31", "08-31", "09-30")
LV_YEARS: tuple[int, ...] = (2017, 2018, 2019)
VM_YEARS: tuple[int, ...] = tuple(range(2017, 2024))
#: No minor league season was played in 2020: its to-date lines are empty.
NO_MILB_SEASONS: frozenset[int] = frozenset({2020})
MINOR_SPORTS: tuple[int, ...] = tuple(mh.MINOR_SPORTS)
GROUPS: tuple[str, ...] = ("hitting", "pitching")
B_DEFAULT = 2000
SEED = 20261015
MIN_GROUP_ROWS = S.MIN_GROUP_ROWS
#: The nightly fetch window (UTC hours, inclusive start, exclusive end): no fetch inside it.
NIGHTLY_UTC = (6, 11)
PAGE = 2000

SCORES = ("v5c_d", "cons_d", "v2_d", "v5c_pre", "v2_pre", "cons_pre")


def read_dates(season: int) -> list[str]:
    return [f"{int(season)}-{m}" for m in READ_MMDD]


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# to-date minor league lines
# ---------------------------------------------------------------------------

def todate_path(group: str, sport: int, season: int, end: str) -> Path:
    return CACHE_DIR / f"{group}_{int(sport)}_{int(season)}_{end}.json"


def _in_nightly_window(now: datetime | None = None) -> bool:
    h = (now or datetime.now(timezone.utc)).hour
    return NIGHTLY_UTC[0] <= h < NIGHTLY_UTC[1]


def _lean(split: dict, sport: int, season: int, group: str, ages: dict) -> dict:
    """milb_history.season_splits' lean row for one date-range split."""
    st = split.get("stat") or {}
    league = (split.get("league") or {}).get("name") or ""
    level = mh._level16(league) if sport == 16 else mh.SPORT_LEVEL.get(sport, "?")
    pid = (split.get("player") or {}).get("id")
    row = {"mlbam": pid, "name": (split.get("player") or {}).get("fullName"),
           "season": int(season), "level": level, "league": league,
           # a date-range line carries no age; the season age is a function of the birth
           # date only, so it is read off the season file (no statistic is)
           "age": st.get("age") if st.get("age") is not None else ages.get(pid)}
    if group == "hitting":
        row.update({
            "pa": st.get("plateAppearances"), "ab": st.get("atBats"),
            "ops": st.get("ops"), "obp": st.get("obp"),
            "slg": st.get("slg"), "avg": st.get("avg"),
            "so": st.get("strikeOuts"), "bb": st.get("baseOnBalls"),
            "hr": st.get("homeRuns"),
            "h": st.get("hits"), "doubles": st.get("doubles"),
            "triples": st.get("triples"), "ibb": st.get("intentionalWalks"),
            "hbp": st.get("hitByPitch"), "sf": st.get("sacFlies"),
            "sb": st.get("stolenBases"),
        })
    else:
        row.update({
            "ip": st.get("inningsPitched"), "bf": st.get("battersFaced"),
            "era": st.get("era"), "so": st.get("strikeOuts"),
            "bb": st.get("baseOnBalls"), "g": st.get("gamesPlayed"),
            "gs": st.get("gamesStarted"),
        })
    return row


def _read_doc(p: Path) -> dict | None:
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(doc, dict) or not isinstance(doc.get("rows"), list):
        return None
    return doc


def fetch_todate(sport: int, season: int, group: str, end: str, *, fetch: bool = True,
                 log=print) -> list[dict]:
    """Every player's line for (sport, season, group) from S-01-01 through `end`. Season
    2020 is empty (no season). Raises when the file is absent and fetch is False, or when
    a fetch is asked for inside the nightly window."""
    season = int(season)
    if season in NO_MILB_SEASONS:
        return []
    if str(end)[:4] != str(season):
        raise ValueError(f"end {end} is not inside season {season}")
    p = todate_path(group, sport, season, end)
    doc = _read_doc(p) if p.exists() else None
    if doc is not None:
        if doc.get("end") != end or int(doc.get("season")) != season:
            raise AssertionError(f"{p.name}: receipt end {doc.get('end')} is not {end}")
        return doc["rows"]
    if not fetch:
        raise FileNotFoundError(f"to-date lines not cached: {p}")
    if _in_nightly_window():
        raise RuntimeError("no fetch inside the 06:00 to 11:00 UTC nightly window")
    start = f"{season}-01-01"
    ages = {r.get("mlbam"): r.get("age")
            for r in mh.season_splits(sport, season, group, fetch=False) if r.get("mlbam")}
    splits: list[dict] = []
    offset = 0
    url0 = ""
    while True:
        url = (f"{mh.BASE}?stats=byDateRange&group={group}&season={season}"
               f"&sportIds={sport}&playerPool=ALL&limit={PAGE}&offset={offset}"
               f"&startDate={start}&endDate={end}")
        url0 = url0 or url
        last = None
        for attempt in range(4):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=60) as r:
                    d = json.loads(r.read())
                last = None
                break
            except Exception as e:  # noqa: BLE001
                last = e
                time.sleep(2 + 3 * attempt)
        if last is not None:
            raise RuntimeError(f"fetch failed {url}: {last}")
        block = (d.get("stats") or [{}])[0]
        page = block.get("splits") or []
        splits.extend(page)
        total = block.get("totalSplits") or len(splits)
        offset += len(page)
        if not page or offset >= total:
            break
    rows = [_lean(s, sport, season, group, ages) for s in splits]
    out = {"tool": TOOL, "season": season, "sport": int(sport), "group": group,
           "start": start, "end": end, "fetched_at": _now(), "url": url0,
           "n": len(rows), "rows": rows}
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, p)
    log(f"  fetched {p.name}: {len(rows)} lines")
    return rows


def fetch_all(seasons, *, log=print) -> dict:
    """Every to-date file the read needs. Returns {name: n lines}."""
    got = {}
    for season in seasons:
        if int(season) in NO_MILB_SEASONS:
            continue
        for end in read_dates(season):
            for sport in MINOR_SPORTS:
                for group in GROUPS:
                    rows = fetch_todate(sport, season, group, end, log=log)
                    got[todate_path(group, sport, season, end).name] = len(rows)
    return got


#: (sport, season, group) -> the cache file's rows, for seasons other than the read season
#: (immutable on disk; read once per process instead of once per row).
_PAST: dict = {}


@contextmanager
def season_todate(season: int, end: str):
    """Inside the block, season `season` of milb_history reads the to-date lines through
    `end` (sport 1 reads empty: no major league line enters a minor league block), its
    level norms come from those lines blended with the prior season by qualified count,
    and the AAA Statcast and park line adjustments skip it. Every other season reads the
    cache files only (fetch=False), exactly as on disk. player_index and league_norms are
    swapped for season `season` only, so their lru caches never hold a to-date entry."""
    season = int(season)
    orig_ss, orig_ln, orig_pi = mh.season_splits, mh.league_norms, mh.player_index
    orig_x, orig_p = D._xline, D._parkline
    memo: dict = {}

    def ss(sport_id, s, group, fetch=True):
        if int(s) == season:
            if int(sport_id) not in MINOR_SPORTS:
                return []
            k = ("ss", int(sport_id), group)
            if k not in memo:
                memo[k] = fetch_todate(int(sport_id), season, group, end, fetch=False)
            return list(memo[k])
        k = (int(sport_id), int(s), group)
        if k not in _PAST:
            _PAST[k] = orig_ss(sport_id, s, group, fetch=False)
        return list(_PAST[k])

    def pi(s, group, fetch=True):
        if int(s) != season:
            return orig_pi(s, group, fetch)
        k = ("pi", group)
        if k not in memo:
            idx: dict = {}
            for sport in mh.ALL_SPORTS:
                for r in ss(sport, s, group):
                    if r.get("mlbam"):
                        idx.setdefault(int(r["mlbam"]), []).append(r)
            memo[k] = idx
        return memo[k]

    def ln(s, level, group, fetch=True):
        if int(s) != season:
            return orig_ln(s, level, group, fetch=False)
        k = ("ln", level, group)
        if k in memo:
            return memo[k]
        rows = []
        for sport, lv in mh.SPORT_LEVEL.items():
            if lv == level or (level in ("DSL", "CPX") and sport == 16):
                rows.extend(r for r in ss(sport, s, group) if r.get("level") == level)
        out = mh.level_norms_from_rows(rows, group)
        if out is not None:
            prior = orig_ln(season - 1, level, group, fetch=False)
            if prior and (prior.get("n") or 0) > 0:
                n, n_prior = out["n"], prior["n"]
                w = n / (n + n_prior)
                blended = {}
                for kk, v in out.items():
                    if kk == "n":
                        continue
                    blended[kk] = (round(w * v + (1 - w) * prior[kk], 4)
                                   if prior.get(kk) is not None else v)
                out = blended | {"n": n, "norm_prior_blend_w": round(w, 3)}
        memo[k] = out
        return out

    def _skip(mod):
        if mod is None:
            return None
        return SimpleNamespace(maybe_adjust_row=lambda row, mlbam, s, level, side:
                               row if int(s or 0) == season
                               else mod.maybe_adjust_row(row, mlbam, s, level, side))

    mh.season_splits, mh.league_norms, mh.player_index = ss, ln, pi
    D._xline, D._parkline = _skip(orig_x), _skip(orig_p)
    try:
        yield
    finally:
        mh.season_splits, mh.league_norms, mh.player_index = orig_ss, orig_ln, orig_pi
        D._xline, D._parkline = orig_x, orig_p


# ---------------------------------------------------------------------------
# a row re-read at a read date
# ---------------------------------------------------------------------------

def _pt_cons(pt: dict):
    v = pt.get("consensus_fv_raw", pt.get("consensus_fv"))
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def point_at(rec: dict | None, season: int, d: str) -> dict | None:
    """The record's latest board point dated in [S-01-01, d]: the board as it stood at d."""
    if not rec:
        return None
    lo = f"{int(season)}-01-01"
    pts = [p for p in (rec.get("points") or [])
           if p.get("snapshot_date") and lo <= str(p["snapshot_date"])[:10] <= d]
    if not pts:
        return None
    return sorted(pts, key=lambda p: p["snapshot_date"])[-1]


def assert_point_dated(pt: dict, d: str) -> None:
    sd = str(pt.get("snapshot_date"))[:10]
    if sd > d:
        raise AssertionError(f"point {sd} after read date {d}")
    for s, ps in (pt.get("per_source") or {}).items():
        psd = (ps or {}).get("snapshot_date")
        if psd and str(psd)[:10] > d:
            raise AssertionError(f"source {s} dated {psd} after read date {d}")


def preseason_point(rec: dict | None, season: int) -> dict | None:
    lo, hi = D.preseason_window(int(season))
    pts = [p for p in ((rec or {}).get("points") or [])
           if p.get("snapshot_date") and lo <= p["snapshot_date"] < hi]
    return sorted(pts, key=lambda p: p["snapshot_date"])[-1] if pts else None


def lv_feats(fr: dict, rec: dict, side: str, pt: dict, milb) -> dict:
    """efv_model._vec on an F-LV frame row with its prior block at `pt` and `milb`."""
    m = dict(fr, prior=D._prior_features(rec, pt, side), milb=milb)
    return V1._vec(H.lv_model_row(m), side)


def vm_feats(raw: dict, rec: dict, side: str, pt: dict, milb) -> dict:
    """efv_model._vec on a matrix row with its prior block at `pt` (pinned_inputs' rule)
    and `milb`."""
    row = dict(raw)
    pre = D._prior_features(rec, pt, side)
    pre["consensus_fv_raw"] = _pt_cons(pt)
    row.update(pre)
    row.pop("fv_effective", None)
    row["milb"] = milb
    return V1._vec(row, side)


def lv_milb_todate(fr: dict, side: str):
    """The minor league block of an F-LV row, the live board's walk (the read season
    first). Call inside season_todate(V, d)."""
    return D._milb_features(fr.get("mlbam_id"), int(fr["vintage"]) + 1, fr.get("birth_date"),
                            side, cutoff=None, first_season_floor=int(fr["milb_floor"]))


def vm_milb_todate(raw: dict, side: str, season: int):
    return D._milb_features(raw.get("mlbam_id"), int(season) + 1, raw.get("birth_date"), side,
                            cutoff=None)


# ---------------------------------------------------------------------------
# the build
# ---------------------------------------------------------------------------

def _cmb():
    import efv5_combined as CMB
    return CMB


def build(*, log=print) -> dict:
    """The development inputs and fits, then every scored row re-read at every read date.
    Returns {"rows": [...], "receipts": {...}}."""
    CMB = _cmb()
    import efv5_group_drivers as G
    BT, _B4 = CMB._tools()
    t0 = time.time()
    out_rows: list[dict] = []
    rec: dict = {"parity": {}, "dropped": {}, "membership": {}, "points": {}, "milb": {}}
    with G.registered(), CMB.v5c_names():
        inp, frames_lv, _crec = CMB.build_dev(log=log)
        fits = CMB.Fits(inp)
        log(f"development inputs built ({round(time.time() - t0, 1)} s)")
        universe = F.load_universe()
        asof = D.asof_records()
        raw_by_side = CMB._raw_by_side()
        for fid in BT.FRAMES_DEV:
            kind = BT.FRAME_KIND[fid]
            for side in F.SIDES:
                cols = (inp.cols.get(fid) or {}).get(side) or {}
                for fold, blk in sorted(inp.frames[fid]["by_side"][side].items()):
                    Y = int(fold)
                    f = fits.fold(fid, side, Y)
                    m5 = f["model"]
                    m2 = blk["v2_model"]
                    test_by = {r["player_key"]: r for r in blk["test"]}
                    scored = list(blk["scored"])
                    if kind == "lv":
                        fr_by = {r["player_key"]: r for r in frames_lv[side][Y][0]}
                        lab_by = {lab["player_key"]: lab for lab in frames_lv[side][Y][1]}
                    else:
                        fr_by, lab_by = {}, {}
                    base = []
                    for c in scored:
                        k = c["key"]
                        t = test_by[k]
                        if kind == "lv":
                            fr = fr_by[k]
                            r0 = universe[k]
                            lab = lab_by[k]
                            dy = lab.get("debut_year")
                            dd, ph, _frm = D.debut_day_for_cutoff(r0)
                            debut = (None if dy is None or int(dy) != Y else
                                     (str(dd)[:10] if dd and str(dd)[:4] == str(Y) and not ph
                                      else f"{Y}-01-01"))
                            lo, hi = fr["window"]
                            win = sorted((p for p in r0.get("points") or []
                                          if p.get("snapshot_date")
                                          and lo <= p["snapshot_date"][:10] < hi),
                                         key=lambda p: p["snapshot_date"])
                            pre_pt = win[-1] if win else None
                            # parity: the builder at the preseason point and milb reproduces
                            # the development read's own features
                            if lv_feats(fr, r0, side, pre_pt, fr["milb"]) != t["feats"]:
                                raise RuntimeError(f"lv {side} {Y} {k}: preseason parity fails")
                            r3 = lab.get("r3")
                        else:
                            raw = raw_by_side[side][k]
                            r0 = asof.get(k)
                            cut = str(raw.get("cutoff") or "")[:10]
                            ok = (len(cut) == 10 and cut[:4] == str(Y)
                                  and not raw.get("debut_date_is_placeholder"))
                            debut = cut if ok else f"{Y}-01-01"
                            pre_pt = preseason_point(r0, Y)
                            if vm_feats(raw, r0, side, pre_pt, raw.get("milb")) != t["feats"]:
                                raise RuntimeError(f"vm {side} {Y} {k}: preseason parity fails")
                            fr = None
                            r3 = None
                        base.append({"c": c, "t": t, "fr": fr, "raw": None if kind == "lv" else raw,
                                     "rec": r0, "debut": debut, "r3": r3,
                                     "club": (pre_pt or {}).get("org")})
                    rec["parity"][f"{fid}|{side}|{Y}"] = len(base)
                    for d in read_dates(Y):
                        keep = [b for b in base if b["debut"] is None or b["debut"] > d]
                        rec["membership"][f"{fid}|{side}|{Y}|{d}"] = {
                            "scored": len(base), "kept": len(keep),
                            "no_debut_day": sum(1 for b in base if b["debut"] == f"{Y}-01-01")}
                        rows_d, rows_pre, meta = [], [], []
                        moved_pts = 0
                        with season_todate(Y, d):
                            for b in keep:
                                pt = point_at(b["rec"], Y, d)
                                if pt is None or _pt_cons(pt) is None:
                                    raise RuntimeError(f"{fid} {side} {Y} {b['c']['key']}: no point by {d}")
                                assert_point_dated(pt, d)
                                if b["debut"] is not None and not b["debut"] > d:
                                    raise AssertionError("a kept row debuted by the read date")
                                if kind == "lv":
                                    milb = lv_milb_todate(b["fr"], side)
                                    feats = lv_feats(b["fr"], b["rec"], side, pt, milb)
                                else:
                                    milb = vm_milb_todate(b["raw"], side, Y)
                                    feats = vm_feats(b["raw"], b["rec"], side, pt, milb)
                                t = b["t"]
                                cons_d = _pt_cons(pt)
                                if cons_d != float(b["c"]["grades"][BT.CONS]):
                                    moved_pts += 1
                                rows_d.append(dict(t, fv=cons_d, feats=feats,
                                                   v2=H.v2_row(feats, t.get("extra"))))
                                rows_pre.append(dict(t))
                                meta.append({"pt_date": str(pt["snapshot_date"])[:10],
                                             "cons_d": cons_d,
                                             "milb_season": (milb or {}).get("milb_season")})
                        if not rows_d:
                            continue
                        rec["points"][f"{fid}|{side}|{Y}|{d}"] = {"rows": len(rows_d),
                                                                   "consensus_moved": moved_pts}
                        rec["milb"][f"{fid}|{side}|{Y}|{d}"] = {
                            "rows": len(rows_d),
                            "read_season_line": sum(1 for x in meta if x["milb_season"] == Y)}
                        p5 = CMB.predict_combined(m5, CMB.attach(rows_d, side, cols, "test"))
                        p2 = H.predict_v2(m2, rows_d)
                        q5 = CMB.predict_combined(m5, CMB.attach(rows_pre, side, cols, "test"))
                        q2 = H.predict_v2(m2, rows_pre)
                        for i, b in enumerate(keep):
                            c = b["c"]
                            out_rows.append({
                                "frame": fid, "side": side, "year": Y, "d": d,
                                "month": d[5:7], "key": c["key"], "club": b["club"] or "none",
                                "group": f"{side}|{Y}|{d}",
                                "y": float(c["outcome"]["war"]),
                                "r3": b["r3"],
                                "v5c_d": float(p5[i]["order_idx"]),
                                "cons_d": float(meta[i]["cons_d"]),
                                "v2_d": float(p2[i]["order_idx"]),
                                "v5c_pre": float(q5[i]["order_idx"]),
                                "v2_pre": float(q2[i]["order_idx"]),
                                "cons_pre": float(c["grades"][BT.CONS]),
                                "pt_date": meta[i]["pt_date"],
                                "milb_season": meta[i]["milb_season"]})
                    log(f"  {fid} {side} {Y}: {len(base)} scored rows re-read at "
                        f"{len(read_dates(Y))} dates ({round(time.time() - t0, 1)} s)")
    rec["elapsed_build_s"] = round(time.time() - t0, 1)
    return {"rows": out_rows, "receipts": rec}


# ---------------------------------------------------------------------------
# the statistic
# ---------------------------------------------------------------------------

def paired_within(rows: list[dict], a: str, b: str, *, label: str = "y",
                  cluster: str = "key", B: int = B_DEFAULT, seed: int = SEED) -> dict:
    """within(a) - within(b) over the rows' (side, year, read date) groups of at least
    MIN_GROUP_ROWS rows, paired; a clustered bootstrap (scores fixed) gives the two-sided
    CI95 and the one-sided 95 percent lower bound (the 5th percentile)."""
    sel = [r for r in rows if r.get(label) is not None]
    out = {"a": a, "b": b, "label": label, "cluster": cluster, "n": len(sel),
           "n_clusters": len({r[cluster] for r in sel}), "B": int(B), "seed": int(seed),
           "delta": None, "ci95": None, "lb95_one_sided": None, "sd": None, "B_used": 0}
    if not sel:
        out["status"] = "no rows"
        return out
    av = np.array([r[a] for r in sel], dtype=np.float64)
    bv = np.array([r[b] for r in sel], dtype=np.float64)
    yy = np.array([r[label] for r in sel], dtype=np.float64)
    codes = np.array([r["group"] for r in sel])
    keep = S.kept_groups(codes, MIN_GROUP_ROWS)
    out["groups_kept"] = int(len(keep))
    out["rows_in_kept_groups"] = int(np.isin(codes, keep).sum())
    full = np.arange(len(sel))
    pa, pb = S._within_pair(av, bv, yy, codes, keep, full)
    if pa is None or pb is None:
        out["status"] = "undefined"
        return out
    out.update(within_a=round(pa, 5), within_b=round(pb, 5), delta=round(pa - pb, 5))
    ids = {k: i for i, k in enumerate(dict.fromkeys(r[cluster] for r in sel))}
    order, starts, lens = SB._cluster_layout(np, [ids[r[cluster]] for r in sel])
    rng = np.random.default_rng(int(seed))
    diffs = []
    for _ in range(int(B)):
        idx = SB._cluster_draw(np, rng, order, starts, lens)
        if idx.size < 8:
            continue
        xa, xb = S._within_pair(av, bv, yy, codes, keep, idx)
        if xa is not None and xb is not None:
            diffs.append(xa - xb)
    if len(diffs) <= 49:
        out["status"] = "too few usable draws"
        return out
    dd = np.asarray(diffs)
    q = np.quantile(dd, [0.025, 0.05, 0.975])
    out.update(ci95=[round(float(q[0]), 4), round(float(q[2]), 4)],
               lb95_one_sided=round(float(q[1]), 4), sd=round(float(dd.std(ddof=1)), 5),
               p_gt_0=round(float((dd > 0).mean()), 4), B_used=len(dd), status="derived")
    return out


def frame_read(rows: list[dict], *, B: int, seed: int, log=print) -> dict:
    """Every comparison of the document on one frame's rows."""
    t0 = time.time()
    blk: dict = {"n_rows": len(rows), "n_players": len({r["key"] for r in rows}),
                 "groups": {}}
    for r in rows:
        blk["groups"][r["group"]] = blk["groups"].get(r["group"], 0) + 1
    blk["primary"] = paired_within(rows, "v5c_d", "cons_d", B=B, seed=seed)
    blk["primary_club"] = paired_within(rows, "v5c_d", "cons_d", cluster="club", B=B, seed=seed)
    blk["v2_d_vs_cons_d"] = paired_within(rows, "v2_d", "cons_d", B=B, seed=seed)
    blk["control_v5c_pre_vs_cons_pre"] = paired_within(rows, "v5c_pre", "cons_pre", B=B, seed=seed)
    blk["control_v2_pre_vs_cons_pre"] = paired_within(rows, "v2_pre", "cons_pre", B=B, seed=seed)
    blk["cons_d_vs_cons_pre"] = paired_within(rows, "cons_d", "cons_pre", B=B, seed=seed)
    blk["v5c_d_vs_v5c_pre"] = paired_within(rows, "v5c_d", "v5c_pre", B=B, seed=seed)
    blk["by_side"] = {s: paired_within([r for r in rows if r["side"] == s], "v5c_d", "cons_d",
                                       B=B, seed=seed) for s in F.SIDES}
    blk["by_month"] = {mo: paired_within([r for r in rows if r["month"] == mo], "v5c_d",
                                         "cons_d", B=B, seed=seed)
                       for mo in sorted({r["month"] for r in rows})}
    blk["by_year"] = {str(y): paired_within([r for r in rows if r["year"] == y], "v5c_d",
                                            "cons_d", B=B, seed=seed)
                      for y in sorted({r["year"] for r in rows})}
    if any(r.get("r3") is not None for r in rows):
        blk["arrival_r3"] = paired_within(rows, "v5c_d", "cons_d", label="r3", B=B, seed=seed)
    blk["elapsed_s"] = round(time.time() - t0, 1)
    p = blk["primary"]
    log(f"  primary delta {p.get('delta')} CI95 {p.get('ci95')} lb95 {p.get('lb95_one_sided')} "
        f"({blk['elapsed_s']} s)")
    return blk


def verdict(frames: dict) -> dict:
    lb = {fid: (frames[fid]["primary"] or {}).get("lb95_one_sided") for fid in frames}
    passed = all(v is not None and v > 0 for v in lb.values()) and set(lb) == {"lv_dev", "vm_dev"}
    return {"rule": ("pooled over read dates by row count, the one-sided 95 percent "
                     "player-clustered lower bound of (eFV v5 COMBINED as of d minus consensus "
                     "as published at d), within Spearman, above 0 on lv_dev AND vm_dev"),
            "lower_bounds": lb, "pass": bool(passed),
            "verdict": "PASS" if passed else "NOT PASS",
            "spent_frames": ("open once each by a later run (the document, section 9)" if passed
                             else "not opened (the document, section 9: only on a development PASS)")}


def _git_head() -> str | None:
    import subprocess
    try:
        r = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True,
                           text=True, timeout=30)
        return r.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def run(*, B: int = B_DEFAULT, log=print, out: Path | None = None) -> dict:
    t0 = time.time()
    built = build(log=log)
    rows = built["rows"]
    frames = {}
    for fid in ("lv_dev", "vm_dev"):
        sel = [r for r in rows if r["frame"] == fid]
        log(f"{fid}: {len(sel)} read-date rows")
        frames[fid] = frame_read(sel, B=B, seed=SEED, log=log)
    doc = {"schema": 1, "tool": TOOL, "item": ITEM, "doc": DOC,
           "registration_commit": REGISTRATION_COMMIT, "code_commit": _git_head(),
           "generated_at": _now(), "role": "development", "served": False,
           "label": {"lv_dev": "W3 (fWAR, frozen label of the development read)",
                     "vm_dev": "career WAR to date (the development read's label)"},
           "read_dates": list(READ_MMDD), "B": int(B), "seed": SEED,
           "min_group_rows": MIN_GROUP_ROWS,
           "frames": frames, "verdict": verdict(frames), "receipts": built["receipts"],
           "elapsed_s": round(time.time() - t0, 1)}
    path = out or OUT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(doc, indent=1, sort_keys=False, default=str)
    if chr(0x2014) in text or chr(0x2013) in text:
        raise AssertionError("dash in the artifact")
    path.write_text(text + "\n", encoding="utf-8")
    log(f"wrote {path} ({doc['elapsed_s']} s); verdict {doc['verdict']['verdict']}")
    return doc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fetch", action="store_true", help="fetch every to-date file")
    ap.add_argument("--run", action="store_true", help="the development read")
    ap.add_argument("--B", type=int, default=B_DEFAULT)
    a = ap.parse_args(argv)
    if a.fetch:
        got = fetch_all(sorted(set(LV_YEARS) | set(VM_YEARS)))
        print(f"{len(got)} to-date files ready")
    if a.run:
        run(B=a.B)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
