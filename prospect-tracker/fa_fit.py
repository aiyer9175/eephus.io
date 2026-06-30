# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Team fit engine for the MLB Free Agency module (Stage 4).

Five transparent components, weighted per fa_config.yaml `fit.weights`,
every score decomposable in the UI:

  NEED      incumbent committed strength at the player's position for the
            contract season (projected WAR of resolved contracted players)
            minus blockers. Blockers come in TWO kinds, both listed in the
            UI: PROSPX prospects with a near ETA at the existing FV grid
            (fv_close >= 50, ETA <= class_year + 1 — read-only, no parallel
            thresholds), and MLB INCUMBENTS already producing at the
            position (the displaced player projects >= incumbent_block_war).
            Incumbent strength also flows CONTINUOUSLY through the
            displacement gap, so only the prospect kind carries an extra
            multiplier — a prospect isn't on the contracted roster, so the
            gap can't see him.
  WINDOW    marginal playoff leverage at the team's 2027 baseline
            (replacement floor + projected WAR of players signed through
            the season): the 85-win team gains far more from +4 WAR than
            the 70-win team. Fixed documented logistic (not fitted, v1).
  AFFORD    CAN the team fit the price: CBT-basis payroll vs the
            rule-versioned threshold (Spotrac's own tax-space number when
            present). Habitual taxpayers who keep spending get a documented
            floor — the Dodgers' afford is not zero just because they're
            over the line. For 2027 the threshold is an explicit
            carry-forward and the flag rides every output.
  PARK      destination park factors (Savant, 100 = neutral) aligned to
            the player's batted side; pitchers prefer suppressive parks.
            Deliberately the SMALLEST weight: park is a tiebreaker, not a
            driver (the v1 weighting recommended suppressive parks for
            every pitcher — the Giants-for-all-pitchers failure).
  BEHAVIOR  WILL the team spend: priors from the team's OWN signing
            history — biggest guarantee ever (vs this price), recent
            3-winter FA outlay, $100M-deal participation. Some teams
            structurally never shop in certain aisles.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date
from functools import lru_cache

import fa_cba
import fa_class
import fa_ident
import fa_market as fm
import fa_projection as fp
import fa_sources
import storage
from trades import canonical_org

log = logging.getLogger(__name__)

POSITIONS = ("C", "1B", "2B", "SS", "3B", "LF", "CF", "RF", "DH", "SP", "RP")
_SAVANT_CLUB_OVERRIDES = {"D-backs": "ARI", "Diamondbacks": "ARI"}


def _fit_cfg() -> dict:
    return fa_class.get_config()["fit"]


def _position_norm(raw: str | None) -> str:
    head = (raw or "").upper().split("/")[0].strip()
    if head in ("SP", "SP2", "P", "LHP", "RHP"):
        return "SP"
    if head in ("RP", "CL", "SIRP", "MIRP"):
        return "RP"
    if head in ("OF",):
        return "CF"
    return head if head in POSITIONS else "DH"


# ============================================================================
# Park factors
# ============================================================================

@lru_cache(maxsize=8)
def park_factors(season: int, bat_side: str = "") -> dict[str, dict]:
    """{org: {woba, hr, runs}} (ints, 100 = neutral). Missing venues fall
    back to neutral at lookup time — never invented."""
    rows = fa_sources.fetch_savant_park_factors(season, bat_side)
    out: dict[str, dict] = {}
    for r in rows:
        club = r.get("name_display_club") or ""
        org = _SAVANT_CLUB_OVERRIDES.get(club) or canonical_org(club)
        if not org or len(org) > 3:
            continue
        out[org] = {"woba": int(r.get("index_woba") or 100),
                    "hr": int(r.get("index_hr") or 100),
                    "runs": int(r.get("index_runs") or 100)}
    return out


