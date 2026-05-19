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


def build_spotlights(players: list[dict], graduates: list[dict]) -> dict:
    hot: list[dict] = []
    rebounders: list[dict] = []

    for p in players:
        surface, surface_drivers = _surface_score(p)
        sc_score, sc_drivers = _statcast_drivers(p)
        if surface <= 0 and sc_score <= 0:
            continue
        age = p.get("age_vs_level") or {}
        age_score = 1.0 if age.get("tier") in {"very-young", "young"} else 0.0
        rank_score = max(0.0, 2.5 - ((p.get("overall_rank") or 300) / 120.0))
        hot_score = surface + sc_score + age_score + rank_score
        prior, prior_drivers = _prior_underperformance(p)
        change_drivers = _change_drivers(p)
        list_jump_score, list_jump_drivers = _baseline_to_now_list_jump(p)
        hot_drivers = change_drivers + surface_drivers + sc_drivers
        if (p.get("overall_rank") or 9999) <= 100 and prior >= 2.0:
            hot_score += 2.0
            hot_drivers += [d for d in prior_drivers if d not in hot_drivers]
        hot.append(_entry("hot", p, hot_score, hot_drivers))

        pedigree, pedigree_drivers = _pedigree_score(p.get("acquisition"))
        ps_score = _num((p.get("prospect_savant") or {}).get("ps_score"))
        if _is_rebound_candidate(p) and (pedigree >= 1.5 or prior >= 1.0 or (ps_score is not None and ps_score >= 0.95)):
            rebound_score = surface + sc_score + pedigree + prior + list_jump_score
            if (p.get("overall_rank") or 9999) <= 100 and prior >= 2.0:
                rebound_score += 3.0
            if (p.get("overall_rank") or 9999) <= 100 and ps_score is not None and ps_score >= 0.95:
                rebound_score += 3.0
            if (p.get("age_vs_level") or {}).get("tier") in {"very-young", "young"}:
                rebound_score += 1.0
            if rebound_score >= 5.0:
                rebounders.append(_entry(
                    "rebounder", p, rebound_score,
                    list_jump_drivers + change_drivers + surface_drivers + sc_drivers + prior_drivers + pedigree_drivers,
                ))

    return {
        "hot": sorted(hot, key=lambda x: -x["score"])[:TOP_N],
        "rebounders": sorted(rebounders, key=lambda x: -x["score"])[:TOP_N],
    }
