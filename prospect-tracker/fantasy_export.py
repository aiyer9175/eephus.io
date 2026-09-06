# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""fantasy_export.py — data/fantasy.json for the /fantasy/ module.

Rest-of-season (ROS) fantasy projections for the whole MLB player pool, scored
by the canonical Ottoneu engines (`fantasy_scoring`), plus the forward
probable-pitcher schedule (`fantasy_schedule`). The client re-scores in any of
the four systems from the per-player COUNTING-STAT vectors we bake here.

Projection method (reuses the Gate-1-validated FA engine, no new model):
  * `fp.build_corpus()` → `fp.fitted_models()` → `fp.project_player(target=cur+1,
    in_progress=(cur, frac))` gives each player's current TRUE-TALENT rate
    components + full-season playing time, blending the partial current season
    (fa_projection.py:587-639).
  * ROS playing time = projected full-season PT × (1 − season_fraction): what's
    left to play. Counting stats = rates × ROS PT, inverting ISO/BABIP into hit
    types with the SAME algebra as `_assemble_hitter` (fa_projection.py:694-717).
  * Skill counting stats (H, 1B/2B/3B, HR, BB, K, IP) are engine-projected.
    CONTEXT stats the rate model can't produce — R, RBI, SB (hitters); W, QS, H
    allowed (pitchers); SV, HLD (relievers) — are heuristic estimates, clearly
    marked `_est`, scaled from league rates / observed pace. These affect roto R/
    RBI/SB/W/SV and the FGP hit penalty only; the core skill ranking stands on
    the engine.

