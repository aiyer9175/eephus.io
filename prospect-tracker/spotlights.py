"""
Prospect spotlight scoring.

These helpers build the editorial-style feeds used by the front end:

  - hot: current-season surface-stat leaders with prospect relevance
  - rebounders: pedigree or past-list players whose current performance
    meaningfully outruns prior stock / recent career performance

The output is intentionally explainable. Every entry carries short driver
strings so the UI can say why a player appears instead of only presenting a
black-box score.
"""

from __future__ import annotations

from datetime import date
from statistics import mean


TOP_N = 60


def _num(v, default: float | None = None) -> float | None:
    if v in (None, "", "—"):
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _latest_fv(p: dict) -> float:
    pts = p.get("points") or []
    return _num(pts[-1].get("consensus_fv_raw") if pts else None, 0.0) or 0.0


def _previous_fv(p: dict) -> float | None:
    pts = p.get("points") or []
    if len(pts) < 2:
        return None
    return _num(pts[-2].get("consensus_fv_raw"))


def _recent_baseline_top100_source_count(p: dict) -> int:
    prior_year = date.today().year - 1
    current_year = date.today().year
    sources: set[str] = set()
    for pt in p.get("points") or []:
        snap_date = pt.get("snapshot_date") or ""
        in_prior_year = snap_date.startswith(f"{prior_year}-")
        in_current_preseason = (
            snap_date.startswith(f"{current_year}-")
            and snap_date[5:10] <= "03-31"
        )
        if not (in_prior_year or in_current_preseason):
            continue
        for source, rec in (pt.get("per_source") or {}).items():
            rank = rec.get("rank")
            try:
                rank_num = int(rank)
            except (TypeError, ValueError):
                continue
            if rank_num <= 100:
                sources.add(source)
    return len(sources)


def _baseline_to_now_list_jump(p: dict) -> tuple[float, list[str]]:
    prior_year = date.today().year - 1
    current_year = date.today().year
    baseline_ranks: list[int] = []
    current_ranks: list[int] = []
    for pt in p.get("points") or []:
        snap_date = pt.get("snapshot_date") or ""
        is_baseline = snap_date.startswith(f"{prior_year}-") or (
            snap_date.startswith(f"{current_year}-")
            and snap_date[5:10] <= "03-31"
        )
        is_current = snap_date.startswith(f"{current_year}-") and snap_date[5:10] > "03-31"
        if is_baseline:
            if pt.get("avg_rank") is not None:
                baseline_ranks.append(int(round(pt["avg_rank"])))
        elif is_current:
            if pt.get("avg_rank") is not None:
                current_ranks.append(int(round(pt["avg_rank"])))
    drivers: list[str] = []
    score = 0.0
    if baseline_ranks and current_ranks:
        baseline = max(baseline_ranks)
        current = min(current_ranks)
        jump = baseline - current
        prior_high_fv = _num(p.get("fv_high"), _latest_fv(p)) or _latest_fv(p)
        if prior_high_fv >= 55 and jump >= 25 and (baseline >= 70 or current <= 25):
            score += min(5.0, jump / 10.0)
            drivers.append(f"rank up {jump} spots from baseline lists")
    return score, drivers


def _career_row(p: dict, season: int | None = None) -> dict | None:
    rows = p.get("career_stats") or []
    if season is None:
        return rows[0] if rows else None
    return next((r for r in rows if r.get("season") == season), None)


def _prior_rows(p: dict) -> list[dict]:
    rows = p.get("career_stats") or []
    if not rows:
        return []
    latest_season = max((r.get("season") or 0) for r in rows)
    return [r for r in rows if (r.get("season") or 0) < latest_season]


def _ops(row: dict | None) -> float | None:
    return _num((row or {}).get("ops"))


def _era(row: dict | None) -> float | None:
    return _num((row or {}).get("era"))


def _ip(row: dict | None) -> float:
    return _num((row or {}).get("ip"), 0.0) or 0.0


def _hitter_ab(row: dict | None) -> int:
    return int(_num((row or {}).get("ab"), 0.0) or 0)


def _pedigree_score(acq: dict | None) -> tuple[float, list[str]]:
    if not acq:
        return 0.0, []
    score = 0.0
    drivers: list[str] = []
    method = acq.get("method")
    overall = acq.get("pick_overall")
    bonus = acq.get("bonus_usd")
    if method == "draft":
        if overall and overall <= 30:
            score += 4.0
            drivers.append(f"first-round pedigree ({overall} overall)")
        elif overall and overall <= 100:
            score += 2.5
            drivers.append(f"top-100 pick pedigree ({overall} overall)")
        elif overall:
            score += 1.0
            drivers.append(f"draft pedigree ({overall} overall)")
    elif method == "international_fa":
        score += 1.5
        drivers.append("international signing pedigree")
    if bonus:
        if bonus >= 3_000_000:
            score += 2.5
            drivers.append(f"${bonus / 1_000_000:.1f}M bonus")
        elif bonus >= 1_000_000:
            score += 1.5
            drivers.append(f"${bonus / 1_000_000:.1f}M bonus")
    return score, drivers


