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
from datetime import datetime, timezone
from pathlib import Path

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
        "k9": round(9 * k / ip, 1) if ip > 0 else None,
        "_est": ["h", "er"],
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


# hitter/bullpen leaderboards key teams by MLB-style codes (AZ, CWS, KC, SD,
# SF, TB, WSH); the schedule feed emits canonical codes (ARI, CHW, KCR, SDP,
# SFG, TBR, WSN). Re-key on ingest so teams_ctx.get(opp_org) resolves all 30
# opponents (7 previously fell through to the neutral offense_plus=100 path;
# see data/fantasy_startscore_eval.json, 23% of 2026 starts affected).
_LB_TO_CANON = {"AZ": "ARI", "CWS": "CHW", "KC": "KCR", "SD": "SDP",
                "SF": "SFG", "TB": "TBR", "WSH": "WSN"}


def _teams_context() -> dict:
    """{org: {offense_plus, heart_hem, bullpen_plus, leverage_deploy_plus}} — the
    opponent-quality context a streamer ranking needs."""
    out: dict = {}
    for t in ((_load_json("hitter_leaderboards.json") or {}).get("teams") or []):
        out.setdefault(_LB_TO_CANON.get(t.get("team"), t.get("team")), {}).update(
            {"offense_plus": t.get("offense_plus"), "heart_hem": t.get("heart_hem")})
    for t in ((_load_json("bullpen_leaderboards.json") or {}).get("teams") or []):
        out.setdefault(_LB_TO_CANON.get(t.get("team"), t.get("team")), {}).update(
            {"bullpen_plus": t.get("bullpen_plus"),
             "leverage_deploy_plus": t.get("leverage_deploy_plus")})
    return out


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
    payload predates this field."""
    hit = _lb_index("hitter_leaderboards.json", "hitters")
    sp = _lb_index("starter_leaderboards.json", "starters")
    rp = _lb_index("bullpen_leaderboards.json", "relievers")
    elig = _elig_positions()
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


# ETA-proximity discount per year still to come (sooner ETA = more dynasty value now).
_DYN_ETA_DECAY = 0.18
_DYN_ETA_UNKNOWN = 0.4          # proximity credit when a prospect has no ETA year


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
    by a composite that keeps the eFV grade quantile PRIMARY:

        score = xfv_grade_quantile            # primary driver (~20-80 scale)
              + 10 * p_bucket['star']         # ceiling premium (star odds)
              -  6 * p_bust                    # floor risk
              +  4 * eta_proximity             # sooner ETA = value sooner
              +  2 * clamp(surplus_mm / 100)   # surplus composite (small tiebreak)

    The DISPLAYED `efv` column is NOT that quantile: it is THE board grade
    (_board_grade), the same number PROSPX, the homepage and /projections/ serve,
    so /fantasy/ carries ONE eFV basis across Dynasty and Call-up Watch. The
    quantile stays in the SCORE only, as a registered model input.

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
        # SCORE input (not the displayed column): the retired per-side quantile is
        # kept here on purpose. The blend's weights (+10 star, -6 bust, +4 ETA) were
        # set against the quantile's spread, so swapping the driver would silently
        # re-weight the composite. This is a model input, not a served grade.
        efv_q = xr.get("xfv_grade_quantile")
        if efv_q is None:
            efv_q = xr.get("xfv_grade")
        if efv_q is None:
            continue
        # DISPLAYED column: THE board grade. Reading the quantile here made the
        # Dynasty eFV column disagree with Call-up Watch's fvE and with the PROSPX
        # board for the same prospect (2026-08-03 repair).
        efv_disp = _board_grade(xr)
        if efv_disp is None:
            efv_disp = efv_q
        pb = xr.get("p_bucket") or {}
        star = pb.get("star") or 0.0
        bust = xr.get("p_bust")
        if bust is None:
            bust = pb.get("bust") or 0.0
        surplus = xr.get("surplus_mm") or 0.0
        eta = pl.get("eta")
        eta_year = eta.get("year") if isinstance(eta, dict) else (eta if isinstance(eta, int) else None)
        if eta_year:
            eta_prox = max(0.0, 1.0 - _DYN_ETA_DECAY * max(0, eta_year - season))
        else:
            eta_prox = _DYN_ETA_UNKNOWN
        surplus_norm = max(-0.5, min(1.5, surplus / 100.0))
        score = (efv_q + 10.0 * star - 6.0 * bust + 4.0 * eta_prox + 2.0 * surplus_norm)
        rows.append({
            "mlbam": mid, "name": pl.get("player_name"), "org": pl.get("org"),
            "pos": pl.get("position"), "eta": eta_year,
            "efv": round(efv_disp, 1), "star": round(star * 100),
            "bust": round((bust or 0.0) * 100), "surplus": round(surplus),
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
    offense (weaker offense → better streamer)."""
    if not p:
        return None
    ros = p.get("ros") or {}
    gs = ros.get("gs") or 0
    if gs <= 0:
        return None
    per_start = (p.get("fpts_fgp") or 0) / gs
    opp_off = (teams_ctx.get(opp_org) or {}).get("offense_plus") or 100
    mult = max(0.6, min(1.5, 100.0 / opp_off)) if opp_off else 1.0
    return {"per_start_fgp": round(per_start * mult, 1),
            "per_start_base": round(per_start, 1), "opp_off": opp_off}


def build_sections(payload: dict) -> dict:
    """Organize the projected pool + schedule + skill context into the 9 sections.
    ROS/streamer/buy-sell/closer sections reference the MLB pool by mlbam (client
    resolves against `players`); the prospect sections (callup_watch, dynasty) are
    self-contained rows joined from timeseries.json + xfv.json."""
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
        }
    except Exception:
        log.exception("fantasy: schedule attach failed — continuing without probables")
        payload["schedule"] = {"games": [], "two_start": {}}


def _record_schedule_anomaly(n_prev: int) -> None:
    """Raise an empty schedule fetch into the ingest-health RED ledger.

    Best-effort by design: this is a reporting path, and it must never be the
    reason a refresh fails. The ledger is what the deploy shell prints as
    `!!! INGEST RED`, so a silent schedule outage becomes visible instead of
    showing up days later as four empty modules."""
    try:
        from run_monthly import _record_ingest
        _record_ingest(
            "fantasy_schedule", ok=False,
            message=(f"probables fetch returned 0 game days; kept the previous "
                     f"{n_prev}-day schedule. Streamers, two-start, DFS and the "
                     f"betting slate all read this schedule."),
        )
    except Exception:
        log.debug("could not record the schedule anomaly", exc_info=True)


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
    OUT_PATH.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    if callable(log):
        n = len((payload.get("sections") or {}).get("daily_streamers") or [])
        log(f"fantasy: daily schedule refresh — {n} streamer starts")
    return len(payload.get("players") or [])


def export(log=print, *, limit: int | None = None) -> int:
    """Build data/fantasy.json. Returns the player count."""
    payload = build_players(limit=limit)
    _attach_schedule(payload)
    payload["sections"] = build_sections(payload)
    DATA_DIR.mkdir(exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
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