Best-effort + additive: any failure logs and degrades (a section renders "being
computed"); never aborts the pipeline. Run: `python fantasy_export.py`
(or `--limit N` for a fast partial). Wired into run_monthly (see run_monthly).
"""
from __future__ import annotations

import functools
import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import dynasty_blend
import fa_projection as fp
import fantasy_schedule as fsched
import fantasy_scoring as fscore

log = logging.getLogger("fantasy_export")

DATA_DIR = Path(__file__).parent / "data"
OUT_PATH = DATA_DIR / "fantasy.json"

# League anchors for the CONTEXT-stat heuristics (rate model doesn't emit these).
_LG_OBP, _LG_SLG = 0.315, 0.410
_LG_PIT_BABIP = 0.290           # hits-allowed on balls in play
_SP_DECISION_RATE = 0.60        # fraction of a start that yields a W/L decision
_LG_CS_PER_SB = 0.26            # caught-stealing per stolen base


def _load_json(name: str) -> dict | list | None:
    p = DATA_DIR / name
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _record_ingest_safe(source: str, *, ok: bool, message: str = "",
                        n_rows: int = 0) -> None:
    """File one outcome into the ingest-health RED ledger, never raising.

    THE ledger call for this module and for dfs_export (which imports it rather
    than growing a second copy). run_monthly.write_ingest_health drains it into
    data/ingest_health.json and prints `!!! INGEST RED` in the run summary, so a
    join or a fetch that quietly produced nothing becomes visible on the day it
    happens instead of days later as a blank module.

    Best-effort BY DESIGN: reporting must never be the reason a refresh fails,
    and importing run_monthly is expensive enough that only anomaly paths should
    reach this."""
    try:
        from run_monthly import _record_ingest
        _record_ingest(source, ok=ok, n_rows=n_rows, message=message)
    except Exception:
        log.debug("could not record ingest health for %s", source, exc_info=True)


def _json_blob(payload: dict, source: str) -> str | None:
    """Serialize an artifact, or report and refuse to write one.

    `allow_nan=False` is the whole point. json.dumps DEFAULTS to emitting the
    bare tokens NaN / Infinity, which are not JSON at all: the browser's
    JSON.parse throws on the first one, so a single non-finite number anywhere
    in the tree does not degrade one section, it dark-starts the entire page.
    Refusing to write keeps the previous (parseable) artifact served, the same
    trade refresh_live's EMPTY-FETCH GUARD makes for an empty schedule.

    Returns None after an error log AND a RED ledger row, so a caller cannot
    swallow the failure by accident. dfs_export writes through this too."""
    try:
        return json.dumps(payload, separators=(",", ":"), allow_nan=False)
    except (ValueError, TypeError) as exc:
        msg = (f"{source}: payload is not serializable as valid JSON ({exc}); "
               "refused to write it. A non-finite number reaches the page as a "
               "bare NaN token that JSON.parse rejects, which blanks the whole "
               "surface. The previous artifact stays served.")
        log.error(msg)
        _record_ingest_safe(source, ok=False, message=msg)
        return None


# ONE eFV BASIS FOR THIS WHOLE MODULE (2026-08-03). /fantasy/ used to show two
# different eFV numbers on one page: Call-up Watch read raw `xfv_grade` while the
# Dynasty board's eFV column read the RETIRED `xfv_grade_quantile`, so the same
# prospect could carry two grades a tab apart. Both now go through _board_grade,
# which mirrors build_site._load_xfv_grades / storage.BOARD_GRADE_FIELD / the
# prospx client's efvBoardValue exactly. The SCALE is owned by efv_board_scale;
# no copy of the coefficients lives here.
try:
    from efv_board_scale import board_value as _efv_board_value
except Exception:                                            # pragma: no cover
    def _efv_board_value(rec):
        return (rec or {}).get("xfv_grade")


def _board_grade(rec: dict | None):
    """THE displayed eFV grade for an xfv.json record, or None. Unrounded -
    callers that display it round to NEAREST (eFV is not a scouting FV)."""
    rec = rec or {}
    g = _efv_board_value(rec)
    if g is None:
        g = rec.get("xfv_grade_realized")
    if g is None:
        g = rec.get("xfv_grade_quantile")
    return float(g) if isinstance(g, (int, float)) else None


@functools.lru_cache(maxsize=1)
def _efv_by_key() -> dict:
    """{player_key: board eFV grade} off data/xfv.json - the site-wide grade.
    Empty when the artifact is absent (fresh checkout), so callers fall back
    to consensus rather than failing."""
    x = _load_json("xfv.json") or {}
    by = x.get("by_player") if isinstance(x, dict) else None
    if not isinstance(by, dict):
        return {}
    out = {}
    for k, v in by.items():
        g = _board_grade(v) if isinstance(v, dict) else None
        if g is not None:
            out[k] = g
    return out


def _sb_rate_by_mlbam() -> dict:
    """Observed season-to-date SB per PA from the hitter leaderboard (the only
    committed SB source) — the base rate for the ROS SB estimate."""
    lb = _load_json("hitter_leaderboards.json") or {}
    out: dict = {}
    for r in (lb.get("hitters") or []):
        mid, pa, sb = r.get("mlbam"), r.get("pa"), r.get("sb")
        if mid and pa and pa > 0 and sb is not None:
            out[int(mid)] = sb / pa
    return out


def _names_from_leaderboards() -> dict:
    """{mlbam: name} from the three skill leaderboards — the local, committed name
    source (corpus rows carry no display name; proj_export uses pybaseball)."""
    out: dict = {}
    for fname, key in (("hitter_leaderboards.json", "hitters"),
                       ("starter_leaderboards.json", "starters"),
                       ("bullpen_leaderboards.json", "relievers")):
        for r in ((_load_json(fname) or {}).get(key) or []):
            if r.get("mlbam") and r.get("name"):
                out.setdefault(int(r["mlbam"]), r["name"])
    return out


def _name_from_links(links, mid) -> str | None:
    """Resolve a display name from player_links.json. Its shape is
    {generated_at, byKey, byMlbam}; the mlbam->entry map is nested under byMlbam
    and is STRING-keyed, so the lookup must go through byMlbam[str(mid)] (not the
    top-level dict). Returns None when absent."""
    by_mlbam = links.get("byMlbam") if isinstance(links, dict) else None
    e = (by_mlbam or {}).get(str(mid)) if isinstance(by_mlbam, dict) else None
    if isinstance(e, dict):
        return e.get("name")
    return e if isinstance(e, str) else None


def _hitter_ros(proj: dict, ros_pa: float, sb_per_pa: float | None) -> dict:
    """Invert the projected per-PA rate components into ROS counting stats over
    `ros_pa`, mirroring _assemble_hitter's hit-type algebra."""
    a = fp._pcfg()["assembly"]
    pa = max(0.0, ros_pa)
    bb = proj["bb_pct"] * pa
    hbp = a["hbp_rate"] * pa
    sf = a["sf_rate"] * pa
    ab = max(0.0, pa - bb - hbp - sf)
    so = proj["k_pct"] * pa
    hr = proj["hr_pa"] * pa
    bip = max(0.0, ab - so - hr + sf)
    hits_in_play = (proj["babip"] or 0.28) * bip
    h = hits_in_play + hr
    eb_nonhr = max(0.0, proj["iso"] * ab - 3 * hr)          # 2B + 2·3B, ISO is per-AB
    ratio = a["double_triple_ratio"]
    triples = eb_nonhr / (ratio + 2) if (ratio + 2) else 0.0
    doubles = ratio * triples
    singles = max(0.0, h - hr - doubles - triples)
    # Context estimates (heuristic): SB from observed pace; R from OBP; RBI from SLG.
    obp = ((h + bb + hbp) / pa) if pa > 0 else 0.0
    slg = ((singles + 2 * doubles + 3 * triples + 4 * hr) / ab) if ab > 0 else 0.0
    r_pa = 0.12                                             # league R (≈RBI) per PA anchor
    sb = (sb_per_pa if sb_per_pa is not None else 0.012) * pa
    runs = r_pa * (obp / _LG_OBP) * pa
    rbi = r_pa * (slg / _LG_SLG) * pa
    return {
        "pa": round(pa, 1), "ab": round(ab, 1),
        "h": round(h, 1), "single": round(singles, 1), "double": round(doubles, 1),
        "triple": round(triples, 1), "hr": round(hr, 1), "bb": round(bb, 1),
        "hbp": round(hbp, 1), "so": round(so, 1),
        "sb": round(sb, 1), "cs": round(sb * _LG_CS_PER_SB, 1),
        "r": round(runs, 1), "rbi": round(rbi, 1),
        "avg": round(h / ab, 3) if ab > 0 else None,
        "obp": round(obp, 3), "slg": round(slg, 3),
        "_est": ["r", "rbi", "sb", "cs"],
    }


def _pitcher_ros(proj: dict, ros_bf: float, ros_ip: float, role: str,
                 ip_per_gs: float | None) -> dict:
    """ROS pitcher counting stats. K/BB/HR/IP are engine-projected; H allowed,
    W, QS, SV/HLD are heuristic context estimates."""
    bf = max(0.0, ros_bf)
    ip = max(0.0, ros_ip)
    k = proj["k_pct"] * bf
    bb = proj["bb_pct"] * bf
    hr = proj["hr_bf"] * bf
    hbp = 0.008 * bf
    bip = max(0.0, bf - k - bb - hbp - hr)
    h = _LG_PIT_BABIP * bip + hr                            # hits allowed (est)
    fip = proj.get("fip_proj") or 4.2
    er = (fip / 9.0) * ip                                   # ERA≈FIP for pricing
    whip = ((h + bb) / ip) if ip > 0 else None
    row = {
        "role": role, "ip": round(ip, 1), "bf": round(bf, 0),
        "k": round(k, 1), "bb": round(bb, 1), "hr": round(hr, 1),
        "hbp": round(hbp, 1), "h": round(h, 1), "er": round(er, 1),
        "era": round(9 * er / ip, 2) if ip > 0 else None,
        "whip": round(whip, 2) if whip is not None else None,
        "hr9": round(9 * hr / ip, 2) if ip > 0 else None,
        # era belongs in _est (added 2026-08-16): it is 9*er/ip and er is priced
        # at FIP (the line above), so the ERA column is exactly as heuristic as
        # the h and er it derives from. Marking only h/er let the client render
        # a FIP-derived ERA without the estimate marker its own inputs carried.
        "_est": ["h", "er", "era"],
    }
    if role == "SP":
        ipgs = ip_per_gs or 5.4
        starts = ip / ipgs if ipgs > 0 else 0.0
        qs_rate = min(0.85, max(0.0, 0.20 + 0.14 * (ipgs - 5.0) - 0.11 * (fip - 4.0)))
        decisions = starts * _SP_DECISION_RATE
        pwin = min(0.80, max(0.20, 0.5 - 0.07 * (fip - 4.2)))
        row.update({"gs": round(starts, 1), "qs": round(starts * qs_rate, 1),
                    "w": round(decisions * pwin, 1),
                    "l": round(decisions * (1 - pwin), 1)})
        row["_est"] += ["w", "l", "qs", "gs"]
    else:
        row.update({"sv": 0.0, "hld": 0.0, "_rp": True})    # filled from pace in build
        row["_est"] += ["sv", "hld"]
    return row


def _rp_saves_holds() -> dict:
    """Season-to-date SV/HLD per reliever (bullpen leaderboard) for the ROS pace
    forecast."""
    lb = _load_json("bullpen_leaderboards.json") or {}
    out: dict = {}
    for r in (lb.get("relievers") or []):
        mid = r.get("mlbam")
        if mid:
            out[int(mid)] = {"sv": r.get("saves") or 0, "hld": r.get("holds") or 0,
                             "gmli": r.get("gmli")}
    return out


def _ip_per_gs() -> dict:
    lb = _load_json("starter_leaderboards.json") or {}
    return {int(r["mlbam"]): r.get("ip_per_gs")
            for r in (lb.get("starters") or []) if r.get("mlbam")}


def build_players(limit: int | None = None) -> dict:
    """Project the whole pool ROS and score it. Returns the full payload dict."""
    corpus = fp.build_corpus()
    league = corpus["league"]
    seasons = [s for s in league if isinstance(s, int)]
    cur = max(seasons) if seasons else datetime.now(timezone.utc).year
    curves, _war_map = fp.fitted_models(corpus, cur)
    frac = fp.season_fraction(league, cur)
    remaining = max(0.0, 1.0 - frac)
    in_prog = (cur, frac)

    # Latest-3-season history per player per side.
    by_player: dict[str, dict[int, dict[int, dict]]] = {"hit": {}, "pit": {}}
    for side in ("hit", "pit"):
        for row in corpus[side]:
            mid = row.get("mlbam")
            if mid and row.get("season", 0) >= cur - 3:
                by_player[side].setdefault(int(mid), {})[row["season"]] = row

    sb_rate = _sb_rate_by_mlbam()
    rp_sh = _rp_saves_holds()
    ipgs_map = _ip_per_gs()
    name_map = _names_from_leaderboards()
    links = (_load_json("player_links.json") or {})

    def _name(mid: int) -> str | None:
        if mid in name_map:
            return name_map[mid]
        return _name_from_links(links, mid)

    players: list[dict] = []
    ids = set(by_player["hit"]) | set(by_player["pit"])
    for i, mid in enumerate(sorted(ids)):
        if limit and i >= limit:
            break
        for side in ("hit", "pit"):
            seasons_d = by_player[side].get(mid)
            if not seasons_d:
                continue
            hist = [seasons_d[t] for t in (cur, cur - 1, cur - 2) if t in seasons_d]
            if not hist:
                continue
            expo = "pa" if side == "hit" else "ip"
            if (max((h.get(expo) or 0) for h in hist)) < (100 if side == "hit" else 20):
                continue
            age_row = next((h for h in hist if h.get("age")), None)
            role = hist[0].get("role")
            age = (age_row["age"] + (cur + 1 - age_row["season"])) if age_row else None
            proj = fp.project_player(hist, side, cur + 1, curves, league, age,
                                     role=role, in_progress=in_prog)
            if not proj:
                continue
            name = _name(mid)
            if side == "hit":
                ros_pa = (proj.get("pt_proj") or 0) * remaining
                if ros_pa < 20:
                    continue
                stats = _hitter_ros(proj, ros_pa, sb_rate.get(mid))
                pts = fscore.score_points(stats, "fgp", "hit")
                players.append({"mlbam": mid, "name": name, "side": "hit",
                                "pos": role, "ros": stats, "fpts_fgp": pts})
            else:
                ros_bf = (proj.get("pt_proj") or 0) * remaining
                ros_ip = (proj.get("ip_proj") or 0) * remaining
                if ros_ip < 8:
                    continue
                pr = "SP" if (role == "SP") else "RP"
                stats = _pitcher_ros(proj, ros_bf, ros_ip, pr, ipgs_map.get(mid))
                if pr == "RP" and frac > 0:
                    sh = rp_sh.get(mid) or {}
                    stats["sv"] = round((sh.get("sv") or 0) * remaining / frac, 1)
                    stats["hld"] = round((sh.get("hld") or 0) * remaining / frac, 1)
                pts = fscore.score_points(stats, "fgp", "pit")
                players.append({"mlbam": mid, "name": name, "side": "pit",
                                "pos": pr, "ros": stats, "fpts_fgp": pts})

    _enrich(players)
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "season": cur,
        "season_fraction": round(frac, 3),
        "n_players": len(players),
        "scoring": fscore.points_weight_tables(),
        "scoring_catalog": fscore.SCORING_CATALOG,
        "players": players,
    }


