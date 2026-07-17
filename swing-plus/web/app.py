# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
FastAPI app for the Swing+ leaderboard.

Run:
    cd ~/swing_plus
    .venv/bin/uvicorn web.app:app --reload

Then open http://localhost:8000

Reads the three CSVs produced by run_leaderboard.py from data/processed/.
Refreshes the in-memory cache automatically when the files change on disk.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

ROOT = Path(__file__).resolve().parent.parent
PROCESSED = ROOT / "data" / "processed"
WEB = ROOT / "web"

app = FastAPI(title="Swing+ Leaderboard")
app.mount("/static", StaticFiles(directory=WEB / "static"), name="static")
templates = Jinja2Templates(directory=WEB / "templates")

_CACHE: dict[str, tuple[float, pd.DataFrame]] = {}
_META_CACHE: dict = {}

# What-if adjustment tool
from whatif import WhatIfScorer, STAT_FMT
SCORER = WhatIfScorer(ROOT)
# adjustable slider -> model feature
ADJUSTABLE = {
    "bat_speed": "bat_speed_mean",
    "attack_angle": "attack_angle_mean",
    "attack_direction": "attack_direction_mean",
    "swing_tilt": "swing_path_tilt_mean",
    "contact_depth": "intercept_ball_minus_batter_pos_y_inches_mean",
}

# Realistic slider bounds (2nd-98th pctile across qualified player-halves) so the
# what-if can't be pushed to values no MLB hitter actually has.
_BOUNDS = {}
try:
    _hb = pd.read_parquet(PROCESSED / "leaderboard_half.parquet")
    # 0.5-99.5 pctile = realistic envelope (up to the hardest swings in MLB)
    # without letting the slider extrapolate to impossible values.
    for _k, _fc in ADJUSTABLE.items():
        _BOUNDS[_k] = [round(float(_hb[_fc].quantile(0.005)), 1),
                       round(float(_hb[_fc].quantile(0.995)), 1)]
except Exception:
    pass

# Percentile reference distributions (value at each 0-100 pctl) across qualified
# career hitters — for "where does this rank" context on the board + adjust tool.
_PCTL_SRC = {
    "swing_plus": "swing_plus", "xwoba": "obs_xwoba", "xwobacon": "obs_xwobacon",
    "avg_ev": "obs_avg_ev", "avg_ev90": "obs_avg_ev90", "barrel_pct": "obs_barrel_pct",
    "hard_hit_pct": "obs_hard_hit_pct", "avg_la": "obs_avg_la",
    "bat_speed": "bat_speed_mean", "attack_angle": "attack_angle_mean",
    "attack_direction": "attack_direction_mean", "swing_tilt": "swing_path_tilt_mean",
    "contact_depth": "intercept_ball_minus_batter_pos_y_inches_mean",
}
_PCTL = {}
try:
    _atb = pd.read_parquet(PROCESSED / "leaderboard_alltime.parquet")
    _qb = _atb[_atb["n_pa"] >= 200]
    for _pk, _pc in _PCTL_SRC.items():
        if _pc in _qb.columns:
            _pv = _qb[_pc].dropna().to_numpy()
            if len(_pv):
                _PCTL[_pk] = [round(float(np.percentile(_pv, i)), 4) for i in range(101)]
except Exception:
    pass


@app.get("/api/percentiles")
def api_percentiles():
    return _PCTL


# Comps (RBF-kernel swing-path similarity) + aging projection
from comps import comps_for
from aging import project as aging_project
import matchup as _matchup


@app.get("/api/comps/{batter}")
def api_comps(batter: int, stand: str | None = None, n: int = 10, shape_only: bool = False):
    res = comps_for(batter, stand=stand, n=n, shape_only=shape_only)
    if not res:
        raise HTTPException(status_code=404, detail="player not in comp index (need PA>=200)")
    return res


@app.get("/api/pitchers")
def api_pitchers(q: str = ""):
    """Search pitchers by name for the matchup tab."""
    if not q or len(q) < 2:
        return {"pitchers": []}
    try:
        return {"pitchers": _matchup.search_pitchers(q)}
    except Exception:
        return {"pitchers": []}


@app.get("/api/matchup/{batter}")
def api_matchup(batter: int, pitcher: int, stand: str | None = None, form: str = "career"):
    """Grade a hitter's swing path against a pitcher's arsenal. form=career|recent."""
    res = _matchup.matchup(batter, pitcher, stand=stand, form=form)
    if not res:
        raise HTTPException(status_code=404, detail="no matchup (missing hitter path or pitcher arsenal vs this hand)")
    res["form"] = form
    return res