def park_component(player: dict, org: str, season: int) -> dict:
    """0..1 score + the underlying indices. Hitters want >100 wOBA/HR in
    their batted side; pitchers want <100. ±25 index points saturate —
    flattened from the v1 ±20 (and the weight cut in fa_config) after the
    measured failure mode: the most suppressive park topped EVERY pitcher's
    fit list because park alone separated otherwise-similar teams."""
    side = (player.get("bat_throw") or "").split("/")[0].strip().upper()
    bat_side = side if side in ("L", "R") else ""
    pf = park_factors(season, bat_side).get(org) or park_factors(season).get(org) \
        or {"woba": 100, "hr": 100, "runs": 100}
    idx = (pf["woba"] + pf["hr"]) / 2.0
    is_pitcher = _position_norm(player.get("position")) in ("SP", "RP")
    edge = (100.0 - idx) if is_pitcher else (idx - 100.0)
    score = max(0.0, min(1.0, 0.5 + edge / 60.0))
    return {"score": round(score, 3), "park_woba": pf["woba"], "park_hr": pf["hr"],
            "bat_side": bat_side or None, "view": "suppressive-good" if is_pitcher else "hitter-good"}


# ============================================================================
# Rosters, baselines, needs
# ============================================================================

@lru_cache(maxsize=2)
def _contracted_projections(class_year: int) -> dict[str, list[dict]]:
    """{org: [{name, position, war_proj}]} — every Spotrac-contracted
    player signed through ``class_year``, identity-resolved via the shared
    war_daily index and projected with the LATEST fitted models. Unresolved
    players are counted, not faked."""
    from spotrac import scrape_all_spotrac_contracts, _SPOTRAC_TEAM_SLUGS
    slug_to_org = {slug: code for code, slug in _SPOTRAC_TEAM_SLUGS.items()}
    corpus = fp.build_corpus()
    league = corpus["league"]
    curves, war_map = fp.fitted_models(corpus, class_year - 1)
    in_prog = (class_year - 1, fp.season_fraction(league, class_year - 1))
    by_player: dict[str, dict[int, dict]] = {"hit": defaultdict(dict), "pit": defaultdict(dict)}
    for side in ("hit", "pit"):
        for r in corpus[side]:
            if r.get("mlbam"):
                by_player[side][r["mlbam"]][r["season"]] = r
    out: dict[str, list[dict]] = defaultdict(list)
    n_unresolved = 0
    for c in scrape_all_spotrac_contracts():
            if (c.get("signed_through") or 0) < class_year:
                continue
            org = slug_to_org.get(c.get("team_slug"))
            name = c.get("player_name")
            if not org or not name:
                continue
            mlbam = fa_ident.resolve(name, range(class_year - 4, class_year))
            if not mlbam:
                n_unresolved += 1
                continue
            pos = _position_norm(c.get("position"))
            side = "pit" if pos in ("SP", "RP") else "hit"
            seasons = by_player[side].get(mlbam) or {}
            hist = [seasons[t] for t in (class_year - 1, class_year - 2, class_year - 3)
                    if t in seasons]
            if not hist:
                continue
            age_prev = next((h.get("age") for h in hist if h.get("age")), None)
            age = (age_prev + (class_year - hist[0]["season"])) if age_prev else None
            proj = fp.project_player(hist, side, class_year, curves, league, age,
                                     in_progress=in_prog)
            if proj is None:
                continue
            war = fp.war_from_projection(proj, side, war_map, league, class_year)
            out[org].append({"name": name, "position": pos, "war_proj": round(war, 2)})
    log.info("fit rosters %d: %d orgs, %d unresolved contracted names",
             class_year, len(out), n_unresolved)
    return dict(out)