def _lb_index(fname: str, key: str) -> dict:
    return {int(r["mlbam"]): r
            for r in ((_load_json(fname) or {}).get(key) or []) if r.get("mlbam")}


def _player_luck(p: dict):
    """Raw regression-candidate luck for a player: hitter luck_gap (xHEM+ - HEM+,
    a plus-stat delta) or pitcher luck (wOBA - xwOBA, in wOBA points)."""
    s = p.get("skill") or {}
    return s.get("luck_gap") if p.get("side") == "hit" else s.get("luck")


def _buy_sell(players: list[dict], n: int = 50) -> tuple[list, list]:
    """Combined Buy-Low / Sell-High mlbam lists (positive luck = unlucky = buy).

    Hitter luck_gap (plus-stat units, spread ~+/-50) and pitcher luck (wOBA
    points, spread ~+/-0.05) sit ~500x apart, so a raw combined sort buries
    pitchers in the middle and fills both top-N lists with hitters only. Scale
    each side's luck by its own pool spread (population std) onto a common axis
    before the combined sort. Scaling by std (not mean-centering) preserves the
    sign, so a buy row keeps a positive gap and a sell row a negative one."""
    import statistics
    luckable = [p for p in players
                if _player_luck(p) is not None and (p.get("fpts_fgp") or 0) > 20]
    scale: dict = {}
    for side in ("hit", "pit"):
        vals = [_player_luck(p) for p in luckable if p.get("side") == side]
        scale[side] = statistics.pstdev(vals) if len(vals) >= 2 else 0.0

    def _norm(p):
        sd = scale.get(p.get("side")) or 0.0
        return (_player_luck(p) / sd) if sd else 0.0

    # Entries carry SIDE, unlike the other section lists, because this is the one
    # section a bare mlbam cannot resolve. Every other section is single-sided by
    # construction (ros_hitter is hitters, closer_depth is relievers), so its
    # renderer already knows which side to look up. buy/sell is the only COMBINED
    # ranking, so a two-way player's two records are both eligible and a bare id
    # is genuinely ambiguous. Shohei Ohtani is that player today: he is ranked in
    # on his HIT-side luck_gap, and before this the client resolved him to his
    # pitcher record and rendered a pitcher's luck number under a hitter's ranking.
    buy = [{"mlbam": p["mlbam"], "side": p.get("side")}
           for p in sorted(luckable, key=lambda p: -_norm(p))[:n]]
    sell = [{"mlbam": p["mlbam"], "side": p.get("side")}
            for p in sorted(luckable, key=lambda p: _norm(p))[:n]]
    return buy, sell


def _attach_swing_trend(players: list[dict]) -> None:
    """W6 DISPLAY-ONLY mechanics-trend annotation from the per-season Swing+
    sidecar (data/swing_plus.json, Will Cahoon's model). Latest-season minus
    prior-season Swing+; annotated only when the move is >= +/-5 points.
    NON-SCORING by construction: no ranking, sorting, or section-membership
    code reads swing_trend (_buy_sell sorts on luck only) - the client renders
    it as a context chip on the buy/sell boards."""
    sw = (_load_json("swing_plus.json") or {}).get("players") or {}
    for p in players:
        seasons = (sw.get(str(p.get("mlbam"))) or {}).get("seasons") or {}
        yrs = sorted(y for y in seasons
                     if (seasons[y] or {}).get("swing_plus") is not None)
        if len(yrs) < 2:
            continue
        cur, prev = seasons[yrs[-1]], seasons[yrs[-2]]
        delta = round(float(cur["swing_plus"]) - float(prev["swing_plus"]), 1)
        if abs(delta) >= 5:
            p["swing_trend"] = {"delta": delta,
                                "from": int(yrs[-2]), "to": int(yrs[-1])}


@functools.lru_cache(maxsize=64)
def _canon_org(code: str | None) -> str | None:
    """THE org-code canonicaliser for this module and for dfs_export.

    WHAT IT IS FOR. The hitter/bullpen leaderboards key teams by MLB-style codes
    (AZ, CWS, KC, SD, SF, TB, WSH) while the schedule feed emits the canonical
    codes (ARI, CHW, KCR, SDP, SFG, TBR, WSN). Re-key on ingest and
    teams_ctx.get(opp_org) resolves all 30 opponents; do not, and 7 of them fall
    through to the neutral offense_plus=100 path with nothing raised and nothing
    logged (data/fantasy_startscore_eval.json: 23% of 2026 starts affected).

    ONE IMPLEMENTATION, on purpose. This used to be a private 7-entry map right
    here, which disagreed with trades.canonical_org (the site's owner of this
    mapping) in two ways that both cost real rows: it was MISSING OAK -> ATH,
    and any future code change would have had to be found in two places by
    somebody who did not know the second one existed.

    Lazy import: trades.py pulls requests and the scrapers, and this module sits
    on the daily path (the same reason fantasy_schedule._org imports lazily).
    An unavailable canonicaliser returns the code as given, which is exactly
    what an unmapped code already did."""
    if not code:
        return None
    try:
        from trades import canonical_org
    except Exception:                                        # pragma: no cover
        log.warning("trades.canonical_org unavailable; org codes left as given")
        return code
    return canonical_org(code) or code


# One process files at most one short-context RED: _teams_context is called by
# build_sections AND by dfs_export inside the same run, and a ledger that
# repeats itself is a ledger people stop reading.
_MLB_CLUBS = 30
_teams_ctx_reported = False


def _teams_context_health(ctx: dict) -> dict:
    """How much of the opponent context actually resolved, by field."""
    def _n(field: str) -> int:
        return sum(1 for r in (ctx or {}).values()
                   if isinstance((r or {}).get(field), (int, float)))
    return {"n_orgs": len(ctx or {}), "n_offense_plus": _n("offense_plus"),
            "n_bullpen_plus": _n("bullpen_plus")}


def _teams_context() -> dict:
    """{org: {offense_plus, heart_hem, bullpen_plus, leverage_deploy_plus}} - the
    opponent-quality context a streamer ranking needs.

    Keyed by CANONICAL org on both legs (see _canon_org). A row whose code will
    not canonicalize is DROPPED rather than filed under a None key: a None key
    answers `teams_ctx.get(opp_org)` for every game side whose org failed to
    resolve, which hands an unknown opponent some real club's Offense+.

    The COUNT is reported when it comes up short. Nothing downstream fails on a
    thin context - every consumer defaults a missing club to the neutral 100 -
    so a broken join and a league-average opponent read identically unless
    somebody counts. That is the 2026-08-05 defect class exactly."""
    out: dict = {}
    for fname, fields in (
            ("hitter_leaderboards.json", ("offense_plus", "heart_hem")),
            ("bullpen_leaderboards.json", ("bullpen_plus", "leverage_deploy_plus"))):
        for t in ((_load_json(fname) or {}).get("teams") or []):
            org = _canon_org(t.get("team"))
            if not org:
                continue
            out.setdefault(org, {}).update({f: t.get(f) for f in fields})
    _report_teams_context(out)
    return out