@app.get("/api/matchup_top/{batter}")
def api_matchup_top(batter: int, stand: str | None = None, n: int = 5):
    """Top-n best and worst pitcher matchups for a hitter (all arsenal pitchers)."""
    try:
        res = _matchup.top_matchups(batter, stand=stand, n=n)
        return res
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/pitchtype/{batter}")
def api_pitchtype(batter: int, stand: str | None = None):
    """Swing+ by pitch group (Fastball / Breaking / Offspeed) for a player(+stand)."""
    path = PROCESSED / "swing_by_pitch.parquet"
    if not path.exists():
        raise HTTPException(status_code=503, detail="swing_by_pitch.parquet not found.")
    df = pd.read_parquet(path)
    d = df[df["batter"] == batter]
    if stand and "stand" in d.columns and (d["stand"] == stand).any():
        d = d[d["stand"] == stand]
    if d.empty:
        raise HTTPException(status_code=404, detail="no pitch-type splits for player")
    ORDER = {"FB": 0, "BR": 1, "OFF": 2}
    LABEL = {"FB": "Fastball", "BR": "Breaking", "OFF": "Offspeed"}
    has_level = "level" in d.columns

    def rec(r):
        return {"key": r["key"] if has_level else r.get("pgroup"),
                "label": r.get("label", LABEL.get(r.get("pgroup"), r.get("pgroup"))),
                "swing_plus": round(float(r["swing_plus"]), 1),
                "n_swings": int(r["n_swings"]),
                "bat_speed": round(float(r["bat_speed_mean"]), 1) if pd.notna(r.get("bat_speed_mean")) else None,
                "attack_angle": round(float(r["attack_angle_mean"]), 1) if pd.notna(r.get("attack_angle_mean")) else None}

    groups = []
    grp_rows = d[d["level"] == "group"] if has_level else d
    for r in sorted(grp_rows.to_dict("records"), key=lambda x: ORDER.get(x["pgroup"], 9)):
        g = rec(r)
        g["group"] = r["pgroup"]
        g["label"] = LABEL.get(r["pgroup"], r["pgroup"])
        if has_level:
            kids = d[(d["level"] == "type") & (d["pgroup"] == r["pgroup"])].to_dict("records")
            g["children"] = [rec(k) for k in sorted(kids, key=lambda x: -x["n_swings"])]
        else:
            g["children"] = []
        groups.append(g)
    return {"batter": int(batter), "stand": stand, "groups": groups}


_GRADES_CACHE = {}
def _swing_grades() -> pd.DataFrame | None:
    p = PROCESSED / "swing_grades.parquet"
    if not p.exists():
        return None
    mt = p.stat().st_mtime
    if _GRADES_CACHE.get("mt") != mt:
        _GRADES_CACHE["mt"] = mt
        _GRADES_CACHE["df"] = pd.read_parquet(p)
        _GRADES_CACHE.pop("ref", None)
    return _GRADES_CACHE["df"]


def _s20(g):
    """swing_grade is stored on the 20-90 scouting scale (50 = avg, 10 = 1 SD)."""
    return float(g)


def _grade_ref():
    """League reference: per pitch_type (+ 'all'), the sorted array of per-hitter
    MEAN swing grades (20-90), for percentile-ranking a hitter on that pitch."""
    df = _swing_grades()
    if "ref" not in _GRADES_CACHE:
        ref = {}
        per_h = df.groupby(["batter", "pitch_type"]).agg(g=("swing_grade", "mean"), n=("swing_grade", "size"))
        for pt, sub in per_h.groupby(level="pitch_type"):
            arr = np.sort(sub[sub["n"] >= 20]["g"].map(_s20).values)
            if len(arr) >= 20:
                ref[pt] = arr
        allh = df.groupby("batter")["swing_grade"].mean().map(_s20)
        ref["all"] = np.sort(allh.values)
        _GRADES_CACHE["ref"] = ref
    return _GRADES_CACHE["ref"]


def _pctile(arr, v):
    return int(round(float(np.searchsorted(arr, v) / len(arr) * 100))) if arr is not None and len(arr) else None


