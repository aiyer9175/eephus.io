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
        e = links.get(str(mid)) if isinstance(links, dict) else None
        if isinstance(e, dict):
            return e.get("name")
        return e if isinstance(e, str) else None

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


def _teams_context() -> dict:
    """{org: {offense_plus, heart_hem, bullpen_plus, leverage_deploy_plus}} — the
    opponent-quality context a streamer ranking needs."""
    out: dict = {}
    for t in ((_load_json("hitter_leaderboards.json") or {}).get("teams") or []):
        out.setdefault(t.get("team"), {}).update(
            {"offense_plus": t.get("offense_plus"), "heart_hem": t.get("heart_hem")})
    for t in ((_load_json("bullpen_leaderboards.json") or {}).get("teams") or []):
        out.setdefault(t.get("team"), {}).update(
            {"bullpen_plus": t.get("bullpen_plus"),
             "leverage_deploy_plus": t.get("leverage_deploy_plus")})
    return out


def _enrich(players: list[dict]) -> None:
    """Attach each player's team + skill metrics + season-to-date line from the
    matching skill leaderboard (mlbam-joined). Powers the section signals
    (luck_gap → buy/sell, gmli/saves → closers) and the card display."""
    hit = _lb_index("hitter_leaderboards.json", "hitters")
    sp = _lb_index("starter_leaderboards.json", "starters")
    rp = _lb_index("bullpen_leaderboards.json", "relievers")
    for p in players:
        mid, r = p["mlbam"], None
        if p["side"] == "hit":
            r = hit.get(mid) or {}
            p["skill"] = {k: r.get(k) for k in
                          ("hem_plus", "xhem_plus", "luck_gap", "fwdhem_plus", "pwoba", "tier", "bats")}
            p["std"] = {k: r.get(k) for k in ("pa", "hr", "sb", "avg", "obp", "slg", "ops", "woba")}
        elif p["pos"] == "SP":
            r = sp.get(mid) or {}
            p["skill"] = {k: r.get(k) for k in
                          ("sem_plus", "xsem_plus", "luck", "ip_per_gs", "fip", "era")}
            p["std"] = {k: r.get(k) for k in ("ip", "g", "gs", "k_pct", "bb_pct")}
        else:
            r = rp.get(mid) or {}
            p["skill"] = {k: r.get(k) for k in
                          ("rem_plus", "riv_plus", "gmli", "saves", "holds", "luck", "sd", "md")}
            p["std"] = {k: r.get(k) for k in ("ip", "g", "era")}
        p["team"] = r.get("team")


def _callup_watch() -> list:
    """Best-effort: fantasy-relevant prospects near the majors, from PROSPX forward
    signals (timeseries.json, a generated artifact). Empty when unavailable."""
    ts = _load_json("timeseries.json")
    if not isinstance(ts, dict):
        return []
    out = []
    for pl in (ts.get("players") or []):
        eta = pl.get("eta") or pl.get("eta_year")
        near = (str(eta) in ("2026", "2027")) if eta else False
        if near and pl.get("mlbam_id"):
            out.append({"mlbam": pl.get("mlbam_id"), "name": pl.get("player_name"),
                        "org": pl.get("org"), "pos": pl.get("position"), "eta": eta,
                        "fv": pl.get("consensus_fv") or pl.get("fv_close")})
    out.sort(key=lambda x: -(x.get("fv") or 0))
    return out[:60]


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
    """Organize the projected pool + schedule + skill context into the 8 sections.
    Sections reference players by mlbam (the client resolves against `players`)."""
    players = payload["players"]
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

    # Buy-Low / Sell-High — hitters by luck_gap (xHEM+ − HEM+; + = unlucky = buy),
    # pitchers by `luck` (xERA/xwOBA vs actual). Positive residual = due to regress up.
    def _luck(p):
        s = p.get("skill") or {}
        return s.get("luck_gap") if p["side"] == "hit" else s.get("luck")
    luckable = [p for p in players if _luck(p) is not None and (p.get("fpts_fgp") or 0) > 20]
    sections["buy_low"] = [p["mlbam"] for p in sorted(luckable, key=lambda p: -_luck(p))[:50]]
    sections["sell_high"] = [p["mlbam"] for p in sorted(luckable, key=lambda p: _luck(p))[:50]]

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

    # Two-Start SP — pitchers with 2 starts this week, ranked by summed expected FGP.
    two = []
    for mid_s, starts in (sched.get("two_start") or {}).items():
        p = sp_by_id.get(int(mid_s))
        legs, total = [], 0.0
        for st in starts:
            sc = _start_score(p, st.get("opp_org"), teams_ctx)
            legs.append({"date": st.get("date"), "opp_org": st.get("opp_org"),
                         "exp_fgp": (sc or {}).get("per_start_fgp")})
            total += (sc or {}).get("per_start_fgp") or 0
        two.append({"mlbam": int(mid_s), "name": (p or {}).get("name"),
                    "team": (p or {}).get("team"), "n_starts": len(starts),
                    "total_fgp": round(total, 1), "legs": legs})
    two.sort(key=lambda s: -(s.get("total_fgp") or -1e9))
    sections["two_start"] = two

    sections["callup_watch"] = _callup_watch()
    return sections


def _attach_schedule(payload: dict) -> None:
    """Attach the next-3-day probables (streamers) and the 7-day two-start view."""
    try:
        s3, e3 = fsched.date_window(3)
        games3 = fsched.fetch_probables(s3, e3)
        s7, e7 = fsched.date_window(7)
        games7 = fsched.fetch_probables(s7, e7)
        starts7 = fsched.starts_index(games7)
        payload["schedule"] = {
            "streamer_window": [s3, e3],
            "games": games3,
            "two_start": {str(m): v for m, v in fsched.two_start_pitchers(starts7).items()},
        }
    except Exception:
        log.exception("fantasy: schedule attach failed — continuing without probables")
        payload["schedule"] = {"games": [], "two_start": {}}


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
    _attach_schedule(payload)
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