def _report_teams_context(ctx: dict) -> None:
    """Log (and RED, once) an opponent context that does not cover all 30 clubs."""
    global _teams_ctx_reported
    h = _teams_context_health(ctx)
    if h["n_offense_plus"] >= _MLB_CLUBS and h["n_bullpen_plus"] >= _MLB_CLUBS:
        log.info("fantasy: opponent context resolved for %d orgs (Offense+ %d, "
                 "Bullpen+ %d)", h["n_orgs"], h["n_offense_plus"], h["n_bullpen_plus"])
        return
    msg = (f"opponent context covers {h['n_offense_plus']}/{_MLB_CLUBS} clubs on "
           f"Offense+ and {h['n_bullpen_plus']}/{_MLB_CLUBS} on Bullpen+; every "
           f"club that missed is priced at the neutral 100 on the streamer, "
           f"two-start and DFS boards")
    log.warning("fantasy: %s", msg)
    if not _teams_ctx_reported:
        _teams_ctx_reported = True
        _record_ingest_safe("fantasy_teams_context", ok=False, message=msg,
                            n_rows=h["n_offense_plus"])


def _enrich(players: list[dict]) -> None:
    """Attach each player's team + the skill metrics the /fantasy/ surface reads
    from the matching skill leaderboard (mlbam-joined). Powers the section
    signals (luck_gap/luck -> buy/sell, gmli/saves -> closers) and the card
    HEM+/SEM+/REM+ display. Only the read keys are baked: the old p['std'] block
    and the wider skill set had zero reader (client or server) - dead payload.

    ALSO bakes `elig`, the fantasy position eligibility list (2026-08-05, for
    the /dfs/ and /redraft/ split). The corpus role for a hitter is the bare
    string "H", which is useless to a lineup slot, so eligibility is joined from
    data/mlb_fielding_positions.json. Additive: every existing reader of `pos`
    is untouched, and dfs_export re-reads the same artifact itself when a
    payload predates this field.

    DATA-HOLE FALLBACK (2026-08-16): the three skill leaderboards carry only
    players who qualified for a board, so joining team from them alone left
    169 of 1184 pool players teamless, 10 nameless and 88 hitters without elig
    on the live artifact. data/mlb_player_detail.json (mlbam-resolvable,
    nightly-fresh) backfills team, name and a single-position elig; it fills
    holes only and never overrides a leaderboard value."""
    hit = _lb_index("hitter_leaderboards.json", "hitters")
    sp = _lb_index("starter_leaderboards.json", "starters")
    rp = _lb_index("bullpen_leaderboards.json", "relievers")
    elig = _elig_positions()
    detail = _detail_by_mlbam()
    for p in players:
        mid, r = p["mlbam"], None
        if p["side"] == "hit":
            r = hit.get(mid) or {}
            p["skill"] = {k: r.get(k) for k in ("hem_plus", "luck_gap")}
            slots = elig.get(mid)
            if slots:
                p["elig"] = slots
        elif p["pos"] == "SP":
            r = sp.get(mid) or {}
            p["skill"] = {k: r.get(k) for k in ("sem_plus", "luck")}
            p["elig"] = ["P"]
        else:
            r = rp.get(mid) or {}
            p["skill"] = {k: r.get(k) for k in ("rem_plus", "gmli", "saves", "luck")}
            p["elig"] = ["P"]
        p["team"] = r.get("team")
        d = detail.get(mid)
        if d:
            if not p.get("team"):
                p["team"] = d.get("team")
            if not p.get("name"):
                p["name"] = d.get("name")
            if p["side"] == "hit" and not p.get("elig"):
                slot = _POS_SLOT.get(d.get("pos") or "")
                if slot:
                    p["elig"] = [slot]


# StatsAPI fielding abbreviation -> fantasy lineup slot. A hitter with no
# fielding position over the games floor gets no `elig` at all rather than a
# guessed one; the reader falls back to UTIL and says so.
_POS_SLOT = {"C": "C", "1B": "1B", "2B": "2B", "3B": "3B", "SS": "SS",
             "LF": "OF", "CF": "OF", "RF": "OF", "OF": "OF", "DH": "UTIL"}
_ELIG_MIN_GAMES = 5


def _elig_positions() -> dict:
    """{mlbam: [slot, ...]} from data/mlb_fielding_positions.json, most-played
    first. A position counts at >= _ELIG_MIN_GAMES; the modal position always
    counts so a mid-season call-up is never slotless. Empty when the artifact
    is absent (fresh checkout), which simply leaves `elig` off the row."""
    raw = _load_json("mlb_fielding_positions.json")
    players = (raw or {}).get("players") if isinstance(raw, dict) else None
    out: dict = {}
    if not isinstance(players, dict):
        return out
    for rec in players.values():
        mid = (rec or {}).get("mlbam")
        pos = (rec or {}).get("positions") or {}
        if not mid or not isinstance(pos, dict):
            continue
        counts = {p: float((v or {}).get("games") or 0)
                  for p, v in pos.items() if p != "P"}
        if not counts:
            continue
        modal = max(counts, key=lambda p: counts[p])
        slots: list = []
        for p, games in sorted(counts.items(), key=lambda kv: -kv[1]):
            if games < _ELIG_MIN_GAMES and p != modal:
                continue
            s = _POS_SLOT.get(p)
            if s and s not in slots:
                slots.append(s)
        if slots:
            out[int(mid)] = slots
    return out


def _detail_by_mlbam() -> dict:
    """{mlbam: {team, name, pos}} off data/mlb_player_detail.json - the fallback
    identity join for pool players the three skill leaderboards never carried
    (see _enrich). One load, three fields kept, dict lookups after that; empty
    when the artifact is absent, which simply leaves the holes as they were."""
    raw = _load_json("mlb_player_detail.json")
    players = (raw or {}).get("players") if isinstance(raw, dict) else None
    out: dict = {}
    if not isinstance(players, dict):
        return out
    for rec in players.values():
        mid = (rec or {}).get("mlbam")
        if not mid:
            continue
        out[int(mid)] = {"team": rec.get("team"), "name": rec.get("name"),
                         "pos": rec.get("pos")}
    return out


def _callup_watch(ts: dict | None = None) -> list:
    """Best-effort: fantasy-relevant prospects near the majors, from PROSPX forward
    signals (timeseries.json, a generated artifact). Empty when unavailable. Accepts
    a pre-loaded timeseries dict so build_sections parses the ~66MB file once for
    both this and the dynasty ranking."""
    if ts is None:
        ts = _load_json("timeseries.json")
    if not isinstance(ts, dict):
        return []
    out = []
    for pl in (ts.get("players") or []):
        eta = pl.get("eta")
        eta_year = eta.get("year") if isinstance(eta, dict) else eta
        near = (str(eta_year) in ("2026", "2027")) if eta_year else False
        if near and pl.get("mlbam_id"):
            # eFV leads, consensus is the fallback: this column served an
            # unlabeled consensus FV on a site whose grade is eFV, so a
            # call-up-watch row could disagree with the same player's board row.
            efv = (_efv_by_key() or {}).get(pl.get("player_key"))
            out.append({"mlbam": pl.get("mlbam_id"), "name": pl.get("player_name"),
                        "org": pl.get("org"), "pos": pl.get("position"), "eta": eta_year,
                        "fv": pl.get("consensus_fv") or pl.get("fv_close"),
                        "fvE": round(efv, 1) if efv is not None else None})
    out.sort(key=lambda x: -(x.get("fvE") if x.get("fvE") is not None else (x.get("fv") or 0)))
    return out[:60]