@app.get("/api/swing_grades/{batter}")
def api_swing_grades(batter: int, stand: str | None = None, pitch_type: str = "all",
                     region: str = "all", limit: int = 60):
    """Per-pitch swing grades for a hitter, filterable by pitch type + location region."""
    df = _swing_grades()
    if df is None:
        raise HTTPException(status_code=503, detail="swing_grades.parquet not found — run swing_grade.py")
    base = df[df["batter"] == batter]
    if stand and (base["stand"] == stand).any():
        base = base[base["stand"] == stand]
    if base.empty:
        raise HTTPException(status_code=404, detail="no graded swings (MLB bat-tracking 2024+ only)")
    st = base["stand"].iloc[0]
    d = base
    if pitch_type and pitch_type != "all":
        d = d[d["pitch_type"] == pitch_type]
    if region and region != "all":
        px, pz = d["plate_x"], d["plate_z"]
        inside = (px > 0.25) if st == "L" else (px < -0.25)
        if region == "inside":
            d = d[inside]
        elif region == "outside":
            d = d[(~inside) & (px.abs() > 0.25)]
        elif region == "up":
            d = d[pz > 3.0]
        elif region == "down":
            d = d[pz < 2.2]
        elif region == "heart":
            d = d[(px.abs() < 0.33) & pz.between(2.0, 3.3)]
    if d.empty:
        return {"batter": batter, "stand": st, "n": 0, "summary": None, "swings": [],
                "pitch_types": sorted(base["pitch_type"].dropna().unique().tolist()),
                "league_grade": 50.0}
    ref = _grade_ref()
    summary = {"n": int(len(d)), "avg_grade": round(_s20(d["swing_grade"].mean()), 1),
               "whiff_pct": round(float(d["whiff"].mean() * 100), 1),
               "exp_xwobacon": round(float(d["exp_con"].mean()), 3),
               "contact_fit": round(float(d["contact_fit"].mean()), 3),
               "avg_bat_speed": round(float(d["bat_speed"].mean()), 1),
               "avg_velo": round(float(d["release_speed"].mean()), 1),
               "pctile": _pctile(ref.get(pitch_type if pitch_type != "all" else "all"), _s20(d["swing_grade"].mean()))}
    top = d.sort_values("swing_grade", ascending=False).head(limit)
    def rec(r):
        return {"season": r["season"], "date": str(r["game_date"]), "pitch_type": r["pitch_type"],
                "velo": round(float(r["release_speed"]), 1), "px": round(float(r["plate_x"]), 2),
                "pz": round(float(r["plate_z"]), 2), "count": f"{int(r['balls'])}-{int(r['strikes'])}",
                "bat_speed": round(float(r["bat_speed"]), 1), "attack_angle": round(float(r["attack_angle"]), 1),
                "result": r["description"], "event": (r["events"] if pd.notna(r["events"]) else None),
                "ev": round(float(r["launch_speed"]), 1) if pd.notna(r["launch_speed"]) else None,
                "xwobacon": round(float(r["estimated_woba_using_speedangle"]), 3) if pd.notna(r["estimated_woba_using_speedangle"]) else None,
                "whiff_prob": round(float(r["whiff_prob"]), 0), "exp_con": round(float(r["exp_con"]), 3),
                "grade": round(_s20(r["swing_grade"]), 1)}
    pts = base["pitch_type"].value_counts()
    # zone heatmap: batter-relative 3x3 (cols inside->away, rows up->down), pitch-type filtered, all locations
    dpt = base if (not pitch_type or pitch_type == "all") else base[base["pitch_type"] == pitch_type]
    bx = dpt["plate_x"] * (1.0 if st == "L" else -1.0)        # inside = +x for both hands
    col = np.where(bx > 0.25, 0, np.where(bx < -0.25, 2, 1))   # 0 inside, 1 mid, 2 away
    row = np.where(dpt["plate_z"] > 3.0, 0, np.where(dpt["plate_z"] < 2.2, 2, 1))  # 0 up,1 mid,2 down
    grid = []
    for rr in range(3):
        for cc in range(3):
            cell = dpt[(row == rr) & (col == cc)]
            grid.append({"row": rr, "col": cc, "n": int(len(cell)),
                         "grade": round(_s20(cell["swing_grade"].mean()), 1) if len(cell) >= 8 else None,
                         "whiff_pct": round(float(cell["whiff"].mean() * 100), 0) if len(cell) >= 8 else None})

    # per-pitch-type grade + percentile vs league (how his swing ranks on each pitch)
    pitch_grades = []
    TYPE_LABEL = {"FF": "4-Seam", "SI": "Sinker", "FC": "Cutter", "SL": "Slider", "ST": "Sweeper",
                  "CU": "Curve", "KC": "Knuckle-Curve", "SV": "Slurve", "CH": "Change", "FS": "Splitter"}
    for pt, sub in base.groupby("pitch_type"):
        if len(sub) < 15:
            continue
        g20 = _s20(sub["swing_grade"].mean())
        pitch_grades.append({"pitch_type": pt, "label": TYPE_LABEL.get(pt, pt), "n": int(len(sub)),
                             "grade": round(g20, 1), "pctile": _pctile(ref.get(pt), g20)})
    pitch_grades.sort(key=lambda x: -x["n"])

    # distribution of his swing grades (20-90) for the current filter, in bins of 5
    bins = list(range(20, 91, 5))
    his = np.clip([_s20(g) for g in d["swing_grade"]], 20, 90)
    hist, _ = np.histogram(his, bins=bins)
    dist = {"bins": bins, "counts": hist.tolist(),
            "his_mean": round(_s20(d["swing_grade"].mean()), 1), "league_mean": 50.0}

    return {"batter": batter, "stand": st, "n": int(len(d)), "summary": summary,
            "swings": [rec(r) for _, r in top.iterrows()],
            "pitch_types": [p for p in pts.index.tolist() if pts[p] >= 15],
            "grid": grid, "pitch_grades": pitch_grades, "dist": dist, "league_grade": 50.0}