def _surface_score(p: dict) -> tuple[float, list[str]]:
    sl = p.get("statline") or {}
    if sl.get("is_prior_season"):
        return 0.0, []
    row = _career_row(p, sl.get("season"))
    drivers: list[str] = []
    if sl.get("is_pitcher"):
        k9 = _num(sl.get("k_per_9"), 0.0) or 0.0
        bb9 = _num(sl.get("bb_per_9"), 9.0) or 9.0
        era = _num(sl.get("era"), 9.0) or 9.0
        ip = _num(sl.get("ip"), _ip(row)) or 0.0
        if ip < 12:
            return 0.0, []
        score = max(0.0, k9 - 8.0) * 0.7 + max(0.0, 4.25 - era) * 1.4
        score += max(0.0, 3.0 - bb9) * 0.6
        drivers.append(f"{k9:.1f} K/9")
        if era < 3.5:
            drivers.append(f"{era:.2f} ERA")
        if bb9 < 3.0:
            drivers.append(f"{bb9:.1f} BB/9")
        return score, drivers

    ops = _num(sl.get("ops"), 0.0) or 0.0
    ab = _hitter_ab(row)
    if ab < 45:
        return 0.0, []
    bb_pct = _num(sl.get("bb_pct"))
    k_pct = _num(sl.get("k_pct"))
    score = max(0.0, ops - 0.760) * 18.0
    if bb_pct is not None and bb_pct >= 10:
        score += 1.0
    if k_pct is not None and k_pct <= 18:
        score += 1.0
    if (sl.get("hr") or 0) >= 6:
        score += 0.8
    if (sl.get("sb") or 0) >= 6:
        score += 0.5
    drivers.append(f"{sl.get('ops')} OPS")
    if bb_pct is not None and k_pct is not None:
        drivers.append(f"{bb_pct:.1f}% BB / {k_pct:.1f}% K")
    if sl.get("hr") or sl.get("sb"):
        drivers.append(f"{sl.get('hr') or 0} HR, {sl.get('sb') or 0} SB")
    return score, drivers


def _statcast_drivers(p: dict) -> tuple[float, list[str]]:
    sc = p.get("statcast") or {}
    ps = p.get("prospect_savant") or {}
    pa = p.get("pitch_arsenal") or {}
    score = 0.0
    drivers: list[str] = []
    ev = _num(sc.get("exit_velo"))
    hh = _num(sc.get("hard_hit_pct"))
    barrel = _num(sc.get("barrel_pct"))
    fb = _num(pa.get("fb_velo"))
    if ev is not None and ev >= 90:
        score += 1.5
        drivers.append(f"{ev:.1f} mph avg EV")
    if hh is not None and hh >= 42:
        score += 1.0
        drivers.append(f"{hh:.1f}% hard-hit")
    if barrel is not None and barrel >= 10:
        score += 1.0
        drivers.append(f"{barrel:.1f}% barrels")
    if fb is not None and fb >= 95:
        score += 1.5
        drivers.append(f"{fb:.1f} mph fastball")
    ps_score = _num(ps.get("ps_score"))
    if ps_score is not None and ps_score >= 0.95:
        score += 3.0
    elif ps_score is not None and ps_score >= 0.85:
        score += 1.5
    max_ev = _num(ps.get("max_ev"))
    ev_90 = _num(ps.get("ev_90"))
    ps_ev = _num(ps.get("ev"))
    hard_hit = _num(ps.get("hard_hit_pct"))
    if max_ev is not None and max_ev >= 110:
        score += 1.3
        drivers.append(f"{max_ev:.1f} max EV")
    if ev_90 is not None and ev_90 >= 104:
        score += 1.2
        drivers.append(f"{ev_90:.1f} mph 90th EV")
    if ps_ev is not None and ps_ev >= 91:
        score += 0.8
        drivers.append(f"{ps_ev:.1f} mph avg EV")
    if hard_hit is not None and hard_hit >= 45:
        score += 0.8
        drivers.append(f"{hard_hit:.1f}% hard-hit")
    max_velo = _num(ps.get("max_velo"))
    if max_velo is not None and max_velo >= 0.90:
        score += 1.2
        drivers.append(f"top-tier max velo score {max_velo:.3f}")
    return score, drivers