# The blend weights and the ETA-proximity decay live in dynasty_blend (shared
# with the card market exporter until that module was removed 2026-09-05). This module carried its own copies
# until 2026-08-16, when the card clone was found decaying ETA at 0.25 against
# this module's 0.18; one importable module is the only shape that cannot
# re-diverge.


def _dynasty_tier(rank: int) -> str:
    """Rank-bucket label for the dynasty board (mirrors how ranking products group
    an ordered list into tiers)."""
    if rank <= 10:
        return "Elite"
    if rank <= 25:
        return "Tier 1"
    if rank <= 50:
        return "Tier 2"
    if rank <= 100:
        return "Tier 3"
    if rank <= 200:
        return "Tier 4"
    return "Depth"


def _dynasty_prospects(ts: dict | None, season: int, xfv: dict | None = None,
                       n: int = 300) -> list:
    """eFV-derived Dynasty Prospect rankings.

    A DISPLAY-LAYER blend (like the client's scoring re-rank), not a trained model:
    it moves no served eFV number and triggers no model gate. Joins the flagship
    eFV rows in data/xfv.json (by_player, slug-keyed) to the PROSPX prospect roster
    in timeseries.json (player_key -> mlbam / name / org / pos / ETA), then ranks
    by the shared dynasty_blend composite with THE board grade PRIMARY:

        score = _board_grade(xr)                       # primary driver, the shown eFV
              + W_STAR * p_bucket['star']              # ceiling premium (star odds)
              + W_BUST * p_bust                        # floor risk (negative weight)
              + W_ETA * eta_proximity(eta, season)     # sooner ETA = value sooner
              + W_SURPLUS * clamp(surplus_mm / 100)    # surplus composite (tiebreak)

    Driver and DISPLAYED `efv` column are the SAME number since 2026-08-16: the
    board grade PROSPX, the homepage and /projections/ serve, so the ranking can
    no longer contradict its own visible column (see the driver comment below for
    the measurement). One eFV basis across Dynasty and Call-up Watch, as before.

    Returns rows sorted desc with rank + rank-bucket tier + the eFV outcome band
    (band_p10_mm..band_p90_mm, $M). Best-effort: empty list when inputs unavailable."""
    if not isinstance(ts, dict):
        return []
    if xfv is None:
        xfv = _load_json("xfv.json")
    by_player = (xfv or {}).get("by_player")
    if not isinstance(by_player, dict):
        return []
    rows: list[dict] = []
    for pl in (ts.get("players") or []):
        key = pl.get("player_key")
        xr = by_player.get(key) if key else None
        mid = pl.get("mlbam_id")
        if not xr or not mid:
            continue
        # THE DRIVER IS THE BOARD GRADE (2026-08-16). Until today the score drove
        # on the retired xfv_grade_quantile, a scale the site displays nowhere,
        # while the row displayed _board_grade. The comment that used to sit here
        # defended that with a fear: swapping the driver would silently re-weight
        # the composite, because the weights were set against the quantile's
        # spread. Measured on the live artifacts, the fear points the wrong way.
        # On the served top-300 board, ranking on _board_grade with UNCHANGED
        # weights cut visible adjacent inversions 82 to 75, >=2pt inversions 52
        # to 20, the worst inversion 7.2 to 3.4 FV, and lifted Spearman(rank,
        # shown eFV) 0.848 to 0.951 - a variance-matched re-derivation was WORSE
        # than leaving them alone (98 inversions). The quantile now survives only
        # inside _board_grade's standing fallback chain (board_value ->
        # xfv_grade_realized -> xfv_grade_quantile), where it is a last resort,
        # not a driver. tools/dynasty_basis_probe.py reproduces the measurement.
        grade = _board_grade(xr)
        if grade is None:
            continue
        pb = xr.get("p_bucket") or {}
        star = pb.get("star") or 0.0
        bust = xr.get("p_bust")
        if bust is None:
            bust = pb.get("bust") or 0.0
        eta = pl.get("eta")
        eta_year = eta.get("year") if isinstance(eta, dict) else (eta if isinstance(eta, int) else None)
        score = dynasty_blend.blend_score(
            grade, star, bust,
            dynasty_blend.eta_proximity(eta_year, season),
            dynasty_blend.surplus_norm(xr.get("surplus_mm")))
        rows.append({
            "mlbam": mid, "name": pl.get("player_name"), "org": pl.get("org"),
            "pos": pl.get("position"), "eta": eta_year,
            "efv": round(grade, 1), "star": round(star * 100),
            "bust": round((bust or 0.0) * 100),
            "surplus": round(xr.get("surplus_mm") or 0.0),
            "band": [xr.get("band_p10_mm"), xr.get("band_p90_mm")],
            "score": round(score, 1),
        })
    rows.sort(key=lambda r: -(r["score"] if r.get("score") is not None else -1e9))
    rows = rows[:n]
    for i, r in enumerate(rows):
        r["rank"] = i + 1
        r["tier"] = _dynasty_tier(i + 1)
    return rows


def _start_score(p: dict, opp_org: str | None, teams_ctx: dict) -> dict | None:
    """Expected FGP for ONE start: per-start ROS points scaled by the opponent's
    offense (weaker offense → better streamer).

    THE FALLBACK 100 IS NOW LABELLED. An opponent we cannot look up still prices
    at Offense+ 100, because a league-average opponent is the honest guess and
    changing that would move served numbers. What changes is that the row says
    which kind of 100 it is: `opp_off_resolved` false means nobody measured this
    club today. Five clubs genuinely sit at 100, so an unlabelled 100 made a
    total join failure look exactly like an average lineup - and that is how the
    7-org code-set miss went unnoticed for months. The multiplier math below is
    untouched."""
    if not p:
        return None
    ros = p.get("ros") or {}
    gs = ros.get("gs") or 0
    if gs <= 0:
        return None
    per_start = (p.get("fpts_fgp") or 0) / gs
    raw_off = ((teams_ctx or {}).get(opp_org) or {}).get("offense_plus")
    resolved = isinstance(raw_off, (int, float)) and bool(raw_off)
    opp_off = raw_off if resolved else 100
    mult = max(0.6, min(1.5, 100.0 / opp_off)) if opp_off else 1.0
    return {"per_start_fgp": round(per_start * mult, 1),
            "per_start_base": round(per_start, 1), "opp_off": opp_off,
            "opp_off_resolved": resolved}


def _team_next7(sched7: dict | None, teams_ctx: dict) -> dict:
    """sections.team_next7: {org: [{d, opp, home, opp_off, opp_bp}, ...]} for the
    next 7 days (2026-08-16), the schedule strip the player card renders.

    The raw slate is schedule.team_sched7 (see _attach_schedule: the 7-day
    probables fetch used to be discarded once two_start was derived from it);
    this join only adds the opponent context the card colors chips by, from the
    same _teams_context the streamer and DFS boards already price against. An
    opponent the context cannot resolve carries None rather than a fabricated
    100: the card renders that chip neutral, which is the same "missing is not
    average" rule the DFS matchup mark enforces. Values are rounded to ints
    because 30 orgs x 7 games ride the corpus payload and a decimal tail is
    pure bytes on a display strip."""
    def _plus(v):
        return round(v) if isinstance(v, (int, float)) else None
    out: dict = {}
    for org, games in (sched7 or {}).items():
        rows = []
        for g in (games or [])[:7]:
            g = g or {}
            opp = g.get("opp")
            ctx = (teams_ctx or {}).get(opp) or {}
            rows.append({"d": g.get("d"), "opp": opp,
                         "home": bool(g.get("home")),
                         "opp_off": _plus(ctx.get("offense_plus")),
                         "opp_bp": _plus(ctx.get("bullpen_plus"))})
        if rows:
            out[org] = rows
    return out