@app.get("/api/aging/{batter}")
def api_aging(batter: int, stand: str | None = None):
    # full swing profile from the latest season row for this player(+stand)
    sb = _load("season")
    d = sb[sb["batter"] == batter]
    if stand and "stand" in d.columns and (d["stand"] == stand).any():
        d = d[d["stand"] == stand]
    if d.empty:
        raise HTTPException(status_code=404, detail="no season row for player")
    d = d.sort_values("season")
    row = d.iloc[-1]
    feats = SCORER.feats   # the 9 swing-tracking features
    if not all(f in row.index and pd.notna(row[f]) for f in feats):
        raise HTTPException(status_code=404, detail="incomplete swing profile")
    profile = {f: float(row[f]) for f in feats}
    res = aging_project(batter, profile, season=int(row["season"]))
    if not res:
        raise HTTPException(status_code=404, detail="no birthdate / drift data")
    res["name"] = row["name"]

    # full career: actual Swing+ (raw, same scale as the projection) at the age each season
    import aging as _ag
    bd = _ag.birthdate(batter)
    history = []
    if bd:
        bdts = pd.Timestamp(bd)
        for _, r in d.iterrows():
            if not all(pd.notna(r[f]) for f in feats):
                continue
            age = (pd.Timestamp(f"{int(r['season'])}-07-01") - bdts).days / 365.25
            history.append({"season": int(r["season"]), "age": round(age, 1),
                            "swing_plus": _ag.score_profile({f: float(r[f]) for f in feats})})
    res["history"] = history
    # league-average aging curve over the plotted age span
    lc = _ag.league_curve()
    a_lo = int(min([h["age"] for h in history] + [res["current_age"]])) if history else int(res["current_age"])
    a_hi = max(res["ages"])
    res["league"] = [{"age": a, "swing_plus": lc[a]} for a in range(a_lo, a_hi + 1) if a in lc]
    return res


def _load(view: str) -> pd.DataFrame:
    path = PROCESSED / f"leaderboard_{view}.parquet"
    if not path.exists():
        raise HTTPException(
            status_code=503,
            detail=f"leaderboard_{view}.parquet not found. Run `python run_leaderboard.py` first.",
        )
    mtime = path.stat().st_mtime
    cached = _CACHE.get(view)
    if cached and cached[0] == mtime:
        return cached[1]
    df = pd.read_parquet(path)
    meta = _load_meta()
    if meta is not None and "batter" in df.columns:
        df = df.merge(meta, on="batter", how="left")
    _CACHE[view] = (mtime, df)
    return df


def _load_meta() -> pd.DataFrame | None:
    p = PROCESSED / "player_meta.parquet"
    if not p.exists():
        return None
    mt = p.stat().st_mtime
    if _META_CACHE.get("mt") != mt:
        _META_CACHE["mt"] = mt
        _META_CACHE["df"] = pd.read_parquet(p)[["batter", "team", "position"]]
    return _META_CACHE["df"]


def _records(df: pd.DataFrame) -> list[dict]:
    # JSON-safe: NaN/inf -> None. Must cast to object first — a float column
    # can't hold None (pandas coerces it back to NaN), which would slip past
    # Starlette's allow_nan=False and 500 the whole response.
    clean = df.replace([np.inf, -np.inf], np.nan)
    return clean.astype(object).where(clean.notna(), None).to_dict(orient="records")


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    available = {
        v: (PROCESSED / f"leaderboard_{v}.parquet").exists()
        for v in ("alltime", "season", "half")
    }
    seasons = halves = []
    if available["season"]:
        seasons = sorted(_load("season")["season"].dropna().unique().tolist())
    if available["half"]:
        halves = sorted(_load("half")["half"].dropna().unique().tolist())
    css = WEB / "static" / "style.css"
    css_v = int(css.stat().st_mtime) if css.exists() else 0
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "available": available,
            "seasons": seasons,
            "halves": halves,
            "css_v": css_v,
        },
    )


@app.get("/api/leaderboard/alltime")
def api_alltime(min_swings: int = Query(0, ge=0)):
    df = _load("alltime")
    df = df[df["n_swings"] >= min_swings]
    return _records(df)


@app.get("/api/leaderboard/season")
def api_season(season: str | None = None, min_swings: int = Query(0, ge=0)):
    df = _load("season")
    if season:
        df = df[df["season"] == season]
    df = df[df["n_swings"] >= min_swings]
    return _records(df)


@app.get("/api/leaderboard/half")
def api_half(half: str | None = None, min_swings: int = Query(0, ge=0)):
    df = _load("half")
    if half:
        df = df[df["half"] == half]
    df = df[df["n_swings"] >= min_swings]
    return _records(df)