def _prior_underperformance(p: dict) -> tuple[float, list[str]]:
    priors = _prior_rows(p)
    if not priors:
        return 0.0, []
    latest = _career_row(p)
    drivers: list[str] = []
    if latest and not latest.get("is_pitcher"):
        current_ops = _ops(latest)
        prior_ops_vals = [_ops(r) for r in priors if not r.get("is_pitcher") and _hitter_ab(r) >= 40]
        prior_ops_vals = [v for v in prior_ops_vals if v is not None]
        if current_ops is not None and prior_ops_vals:
            prior_avg = mean(prior_ops_vals)
            if current_ops - prior_avg >= 0.130:
                drivers.append(f"OPS up {current_ops - prior_avg:.3f} vs recent prior seasons")
                return min(4.0, (current_ops - prior_avg) * 12.0), drivers
    if latest and latest.get("is_pitcher"):
        current_era = _era(latest)
        prior_eras = [_era(r) for r in priors if r.get("is_pitcher") and _ip(r) >= 10]
        prior_eras = [v for v in prior_eras if v is not None]
        if current_era is not None and prior_eras:
            prior_avg = mean(prior_eras)
            if prior_avg - current_era >= 0.75:
                drivers.append(f"ERA down {prior_avg - current_era:.2f} vs recent prior seasons")
                return min(4.0, (prior_avg - current_era) * 0.9), drivers
    return 0.0, []


def _change_drivers(p: dict) -> list[str]:
    latest = _career_row(p)
    if not latest:
        return []
    priors = _prior_rows(p)
    drivers: list[str] = []
    if not latest.get("is_pitcher"):
        current_ops = _ops(latest)
        prior_ops_vals = [_ops(r) for r in priors if not r.get("is_pitcher") and _hitter_ab(r) >= 40]
        prior_ops_vals = [v for v in prior_ops_vals if v is not None]
        if current_ops is not None and prior_ops_vals:
            prior_avg = mean(prior_ops_vals)
            diff = current_ops - prior_avg
            if diff >= 0.050:
                drivers.append(f"OPS up {diff:.3f} vs recent prior seasons")
        for key, label, improves_when_up in (
            ("bb_pct", "BB%", True),
            ("k_pct", "K%", False),
        ):
            current = _num(latest.get(key))
            prior_vals = [_num(r.get(key)) for r in priors if not r.get("is_pitcher") and _hitter_ab(r) >= 40]
            prior_vals = [v for v in prior_vals if v is not None]
            if current is not None and prior_vals:
                diff = current - mean(prior_vals)
                improved = diff > 0 if improves_when_up else diff < 0
                if improved and abs(diff) >= 3.0:
                    direction = "up" if diff > 0 else "down"
                    drivers.append(f"{label} {direction} {abs(diff):.1f} pts")
    else:
        current_era = _era(latest)
        prior_eras = [_era(r) for r in priors if r.get("is_pitcher") and _ip(r) >= 10]
        prior_eras = [v for v in prior_eras if v is not None]
        if current_era is not None and prior_eras:
            diff = mean(prior_eras) - current_era
            if diff >= 0.50:
                drivers.append(f"ERA down {diff:.2f} vs recent prior seasons")
        current_k9 = _num(latest.get("k_per_9"))
        prior_k9 = [_num(r.get("k_per_9")) for r in priors if r.get("is_pitcher") and _ip(r) >= 10]
        prior_k9 = [v for v in prior_k9 if v is not None]
        if current_k9 is not None and prior_k9:
            diff = current_k9 - mean(prior_k9)
            if diff >= 1.5:
                drivers.append(f"K/9 up {diff:.1f}")
        current_bb9 = _num(latest.get("bb_per_9"))
        prior_bb9 = [_num(r.get("bb_per_9")) for r in priors if r.get("is_pitcher") and _ip(r) >= 10]
        prior_bb9 = [v for v in prior_bb9 if v is not None]
        if current_bb9 is not None and prior_bb9:
            diff = mean(prior_bb9) - current_bb9
            if diff >= 1.0:
                drivers.append(f"BB/9 down {diff:.1f}")
    return drivers


def _entry(bucket: str, p: dict, score: float, drivers: list[str]) -> dict:
    sl = p.get("statline") or {}
    pts = p.get("points") or []
    latest = pts[-1] if pts else {}
    return {
        "bucket": bucket,
        "player_key": p.get("player_key"),
        "player_name": p.get("player_name"),
        "position": p.get("position"),
        "org": p.get("org"),
        "level": sl.get("level"),
        "age": p.get("age"),
        "overall_rank": p.get("overall_rank"),
        "fv": latest.get("consensus_fv_label"),
        "score": round(score, 2),
        "why": "Breakout" if bucket == "hot" else "Rebound",
        "line": _line_text(sl),
        "drivers": drivers[:4],
    }


def _line_text(sl: dict) -> str:
    if not sl:
        return "No current line"
    if sl.get("is_pitcher"):
        return f"{sl.get('era', '—')} ERA, {sl.get('ip', '—')} IP, {sl.get('k_per_9', '—')} K/9"
    return f"{sl.get('avg', '—')}/{sl.get('obp', '—')}/{sl.get('slg', '—')}, {sl.get('hr') or 0} HR, {sl.get('sb') or 0} SB"