@lru_cache(maxsize=2)
def _blockers(class_year: int) -> dict[tuple[str, str], list[dict]]:
    """{(org, position): [prospect blockers]} from the EXISTING platform
    export — read-only, existing FV grid (>= blocker_fv_min), near ETA."""
    import json
    from pathlib import Path
    cfg = _fit_cfg()
    out: dict[tuple[str, str], list[dict]] = defaultdict(list)
    try:
        d = json.loads((Path(__file__).parent / "data" / "timeseries.json")
                       .read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.warning("fit blockers: timeseries.json unavailable")
        return {}
    try:
        xfv_by = (json.loads((Path(__file__).parent / "data" / "xfv.json")
                  .read_text(encoding="utf-8")).get("by_player") or {})
    except (OSError, ValueError):
        xfv_by = {}
    for p in d.get("players") or []:
        # eFV sweep: a near-ETA prospect blocks on the eFV grade (the OOS-better
        # prospect read) where present, consensus FV otherwise. Read-only join, same
        # platform invariant as the timeseries read above. Uses the CONSENSUS-SCALE
        # xfv_grade_quantile (NOT the now-realized headline xfv_grade): blocker_fv_min is
        # a consensus-scale threshold, so the grade fed to it must stay on that scale.
        _xg = (xfv_by.get(p.get("player_key")) or {}).get("xfv_grade_quantile")
        fv = _xg if _xg is not None else p.get("fv_close")
        eta = (p.get("eta") or {}).get("year")
        if (fv is not None and fv >= cfg["blocker_fv_min"] and p.get("org")
                and eta is not None and eta <= class_year + cfg["blocker_eta_horizon"]):
            out[(p["org"], _position_norm(p.get("position")))].append(
                {"player_key": p["player_key"], "player_name": p["player_name"],
                 "fv": fv, "eta": eta})
    return dict(out)


def needs_matrix(class_year: int) -> dict[str, dict[str, dict]]:
    """{org: {position: {incumbent_war, incumbents, blockers, mlb_blockers,
    outgoing}}}. Blockers come in two kinds: PROSPX prospects (near-ETA,
    FV grid) and MLB incumbents already producing at the slot the signing
    would displace (war_proj >= incumbent_block_war) — a team whose
    displaced starter projects 3 WAR is not a buyer there, and the UI says
    WHO is doing the blocking, not just that it's blocked."""
    cfg = _fit_cfg()
    inc_block = float(cfg.get("incumbent_block_war", 2.5))
    rosters = _contracted_projections(class_year)
    blockers = _blockers(class_year)
    outgoing: dict[tuple[str, str], list[str]] = defaultdict(list)
    for p in storage.load_fa_class_players(class_year).values():
        if p.get("from_team"):
            outgoing[(p["from_team"], _position_norm(p.get("position")))].append(p["player_name"])
    out: dict[str, dict[str, dict]] = {}
    # Org universe = clubs with a contracted roster (exactly the 30 MLB
    # teams). from_team rides foreign postings too (Woo Jin An → "KOR"),
    # and a posting league must not get a needs page of its own.
    orgs = set(rosters)
    for org in sorted(orgs):
        out[org] = {}
        roster = rosters.get(org, [])
        for pos in POSITIONS:
            inc = sorted((r for r in roster if r["position"] == pos),
                         key=lambda r: -r["war_proj"])
            # Need is about DISPLACEMENT, not unit totals: an ace joining
            # a rotation displaces the 5th starter, not the staff sum; a
            # position player displaces the incumbent starter; a reliever
            # the back of the pen. unit_war (the sum) stays for context.
            slot = {"SP": 4, "RP": 2}.get(pos, 0)
            displaced = inc[slot]["war_proj"] if len(inc) > slot else 0.0
            # MLB incumbent blocker: the player the signing would actually
            # DISPLACE (the starter at the slot, the 5th starter, the back
            # of the pen) when he himself projects as a real producer. An
            # ace doesn't block adding another SP — only a full slot does.
            # The WAR already discounts need through the gap; this list
            # exists so the surfaces can NAME the blocker.
            mlb_blockers = ([{"player_name": inc[slot]["name"],
                              "war_proj": inc[slot]["war_proj"]}]
                            if len(inc) > slot and inc[slot]["war_proj"] >= inc_block
                            else [])
            out[org][pos] = {
                "unit_war": round(sum(max(0.0, r["war_proj"]) for r in inc[:5 if pos == "SP" else 2]), 2),
                "displaced_war": round(max(0.0, displaced), 2),
                "incumbents": inc[:3],
                "blockers": blockers.get((org, pos), []),
                "mlb_blockers": mlb_blockers,
                "outgoing": outgoing.get((org, pos), []),
            }
    return out


@lru_cache(maxsize=2)
def team_baselines(class_year: int) -> dict[str, dict]:
    """{org: {war_committed, baseline_wins}} — replacement floor + the
    projected WAR of everyone signed through the season."""
    cfg = _fit_cfg()
    out = {}
    for org, roster in _contracted_projections(class_year).items():
        war = sum(max(0.0, r["war_proj"]) for r in roster)
        out[org] = {"war_committed": round(war, 1),
                    "baseline_wins": round(cfg["replacement_wins"] + war, 1)}
    return out


def win_leverage(wins: float) -> float:
    """Marginal playoff leverage at a talent level: P×(1−P) of the fixed
    documented logistic, normalized to peak 1.0 at the curve center."""
    import math
    wc = _fit_cfg()["win_curve"]
    w = wins + float(wc.get("roster_fill_wins", 0))
    p = 1.0 / (1.0 + math.exp(-(w - wc["center"]) / wc["scale"]))
    return 4.0 * p * (1.0 - p)


# ============================================================================
# Affordability + behavior
# ============================================================================

@lru_cache(maxsize=2)
def affordability(class_year: int) -> dict[str, dict]:
    """{org: {committed_usd, tax_payroll_usd, threshold_usd, space_usd,
    carry_forward, payor_status}} — rule-versioned; the 2027 threshold is
    an explicit carry-forward and the flag rides every consumer. Space is
    measured on the CBT BASIS (Spotrac's own tax-space figure when
    present) — the number front offices actually budget against."""
    thr = fa_cba.cbt_threshold(class_year)
    pay = storage.load_fa_team_payroll(class_year)
    tax_prev = storage.load_fa_team_payroll(class_year - 1)
    out = {}
    for (team, _season), row in pay.items():
        committed = row.get("total_payroll_usd") or 0
        tax_payroll = row.get("tax_payroll_usd")
        space = row.get("space_usd")
        if space is None:
            space = thr["threshold_usd"] - (tax_payroll or committed)
        prev = tax_prev.get((team, class_year - 1)) or {}
        out[team] = {
            "committed_usd": committed,
            "tax_payroll_usd": tax_payroll,
            "threshold_usd": thr["threshold_usd"],
            "space_usd": space,
            "carry_forward": thr["carry_forward"],
            "payor_status": prev.get("payor_status_raw") or row.get("payor_status_raw"),
        }
    return out


@lru_cache(maxsize=1)
def behavior_priors() -> dict[str, dict]:
    """Per-team WILL-SPEND priors from the team's OWN signings in the
    corpus: max guarantee ever, count of $100M deals, total FA spend, and
    the recent 3-winter outlay (spending appetite is a recency story —
    an owner who spent $400M since 2024 is live in a way 2016 can't show)."""
    signings = storage.load_fa_signings()
    last_winter = max((y for (_k, y) in signings), default=0)
    out: dict[str, dict] = defaultdict(lambda: {"max_guarantee_usd": 0,
                                                "n_100m": 0, "total_spend_usd": 0,
                                                "recent_spend_usd": 0})
    for (_k, y), s in signings.items():
        team, g = s.get("to_team"), s.get("guarantee_usd") or 0
        if not team or not s.get("mlb_deal"):
            continue
        b = out[team]
        b["max_guarantee_usd"] = max(b["max_guarantee_usd"], g)
        b["total_spend_usd"] += g
        if y >= last_winter - 2:
            b["recent_spend_usd"] += g
        if g >= 100_000_000:
            b["n_100m"] += 1
    return dict(out)


# ============================================================================
# Composite fit
# ============================================================================

def _is_taxpayer(payor_status: str | None) -> bool:
    """Spotrac's payor strings are free-form; anything that isn't an
    explicit non-payor reads as a taxpayer signal."""
    s = (payor_status or "").strip().lower()
    return bool(s) and "non" not in s


def fit_scores(player: dict, market_pred: dict, class_year: int,
               top_n: int = 5) -> list[dict]:
    """Per-team transparent composite for one class member. ``player`` is a
    class row (position, bat_throw, from_team); ``market_pred`` carries
    proj_guarantee_usd / proj_aav_usd. Every component returns its inputs."""
    cfg = _fit_cfg()
    w = cfg["weights"]
    bw = cfg.get("behavior_weights") or {"max_guar": 0.5, "recent": 0.3, "rich": 0.2}
    pos = _position_norm(player.get("position"))
    needs = needs_matrix(class_year)
    bases = team_baselines(class_year)
    afford = affordability(class_year)
    priors = behavior_priors()
    # League-max recent spend normalizes the will-spend component to [0,1].
    max_recent = max((b.get("recent_spend_usd") or 0) for b in priors.values()) or 1
    war1 = (player.get("_war_path") or {}).get("war_y1") or 1.0
    rows = []
    for org, by_pos in needs.items():
        cell = by_pos.get(pos) or {}
        gap = max(0.0, war1 - (cell.get("displaced_war") or 0.0))
        # Prospect blockers carry the multiplier (they're invisible to the
        # contracted-roster gap); MLB incumbents already discount need
        # continuously THROUGH the gap, so they're listed but not
        # double-counted.
        prospect_blocked = bool(cell.get("blockers"))
        need = (min(1.0, gap / cfg["need_war_saturation"])
                * (float(cfg.get("prospect_block_multiplier", 0.5)) if prospect_blocked else 1.0))
        blocked_by = ([{"player_name": b["player_name"], "kind": "prospect"}
                       for b in (cell.get("blockers") or [])]
                      + [{"player_name": b["player_name"], "kind": "mlb",
                          "war_proj": b.get("war_proj")}
                         for b in (cell.get("mlb_blockers") or [])])
        base = bases.get(org) or {"baseline_wins": cfg["replacement_wins"]}
        window = win_leverage(base["baseline_wins"] + war1 / 2.0)
        a = afford.get(org) or {}
        b = priors.get(org) or {}
        aav = market_pred.get("proj_aav_usd") or 10_000_000
        space = a.get("space_usd")
        afford_score = (max(0.0, min(1.0, space / (aav * 2.0))) if space is not None else 0.5)
        # Habitual-taxpayer floor: a club that lives above the threshold AND
        # keeps signing nine-figure deals is not priced out by CBT space —
        # its real constraint is appetite (the behavior component's job).
        if (_is_taxpayer(a.get("payor_status")) and (b.get("n_100m") or 0) >= 3):
            afford_score = max(afford_score, float(cfg.get("taxpayer_afford_floor", 0.4)))
        park = park_component(player, org, class_year - 1)
        guar = market_pred.get("proj_guarantee_usd") or 20_000_000
        scale = min(1.0, (b.get("max_guarantee_usd") or 0) / max(guar, 1)) ** 0.5
        recent = min(1.0, (b.get("recent_spend_usd") or 0) / max_recent)
        rich = min(1.0, (b.get("n_100m") or 0) / 5.0)
        behavior = bw["max_guar"] * scale + bw["recent"] * recent + bw["rich"] * rich
        comp = (w["need"] * need + w["window"] * window + w["afford"] * afford_score
                + w["park"] * park["score"] + w["behavior"] * behavior)
        rows.append({
            "org": org, "fit": round(comp, 3),
            "components": {
                "need": {"score": round(need, 3), "war_gap": round(gap, 2),
                         "displaced_war": cell.get("displaced_war"),
                         "unit_war": cell.get("unit_war"),
                         "blocked_by": blocked_by,
                         "outgoing": cell.get("outgoing") or []},
                "window": {"score": round(window, 3),
                           "baseline_wins": base.get("baseline_wins")},
                "afford": {"score": round(afford_score, 3),
                           "space_usd": space,
                           "tax_payroll_usd": a.get("tax_payroll_usd"),
                           "carry_forward": a.get("carry_forward", True),
                           "payor_status": a.get("payor_status")},
                "park": park,
                "behavior": {"score": round(behavior, 3),
                             "max_guarantee_usd": b.get("max_guarantee_usd"),
                             "recent_spend_usd": b.get("recent_spend_usd"),
                             "n_100m": b.get("n_100m", 0)},
            },
        })
    rows.sort(key=lambda r: -r["fit"])
    return rows[:top_n]