@app.get("/api/player/{batter}")
def api_player(batter: int, stand: str | None = None):
    """A player's per-season Swing+ trajectory (rolling window) + name.
    `stand` (L/R) selects a switch hitter's side for the profile/meta/residual."""
    path = PROCESSED / "trajectories.parquet"
    if not path.exists():
        raise HTTPException(status_code=503, detail="trajectories.parquet not found.")
    mtime = path.stat().st_mtime
    cached = _CACHE.get("trajectories")
    if cached and cached[0] == mtime:
        traj = cached[1]
    else:
        traj = pd.read_parquet(path)
        _CACHE["trajectories"] = (mtime, traj)

    d = traj[traj["batter"] == batter].sort_values(["season", "game_date"])
    if d.empty:
        raise HTTPException(status_code=404, detail=f"no trajectory for batter {batter}")
    # name from the all-time board (prefer the requested stand for switch hitters)
    alltime = _load("alltime")
    arows = alltime[alltime["batter"] == batter]
    if stand and "stand" in arows.columns and (arows["stand"] == stand).any():
        arows = arows[arows["stand"] == stand]
    name = arows["name"].iloc[0] if len(arows) else str(batter)
    def by_stand(df):  # filter a board frame to this batter (+ stand if given)
        d = df[df["batter"] == batter]
        if stand and "stand" in d.columns and (d["stand"] == stand).any():
            d = d[d["stand"] == stand]
        return d
    drv_groups = ["bat_speed", "attack_angle", "swing_length",
                  "attack_direction", "swing_tilt", "contact_point"]
    have_drv = all(f"shap_{x}" in d.columns for x in drv_groups)
    series = {}
    for season, g in d.groupby("season"):
        pts = []
        for r in g.itertuples():
            pt = {"date": r.game_date, "sp": round(float(r.swing_plus), 1),
                  "bs": round(float(r.bat_speed), 1)}
            if have_drv:
                pt["drv"] = {x: round(float(getattr(r, f"shap_{x}")), 2) for x in drv_groups}
            pts.append(pt)
        series[str(season)] = pts
    # season reference values (the leaderboard numbers) + league baselines
    meta, league = {}, {"swing_plus": 100.0, "bat_speed": None}
    try:
        sb = _load("season")
        ps = by_stand(sb)
        for _, r in ps.iterrows():
            meta[str(r["season"])] = {
                "weighted": round(float(r["swing_plus"]), 1),
                "n_swings": int(r["n_swings"]),
                "bat_speed": round(float(r["bat_speed_mean"]), 1)
                if pd.notna(r["bat_speed_mean"]) else None,
            }
        m = sb.dropna(subset=["bat_speed_mean", "n_swings"])
        if len(m):
            league["bat_speed"] = round(
                float(np.average(m["bat_speed_mean"], weights=m["n_swings"])), 1)
    except HTTPException:
        pass
    # adjustable swing profile per season + career residuals (adjustment tool)
    profiles, residual = {}, {}
    try:
        sb = _load("season")
        ps = by_stand(sb)
        SIDE_COL = "intercept_ball_minus_batter_pos_x_inches_mean"
        for _, r in ps.iterrows():
            if all(c in sb.columns for c in ADJUSTABLE.values()):
                prof = {k: round(float(r[fc]), 1) for k, fc in ADJUSTABLE.items()}
                if SIDE_COL in sb.columns and pd.notna(r.get(SIDE_COL)):
                    prof["contact_side"] = round(float(r[SIDE_COL]), 1)  # lateral intercept (in)
                profiles[str(r["season"])] = prof
        ar = alltime[alltime["batter"] == batter]
        if not ar.empty:
            ar = ar.iloc[0]
            for key in STAT_FMT:
                c = f"bbdiff_{key}"
                if c in alltime.columns and pd.notna(ar[c]):
                    residual[key] = round(float(ar[c]), 3 if key == "xwobacon" else 1)
            residual["n_bip"] = int(ar["n_bip"]) if pd.notna(ar.get("n_bip")) else 0
    except HTTPException:
        pass
    # per-season skill-axis values (from the season leaderboard) — for season-aware cards + bar charts
    skill_by_season: dict[str, dict] = {}
    _SK_COLS = ["swing_plus", "decision_plus_mlb", "b2b_plus", "contact_axis", "dcv_plus",
                "hitter_plus", "h_swing_part", "h_dec_part", "h_b2b_part", "h_contact_part",
                "h_dcv_part", "dec100_chase", "dec100_zone", "dec100_2k", "swingdecision_plus",
                "projected_k_pct", "sk_woba", "luck_woba", "sk_iso", "luck_iso"]
    try:
        sb2 = _load("season")
        ps2 = by_stand(sb2)
        for _, r in ps2.iterrows():
            s = str(int(r["season"]))
            skill_by_season[s] = {
                c: (round(float(r[c]), 3) if pd.notna(r.get(c)) else None)
                for c in _SK_COLS if c in sb2.columns
            }
    except HTTPException:
        pass

    # rolling Decision+ driver trajectory (per game-date), for the drivers graph
    dec_series = {}
    try:
        dtp = PROCESSED / "decision_traj.parquet"
        if dtp.exists():
            dt = _CACHE.get("dec_traj")
            if not dt or dt[0] != dtp.stat().st_mtime:
                dt = (dtp.stat().st_mtime, pd.read_parquet(dtp)); _CACHE["dec_traj"] = dt
            dd = dt[1][dt[1]["batter"] == batter]
            # canonical per-season Decision+ (re-anchored to board scale) so modal == board
            dps_map = {}
            try:
                dpsp = PROCESSED / "decision_plus_season.parquet"
                if dpsp.exists():
                    dps_c = _CACHE.get("dec_season")
                    if not dps_c or dps_c[0] != dpsp.stat().st_mtime:
                        dps_c = (dpsp.stat().st_mtime, pd.read_parquet(dpsp)); _CACHE["dec_season"] = dps_c
                    dr = dps_c[1][dps_c[1]["batter"] == batter]
                    dps_map = {str(int(r.season)): round(float(r.decision_plus_mlb), 1) for r in dr.itertuples()}
            except Exception:
                pass
            for season, g in dd.groupby("season"):
                gs = g.sort_values("game_date")
                dec_series[str(season)] = [
                    {"date": r.game_date, "dp": round(float(r.dp), 1),
                     "parts": {"oze": float(r.b_oze), "ozl": float(r.b_ozl),
                               "ize": float(r.b_ize), "izl": float(r.b_izl)}}
                    for r in gs.itertuples()]
                # Override career-level decision_plus_mlb with canonical per-season value
                s = str(int(season))
                season_dp = dps_map.get(s, round(float(gs["dp"].mean()), 1))
                if s in skill_by_season:
                    skill_by_season[s]["decision_plus_mlb"] = season_dp
                else:
                    skill_by_season[s] = {"decision_plus_mlb": season_dp}
    except Exception:
        pass
    # rolling B2B+ / Contact+ / DCV+ trajectories with driver decomposition
    axis_series: dict[str, list] = {}
    try:
        atp = PROCESSED / "axis_traj.parquet"
        if atp.exists():
            at = _CACHE.get("axis_traj")
            if not at or at[0] != atp.stat().st_mtime:
                at = (atp.stat().st_mtime, pd.read_parquet(atp)); _CACHE["axis_traj"] = at
            ad = at[1][at[1]["batter"] == batter]
            for season, g in ad.groupby("season"):
                def _f(row, col):
                    v = row.get(col)
                    return round(float(v), 3) if v is not None and not (isinstance(v, float) and np.isnan(v)) else None
                axis_series[str(int(season))] = [
                    {"date": r.game_date,
                     "b2b": _f(r._asdict(), "b2b"), "b_ev": _f(r._asdict(), "b_ev"),
                     "b_xw": _f(r._asdict(), "b_xw"), "b_ba": _f(r._asdict(), "b_ba"),
                     "b_su": _f(r._asdict(), "b_su"),
                     "con": _f(r._asdict(), "con"), "c_zone": _f(r._asdict(), "c_zone"),
                     "c_chase": _f(r._asdict(), "c_chase"),
                     "dcv": _f(r._asdict(), "dcv"), "d_pa": _f(r._asdict(), "d_pa"),
                     "d_pb": _f(r._asdict(), "d_pb"), "d_hw": _f(r._asdict(), "d_hw"),
                     "d_pr": _f(r._asdict(), "d_pr")}
                    for r in g.sort_values("game_date").itertuples()]
    except Exception:
        pass

    # SwingDecision+ / Decision+ driver decomposition (from the all-time board row)
    decomp = {}
    if len(arows):
        ar0 = arows.iloc[0]
        g = lambda c: round(float(ar0[c]), 1) if c in arows.columns and pd.notna(ar0.get(c)) else None
        decomp = {"swingdecision_plus": g("swingdecision_plus"),
                  "swing_plus": g("swing_plus"), "decision_plus_mlb": g("decision_plus_mlb"),
                  "sd_swing_part": g("sd_swing_part"), "sd_dec_part": g("sd_dec_part"),
                  # Decision+ run-value components (runs/100 pitches; sum ≈ total decision RV/100)
                  "dec_chase": g("dec100_chase"), "dec_zone": g("dec100_zone"),
                  "dec_2k": g("dec100_2k"), "dec_early": g("dec100_early")}
    # Variance+ risk card (2027 forward distribution + 3-year fan projection)
    risk_card = None
    try:
        vpp = PROCESSED / "variance_plus_2027.parquet"
        if vpp.exists():
            vp_cached = _CACHE.get("variance_plus")
            if not vp_cached or vp_cached[0] != vpp.stat().st_mtime:
                vp_cached = (vpp.stat().st_mtime, pd.read_parquet(vpp))
                _CACHE["variance_plus"] = vp_cached
            vp_row = vp_cached[1][vp_cached[1]["batter"] == str(batter)]
            if len(vp_row):
                r = vp_row.iloc[0]
                # Multi-year projection using 2.6yr wOBA half-life (λ ≈ 0.767/yr)
                LAMBDA, MU = 0.767, 0.310
                frag = str(r["fragility"])
                ff = 1.35 if "fragile" in frag else (1.10 if "mid" in frag else 0.85)
                c1 = float(r["center"])
                hw = (float(r["wp90"]) - float(r["wp10"])) / 2
                c2 = MU + LAMBDA * (c1 - MU)
                c3 = MU + LAMBDA**2 * (c1 - MU)
                # Band grows ~sqrt(t); fragile asymmetry widens downside
                def band(c, hw_mult, ff):
                    return (round(c - hw * hw_mult * ff, 4),
                            round(c, 4),
                            round(c + hw * hw_mult / ff * 1.05, 4))
                risk_card = {
                    "center": round(c1, 4),
                    "wp10": round(float(r["wp10"]), 4), "wp50": round(float(r["wp50"]), 4),
                    "wp90": round(float(r["wp90"]), 4),
                    "y2": band(c2, 1.35, ff), "y3": band(c3, 1.65, ff),
                    "p_collapse": round(float(r["p_collapse"]), 4),
                    "p_jobloss": round(float(r["p_jobloss"]), 4),
                    "p_bad": round(float(r["p_bad"]), 4),
                    "p_elite": round(float(r["p_elite"]), 4),
                    "fragility": frag,
                    "total_runs": round(float(r["total_runs"]), 1),
                    "def_runs": round(float(r["def_runs"]), 1),
                    "def_source": str(r["def_source"]),
                    "def_sd": (round(float(r["def_sd"]), 1) if "def_sd" in vp_row.columns and pd.notna(r.get("def_sd")) else None),
                    "def_parts": {k: (round(float(r[c]), 1) if c in vp_row.columns and pd.notna(r.get(c)) else None)
                                  for k, c in [("oaa", "d_oaa"), ("drs", "d_drs"), ("frp", "d_frp"), ("framing", "d_framing")]},
                    "pos": str(r["pos"]) if "pos" in vp_row.columns else None,
                }
                # historical track record: past projected bands vs realized wOBA
                hp = PROCESSED / "variance_plus_history.parquet"
                if hp.exists():
                    h_cached = _CACHE.get("variance_history")
                    if not h_cached or h_cached[0] != hp.stat().st_mtime:
                        h_cached = (hp.stat().st_mtime, pd.read_parquet(hp)); _CACHE["variance_history"] = h_cached
                    hr = h_cached[1][h_cached[1]["batter"] == batter].sort_values("proj_year")
                    risk_card["history"] = [
                        {"year": int(x.proj_year), "p10": round(float(x.p10), 3), "p50": round(float(x.p50), 3),
                         "p90": round(float(x.p90), 3), "actual": round(float(x.actual_woba), 3),
                         "covered": bool(x.covered)}
                        for x in hr.itertuples()]
    except Exception:
        pass

    # zone-coverage vulnerability (DESCRIPTIVE only — whiff vs expected by pitch height)
    coverage = None
    try:
        cvp = PROCESSED / "coverage_profile.parquet"
        if cvp.exists():
            cv_cached = _CACHE.get("coverage")
            if not cv_cached or cv_cached[0] != cvp.stat().st_mtime:
                cv_cached = (cvp.stat().st_mtime, pd.read_parquet(cvp))
                _CACHE["coverage"] = cv_cached
            cr = cv_cached[1][cv_cached[1]["batter"] == batter]
            if len(cr):
                coverage = {z: round(float(cr[f"cover_{z}"].mean()), 3) for z in ("low", "mid", "high")}
    except Exception:
        pass

    # pitch-type vulnerability profile (DESCRIPTIVE — whiff vs league by pitch family)
    pitch_vuln = None
    try:
        pvp = PROCESSED / "pitch_vuln_profile.parquet"
        if pvp.exists():
            pv_c = _CACHE.get("pitch_vuln")
            if not pv_c or pv_c[0] != pvp.stat().st_mtime:
                pv_c = (pvp.stat().st_mtime, pd.read_parquet(pvp)); _CACHE["pitch_vuln"] = pv_c
            pr = pv_c[1][pv_c[1]["batter"] == batter]
            if len(pr):
                r0 = pr.iloc[0]
                fams = {"fb": "Fastball", "sl": "Slider", "cu": "Curve", "ch": "Off-speed"}
                pitch_vuln = {"worst": (None if pd.isna(r0.get("worst_fam")) else str(r0["worst_fam"])),
                              "fams": {f: {"label": lab,
                                           "whiff": (round(float(r0[f"whiff_shrunk_{f}"]), 3) if pd.notna(r0.get(f"whiff_shrunk_{f}")) else None),
                                           "lg": round(float(r0.get(f"lg_{f}", 0)), 3),
                                           "vuln": (round(float(r0[f"vuln_{f}"]), 3) if pd.notna(r0.get(f"vuln_{f}")) else None),
                                           "n": (int(r0[f"n_{f}"]) if pd.notna(r0.get(f"n_{f}")) else 0)}
                                       for f, lab in fams.items()}}
    except Exception:
        pass

    # injury card (DESCRIPTIVE only — calibrated risk tier + group-level drag-by-type context)
    injury_card = None
    try:
        icp = PROCESSED / "injury_card.parquet"
        if icp.exists():
            ic_cached = _CACHE.get("injury_card")
            if not ic_cached or ic_cached[0] != icp.stat().st_mtime:
                ic_cached = (icp.stat().st_mtime, pd.read_parquet(icp)); _CACHE["injury_card"] = ic_cached
            ir = ic_cached[1][ic_cached[1]["batter"] == batter]
            if len(ir):
                r0 = ir.iloc[0]
                injury_card = {
                    "risk_pct": round(float(r0["risk_pct"]), 3),
                    "risk_tier": str(r0["risk_tier"]),
                    "risk_season": (int(r0["risk_season"]) if "risk_season" in ir.columns and pd.notna(r0.get("risk_season")) else None),
                    "il_2026": (int(r0["il_2026"]) if "il_2026" in ir.columns and pd.notna(r0.get("il_2026")) else 0),
                    "drag_region": (None if pd.isna(r0["drag_region"]) else str(r0["drag_region"])),
                    "drag_value": (None if pd.isna(r0["drag_value"]) else round(float(r0["drag_value"]), 4)),
                    "drag_sig": bool(r0["drag_sig"]),
                }
    except Exception:
        pass

    return {"batter": int(batter), "name": name, "stand": stand,
            "seasons": sorted(series, reverse=True),
            "series": series, "meta": meta, "league": league,
            "profiles": profiles, "residual": residual, "decomp": decomp,
            "dec_series": dec_series, "axis_series": axis_series, "skill_by_season": skill_by_season,
            "risk_card": risk_card, "coverage": coverage, "injury_card": injury_card,
            "pitch_vuln": pitch_vuln,
            "bounds": _BOUNDS}