def _mlb_exposure(p: dict) -> tuple[int, int, float]:
    rows = [r for r in (p.get("career_stats") or []) if r.get("level") == "MLB"]
    seasons = len({r.get("season") for r in rows if r.get("season")})
    games = sum(int(_num(r.get("games"), 0.0) or 0) for r in rows)
    if not rows:
        return 0, 0, 0.0
    if rows[0].get("is_pitcher"):
        ip = sum(_num(r.get("ip"), 0.0) or 0.0 for r in rows)
        return seasons, games, ip
    ab = sum(_num(r.get("ab"), 0.0) or 0.0 for r in rows)
    return seasons, games, ab


def _has_minor_rebound_case(p: dict, sc_score: float) -> tuple[bool, list[str]]:
    drivers: list[str] = []
    if sc_score >= 1.5:
        return True, drivers
    latest_season = max((r.get("season") or 0) for r in (p.get("career_stats") or [])) if p.get("career_stats") else 0
    for r in p.get("career_stats") or []:
        if r.get("level") == "MLB":
            continue
        if latest_season and (r.get("season") or 0) < latest_season - 1:
            continue
        if r.get("is_pitcher"):
            era = _era(r)
            ip = _ip(r)
            k9 = _num(r.get("k_per_9"))
            if ip >= 20 and ((era is not None and era <= 3.75) or (k9 is not None and k9 >= 10.5)):
                if era is not None and era <= 3.75:
                    drivers.append(f"{r.get('season')} MiLB {era:.2f} ERA")
                elif k9 is not None:
                    drivers.append(f"{r.get('season')} MiLB {k9:.1f} K/9")
                return True, drivers
        else:
            ops = _ops(r)
            ab = _hitter_ab(r)
            if ab >= 80 and ops is not None and ops >= 0.800:
                drivers.append(f"{r.get('season')} MiLB {ops:.3f} OPS")
                return True, drivers
    return False, drivers


def _is_roster_fringe_candidate(p: dict, sc_score: float) -> tuple[bool, list[str]]:
    age = p.get("age")
    latest_fv = _latest_fv(p)
    high_fv = _num(p.get("fv_high"), latest_fv) or latest_fv
    seasons, games, playing_time = _mlb_exposure(p)
    drivers: list[str] = []

    # This bucket is about players who have had repeated MLB chances and are
    # plausibly under roster/option pressure, not young top prospects in a
    # small big-league sample.
    if age is None or age < 24.0:
        return False, []
    if latest_fv >= 50.0 or high_fv >= 50.0:
        return False, []
    if seasons < 3 and games < 60 and playing_time < 130:
        return False, []

    has_minor_case, minor_drivers = _has_minor_rebound_case(p, sc_score)
    if not has_minor_case:
        return False, []

    drivers.append(f"{seasons} MLB seasons")
    if games:
        drivers.append(f"{games} MLB games")
    drivers.extend(minor_drivers)
    return True, drivers


def _is_rebound_candidate(p: dict) -> bool:
    age = p.get("age")
    if age is not None and age >= 25:
        return False
    list_jump, _ = _baseline_to_now_list_jump(p)
    if _recent_baseline_top100_source_count(p) > 1 and list_jump <= 0:
        return False
    latest_fv = _latest_fv(p)
    prev_fv = _previous_fv(p)
    rank = p.get("overall_rank") or 9999
    low_fv = _num(p.get("fv_low"), latest_fv) or latest_fv
    ps_score = _num((p.get("prospect_savant") or {}).get("ps_score"))
    # Captures not-current-top-100 names, older low-FV labels, and former
    # highly regarded prospects who had a down prior season.
    if rank > 100 or low_fv <= 42.5 or (prev_fv is not None and latest_fv - prev_fv >= 2.0):
        return True
    if ps_score is not None and ps_score >= 0.95 and rank <= 100:
        return True
    prior_score, _ = _prior_underperformance(p)
    pedigree, _ = _pedigree_score(p.get("acquisition"))
    return pedigree >= 1.5 and prior_score >= 1.0


# ===========================================================================
# Movement engine (2026-05 overhaul) — performance-anchored composite that
# drives both spotlights (Risers / Rebounders / Fallers) and the main-list
# "Top movers" + stockFilter chips. Replaces the FV-delta-only `stock_movement`
# in consensus.py.
# ===========================================================================