def build_sections(payload: dict) -> dict:
    """Organize the projected pool + schedule + skill context into the sections
    (eleven of them as of 2026-08-16; the count in this line has drifted twice,
    so count the keys below rather than trusting a number in prose).
    ROS/streamer/buy-sell/closer sections reference the MLB pool by mlbam (client
    resolves against `players`); the prospect sections (callup_watch, dynasty) are
    self-contained rows joined from timeseries.json + xfv.json; team_next7 is the
    per-club 7-day schedule strip the player card renders."""
    players = payload["players"]
    # Display-only Swing+ mechanics-trend chips (attached here so the daily
    # refresh_live path re-bakes them too). Never read by any section sort.
    _attach_swing_trend(players)
    hitters = [p for p in players if p["side"] == "hit"]
    sps = [p for p in players if p.get("pos") == "SP"]
    rps = [p for p in players if p["side"] == "pit" and p.get("pos") == "RP"]
    sp_by_id = {p["mlbam"]: p for p in sps}
    teams_ctx = _teams_context()

    def rank(lst, n):
        return [p["mlbam"] for p in sorted(lst, key=lambda p: -(p.get("fpts_fgp") if p.get("fpts_fgp") is not None else -1e9))[:n]]

    sections: dict = {
        "ros_hitter": rank(hitters, 350),
        "ros_sp": rank(sps, 250),
        "ros_rp": rank(rps, 180),
    }

    # Buy-Low / Sell-High. Hitters by luck_gap (xHEM+ - HEM+; + = unlucky = buy),
    # pitchers by `luck` (xERA/xwOBA vs actual). Positive residual = due to
    # regress up. The two luck scales are ~500x apart, so _buy_sell normalizes
    # each side by its own spread before the combined sort (see _buy_sell).
    sections["buy_low"], sections["sell_high"] = _buy_sell(players)

    # Closer Depth Chart — relievers grouped by team, ranked by a role score
    # (avg leverage gmli dominates; saves + REM+ break ties). Top = likely closer,
    # rest = handcuffs.
    from collections import defaultdict
    by_team: dict[str, list] = defaultdict(list)
    for p in rps:
        if p.get("team"):
            by_team[p["team"]].append(p)

    def _role_score(p):
        s = p.get("skill") or {}
        return (s.get("gmli") or 0) * 100 + (s.get("saves") or 0) * 3 + (s.get("rem_plus") or 0) * 0.2
    sections["closer_depth"] = {
        team: [p["mlbam"] for p in sorted(lst, key=lambda p: -_role_score(p))[:5]]
        for team, lst in by_team.items()}

    # Daily SP Streamers — each announced probable start over the next 3 days,
    # ranked by matchup-adjusted expected FGP.
    sched = payload.get("schedule") or {}
    streamers = []
    for g in (sched.get("games") or []):
        for me, opp in (("home", "away"), ("away", "home")):
            pp = (g.get(me) or {}).get("probable")
            if not pp or not pp.get("mlbam"):
                continue
            sc = _start_score(sp_by_id.get(pp["mlbam"]), (g.get(opp) or {}).get("org"), teams_ctx)
            if not sc:
                continue
            sc.update({"mlbam": pp["mlbam"], "name": pp.get("name"), "date": g.get("date"),
                       "team": (g.get(me) or {}).get("org"), "opp_org": (g.get(opp) or {}).get("org"),
                       "venue": (g.get("venue") or {}).get("name")})
            streamers.append(sc)
    streamers.sort(key=lambda s: -(s.get("per_start_fgp") or -1e9))
    sections["daily_streamers"] = streamers
    # Count the fallback opponents out loud. A streamer board where every row
    # carries the neutral 100 is a board with no matchup term at all, and it
    # renders exactly like a working one.
    n_unres = sum(1 for s in streamers if not s.get("opp_off_resolved"))
    if n_unres:
        log.warning("fantasy: %d of %d streamer starts could not resolve an "
                    "opponent Offense+ and are priced at the neutral 100",
                    n_unres, len(streamers))

    # Two-Start SP — pitchers with 2 starts this week (announced + projected),
    # ranked by summed expected FGP. A projected leg scores through the same
    # _start_score (the opponent multiplier only needs opp_org) and carries its
    # `projected` flag into the row payload for the client's "(proj)" suffix.
    two = []
    for mid_s, starts in (sched.get("two_start") or {}).items():
        p = sp_by_id.get(int(mid_s))
        legs, total = [], 0.0
        for st in starts:
            sc = _start_score(p, st.get("opp_org"), teams_ctx)
            leg = {"date": st.get("date"), "opp_org": st.get("opp_org"),
                   "exp_fgp": (sc or {}).get("per_start_fgp")}
            if st.get("projected"):
                leg["projected"] = True
            legs.append(leg)
            total += (sc or {}).get("per_start_fgp") or 0
        # Pool misses (spot starters / no ROS projection) still list: fall back
        # to the schedule's own probable name + org so the row never renders
        # blank (they sort to the bottom on total_fgp anyway).
        first = starts[0] if starts else {}
        two.append({"mlbam": int(mid_s),
                    "name": (p or {}).get("name") or first.get("name"),
                    "team": (p or {}).get("team") or first.get("team_org"),
                    "n_starts": len(starts),
                    "total_fgp": round(total, 1), "legs": legs})
    two.sort(key=lambda s: -(s.get("total_fgp") or -1e9))
    sections["two_start"] = two

    # The per-club next-7 strip for the player card, off the same 7-day slate
    # two_start already rides and the same opponent context the streamers price
    # against. Absent on a payload from before 2026-08-16, which simply renders
    # no strip.
    sections["team_next7"] = _team_next7(sched.get("team_sched7"), teams_ctx)

    # Parse the ~66MB timeseries.json ONCE for both prospect-roster sections.
    ts = _load_json("timeseries.json")
    sections["callup_watch"] = _callup_watch(ts)
    season = payload.get("season") or datetime.now(timezone.utc).year
    sections["dynasty"] = _dynasty_prospects(ts, season)
    return sections


def _attach_schedule(payload: dict) -> None:
    """Attach the next-3-day probables (streamers) and the 7-day two-start view.

    Two-start uses PROJECTED second legs (fsched.projected_two_start): probables
    only post ~4-5 days out, so requiring two ANNOUNCED starts left the section
    empty by construction. Legs keep their `projected` flag for the client."""
    try:
        s3, e3 = fsched.date_window(3)
        games3 = fsched.fetch_probables(s3, e3)
        s7, e7 = fsched.date_window(7)
        games7 = fsched.fetch_probables(s7, e7)
        starts7 = fsched.starts_index(games7)
        team_sched = fsched.team_schedule(games7)
        two = fsched.projected_two_start(starts7, team_sched, e7)
        payload["schedule"] = {
            "streamer_window": [s3, e3],
            "games": games3,
            "two_start": {str(m): v for m, v in two.items()},
            # The 7-day per-club slate, compacted to (date, opponent, side).
            # Until 2026-08-16 games7 was fetched and then DISCARDED once
            # two_start was derived from it; keeping this ~10KB view is what
            # lets build_sections bake the card's next-7 strip (team_next7)
            # without a second fetch, and lets a kept stale schedule keep its
            # strip too.
            "team_sched7": {org: [{"d": g.get("date"), "opp": g.get("opp_org"),
                                   "home": bool(g.get("is_home"))}
                                  for g in lst[:7]]
                            for org, lst in team_sched.items()},
            # Every ANNOUNCED probable start in the 7-day window, compacted to
            # (mlbam, date). ~2KB. The two-start ledger grades yesterday's
            # projected legs against these postings (2026-08-16); a projected
            # leg is by construction absent from this list on the day it is
            # projected, so a leg can never confirm itself.
            "announced7": [{"mlbam": s["mlbam"], "d": s.get("date")}
                           for s in starts7
                           if s.get("mlbam") and s.get("date")],
        }
    except Exception:
        log.exception("fantasy: schedule attach failed — continuing without probables")
        payload["schedule"] = {"games": [], "two_start": {}, "team_sched7": {},
                               "announced7": []}