@app.get("/api/whatif")
def whatif(batter: int, season: str,
           bat_speed: float, attack_angle: float, attack_direction: float,
           swing_tilt: float, contact_depth: float, stand: str | None = None,
           adjust: bool = False):
    """Score an adjusted swing profile; return model predictions and the
    player-adjusted version (model + reliability-shrunk career residual)."""
    sb = _load("season")
    row = sb[(sb["batter"] == batter) & (sb["season"] == season)]
    if stand and "stand" in row.columns and (row["stand"] == stand).any():
        row = row[row["stand"] == stand]
    if row.empty:
        raise HTTPException(status_code=404, detail="no season profile for player")
    row = row.iloc[0]
    profile = {f: float(row[f]) for f in SCORER.appr_feats}   # full appr17 profile
    vals = {"bat_speed": bat_speed, "attack_angle": attack_angle,
            "attack_direction": attack_direction, "swing_tilt": swing_tilt,
            "contact_depth": contact_depth}
    for k, fc in ADJUSTABLE.items():                          # override the 5 swing inputs
        profile[fc] = vals[k]
    out = SCORER.score(profile)

    adjusted = dict(out)
    resid_info = {}
    at = _load("alltime")
    ar = at[at["batter"] == batter]
    if stand and "stand" in ar.columns and (ar["stand"] == stand).any():
        ar = ar[ar["stand"] == stand]
    if not ar.empty:
        ar = ar.iloc[0]
        n_bip = float(ar["n_bip"]) if pd.notna(ar.get("n_bip")) else 0.0
        w = n_bip / (n_bip + 200.0) if n_bip > 0 else 0.0
        for key, dec in STAT_FMT.items():
            c = "xwoba_resid" if key == "xwoba" else f"bbdiff_{key}"
            if c in at.columns and pd.notna(ar[c]):
                adjusted[key] = round(out[key] + float(ar[c]) * w, dec)
                resid_info[key] = round(float(ar[c]), dec)
        resid_info["reliability"] = round(w, 2)
    return {"model": out, "adjusted": adjusted, "residual": resid_info}


@app.get("/api/health")
def health():
    return {
        "available": {
            v: (PROCESSED / f"leaderboard_{v}.parquet").exists()
            for v in ("alltime", "season", "half")
        }
    }