def _perf_delta(p: dict) -> tuple[float | None, str | None]:
    """Surface-stat delta from prior season → current season.

    Hitter:  delta = current_ops - prior_ops (positive = better)
    Pitcher: delta = prior_era - current_era (positive = better)

    Returns (delta, driver_string). None when sample is too small for the
    current season (≤ 60 AB hitter, ≤ 15 IP pitcher) or there's no prior
    season row to compare against."""
    sl = p.get("statline") or {}
    if not sl or sl.get("is_prior_season"):
        return (None, None)
    current_row = _career_row(p, sl.get("season"))
    priors = _prior_rows(p)
    if sl.get("is_pitcher"):
        cur_ip = _num(sl.get("ip"), 0.0) or 0.0
        if cur_ip < 15:
            return (None, None)
        cur_era = _num(sl.get("era"))
        prior_eras = [_era(r) for r in priors
                      if r.get("is_pitcher") and _ip(r) >= 15]
        prior_eras = [v for v in prior_eras if v is not None]
        if cur_era is None or not prior_eras:
            return (None, None)
        prior_avg = mean(prior_eras)
        delta = prior_avg - cur_era      # positive = improved
        return (delta, f"ERA {cur_era:.2f} vs {prior_avg:.2f} prior")
    # Hitter
    cur_ab = _hitter_ab(current_row) or int(_num(sl.get("ab"), 0.0) or 0)
    if cur_ab < 50:
        return (None, None)
    cur_ops = _num(sl.get("ops"))
    # Prior AB floor of 30 (not 60) so a light-sample partial 2025 debut
    # (e.g. Cunningham's 47-AB rookie year) still counts as a baseline.
    # Without this, prospects with one limited prior season produce
    # perf_delta=None and slip through unclassified.
    prior_ops_vals = [_ops(r) for r in priors
                      if not r.get("is_pitcher") and _hitter_ab(r) >= 30]
    prior_ops_vals = [v for v in prior_ops_vals if v is not None]
    if cur_ops is None or not prior_ops_vals:
        return (None, None)
    prior_avg = mean(prior_ops_vals)
    delta = cur_ops - prior_avg          # positive = improved
    sign = "+" if delta >= 0 else ""
    return (delta, f"OPS {sign}{delta:.3f} vs '{int(min(r.get('season') or 0 for r in priors)) % 100:02d}-{int(max(r.get('season') or 0 for r in priors)) % 100:02d}")


def _skills_delta(p: dict) -> tuple[float | None, list[str]]:
    """Rate-stat delta — K%/BB% for hitters, K/9 + BB/9 for pitchers.

    Score is integer-scaled: +1 per material improvement, -1 per material
    decline. Captures Bryce Rainer's K-rate jump (22.1% → 43.7% = -7 to
    skills_delta) and Tate Southisene's K-rate drop (40% → 25% = +5)."""
    sl = p.get("statline") or {}
    if not sl or sl.get("is_prior_season"):
        return (None, [])
    priors = _prior_rows(p)
    if not priors:
        return (None, [])
    score = 0.0
    drivers: list[str] = []
    if sl.get("is_pitcher"):
        for key, label, lower_better in (
            ("k_per_9", "K/9", False),
            ("bb_per_9", "BB/9", True),
        ):
            cur = _num(sl.get(key))
            prior_vals = [_num(r.get(key)) for r in priors
                          if r.get("is_pitcher") and _ip(r) >= 15]
            prior_vals = [v for v in prior_vals if v is not None]
            if cur is None or not prior_vals:
                continue
            diff = cur - mean(prior_vals)
            improvement = -diff if lower_better else diff
            threshold = 0.8 if lower_better else 1.5
            if abs(diff) >= threshold:
                # Each (threshold) unit of movement = 1 score point,
                # capped at ±3 per category so a single freak move can't
                # dominate the composite.
                pts = max(-3.0, min(3.0, improvement / threshold))
                score += pts
                direction = "down" if diff < 0 else "up"
                drivers.append(f"{label} {direction} {abs(diff):.1f}")
        return (score, drivers)
    # Hitter
    for key, label, improves_when_up in (
        ("k_pct", "K%", False),
        ("bb_pct", "BB%", True),
    ):
        cur = _num(sl.get(key))
        prior_vals = [_num(r.get(key)) for r in priors
                      if not r.get("is_pitcher") and _hitter_ab(r) >= 60]
        prior_vals = [v for v in prior_vals if v is not None]
        if cur is None or not prior_vals:
            continue
        diff = cur - mean(prior_vals)
        improvement = diff if improves_when_up else -diff
        threshold = 2.0 if improves_when_up else 3.0  # K% threshold tighter
        if abs(diff) >= threshold:
            # Each (threshold)-unit move scores 1 point. Bryce Rainer's
            # K% +21.6pp jump = -7 score points (clamped to -6 per cat).
            pts = max(-6.0, min(6.0, improvement / threshold))
            score += pts
            direction = "down" if diff < 0 else "up"
            drivers.append(f"{label} {direction} {abs(diff):.1f}pp")
    return (score, drivers)


def _tools_flash_floor(p: dict) -> bool:
    """Returns True when the prospect has any non-bat tool graded 70+ —
    Starlyn Caba's 80 field, for example. Used to lower the OPS bar for
    Risers since the bat doesn't need to carry the profile."""
    pts = p.get("points") or []
    if not pts:
        return False
    tc = pts[-1].get("tools_consensus") or {}
    # Non-bat tools to scan: field, throw, speed, fb, sl, cb, ch, cmd, ct.
    non_bat_tools = {"field", "throw", "speed", "fb", "sl", "cb", "ch", "cmd", "ct"}
    return any((tc.get(t) or 0) >= 70 for t in non_bat_tools)