def _record_schedule_anomaly(n_prev: int) -> None:
    """Raise an empty schedule fetch into the ingest-health RED ledger.

    Best-effort by design: this is a reporting path, and it must never be the
    reason a refresh fails. The ledger is what the deploy shell prints as
    `!!! INGEST RED`, so a silent schedule outage becomes visible instead of
    showing up days later as four empty modules."""
    _record_ingest_safe(
        "fantasy_schedule", ok=False,
        message=(f"probables fetch returned 0 game days; kept the previous "
                 f"{n_prev}-day schedule. Streamers, two-start, DFS and the "
                 f"betting slate all read this schedule."))


# ---------------------------------------------------------------------------
# Two-start projection ledger (2026-08-16). AN INSTRUMENT, NOT A MODEL.
#
# The two-start section serves PROJECTED second legs (a rest-cycle guess, see
# fsched.projected_two_start) and nothing ever measured whether those guesses
# come true. This ledger is the measurement: every projected leg served by the
# daily refresh is recorded, and when the real probable postings later confirm
# or refute it, a grade row is appended. After a few weeks the hit rate decides
# whether a rotation-order model is worth building at all; until then no served
# number moves and nothing reads this file at serve time.
#
# Durable per-box state, so it lives under .cache/ (the deploy box runs
# `git checkout -- .` nightly and would revert anything under data/).
# Append-only jsonl in the normal case; the file is BOUNDED by a documented
# compaction (rows older than _LEDGER_RETENTION_DAYS dropped, then a hard line
# cap), applied in the same write pass, so it cannot grow without limit.
# ---------------------------------------------------------------------------
LEDGER_PATH = Path(__file__).parent / ".cache" / "two_start_ledger.jsonl"
_LEDGER_RETENTION_DAYS = 120     # projections older than this have been graded
                                 # or never will be; drop them on write
_LEDGER_MAX_LINES = 50000        # hard cap behind the retention window, so a
                                 # clock bug cannot produce an unbounded file
# A posting within this many days of the projected leg is the SAME start moved,
# not a different one: rotations slide a day around off days and openers. The
# announced first leg sits >= 4 days from the projected second (the projection
# window is D+4..D+6), so it can never fall inside this slack.
_LEDGER_GRADE_SLACK_DAYS = 2


