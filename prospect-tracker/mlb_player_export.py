# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""MLB player detail export - the per-player payload behind the
/projections/ player pages (and the FA board's player links).

Prospects have full PROSPX detail pages; until now MLB players only had
board rows. This sidecar gives every projections veteran and every
FA-class member a real page: identity + contract chips, the projection
path with bands, season-by-season career lines with bWAR, Savant
percentile sliders, pitch arsenal (pitchers), and Swing+ (hitters,
Will Cahoon's model via data/swing_plus.json).

  UNIVERSE   union of mlb_projections.json vets and fa_class.json
             members, keyed by the platform's normalized name key.
             mlbam: vets carry it (proj_export emits it); FA members
             resolve through fa_ident's war_daily identity index.
  CAREER     MLB season lines 2014+ from the cached StatsAPI ladder
             (milb_history sport 1) + per-season bWAR from war_daily
             (pybaseball cache), joined on mlbam.
  STATCAST   Savant MLB leaderboards per season (statcast + expected_
             statistics + pitch-arsenal-stats), cached under
             .cache/savant_mlb/. Percentiles computed within the
             latest qualified season pool - the same Savant-style
             slider data prospect cards carry.
  SWING+     joined from data/swing_plus.json where scored (MLB bat
             tracking 2024+ only - the documented boundary).
  AAA STUFF+ joined from data/stuff_plus_aaa.json for ex-PROSPX
             pitchers (the in-house pitch-quality model; origin gate
             keeps vets' rehab-stint AAA pitches off their pages).

Artifact: data/mlb_player_detail.json (single sidecar, lazy-fetched by
assets/projections.js on first player view). Wired into run_monthly
after proj_export.

Run: python mlb_player_export.py
"""

from __future__ import annotations

import csv
import io
import json
import logging
import statistics
import time
import urllib.request
from datetime import date
from pathlib import Path

import milb_history as mh
from scrapers import normalize_key

try:                                    # site-wide copy rule: no em/en-dashes
    from tools.strip_emdashes import strip_emdashes
except Exception:                       # noqa: BLE001 - normalizer is optional
    def strip_emdashes(text: str) -> str:
        return text.replace("—", "-").replace("–", "-")

log = logging.getLogger(__name__)

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
OUT_PATH = DATA_DIR / "mlb_player_detail.json"
CACHE_DIR = ROOT / ".cache" / "savant_mlb"

CAREER_FROM = 2014
LB = {
    "statcast": ("https://baseballsavant.mlb.com/leaderboard/statcast"
                 "?type={side}&year={year}&csv=true&min=25"),
    "expected": ("https://baseballsavant.mlb.com/leaderboard/expected_statistics"
                 "?type={side}&year={year}&csv=true&min=25"),
    "arsenal": ("https://baseballsavant.mlb.com/leaderboard/pitch-arsenal-stats"
                "?type=pitcher&year={year}&csv=true&min=10"),
}


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


_SAVANT_LIVE_TTL_S = 24 * 3600   # current-season CSVs refresh daily; past seasons are final


def _savant(kind: str, year: int, side: str = "batter") -> list[dict]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{kind}_{side}_{year}.csv"
    # Past seasons are immutable -> cache forever. The CURRENT season's leaderboard
    # moves daily; a forever-cache froze xwOBA/xERA (and every xHEM+/xREM+/xSEM+
    # deserved-stat join downstream) at whatever day the file first landed, so the
    # in-season file gets a TTL. A failed refresh falls back to the stale file
    # (better than dropping the join).
    stale = False
    if path.exists() and year >= date.today().year:
        try:
            stale = (time.time() - path.stat().st_mtime) > _SAVANT_LIVE_TTL_S
        except OSError:
            stale = False
    if not path.exists() or stale:
        url = LB[kind].format(side=side, year=year)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                path.write_bytes(r.read())
        except Exception as e:                                # noqa: BLE001
            log.warning("savant %s/%s/%s failed: %s", kind, side, year, e)
            if not path.exists():
                return []
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    return list(csv.DictReader(io.StringIO(text)))


def _pct_rank(pool: list[float], v: float, invert: bool = False) -> int:
    if not pool:
        return 50
    below = sum(1 for x in pool if x < v) + 0.5 * sum(1 for x in pool if x == v)
    p = below / len(pool)
    if invert:
        p = 1 - p
    return int(round(p * 100))


def _statcast_block(mlbam: int, is_pitcher: bool, year: int) -> dict | None:
    """Savant-style percentile sliders for the latest qualified season.
    Pitcher contact metrics invert (suppression is good)."""
    side = "pitcher" if is_pitcher else "batter"
    for y in range(year, year - 3, -1):
        sc = _savant("statcast", y, side)
        ex = _savant("expected", y, side)
        sc_by = {r.get("player_id"): r for r in sc if r.get("player_id")}
        ex_by = {r.get("player_id"): r for r in ex if r.get("player_id")}
        me_sc = sc_by.get(str(mlbam))
        me_ex = ex_by.get(str(mlbam))
        if not me_sc and not me_ex:
            continue
        out = {"season": y, "metrics": []}

        def add(label, rows_by, row, col, fmt, invert=False):
            if not row:
                return
            v = _f(row.get(col))
            if v is None:
                return
            pool = [x for x in (_f(r.get(col)) for r in rows_by.values())
                    if x is not None]
            out["metrics"].append({
                "label": label, "value": fmt.format(v),
                "pct": _pct_rank(pool, v, invert=invert if is_pitcher else False)})

        add("Exit Velo" if not is_pitcher else "EV Against", sc_by, me_sc,
            "avg_hit_speed", "{:.1f}", invert=True)
        add("Hard-Hit%" if not is_pitcher else "Hard-Hit% Against", sc_by, me_sc,
            "ev95percent", "{:.1f}%", invert=True)
        add("Barrel%" if not is_pitcher else "Barrel% Against", sc_by, me_sc,
            "brl_percent", "{:.1f}%", invert=True)
        add("xwOBA" if not is_pitcher else "xwOBA Against", ex_by, me_ex,
            "est_woba", "{:.3f}", invert=True)
        add("xBA" if not is_pitcher else "xBA Against", ex_by, me_ex,
            "est_ba", "{:.3f}", invert=True)
        # Deserved power + luck (HITTER-SIDE display only; xwOBA-allowed vs FIP was
        # tested and rejected for the pitcher models, so no pitcher claim here).
        # xSLG is a Savant column; xISO = xSLG - xBA (deserved isolated power);
        # Luck = actual minus deserved wOBA (positive = outperformed the contact).
        if not is_pitcher:
            add("xSLG", ex_by, me_ex, "est_slg", "{:.3f}")
            if me_ex is not None:
                xslg, xba = _f(me_ex.get("est_slg")), _f(me_ex.get("est_ba"))
                if xslg is not None and xba is not None:
                    xiso_pool = [s - b for s, b in
                                 ((_f(r.get("est_slg")), _f(r.get("est_ba"))) for r in ex_by.values())
                                 if s is not None and b is not None]
                    out["metrics"].append({
                        "label": "xISO", "value": "{:.3f}".format(xslg - xba),
                        "pct": _pct_rank(xiso_pool, xslg - xba)})
                woba, xwoba = _f(me_ex.get("woba")), _f(me_ex.get("est_woba"))
                if woba is not None and xwoba is not None:
                    luck_pool = [w - x for w, x in
                                 ((_f(r.get("woba")), _f(r.get("est_woba"))) for r in ex_by.values())
                                 if w is not None and x is not None]
                    out["metrics"].append({
                        "label": "Luck (wOBA-xwOBA)", "value": "{:+.3f}".format(woba - xwoba),
                        "pct": _pct_rank(luck_pool, woba - xwoba)})
        return out if out["metrics"] else None
    return None


def _arsenal_block(mlbam: int, year: int) -> list[dict] | None:
    for y in range(year, year - 3, -1):
        rows = [r for r in _savant("arsenal", y, "pitcher")
                if r.get("player_id") == str(mlbam)]
        if rows:
            out = []
            for r in sorted(rows, key=lambda x: -(_f(x.get("pitch_usage")) or 0)):
                out.append({
                    "pitch": r.get("pitch_name"),
                    "usage": _f(r.get("pitch_usage")),
                    "rv100": _f(r.get("run_value_per_100")),
                    "whiff": _f(r.get("whiff_percent")),
                    "ba": _f(r.get("ba")),
                })
            return out[:6]
    return None


def _career_rows(mlbam: int, is_pitcher: bool,
                 war_by: dict[int, dict[int, dict[str, float]]]) -> list[dict]:
    group = "pitching" if is_pitcher else "hitting"
    out = []
    for season in range(CAREER_FROM, date.today().year + 1):
        rows = [r for r in (mh.player_index(season, group).get(mlbam) or [])
                if r.get("level") == "MLB"]
        if not rows:
            continue
        r = max(rows, key=lambda x: _f(x.get("bf" if is_pitcher else "pa")) or 0)
        # Side-specific bWAR (batting vs pitching kept separate) so a two-way arm or a
        # position player's mop-up inning doesn't fold pitching WAR into the hitting row.
        _sw = (war_by.get(mlbam) or {}).get(season) or {}
        war = _sw.get("pit" if is_pitcher else "bat")
        if is_pitcher:
            bf = _f(r.get("bf")) or 0
            so, bb = _f(r.get("so")), _f(r.get("bb"))
            out.append({"y": season, "ip": r.get("ip"), "era": _f(r.get("era")),
                        "kPct": round(so / bf * 100, 1) if so is not None and bf else None,
                        "bbPct": round(bb / bf * 100, 1) if bb is not None and bf else None,
                        "war": round(war, 1) if war is not None else None})
        else:
            pa = _f(r.get("pa")) or 0
            so, bb = _f(r.get("so")), _f(r.get("bb"))
            slg, avg = _f(r.get("slg")), _f(r.get("avg"))
            out.append({"y": season, "pa": int(pa), "avg": r.get("avg"),
                        "obp": r.get("obp"), "slg": r.get("slg"),
                        "ops": r.get("ops"), "hr": r.get("hr"), "sb": r.get("sb"),
                        "kPct": round(so / pa * 100, 1) if so is not None and pa else None,
                        "bbPct": round(bb / pa * 100, 1) if bb is not None and pa else None,
                        "iso": round(slg - avg, 3) if slg is not None and avg is not None else None,
                        "war": round(war, 1) if war is not None else None})
    return out


def _war_daily() -> dict[int, dict[int, dict[str, float]]]:
    """{mlbam: {season: {"bat": bWAR, "pit": bWAR}}} -- batting and pitching bWAR kept
    on SEPARATE keys (they used to be summed onto one number and attached to both the
    hitting and pitching career rows, distorting two-way players and position-player
    pitching cameos)."""
    import pybaseball as pyb
    out: dict[int, dict[int, dict[str, float]]] = {}
    for fn, side in ((pyb.bwar_bat, "bat"), (pyb.bwar_pitch, "pit")):
        try:
            df = fn(return_all=True)
        except Exception:                                      # noqa: BLE001
            continue
        sub = df[df["mlb_ID"].notna() & df["WAR"].notna()]
        for row in sub.itertuples(index=False):
            try:
                mid, yr, war = int(row.mlb_ID), int(row.year_ID), float(row.WAR)
            except (TypeError, ValueError):
                continue
            cell = out.setdefault(mid, {}).setdefault(yr, {})
            cell[side] = cell.get(side, 0.0) + war
    return out


def _ident_mlbams(keys: list[str]) -> dict[str, int]:
    """key -> mlbam via the war_daily identity index (single-candidate
    matches only - ambiguous names stay unresolved and the page renders
    without statcast/career joins). Covers vets exported before
    proj_export carried mlbam, and every FA member."""
    import fa_ident
    idx = fa_ident.war_daily_index()
    out = {}
    for key in keys:
        cands = idx.get(key) or {}
        if len(cands) == 1:
            out[key] = next(iter(cands))
    return out


def _is_pitcher_pos(pos: str | None) -> bool:
    return str(pos or "").upper().split("/")[0].strip() in (
        "P", "SP", "RP", "LHP", "RHP", "SP2", "CL", "SIRP", "MIRP")


def _fv_spark(points: list, cap: int = 40) -> list | None:
    """Compact consensus-FV arc [[date, fv], ...] from a debut row's points[]
    (the same series the PROSPX FV-history chart draws). Downsampled to `cap`
    points if longer, always keeping the first and last snapshot."""
    spark = []
    for pt in points or []:
        dt = pt.get("snapshot_date")
        fv = pt.get("consensus_fv_raw")
        if dt and fv is not None:
            try:
                spark.append([dt, round(float(fv), 1)])
            except (TypeError, ValueError):
                continue
    if len(spark) <= 1:
        return spark or None
    if len(spark) > cap:
        step = (len(spark) - 1) / (cap - 1)
        idx = sorted({int(round(i * step)) for i in range(cap)} | {len(spark) - 1})
        spark = [spark[i] for i in idx]
    return spark


def _debut_origins() -> dict[int, dict]:
    """{mlbam: prospect origin} from debuts.json - the PROSPX identity, the FV
    arc endpoints + full consensus-FV spark, and the consensus tool grades for
    ex-prospects (the scouting slice + hero sparkline sources)."""
    out: dict[int, dict] = {}
    try:
        for d in json.loads((DATA_DIR / "debuts.json").read_text(encoding="utf-8")):
            if d.get("mlbam_id"):
                tools = ((d.get("tools") or {}).get("grades")) or None
                out[int(d["mlbam_id"])] = {
                    "prospx": d.get("player_key"),
                    "fvOpen": d.get("fv_open"),
                    "fvClose": d.get("fv_close"),
                    "debut": d.get("debut_date"),
                    "fvSpark": _fv_spark(d.get("points")),
                    "tools": {k: v for k, v in tools.items() if v is not None} if tools else None,
                }
    except (OSError, ValueError):
        log.warning("mlb player export: debuts.json unavailable - no origins")
    return out


_SCOUT_SRC_LABELS = {"fangraphs": "FanGraphs", "mlb_pipeline": "MLB Pipeline",
                     "espn": "ESPN", "just_baseball": "Just Baseball"}


def _scout_report_slice(prospx: str, reports: dict) -> dict | None:
    """The single most-recent published scouting report for an ex-PROSPX player,
    text capped at ~600 chars on a word boundary. NEVER bakes the whole report
    set (scout_reports.json is 29MB); one latest blurb per player only."""
    rec = reports.get(prospx)
    if not rec:
        return None
    best = None   # (date, source_key, text)
    for src in _SCOUT_SRC_LABELS:
        for it in rec.get(src) or []:
            txt = (it.get("text") or "").strip()
            if not txt:
                continue
            dt = it.get("date") or ""
            if best is None or dt > best[0]:
                best = (dt, src, txt)
    if not best:
        return None
    dt, src, txt = best
    truncated = len(txt) > 600
    if truncated:
        cut = txt[:600]
        sp = cut.rfind(" ")
        if sp > 400:
            cut = cut[:sp]
        txt = cut.rstrip()
    txt = strip_emdashes(txt)           # verbatim quote, dash-normalized to site policy
    return {"source": _SCOUT_SRC_LABELS.get(src, src), "date": dt or None,
            "text": txt, "truncated": truncated}


def _skill_index() -> dict[int, dict]:
    """{mlbam: {"hem": {...} | "pitch": {...}}} from the /mlbstats/ leaderboards
    (hitter HEM+, reliever REM+/RIV+, starter SEM+), joined by MLBAM. Baked onto
    the card so it no longer client-fetches the whole leaderboard just to show a
    few tiles. Relievers take priority over starters for the rare swingman."""
    out: dict[int, dict] = {}

    def _load(fname):
        try:
            return json.loads((DATA_DIR / fname).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    hd = _load("hitter_leaderboards.json")
    for r in hd.get("hitters") or []:
        try:
            mid = int(r.get("mlbam"))
        except (TypeError, ValueError):
            continue
        out.setdefault(mid, {})["hem"] = {
            "hemPlus": r.get("hem_plus"), "hemPlus3yr": r.get("hem_plus_3yr"),
            "xhemPlus": r.get("xhem_plus"), "tier": r.get("tier"),
            "qualified": bool(r.get("qualified")), "luckGap": r.get("luck_gap"),
            # Baked 2026-07-30 (Lane B): every one of these was computed and served
            # on /mlbstats/ but absent from the player card, so a reader had to open
            # a different module to see the same player's own numbers.
            # WAR/PA+ is 100+10z, NOT the wRC+-width ratio scale HEM+ uses -- the
            # renderer must band it with remCell, never hemCell.
            "warPaPlus": r.get("war_pa_plus"), "warPaPlusAdj": r.get("war_pa_plus_adj"),
            "warPaPlusPct": r.get("war_pa_plus_pct"),
            "warPaPlus3yr": r.get("war_pa_plus_3yr"),
            "war": r.get("war"), "pa": r.get("pa"),
            "pwoba": r.get("pwoba"), "fwdhemPlus": r.get("fwdhem_plus"),
            "wrcPlus": r.get("wrc_plus")}

    bd = _load("bullpen_leaderboards.json")
    b_season = bd.get("season")
    for r in bd.get("relievers") or []:
        try:
            mid = int(r.get("mlbam"))
        except (TypeError, ValueError):
            continue
        out.setdefault(mid, {})["pitch"] = {
            "kind": "rel", "season": b_season, "role": r.get("role"),
            "ip": r.get("ip"), "qualified": bool(r.get("qualified")),
            "remPlus": r.get("rem_plus"), "rivPlus": r.get("riv_plus"),
            "remPlus3yr": r.get("rem_plus_3yr"), "xremPlus": r.get("xrem_plus"),
            # Lane B bake. warIpPlus here is RELIEVER-anchored and is NOT comparable
            # with the starter block's field of the same name (separate pools, the
            # SEM+/REM+ precedent). gmLI and the save/hold counts are the deployment
            # story REM+ deliberately leaves out.
            "warIpPlus": r.get("war_ip_plus"), "warIpPlusAdj": r.get("war_ip_plus_adj"),
            "warIpPlusPct": r.get("war_ip_plus_pct"),
            "warIpPlus3yr": r.get("war_ip_plus_3yr"), "war": r.get("war"),
            "gmli": r.get("gmli"), "gmli3yr": r.get("gmli_3yr"),
            "saves": r.get("saves"), "holds": r.get("holds"),
            "wpa": r.get("wpa"), "sd": r.get("sd"), "md": r.get("md")}

    sd = _load("starter_leaderboards.json")
    s_season = sd.get("season")
    for r in sd.get("starters") or []:
        try:
            mid = int(r.get("mlbam"))
        except (TypeError, ValueError):
            continue
        e = out.setdefault(mid, {})
        if "pitch" in e:            # reliever board already claimed this arm
            continue
        e["pitch"] = {
            "kind": "sp", "season": s_season, "role": r.get("role"),
            "ip": r.get("ip"), "qualified": bool(r.get("qualified")),
            "semPlus": r.get("sem_plus"), "semPlus3yr": r.get("sem_plus_3yr"),
            "xsemPlus": r.get("xsem_plus"),
            # Lane B bake. STARTER-anchored WAR/IP+; see the reliever note above for
            # why the two must never share a scale in the renderer.
            "warIpPlus": r.get("war_ip_plus"), "warIpPlusAdj": r.get("war_ip_plus_adj"),
            "warIpPlusPct": r.get("war_ip_plus_pct"),
            "warIpPlus3yr": r.get("war_ip_plus_3yr"), "war": r.get("war"),
            "ipPerGs": r.get("ip_per_gs"), "gs": r.get("gs")}

    # Leverage block (batters + starters), from the fourth /mlbstats/ board. Kept
    # OUT of the hem/pitch blocks on purpose: it is descriptive game-context, not a
    # skill index, and bundling it into "hem" would invite a renderer to band it on
    # a plus scale it does not share.
    ld = _load("leverage_leaderboards.json")
    for grp, key in (("batters", "bat"), ("starters", "sp")):
        for r in ld.get(grp) or []:
            try:
                mid = int(r.get("mlbam"))
            except (TypeError, ValueError):
                continue
            out.setdefault(mid, {}).setdefault("lev", {}).update({
                "kind": key, "wpa": r.get("wpa"), "wpaLi": r.get("wpa_li"),
                "pli": r.get("pli"), "clutch": r.get("clutch"),
                "wpaPerStart": r.get("wpa_per_start")})
    return out


def build_payload() -> dict:
    proj = json.loads((DATA_DIR / "mlb_projections.json").read_text(encoding="utf-8"))
    fa = json.loads((DATA_DIR / "fa_class.json").read_text(encoding="utf-8"))
    members = {m["key"]: m for m in fa.get("members") or []}
    swing = {}
    try:
        sp = json.loads((DATA_DIR / "swing_plus.json").read_text(encoding="utf-8"))
        swing = sp.get("players") or {}
    except (OSError, ValueError):
        pass
    aaa_stuff = {}
    try:
        st = json.loads((DATA_DIR / "stuff_plus_aaa.json").read_text(encoding="utf-8"))
        aaa_stuff = st.get("players") or {}
    except (OSError, ValueError):
        pass
    origins = _debut_origins()
    scout_reports = {}
    try:
        scout_reports = json.loads((DATA_DIR / "scout_reports.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.warning("mlb player export: scout_reports.json unavailable - no scouting slices")
    skills_by_mlbam = _skill_index()

    all_keys = [v["key"] for v in proj.get("vets") or []] + list(members)
    fa_ids = _ident_mlbams(all_keys)
    war_by = _war_daily()
    year = date.today().year
    players: dict[str, dict] = {}

    # vets from the projections universe. proj_export now emits collision-safe keys
    # (base__mlbam for same-named vets), but guard here too: a duplicate key must
    # NEVER silently overwrite an existing card (the Will Smith reliever once
    # replaced the LAD catcher's page) - suffix with mlbam instead.
    for v in proj.get("vets") or []:
        key = v["key"]
        mlbam = v.get("mlbam") or fa_ids.get(key)
        if key in players:
            key = f"{key}__{mlbam or 'dup'}"
        is_pit = _is_pitcher_pos(v.get("pos"))
        p = {"key": key, "name": v.get("name"), "mlbam": mlbam,
             "pos": v.get("pos"), "team": v.get("team"), "age": v.get("age"),
             # surTotal / surRos / rosWar / rosFrac (2026-08-03): the balance of
             # the season in progress. Without them on the card the Trade
             # Machine cannot price a rental and the "Trade Machine" link never
             # renders for one, which is what hid A.J. Minter.
             "proj": {k: v.get(k) for k in ("war", "warP10", "warP90",
                                            "warTotal", "warTotalP10",
                                            "warTotalP90", "sur", "surNpv",
                                            "surTotal", "surRos", "rosWar",
                                            "rosFrac",
                                            "thru", "aav", "warHit", "warPit")},
             "twoWay": bool(v.get("twoWay")) or None,
             "isPit": is_pit and not v.get("twoWay")}
        players[key] = p
    # FA members (some overlap vets; FA fields attach either way)
    for key, m in members.items():
        p = players.setdefault(key, {
            "key": key, "name": m.get("name"), "mlbam": fa_ids.get(key),
            "pos": m.get("pos"), "team": m.get("from"), "age": m.get("age"),
            "isPit": _is_pitcher_pos(m.get("pos"))})
        p.setdefault("mlbam", fa_ids.get(key))
        p["fa"] = {k: m.get(k) for k in (
            "status", "type", "projYears", "projGuar", "projAav",
            "projAavP10", "projAavP90", "rational", "surplus", "dealPlus",
            "verdict", "prevAav", "enterProb")}

    # Thin cards for MLB Stats leaderboard players outside the projections / FA
    # universe, so their leaderboard names link to a card. Collision-safe keys
    # (base__mlbam when the normalized name is already taken) mean a name-key
    # collision no longer silently drops a player's link. Enriched by the same
    # career / statcast / arsenal loop below (keyed by mlbam), so a thin card that
    # has cached data shows a real page; otherwise it degrades to identity only.
    _existing_mlbams = {int(p["mlbam"]) for p in players.values() if p.get("mlbam")}
    _n_thin = 0
    for row in _leaderboard_thin_rows():
        mid = row["mlbam"]
        if mid in _existing_mlbams:
            continue
        base = normalize_key(row["name"] or "") or f"mlbam-{mid}"
        key = base if base not in players else f"{base}__{mid}"
        players[key] = {"key": key, "name": row["name"], "mlbam": mid,
                        "pos": row.get("pos"), "team": row.get("team"), "age": None,
                        "isPit": row["isPit"], "leaderboardOnly": True}
        _existing_mlbams.add(mid)
        _n_thin += 1
    log.info("player detail: +%d thin leaderboard cards", _n_thin)

    n_sc = n_ar = n_car = 0
    for key, p in players.items():
        mlbam = p.get("mlbam")
        if not mlbam:
            continue
        org = origins.get(int(mlbam))
        if org and org.get("prospx"):
            # ex-PROSPX prospect: arc + hub link (hero). Only the render-facing
            # arc fields ride in origin; tool grades go into the scout slice.
            p["origin"] = {k: org[k] for k in ("prospx", "fvOpen", "fvClose",
                                               "debut", "fvSpark")
                           if org.get(k) is not None}
            # Scouting slice (ex-PROSPX only): latest report blurb + tool grades.
            rep = _scout_report_slice(org["prospx"], scout_reports)
            tools = org.get("tools")
            if rep or tools:
                sc_block = {}
                if rep:
                    sc_block["report"] = rep
                if tools:
                    sc_block["tools"] = tools
                p["scout"] = sc_block
        # Skill ratings from the MLB Stats leaderboards (HEM+ for hitters,
        # REM+/RIV+/SEM+ for pitchers), baked so the card stops client-fetching
        # whole leaderboards for a few tiles.
        sk = skills_by_mlbam.get(int(mlbam))
        if sk:
            block = {}
            if sk.get("hem") and not p["isPit"]:
                block["hem"] = sk["hem"]
            if sk.get("pitch") and (p["isPit"] or p.get("twoWay")):
                block["pitch"] = sk["pitch"]
            if block:
                p["skills"] = block
        p["career"] = _career_rows(int(mlbam), p["isPit"], war_by)
        n_car += 1 if p["career"] else 0
        sc = _statcast_block(int(mlbam), p["isPit"], year)
        if sc:
            p["sc"] = sc
            n_sc += 1
        # Two-way players carry BOTH sides: the primary career/sc above is
        # the hitting line (isPit forced False for two-way); the pitching
        # line + arsenal ride alongside.
        if p.get("twoWay"):
            p["careerPit"] = _career_rows(int(mlbam), True, war_by)
            scp = _statcast_block(int(mlbam), True, year)
            if scp:
                p["scPit"] = scp
        if p["isPit"] or p.get("twoWay"):
            ar = _arsenal_block(int(mlbam), year)
            if ar:
                p["arsenal"] = ar
                n_ar += 1
        sw = swing.get(str(mlbam))
        if sw and (not p["isPit"] or p.get("twoWay")):
            p["swingPlus"] = sw["swing_plus"]
            p["swingN"] = sw["n_swings"]
            # W6 display-only: per-season Swing+ slices for the card trend
            # line (same filter + shrink, grouped by season; low_n = under
            # the model's 180-swing floor). Never a model input.
            if sw.get("seasons"):
                p["swingPlusSeasons"] = sw["seasons"]
        # In-house AAA Stuff+ - recent graduates only (the ex-PROSPX origin
        # gate keeps a vet's rehab-stint AAA pitches off his page).
        st = aaa_stuff.get(str(mlbam))
        if st and (p["isPit"] or p.get("twoWay")) and p.get("origin"):
            p["aaaStuffPlus"] = st["stuff_plus"]
            p["aaaStuffN"] = st["n_pitches"]
            p["aaaStuffSeason"] = st["season"]
    return {
        "generated_at": date.today().isoformat(),
        "n_players": len(players),
        "coverage": {"career": n_car, "statcast": n_sc, "arsenal": n_ar,
                     "swing_plus": sum(1 for p in players.values()
                                       if p.get("swingPlus") is not None),
                     "aaa_stuff_plus": sum(1 for p in players.values()
                                           if p.get("aaaStuffPlus") is not None),
                     "skills": sum(1 for p in players.values() if p.get("skills")),
                     "scout": sum(1 for p in players.values() if p.get("scout"))},
        "notes": [
            "career: MLB season lines (StatsAPI) + per-season bWAR (war_daily)",
            "statcast: Savant leaderboard percentiles within the season's qualified pool; pitcher contact metrics invert (suppression = good)",
            "swing_plus: Will Cahoon's model, MLB bat tracking 2024+ only; swingPlusSeasons = per-season slices (low_n under 180 swings)",
            "aaa_stuff_plus: in-house AAA pitch-quality model (stuff_plus_aaa.py), ex-PROSPX pitchers' latest tracked AAA season",
            "skills: HEM+ (hitters), REM+/RIV+/SEM+ (pitchers) from the MLB Stats leaderboards, joined by MLBAM",
            "scout: latest published report blurb (capped) + consensus tool grades, ex-PROSPX players only",
            "origin.fvSpark: consensus-FV arc [[date, fv], ...] for ex-PROSPX players",
            "fa fields attach for current class members; verdict/dealPlus from the gate-validated market model",
        ],
        "players": players,
    }


def _leaderboard_thin_rows() -> list[dict]:
    """Identity rows for MLB Stats leaderboard players (bullpen / starter / hitter
    boards) so their leaderboard names link to a real player card even when they
    aren't in the projections / FA universe. This closes the dominant clickability
    gap (rookies / up-and-down arms like Erik Sabrowski, Didier Fuentes) and, via
    the collision-safe keying in build_payload, gives name-key-collided veterans
    (e.g. Max Muncy 571970 vs the A's Max Muncy 691777) their own linkable card.
    Deduped by mlbam; empty on any error."""
    out: list[dict] = []
    seen: set[int] = set()
    specs = [("bullpen_leaderboards.json", "relievers", True, "RP"),
             ("starter_leaderboards.json", "starters", True, "SP"),
             ("hitter_leaderboards.json", "hitters", False, None)]
    for fname, akey, is_pit, pos in specs:
        try:
            d = json.loads((DATA_DIR / fname).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for r in d.get(akey) or []:
            try:
                mid = int(r.get("mlbam"))
            except (TypeError, ValueError):
                continue
            if mid in seen or not r.get("name"):
                continue
            seen.add(mid)
            out.append({"mlbam": mid, "name": r.get("name"),
                        "team": r.get("team"), "pos": pos, "isPit": is_pit})
    return out


def _active_prospect_rows() -> list[dict]:
    """Slim identity rows for ACTIVE PROSPX prospects (timeseries.json boot
    file) so the site-wide search covers players who haven't debuted yet.
    Empty on any error - the links map degrades to the MLB population."""
    try:
        boot = json.loads((DATA_DIR / "timeseries.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.warning("player links: timeseries.json unavailable - search index "
                    "covers the MLB population only")
        return []
    rows = []
    for p in boot.get("players") or []:
        pkey = p.get("player_key")
        if not pkey:
            continue
        rows.append({"key": pkey, "mlbam": p.get("mlbam_id"),
                     "fa": False, "prospx": pkey,
                     "name": p.get("player_name"),
                     "team": p.get("org"), "pos": p.get("position")})
    return rows


def _export_links(payload: dict) -> None:
    """data/player_links.json - the cross-module identity map every card
    surface reads for its hub strip: one player, every page that renders
    them. byMlbam serves PROSPX (it knows mlbam_id); byKey serves the FA
    and projections apps (they share the normalized-name key). name/team/pos
    ride along so the site-wide ⌘K palette can search players from any page;
    active PROSPX prospects merge in for the same reason (the /player/
    router resolves their keys to the prospect card)."""
    by_key: dict[str, dict] = {}
    by_mlbam: dict[str, dict] = {}
    for key, p in payload["players"].items():
        row = {"key": key, "mlbam": p.get("mlbam"),
               "fa": bool(p.get("fa")),
               # AUDIT 2026-07-18 (A6): mark projection-universe players so the hub
               # strip only offers the "MLB Projections -> player page" chip to
               # players who actually HAVE that page. Every key in payload["players"]
               # is a projections vet or FA member with a real /projections/#player=
               # page; the active-prospect rows merged below are NOT and get proj=False.
               "proj": True,
               "prospx": (p.get("origin") or {}).get("prospx"),
               "name": p.get("name"), "team": p.get("team"), "pos": p.get("pos")}
        by_key[key] = row
        if p.get("mlbam"):
            by_mlbam[str(p["mlbam"])] = row
    n_prospects = 0
    for row in _active_prospect_rows():
        if row["key"] in by_key:
            continue   # ex-prospect already carried by the MLB payload
        row.setdefault("proj", False)   # never-debuted prospect: no projections page
        by_key[row["key"]] = row
        if row.get("mlbam"):
            by_mlbam.setdefault(str(row["mlbam"]), row)
        n_prospects += 1
    out = {"generated_at": payload["generated_at"],
           "byKey": by_key, "byMlbam": by_mlbam}
    (DATA_DIR / "player_links.json").write_text(
        json.dumps(out, separators=(",", ":")), encoding="utf-8")
    log.info("player links: %d keys (%d active prospects merged), %d mlbam-joined",
             len(by_key), n_prospects, len(by_mlbam))


_PAYLOAD_SOFT_BUDGET = 6 * 1024 * 1024   # 6MB - lazy-fetched on first player view


def export() -> int:
    payload = build_payload()
    raw = json.dumps(payload, separators=(",", ":"))
    OUT_PATH.write_text(raw, encoding="utf-8")
    _export_links(payload)
    if len(raw) > _PAYLOAD_SOFT_BUDGET:
        log.warning("mlb player detail: payload %.1fMB exceeds the %dMB soft "
                    "budget (lazy-fetched on first player view) - consider "
                    "trimming baked blocks", len(raw) / 1048576,
                    _PAYLOAD_SOFT_BUDGET // 1048576)
    log.info("mlb player detail: %dKB, %d players, coverage %s",
             len(raw) // 1024, payload["n_players"], payload["coverage"])
    return len(raw)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print(export())