def _level_repeat(p: dict) -> bool:
    """True when the prospect's CURRENT level matches their PRIOR season's
    level. Used by the Rebounders rule (Tate Southisene case)."""
    sl = p.get("statline") or {}
    cur_level = sl.get("level")
    if not cur_level:
        return False
    priors = _prior_rows(p)
    return any(r.get("level") == cur_level for r in priors)


def _classify_movement(p: dict, perf_delta, skills_delta,
                       list_jump_score, pedigree) -> tuple[str, float, list[str]]:
    """Return (bucket, composite_score, drivers). Bucket is one of:
      'riser'    — broad surface-jump cases
      'rebound'  — pedigree-comeback narrative (Southisene)
      'faller'   — decline cases (with tight disqualify gates)
      'none'     — uneventful / insufficient data
    """
    drivers: list[str] = []
    sl = p.get("statline") or {}
    is_pitcher = bool(sl.get("is_pitcher"))
    age = p.get("age_vs_level") or {}
    tier = age.get("tier")
    young_for_level = tier in {"very-young", "young"}
    very_young = tier == "very-young"
    ped_pts = pedigree or 0.0
    cur_ops = _num(sl.get("ops"))
    cur_era = _num(sl.get("era"))
    ps = p.get("prospect_savant") or {}
    ps_score = _num(ps.get("ps_score"))

    # Thresholds — hitter vs pitcher
    PERF_RISER_BAR = 0.080 if is_pitcher else 0.100
    PERF_FALLER_BAR = -0.30 if is_pitcher else -0.080
    SOFT_PERF_FALLER = -0.20 if is_pitcher else -0.060
    if young_for_level:
        # Lower the bar for young-for-level prospects (they don't need
        # to leap as much to count as a Riser; they need a sharper drop
        # to count as a Faller).
        PERF_RISER_BAR -= 0.04
        PERF_FALLER_BAR -= 0.04
    if _tools_flash_floor(p):
        # 70+ non-bat tool → bat doesn't have to carry. Lower the OPS bar.
        PERF_RISER_BAR = min(PERF_RISER_BAR, 0.060)

    skills = skills_delta if skills_delta is not None else 0.0
    perf = perf_delta if perf_delta is not None else 0.0

    # --- Rebounder narrative (pedigree comeback) ---
    # Required signals: pedigree + meaningful current improvement + prior
    # season was weak. Skills_delta ≥ 0 (or None when no rate stats
    # prior) keeps us from rewarding pure BABIP rebounds. The level-
    # repeat path used to be a hard gate but excluded the Cunningham
    # case (advancing levels + huge jump) — kept as a tie-breaker bonus.
    # Age cap at 25: a 25+yo on a "comeback" is no longer a meaningful
    # prospect-development narrative; surface them via the Riser bucket
    # if they truly leapt, but not Rebounders.
    age_val = p.get("age")
    age_ok_for_rebound = age_val is None or age_val < 25
    if (perf_delta is not None and perf >= 0.080 and ped_pts >= 1.5
            and age_ok_for_rebound):
        priors = _prior_rows(p)
        weak_prior = False
        very_weak_prior = False
        if is_pitcher:
            prior_eras = [_era(r) for r in priors
                          if r.get("is_pitcher") and _ip(r) >= 20]
            prior_eras = [v for v in prior_eras if v is not None]
            if prior_eras:
                m_era = mean(prior_eras)
                weak_prior = m_era >= 4.50
                very_weak_prior = m_era >= 5.00
        else:
            prior_ops = [_ops(r) for r in priors
                         if not r.get("is_pitcher") and _hitter_ab(r) >= 30]
            prior_ops = [v for v in prior_ops if v is not None]
            if prior_ops:
                m_ops = mean(prior_ops)
                weak_prior = m_ops <= 0.700
                very_weak_prior = m_ops <= 0.600
        # Stable multi-source top-100 player is NOT a rebounder UNLESS
        # the prior season was VERY weak (Southisene .539 OPS) OR there
        # was a meaningful list jump (Salas 94→58). Both signals indicate
        # a real comeback narrative; without either, a stable top-100
        # prospect is just "continuing the story" and surfaces via Risers.
        stable_top100 = (
            _recent_baseline_top100_source_count(p) >= 2
            and list_jump_score <= 0
            and not very_weak_prior
        )
        skills_ok = (skills_delta is None) or (skills >= 0)
        if weak_prior and skills_ok and not stable_top100:
            score = 3.0 + min(5.0, perf * 20.0)
            if skills_delta is not None:
                score += min(2.0, max(0.0, skills * 0.5))
            if _level_repeat(p):
                score += 1.0
                drivers.append("repeating level + improving")
            drivers.append("pedigree comeback")
            return ("rebound", score, drivers)

    # --- Riser: perf jumped meaningfully OR list-jump fired ---
    is_riser_perf = perf_delta is not None and perf >= PERF_RISER_BAR
    is_riser_jump = list_jump_score >= 2.0
    # Continuing-high-performance Kepley case: prior ≥ .800, current ≥ .850
    # (hitter; pitcher analog: prior ERA ≤ 3.50 + current ≤ 3.25), and
    # not "old" for level.
    is_riser_continuing = False
    if not is_pitcher and cur_ops is not None and cur_ops >= 0.850 and tier not in {"old", "very-old"}:
        priors = _prior_rows(p)
        prior_ops = [_ops(r) for r in priors
                     if not r.get("is_pitcher") and _hitter_ab(r) >= 60]
        prior_ops = [v for v in prior_ops if v is not None]
        if prior_ops and mean(prior_ops) >= 0.800:
            is_riser_continuing = True
            drivers.append(f"continuing high performance ({cur_ops:.3f} OPS)")
    elif is_pitcher and cur_era is not None and cur_era <= 3.25 and tier not in {"old", "very-old"}:
        priors = _prior_rows(p)
        prior_eras = [_era(r) for r in priors
                      if r.get("is_pitcher") and _ip(r) >= 20]
        prior_eras = [v for v in prior_eras if v is not None]
        if prior_eras and mean(prior_eras) <= 3.50:
            is_riser_continuing = True
            drivers.append(f"continuing strong arm ({cur_era:.2f} ERA)")

    if is_riser_perf or is_riser_jump or is_riser_continuing:
        score = 0.0
        if is_riser_perf:
            score += min(6.0, perf * (8.0 if is_pitcher else 25.0))
        if is_riser_jump:
            score += min(3.0, list_jump_score)
            drivers.append("rank jump on baseline lists")
        if is_riser_continuing:
            score += 2.5
        if young_for_level:
            score += 1.0
            drivers.append("young for level")
        if skills_delta is not None and skills > 0:
            score += min(2.0, skills * 0.4)
        return ("riser", max(0.0, score), drivers)

    # --- Faller: perf declined meaningfully ---
    # Disqualify gates:
    #   - very-young: ALWAYS disqualified, NO rescue path. The user's
    #     Lombard Jr / Florentino examples — very-young + (often)
    #     pedigreed — should never surface as fallers even with bad
    #     surface stats. They're playing way above their age cohort.
    #   - young + pedigreed: disqualified, but a Bryce Rainer-style
    #     skills crater (K% jumping 20+ pts in one season) can rescue.
    #   - high ps_score: underlying data is still strong → soft surface
    #     drop doesn't qualify.
    disqualified = False
    disqualified_hard = False
    if very_young:
        disqualified = True
        disqualified_hard = True
    elif young_for_level and ped_pts >= 2.0:
        disqualified = True
    elif ps_score is not None and ps_score >= 0.85 and perf > SOFT_PERF_FALLER:
        disqualified = True

    # Amplifier: a Bryce Rainer-style net-negative skills delta (BB%
    # gains can't offset a K-rate that doubled) can rescue a young +
    # pedigreed prospect from the soft-disqualify gate. Hard-disqualified
    # (very-young) prospects stay out regardless.
    skills_crater = (skills_delta is not None and skills <= -3.0)
    if disqualified_hard:
        return ("none", 0.0, drivers)
    if disqualified and not skills_crater:
        return ("none", 0.0, drivers)

    # Surface stats may still look "OK" but a major skills crater + age
    # ≥ 24 at AAA = the Melton case: K% blew up, repeated AAA, surface
    # OPS is technically not much worse than the prior AAA stint, but
    # the trajectory is broken. Force-faller this path. Skills_crater
    # OR a single-category K% jump ≥ 10pp triggers — Melton's net
    # skills_delta is mild (-0.5) because BB% gains offset, but the
    # raw K% jump (+15pp from 25%→40%) is the real red flag.
    age_val = p.get("age")
    cur_level = (p.get("statline") or {}).get("level")
    cur_k_pct = _num((p.get("statline") or {}).get("k_pct"))
    prior_k_vals: list[float] = []
    if not is_pitcher:
        for r in _prior_rows(p):
            if r.get("is_pitcher"): continue
            if _hitter_ab(r) < 30: continue
            v = _num(r.get("k_pct"))
            if v is not None:
                prior_k_vals.append(v)
    k_pct_jump = (cur_k_pct - mean(prior_k_vals)) if (cur_k_pct is not None and prior_k_vals) else None
    has_k_crater = k_pct_jump is not None and k_pct_jump >= 10.0
    melton_path = (
        (skills_crater or has_k_crater)
        and age_val is not None and age_val >= 24
        and cur_level in {"AAA", "MLB"}
    )

    if perf_delta is None or perf > PERF_FALLER_BAR:
        if not skills_crater and not melton_path:
            return ("none", 0.0, drivers)

    # Faller path.
    score = 0.0
    if perf_delta is not None and perf <= 0:
        score += max(-6.0, perf * (10.0 if is_pitcher else 30.0))
    if skills_delta is not None and skills < 0:
        score += max(-4.0, skills * 0.5)
    if skills_crater:
        score -= 2.0
        drivers.append("major skills decline")
    if ps_score is not None and ps_score <= 0.40:
        score -= 1.0
        drivers.append("underlying data weak")
    if age_val is not None and age_val >= 24 and cur_level in {"AAA", "MLB"}:
        score -= 1.0
        drivers.append("limited runway (24+ at AAA)")
    if _level_repeat(p) and perf_delta is not None and perf <= -0.060:
        score -= 1.0
        drivers.append("regressed while repeating level")
    if melton_path:
        score -= 2.0
        drivers.append("skills broken at upper levels")
    return ("faller", score, drivers)