def _ledger_rows(path: Path) -> list[dict]:
    """Every parseable row of the ledger, oldest first. A corrupt line is
    skipped rather than fatal: the ledger is an instrument and a torn write
    (the box lost power mid-append) must not brick the daily refresh."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return []
    rows: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(r, dict):
            rows.append(r)
    return rows


def _rest_window(first_date: str | None) -> list | None:
    """[D+4, D+6] for an announced first leg on D: the window the projection
    was drawn from (fsched.projected_two_start's rest cycle)."""
    try:
        d0 = date.fromisoformat(first_date or "")
    except ValueError:
        return None
    return [(d0 + timedelta(days=4)).isoformat(), (d0 + timedelta(days=6)).isoformat()]


def _grade_pending(pending: list, ann_by_pid: dict, today: str) -> list:
    """Grade rows for the pending projected legs the announced postings can now
    confirm or refute. Pure. Three outcomes, graded on the POSTING (which is
    what the projection claimed would happen), not on the game result:

      * started: a probable is posted for the pitcher ON the projected date;
      * pushed: a probable is posted within _LEDGER_GRADE_SLACK_DAYS of it but
        on a different date (the start moved, the rotation-order guess held);
      * skipped: the projected date has passed and no posting ever matched
        while it was in view.

    Anything else stays pending: probables post ~4-5 days out, so a projected
    leg is UNGRADEABLE on the day it is made and that is not a miss."""
    out: list = []
    for (mid, leg_date) in pending:
        dates = ann_by_pid.get(mid) or set()
        resolved = resolved_date = None
        if leg_date in dates:
            resolved, resolved_date = "started", leg_date
        else:
            near = []
            for d in dates:
                try:
                    gap = abs((date.fromisoformat(d)
                               - date.fromisoformat(leg_date)).days)
                except ValueError:
                    continue
                if gap <= _LEDGER_GRADE_SLACK_DAYS:
                    near.append(d)
            if near:
                resolved, resolved_date = "pushed", min(near)
            elif leg_date < today:
                resolved, resolved_date = "skipped", today
        if resolved:
            out.append({"kind": "grade", "mlbam": mid, "projected_date": leg_date,
                        "resolved": resolved, "resolved_date": resolved_date,
                        "graded_on": today})
    return out


def _compact_ledger(rows: list, today: str) -> tuple[list, int]:
    """(kept rows, dropped count) under the documented bound: a row's anchor
    date (date_projected for projections, graded_on for grades) must be within
    _LEDGER_RETENTION_DAYS of today, and the survivors are hard-capped at
    _LEDGER_MAX_LINES newest."""
    try:
        cutoff = (date.fromisoformat(today)
                  - timedelta(days=_LEDGER_RETENTION_DAYS)).isoformat()
    except ValueError:
        return rows, 0
    kept = [r for r in rows
            if str(r.get("date_projected") or r.get("graded_on") or today) >= cutoff]
    if len(kept) > _LEDGER_MAX_LINES:
        kept = kept[-_LEDGER_MAX_LINES:]
    return kept, len(rows) - len(kept)


def update_two_start_ledger(two_start: dict, announced: list, *, today: str,
                            path: Path | None = None) -> dict:
    """One daily pass over the ledger: record today's served projected legs,
    grade whatever the announced postings now resolve, compact, write.

    `two_start` is the payload's schedule.two_start ({mlbam_str: [legs]}, legs
    carrying `projected` on the guessed ones); `announced` is the compact
    schedule.announced7 list ([{mlbam, d}]). Idempotent per (mlbam, projected
    leg date) per day for projections and per (mlbam, projected leg date)
    forever for grades, so re-running a refresh appends nothing new. Returns
    {projected_added, grades_added, compacted_away, n_rows} for the caller's
    log line. Never raises past its caller's try (refresh_live wraps it): the
    ledger must never be the reason a refresh fails."""
    path = Path(path) if path is not None else LEDGER_PATH
    rows = _ledger_rows(path)
    proj_seen = {(r.get("date_projected"), r.get("mlbam"), r.get("leg_date"))
                 for r in rows if r.get("kind") == "projected"}
    graded = {(r.get("mlbam"), r.get("projected_date"))
              for r in rows if r.get("kind") == "grade"}

    new_rows: list = []
    for mid_s, legs in (two_start or {}).items():
        try:
            mid = int(mid_s)
        except (TypeError, ValueError):
            continue
        legs = legs or []
        first = legs[0] if legs else {}
        for leg in legs:
            leg = leg or {}
            if not leg.get("projected"):
                continue
            leg_date = leg.get("date")
            if not leg_date:
                continue
            key = (today, mid, leg_date)
            if key in proj_seen:
                continue
            proj_seen.add(key)
            new_rows.append({
                "kind": "projected", "date_projected": today, "mlbam": mid,
                "name": leg.get("name") or first.get("name"),
                "org": leg.get("team_org") or first.get("team_org"),
                "leg_date": leg_date,
                "leg_date_window": _rest_window(first.get("date")),
                "source_row": {"opp_org": leg.get("opp_org"),
                               "is_home": leg.get("is_home"),
                               "venue": leg.get("venue")},
            })

    ann_by_pid: dict = {}
    for a in announced or []:
        m, d0 = (a or {}).get("mlbam"), (a or {}).get("d")
        if m and d0:
            ann_by_pid.setdefault(int(m), set()).add(d0)
    pending: dict = {}
    for r in rows + new_rows:
        if r.get("kind") != "projected":
            continue
        k = (r.get("mlbam"), r.get("leg_date"))
        if None in k or k in graded:
            continue
        pending[k] = True
    grades = _grade_pending(list(pending), ann_by_pid, today)
    new_rows.extend(grades)

    kept, dropped = _compact_ledger(rows, today)
    path.parent.mkdir(parents=True, exist_ok=True)
    if dropped:
        # Compaction rewrites; the normal day is a pure append.
        text = "".join(json.dumps(r, separators=(",", ":")) + "\n"
                       for r in kept + new_rows)
        tmp = path.with_suffix(".jsonl.tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
    elif new_rows:
        with path.open("a", encoding="utf-8") as fh:
            for r in new_rows:
                fh.write(json.dumps(r, separators=(",", ":")) + "\n")
    return {"projected_added": sum(1 for r in new_rows if r["kind"] == "projected"),
            "grades_added": len(grades),
            "compacted_away": dropped,
            "n_rows": len(kept) + len(new_rows)}


def two_start_ledger_summary(path: Path | None = None) -> dict:
    """The instrument's readout: how the projected second legs have graded so
    far. Readable by a future page lane; nothing served reads it today. Legs
    are counted DISTINCT by (mlbam, projected leg date), because the same leg
    is legitimately re-served on consecutive days while it stays in the window
    and that is one guess, not several."""
    rows = _ledger_rows(Path(path) if path is not None else LEDGER_PATH)
    legs = {(r.get("mlbam"), r.get("leg_date")) for r in rows
            if r.get("kind") == "projected"}
    grades = [r for r in rows if r.get("kind") == "grade"]
    by_outcome: dict = {}
    for g in grades:
        by_outcome[str(g.get("resolved"))] = by_outcome.get(str(g.get("resolved")), 0) + 1
    n_graded = len(grades)
    started = by_outcome.get("started", 0)
    pushed = by_outcome.get("pushed", 0)
    graded_pairs = {(g.get("mlbam"), g.get("projected_date")) for g in grades}
    days = sorted({r.get("date_projected") for r in rows
                   if r.get("kind") == "projected" and r.get("date_projected")})
    return {
        "n_rows": len(rows),
        "n_projected_rows": sum(1 for r in rows if r.get("kind") == "projected"),
        "n_distinct_legs": len(legs),
        "n_graded": n_graded,
        # Counted over the legs still on file, not len(legs) - len(grades): a
        # compacted projection can leave a grade behind, and subtraction would
        # let that orphan hide a genuinely pending leg.
        "n_pending": sum(1 for k in legs if k not in graded_pairs),
        "by_outcome": by_outcome,
        # started alone is the strict read; started+pushed is the generous one
        # (the rotation-order guess held, the calendar slid). Both are served
        # so nobody has to re-derive them from the raw rows.
        "hit_rate_strict": round(started / n_graded, 3) if n_graded else None,
        "hit_rate_with_pushed": (round((started + pushed) / n_graded, 3)
                                 if n_graded else None),
        "first_projected": days[0] if days else None,
        "last_projected": days[-1] if days else None,
    }


def refresh_live(log=print) -> int:
    """DAILY cheap refresh: reuse the monthly ROS players, re-pull the probable-
    pitcher schedule, and rebuild the schedule-driven sections (streamers,
    two-start). Skips the heavy build_corpus()/projection entirely, so it's safe
    on the daily path (and off the OOM-sensitive monthly build). No-op until the
    monthly build has created data/fantasy.json."""
    payload = _load_json("fantasy.json")
    if not isinstance(payload, dict) or not payload.get("players"):
        if callable(log):
            log("fantasy: no monthly fantasy.json yet — skipping daily refresh")
        return 0
    # Keep the schedule we already have, so an empty fetch can be told apart from
    # a genuinely empty slate (see the guard below).
    _prev_games = ((payload.get("schedule") or {}).get("games") or {})
    _prev_sched7 = ((payload.get("schedule") or {}).get("team_sched7") or {})
    _prev_ann7 = ((payload.get("schedule") or {}).get("announced7") or [])
    _attach_schedule(payload)
    _new_games = ((payload.get("schedule") or {}).get("games") or {})
    # EMPTY-FETCH GUARD (2026-08-05). A StatsAPI hiccup during the daily refresh
    # returned zero game days mid-season, `build_sections` faithfully rebuilt
    # streamers and two-start as empty, and the resulting artifact was published
    # and committed - which dark-started FOUR surfaces at once (redraft streamers,
    # redraft two-start, the DFS slate, and the betting board, all of which read
    # this one schedule). Nothing errored, because an empty slate is a legitimate
    # state in the off-season and on an off day.
    # So: never let an empty fetch OVERWRITE a populated schedule. Losing a day of
    # freshness is recoverable on the next run; publishing four empty modules is
    # what a reader sees.
    if _prev_games and not _new_games:
        payload["schedule"]["games"] = _prev_games
        # The 7-day club slate rides the same fetch, so a kept schedule keeps
        # its next-7 strip too rather than blanking the card's chips while the
        # streamer board still shows yesterday's slate (2026-08-16).
        if _prev_sched7 and not payload["schedule"].get("team_sched7"):
            payload["schedule"]["team_sched7"] = _prev_sched7
        # The announced-starts view rides the same fetch; keeping it with the
        # kept schedule stops the two-start ledger from mis-grading a leg as
        # skipped on a day the feed was simply down (2026-08-16).
        if _prev_ann7 and not payload["schedule"].get("announced7"):
            payload["schedule"]["announced7"] = _prev_ann7
        payload["schedule"]["stale_schedule"] = True
        if callable(log):
            log("fantasy: schedule fetch returned NO game days but the previous "
                f"payload had {len(_prev_games)} - keeping the older schedule "
                "rather than publishing empty streamer/two-start/DFS/betting boards")
        _record_schedule_anomaly(len(_prev_games))
    else:
        payload.get("schedule", {}).pop("stale_schedule", None)
    payload["sections"] = build_sections(payload)
    payload["schedule_refreshed_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    blob = _json_blob(payload, "fantasy_export")
    if blob is None:
        return 0                    # already logged + RED; the old file stands
    OUT_PATH.write_text(blob, encoding="utf-8")
    # The two-start ledger records what was ACTUALLY served, so it runs only
    # after the write above succeeds. Best-effort by the same doctrine as the
    # ingest ledger: an instrument must never be the reason a refresh fails.
    try:
        sched = payload.get("schedule") or {}
        res = update_two_start_ledger(sched.get("two_start") or {},
                                      sched.get("announced7") or [],
                                      today=date.today().isoformat())
        if callable(log) and (res["projected_added"] or res["grades_added"]):
            log(f"fantasy: two-start ledger +{res['projected_added']} projected, "
                f"+{res['grades_added']} graded ({res['n_rows']} rows)")
    except Exception:
        logging.getLogger("fantasy_export").exception(
            "fantasy: two-start ledger update failed - continuing")
    if callable(log):
        n = len((payload.get("sections") or {}).get("daily_streamers") or [])
        log(f"fantasy: daily schedule refresh — {n} streamer starts")
    return len(payload.get("players") or [])


def export(log=print, *, limit: int | None = None) -> int:
    """Build data/fantasy.json. Returns the player count."""
    payload = build_players(limit=limit)
    _attach_schedule(payload)
    payload["sections"] = build_sections(payload)
    blob = _json_blob(payload, "fantasy_export")
    if blob is None:
        # The monthly corpus is the source of truth for /redraft/, /dynasty/,
        # /dfs/ and the betting slate. A corpus that will not serialize is a
        # model failure, not a quiet day, so it is raised as well as reported:
        # run_monthly's step wrapper logs it, and the previous fantasy.json
        # keeps serving rather than being replaced by nothing.
        raise ValueError("fantasy.json payload contains non-finite values")
    DATA_DIR.mkdir(exist_ok=True)
    OUT_PATH.write_text(blob, encoding="utf-8")
    if callable(log):
        log(f"fantasy: {payload['n_players']} players projected ROS "
            f"({payload['season']} @ {payload['season_fraction']:.0%} elapsed)")
    return payload["n_players"]


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Build data/fantasy.json (ROS projections + scoring).")
    ap.add_argument("--limit", type=int, default=None, help="cap players (fast partial verify)")
    args = ap.parse_args()
    n = export(log=print, limit=args.limit)
    print(f"wrote {OUT_PATH} ({n} players)")