def _direction_from_delta(delta: float) -> str:
    if delta >= 5.0:  return "up_strong"
    if delta >= 2.0:  return "up"
    if delta <= -5.0: return "down_strong"
    if delta <= -2.0: return "down"
    return "flat"


def compute_movement(p: dict) -> dict:
    """Centralized movement engine — performance-anchored composite.

    Drives both the spotlights buckets (via _classify_movement) and the
    main-list "Top movers" / stockFilter chips (via the same {direction,
    delta, drivers} shape stock_movement used to emit on its own)."""
    if (p.get("status") or "") == "graduated":
        return {
            "direction": "graduated", "delta": 0.0,
            "from_label": "—", "to_label": "—",
            "from_date": "", "to_date": "",
            "perf_delta": None, "skills_delta": None,
            "drivers": [],
            "bucket": "none",
        }
    perf, perf_driver = _perf_delta(p)
    skills, skills_drivers = _skills_delta(p)
    list_jump_score, list_jump_drivers = _baseline_to_now_list_jump(p)
    pedigree, _ = _pedigree_score(p.get("acquisition"))
    bucket, score, gate_drivers = _classify_movement(
        p, perf, skills, list_jump_score, pedigree,
    )
    drivers: list[str] = []
    if perf_driver:
        drivers.append(perf_driver)
    drivers.extend(skills_drivers or [])
    drivers.extend(list_jump_drivers or [])
    drivers.extend(gate_drivers)
    # Dedup while preserving order.
    seen = set()
    drivers = [d for d in drivers if not (d in seen or seen.add(d))]

    pts = p.get("points") or []
    latest = pts[-1] if pts else {}
    prior_pt = pts[-2] if len(pts) >= 2 else latest
    return {
        "direction": _direction_from_delta(score),
        "delta": round(score, 2),
        "from_label": prior_pt.get("consensus_fv_label") or "—",
        "to_label": latest.get("consensus_fv_label") or "—",
        "from_date": prior_pt.get("snapshot_date") or "",
        "to_date":   latest.get("snapshot_date") or "",
        "perf_delta": round(perf, 3) if perf is not None else None,
        "skills_delta": round(skills, 2) if skills is not None else None,
        "drivers": drivers[:5],
        "bucket": bucket,
    }


def build_spotlights(players: list[dict], graduates: list[dict]) -> dict:
    """Three-bucket spotlight output: Risers, Rebounders, Fallers.

    All three feed off the centralized compute_movement engine. The legacy
    `hot` key is aliased to `risers` for one release so cached payloads
    still render."""
    risers: list[dict] = []
    rebounders: list[dict] = []
    fallers: list[dict] = []

    for p in players:
        m = compute_movement(p)
        bucket = m.get("bucket")
        if bucket not in {"riser", "rebound", "faller"}:
            continue
        entry = _entry(
            "hot" if bucket == "riser" else
            ("rebounder" if bucket == "rebound" else "faller"),
            p, m["delta"], m["drivers"],
        )
        entry["bucket"] = bucket
        entry["perf_delta"] = m.get("perf_delta")
        entry["skills_delta"] = m.get("skills_delta")
        if bucket == "riser":     risers.append(entry)
        elif bucket == "rebound": rebounders.append(entry)
        elif bucket == "faller":  fallers.append(entry)

    risers_sorted = sorted(risers, key=lambda x: -x["score"])[:TOP_N]
    rebounders_sorted = sorted(rebounders, key=lambda x: -x["score"])[:TOP_N]
    # Fallers sort ASCENDING (most-negative first).
    fallers_sorted = sorted(fallers, key=lambda x: x["score"])[:TOP_N]

    return {
        "risers":     risers_sorted,
        "rebounders": rebounders_sorted,
        "fallers":    fallers_sorted,
        # Back-compat alias — older cached payloads / pre-rebuild frontends
        # read `.hot`. Drop after one rebuild cycle.
        "hot":        risers_sorted,
    }
