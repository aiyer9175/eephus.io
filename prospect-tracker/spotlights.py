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
MAX_DRIVERS_PER_CARD = 8   # v15 — was 4 (cycle 14)


# v15 — Per-stat polarity table. "up_good" means the stat is better when it
# goes UP (OPS, K% for pitchers, wRC+); "down_good" means better when it goes
# DOWN (ERA, FIP-, K% for hitters, BB% for pitchers). Stats not listed default
# to "up_good" since most numeric stats follow that convention.
_STAT_POLARITY = {
    # hitter rate stats — higher = better
    "ops": "up_good", "ops_plus": "up_good", "wrc_plus": "up_good",
    "iso": "up_good", "babip": "up_good", "avg": "up_good",
    "obp": "up_good", "slg": "up_good", "hard_hit_pct": "up_good",
    "barrel_pct": "up_good", "exit_velo": "up_good", "max_ev": "up_good",
    "ev_90": "up_good", "ps_score": "up_good", "max_velo": "up_good",
    "fb_velo": "up_good", "hr": "up_good", "sb": "up_good",
    "bb_pct_hitter": "up_good",
    # hitter rate stats — lower = better
    "k_pct_hitter": "down_good", "whiff_pct_hitter": "down_good",
    "chase_pct": "down_good",
    # pitcher rate stats — higher = better
    "k_pct_pitcher": "up_good", "whiff_pct_pitcher": "up_good",
    "stf_plus": "up_good", "stf_plus_periph": "up_good",
    "k_per_9": "up_good", "gb_pct": "up_good", "swstr_pct": "up_good",
    # pitcher rate stats — lower = better
    "era": "down_good", "era_minus": "down_good", "fip": "down_good",
    "fip_minus": "down_good", "xfip": "down_good", "whip": "down_good",
    "bb_pct_pitcher": "down_good", "bb_per_9": "down_good",
    "hr_per_9": "down_good", "hard_hit_pct_allowed": "down_good",
}


def _stat_valence(stat_key: str, delta: float | None) -> str:
    """Return "good" / "bad" / "neutral" based on the polarity table.
    The polarity decides whether a positive delta is good or bad — e.g. a
    pitcher's ERA going down (negative delta) is "good".

    v17 — Neutral is now reserved only for null/exactly-zero deltas.
    Any directional delta (positive or negative) gets polarized to
    good or bad. This widens the green/red coverage so neutral becomes
    rare (only triggered when we genuinely don't know the direction)."""
    if delta is None:
        return "neutral"
    if delta == 0:
        return "neutral"
    polarity = _STAT_POLARITY.get(stat_key, "up_good")
    if polarity == "up_good":
        return "good" if delta > 0 else "bad"
    return "good" if delta < 0 else "bad"


# v15 — back-compat parser for legacy string-shaped drivers. Walks the
# label looking for known stat tokens and a directional verb (up/down) so
# we can stamp a valence even without a full _mk_driver call. Keeps the
# entire driver-emission codebase (50+ append sites) functional with a
# single normalization step at the entry serialization layer.
_DRIVER_TOKEN_POLARITY = {
    # token (lowercased substring) -> stat polarity key
    "ops":  "ops",
    "wrc+": "wrc_plus",
    "iso":  "iso",
    "babip": "babip",
    "exit velo": "exit_velo",
    "max ev": "max_ev",
    "ev_90": "ev_90", "90th ev": "ev_90",
    "hard-hit": "hard_hit_pct",
    "barrel": "barrel_pct",
    "fastball": "fb_velo", "fb": "fb_velo",
    "max velo": "max_velo",
    "k/9": "k_per_9",
    "bb/9": "bb_per_9",
    "hr/9": "hr_per_9",
    "era": "era",
    "fip": "fip",
    "whip": "whip",
    "stf+": "stf_plus", "stf plus": "stf_plus", "pstuff+": "stf_plus_periph",
}


def _infer_polarity_key(label: str, *, is_pitcher_context: bool = False) -> str | None:
    """Scan a driver label for known stat tokens; return polarity key."""
    lc = label.lower()
    for token, key in _DRIVER_TOKEN_POLARITY.items():
        if token in lc:
            return key
    # K% / BB% — polarity depends on hitter vs pitcher context.
    if "k%" in lc or "k pct" in lc:
        return "k_pct_pitcher" if is_pitcher_context else "k_pct_hitter"
    if "bb%" in lc or "bb pct" in lc:
        return "bb_pct_pitcher" if is_pitcher_context else "bb_pct_hitter"
    return None


# v18 — Intrinsic-polarity table for narrative drivers (no numeric delta,
# no up/down verb, but the phrase itself carries clear positive/negative
# meaning). Without this, legacy string drivers like "first-round pedigree"
# or "major skills decline" fall through to neutral → yellow chip. Match by
# lowercase substring so the embedded round number / FV / level doesn't
# break the lookup. Order is irrelevant since we just return on first hit.
_INTRINSIC_DRIVER_POLARITY: dict[str, str] = {
    # — positive narratives (drivers.append sites in this file) —
    "first-round pedigree":          "good",
    "top-100 pick pedigree":         "good",
    "draft pedigree":                "good",
    "international signing pedigree": "good",
    "high-fv pedigree":              "good",
    "m bonus":                       "good",   # "$5.5M bonus", "$1.2M bonus"
    "x-metrics verified":            "good",
    "young for level":               "good",
    "continuing high performance":   "good",
    "continuing strong arm":         "good",
    "pedigree comeback":             "good",
    "rank jump":                     "good",
    "rank up":                       "good",
    "rank rising":                   "good",
    "repeating level + improving":   "good",
    "vs level mean":                 "good",   # signed-by-direction; positive default — overridden below for "-" prefix
    # v19 — additional positive narratives surfaced in cycles 16-19.
    "breakout":                      "good",
    "elite":                         "good",
    "plus tool":                     "good",
    "plus-plus":                     "good",
    "promotion":                     "good",
    "promoted":                      "good",
    "called up":                     "good",
    "debut":                         "good",
    "no-hitter":                     "good",
    "perfect game":                  "good",
    "comeback":                      "good",
    "returns from il":               "good",
    "off the il":                    "good",
    "off il":                        "good",
    # — negative narratives —
    "major skills decline":          "bad",
    "underlying data weak":          "bad",
    "limited runway":                "bad",
    "regressed while repeating":     "bad",
    "skills broken":                 "bad",
    "high-fv decline":               "bad",
    "unsupported by x-metrics":      "bad",
    # v19 — additional negative narratives.
    "demotion":                      "bad",
    "demoted":                       "bad",
    "sent down":                     "bad",
    "released":                      "bad",
    "designated for assignment":     "bad",
    "dfa":                           "bad",
    "placed on il":                  "bad",
    "on il":                         "bad",
    "tommy john":                    "bad",
    "ucl":                           "bad",
    "fractured":                     "bad",
    "torn":                          "bad",
    "season-ending":                 "bad",
    "rank drop":                     "bad",
    "rank falling":                  "bad",
    "dropped from":                  "bad",
    "sub-aaa prospect":              "neutral",  # informational, not a leaning
    "mlb seasons":                   "neutral",  # informational
    "mlb games":                     "neutral",  # informational
    "milb":                          "neutral",  # historical stat citation
}


def _infer_intrinsic_polarity(label: str) -> str | None:
    """Match a narrative driver label to an intrinsic valence. Returns
    None when the label doesn't match a known phrase (caller falls back
    to direction/polarity inference). Handles the "+X% vs level mean"
    sign by overriding the table's "good" default for negative-signed
    deltas."""
    lc = label.lower()
    # Special-case the signed "X% vs level mean" driver: positive sign
    # is good, negative is bad. Default to "good" (table value) if we
    # can't read the sign.
    if "vs level mean" in lc:
        # Look for the leading sign on the percentage.
        try:
            pct_part = lc.split("%", 1)[0].strip()
            num_str = pct_part.lstrip("+").lstrip()
            if num_str.startswith("-"):
                return "bad"
        except (IndexError, ValueError):
            pass
        return "good"
    for token, val in _INTRINSIC_DRIVER_POLARITY.items():
        if token in lc:
            return val
    return None


def _normalize_driver(d, *, is_pitcher_context: bool = False) -> dict:
    """Accept either a string driver (legacy) or a dict driver (v15 native).
    Return the canonical dict shape with label/direction/valence/tooltip."""
    if isinstance(d, dict):
        # Trust the caller's structure but fill in missing fields.
        out = dict(d)
        if "label" not in out:
            out["label"] = str(out.get("stat") or "")
        if "valence" not in out:
            out["valence"] = _stat_valence(out.get("stat") or "", out.get("delta"))
        if "tooltip" not in out:
            out["tooltip"] = out["label"]
        return out
    # String driver — infer everything from the label.
    label = str(d)
    lc = label.lower()
    polarity_key = _infer_polarity_key(label, is_pitcher_context=is_pitcher_context)
    # Direction inferred from (in priority order):
    #   1. "up" / "down" verbs in the label
    #   2. Signed delta "+0.245" or "-1.5" anywhere in the label
    #   3. "X.XX vs Y.YY prior" comparison — current vs prior
    # The sign/comparison branch fixes drivers like
    #   "OPS +0.245 vs '24-25"   (sign → up)
    #   "ERA 0.81 vs 3.25 prior" (comparison → 0.81 < 3.25 → down)
    # that previously fell through to neutral → yellow chip even though
    # the polarity_key was set correctly.
    import re as _re
    direction: str | None = None
    if " up " in lc or lc.endswith(" up"):
        direction = "up"
    elif " down " in lc or lc.endswith(" down"):
        direction = "down"
    if direction is None:
        # Signed delta: "+0.245", " +5.5pp", "(-1.5 ERA)", etc.
        m_sign = _re.search(r"(?:^|\s|\()([+−-])(\d+(?:\.\d+)?)", label)
        if m_sign:
            direction = "up" if m_sign.group(1) == "+" else "down"
    if direction is None:
        # Comparison: "0.81 vs 3.25 prior" — current first, prior second.
        m_cmp = _re.search(
            r"(\d+(?:\.\d+)?)\s+vs\s+(\d+(?:\.\d+)?)\s*(?:prior|recent\s+prior|recent\s+seasons?)",
            lc,
        )
        if m_cmp:
            try:
                cur, prior = float(m_cmp.group(1)), float(m_cmp.group(2))
                if cur > prior:
                    direction = "up"
                elif cur < prior:
                    direction = "down"
            except ValueError:
                pass
    # v18 — intrinsic polarity wins when present; otherwise fall back to
    # direction + stat-polarity inference (the original v15/v17 path).
    intrinsic = _infer_intrinsic_polarity(label)
    if intrinsic is not None:
        valence = intrinsic
    elif direction and polarity_key:
        valence = _stat_valence(polarity_key, +1.0 if direction == "up" else -1.0)
    else:
        valence = "neutral"
    return {
        "label": label,
        "stat": polarity_key,
        "current": None,
        "baseline": None,
        "delta": None,
        "baseline_label": None,
        "direction": direction,
        "valence": valence,
        "tooltip": label,
    }


def _mk_driver(label: str, *, stat: str | None = None,
               current: float | None = None, baseline: float | None = None,
               delta: float | None = None,
               baseline_label: str | None = None) -> dict:
    """Build the v15 driver dict with valence + tooltip.

    If `delta` is None and both `current`+`baseline` are given, derive it.
    Tooltip surfaces current value, baseline value, and delta in compact form.
    """
    if delta is None and current is not None and baseline is not None:
        delta = current - baseline
    direction = None
    if delta is not None and delta != 0:
        direction = "up" if delta > 0 else "down"
    valence = _stat_valence(stat or "", delta) if stat else "neutral"
    tooltip_lines: list[str] = []
    if current is not None:
        tooltip_lines.append(f"Current: {current:.3f}".rstrip("0").rstrip(".")
                             if abs(current) < 10 else f"Current: {current:.1f}")
    if baseline is not None:
        lbl = baseline_label or "baseline"
        tooltip_lines.append(f"{lbl}: {baseline:.3f}".rstrip("0").rstrip(".")
                             if abs(baseline) < 10 else f"{lbl}: {baseline:.1f}")
    if delta is not None and delta != 0:
        sign = "+" if delta > 0 else "−"
        tooltip_lines.append(f"Δ: {sign}{abs(delta):.3f}".rstrip("0").rstrip(".")
                             if abs(delta) < 10 else f"Δ: {sign}{abs(delta):.1f}")
    return {
        "label": label,
        "stat": stat,
        "current": current,
        "baseline": baseline,
        "delta": delta,
        "baseline_label": baseline_label,
        "direction": direction,
        "valence": valence,
        "tooltip": "\n".join(tooltip_lines) if tooltip_lines else label,
    }


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
        # v22 — Prefer K% / BB% (per-batter rates) over K/9 / BB/9
        # (per-inning). MLB-equivalent benchmarks: ~23% K is league
        # average, 30%+ elite; 8% BB is average, sub-6% elite. Fall
        # back to per-9 when per-batter rate is missing.
        kpct = _num(sl.get("k_pct"))
        bbpct = _num(sl.get("bb_pct"))
        era = _num(sl.get("era"), 9.0) or 9.0
        ip = _num(sl.get("ip"), _ip(row)) or 0.0
        if ip < 12:
            return 0.0, []
        if kpct is not None and bbpct is not None:
            score = max(0.0, kpct - 22.0) * 0.20 + max(0.0, 4.25 - era) * 1.4
            score += max(0.0, 8.0 - bbpct) * 0.18
            drivers.append(f"{kpct:.1f}% K")
            if era < 3.5:
                drivers.append(f"{era:.2f} ERA")
            if bbpct < 8.0:
                drivers.append(f"{bbpct:.1f}% BB")
        else:
            k9 = _num(sl.get("k_per_9"), 0.0) or 0.0
            bb9 = _num(sl.get("bb_per_9"), 9.0) or 9.0
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
        # v22 — Prefer K% / BB% deltas (per-batter rates) over K/9 / BB/9
        # (per-inning). Sensitivity reset: K% jumps of 4pp / BB% drops of
        # 2pp are the per-batter equivalents of the old 1.5 K/9 / 1.0
        # BB/9 thresholds. Fall back to per-9 deltas when neither prior
        # nor current carries k_pct (legacy career rows).
        current_kpct = _num(latest.get("k_pct"))
        prior_kpct = [_num(r.get("k_pct")) for r in priors if r.get("is_pitcher") and _ip(r) >= 10]
        prior_kpct = [v for v in prior_kpct if v is not None]
        if current_kpct is not None and prior_kpct:
            diff = current_kpct - mean(prior_kpct)
            if diff >= 4.0:
                drivers.append(f"K% up {diff:.1f}%")
        else:
            current_k9 = _num(latest.get("k_per_9"))
            prior_k9 = [_num(r.get("k_per_9")) for r in priors if r.get("is_pitcher") and _ip(r) >= 10]
            prior_k9 = [v for v in prior_k9 if v is not None]
            if current_k9 is not None and prior_k9:
                diff = current_k9 - mean(prior_k9)
                if diff >= 1.5:
                    drivers.append(f"K/9 up {diff:.1f}")
        current_bbpct = _num(latest.get("bb_pct"))
        prior_bbpct = [_num(r.get("bb_pct")) for r in priors if r.get("is_pitcher") and _ip(r) >= 10]
        prior_bbpct = [v for v in prior_bbpct if v is not None]
        if current_bbpct is not None and prior_bbpct:
            diff = mean(prior_bbpct) - current_bbpct
            if diff >= 2.0:
                drivers.append(f"BB% down {diff:.1f}%")
        else:
            current_bb9 = _num(latest.get("bb_per_9"))
            prior_bb9 = [_num(r.get("bb_per_9")) for r in priors if r.get("is_pitcher") and _ip(r) >= 10]
            prior_bb9 = [v for v in prior_bb9 if v is not None]
            if current_bb9 is not None and prior_bb9:
                diff = mean(prior_bb9) - current_bb9
                if diff >= 1.0:
                    drivers.append(f"BB/9 down {diff:.1f}")
    return drivers


def _entry(bucket: str, p: dict, score: float, drivers: list) -> dict:
    sl = p.get("statline") or {}
    pts = p.get("points") or []
    latest = pts[-1] if pts else {}
    # v15 — Normalize drivers (strings → dict) and cap at 8. The pitcher-vs-
    # hitter context helps the K%/BB% polarity resolution: if the sl flags
    # is_pitcher, K% UP is good (and BB% DOWN is good); for hitters it's
    # inverted.
    is_pitcher_ctx = bool(sl.get("is_pitcher"))
    normalized = [_normalize_driver(d, is_pitcher_context=is_pitcher_ctx)
                  for d in (drivers or [])]
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
        "drivers": normalized[:MAX_DRIVERS_PER_CARD],
    }


def _line_text(sl: dict) -> str:
    if not sl:
        return "No current line"
    if sl.get("is_pitcher"):
        # v22 — Prefer K% when present; fall back to K/9 only when it isn't.
        kpct = sl.get("k_pct")
        k_str = (f"{float(kpct):.1f}% K" if kpct is not None
                 else f"{sl.get('k_per_9', '—')} K/9")
        return f"{sl.get('era', '—')} ERA, {sl.get('ip', '—')} IP, {k_str}"
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
            kpct = _num(r.get("k_pct"))
            k9 = _num(r.get("k_per_9"))
            # v22 — Trigger on either K% ≥ 28 (elite per-batter) or K/9 ≥ 10.5
            # (legacy threshold). Driver label prefers the K% form.
            k_qual = (kpct is not None and kpct >= 28.0) or (k9 is not None and k9 >= 10.5)
            if ip >= 20 and ((era is not None and era <= 3.75) or k_qual):
                if era is not None and era <= 3.75:
                    drivers.append(f"{r.get('season')} MiLB {era:.2f} ERA")
                elif kpct is not None:
                    drivers.append(f"{r.get('season')} MiLB {kpct:.1f}% K")
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
        # v22 — Per-batter rates (K% / BB%) preferred; fall back to per-9
        # rates when the per-batter value is missing. Thresholds reset to
        # the per-batter scale: 3pp K% jump (was 1.5 K/9), 2pp BB% drop
        # (was 0.8 BB/9). Same ±3-point cap.
        per_batter_specs = (
            ("k_pct", "K%", "%", False, 3.0),
            ("bb_pct", "BB%", "%", True, 2.0),
        )
        per_9_specs = (
            ("k_per_9", "K/9", "", False, 1.5),
            ("bb_per_9", "BB/9", "", True, 0.8),
        )
        used_keys: set[str] = set()
        for key, label, suffix, lower_better, threshold in per_batter_specs:
            cur = _num(sl.get(key))
            prior_vals = [_num(r.get(key)) for r in priors
                          if r.get("is_pitcher") and _ip(r) >= 15]
            prior_vals = [v for v in prior_vals if v is not None]
            if cur is None or not prior_vals:
                continue
            used_keys.add(key)
            diff = cur - mean(prior_vals)
            improvement = -diff if lower_better else diff
            if abs(diff) >= threshold:
                pts = max(-3.0, min(3.0, improvement / threshold))
                score += pts
                direction = "down" if diff < 0 else "up"
                drivers.append(f"{label} {direction} {abs(diff):.1f}{suffix}")
        # Per-9 fallback runs only for rates that the per-batter loop
        # didn't see (rare — legacy career rows without TBF).
        for key, label, _, lower_better, threshold in per_9_specs:
            sibling_key = "k_pct" if key == "k_per_9" else "bb_pct"
            if sibling_key in used_keys:
                continue
            cur = _num(sl.get(key))
            prior_vals = [_num(r.get(key)) for r in priors
                          if r.get("is_pitcher") and _ip(r) >= 15]
            prior_vals = [v for v in prior_vals if v is not None]
            if cur is None or not prior_vals:
                continue
            diff = cur - mean(prior_vals)
            improvement = -diff if lower_better else diff
            if abs(diff) >= threshold:
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
            drivers.append(f"{label} {direction} {abs(diff):.1f}%")
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


# Age cap above level-mean — gates excessively-old prospects out of
# every spotlight bucket (riser / rebound / faller). Anchored on a
# PROSPECT-aspirational baseline by level (NOT the empirical median —
# the empirical AAA pool is ~25.7 because it includes the journeymen
# we want to filter, so anchoring on empirical means defeats the
# purpose). The static baselines below match the scouting convention
# (FanGraphs primer):
#   A=21, A+=22, AA=23, AAA=24, MLB=26
# Caps (years above the baseline, INCLUSIVE on the threshold) — v6
# tightened these from the original 2.0 / 3.0 to drop more journeymen:
#   hitters  → disqualified when (age − baseline) >= +1.5
#   pitchers → disqualified when (age − baseline) >= +2.0  (later debut)
# The complement is _LEVEL_TIER_BOOST below — surviving upper-level
# prospects get a smaller score boost than sub-AAA breakouts, so the
# net effect is "fewer journeymen AND lower-level prospects rank higher".
# Players at rookie levels (DSL / CPX / ROK) or with missing age/level
# pass through (cap doesn't fire) — those levels don't have a clean
# prospect-aspirational anchor.
_SPOTLIGHT_AGE_BASELINES: dict[str, float] = {
    "A":   21.0,
    "A+":  22.0,
    "AA":  23.0,
    "AAA": 24.0,
    "MLB": 26.0,
}
# Tightened in v6 (was 2.0 / 3.0) — more journeymen now drop out. The
# complement is the new _LEVEL_TIER_BOOST below, which surfaces true
# sub-AAA prospects above marginal upper-level survivors.
_AGE_CAP_HITTER = 1.5
_AGE_CAP_PITCHER = 2.0

# Per-level scoring boost. Surfaces lower-level prospects above marginal
# upper-level ones with similar performance — a real A+ breakout should
# outrank a borderline AAA depth-piece rebound. Applied to RISER +
# REBOUND paths only; fallers stay level-agnostic so the decline
# ranking remains clean.
_LEVEL_TIER_BOOST: dict[str, float] = {
    "A":   1.5,
    "A+":  1.5,
    "AA":  1.0,
    "AAA": 0.5,
    "MLB": 0.0,
}


def _level_score_boost(level: str | None) -> float:
    """Per-level score adjustment applied to risers + rebounders."""
    if not level:
        return 0.0
    return _LEVEL_TIER_BOOST.get(level, 0.0)


# Pitcher role classification — derived from the position string the
# consensus pipeline lands on. Position tokens come from FanGraphs +
# MLB Pipeline + others; SP / SIRP / MIRP are the role-tagged values
# we trust, RP is a generic relief tag, RHP / LHP / P are
# role-agnostic. Role-agnostic strings count as "unknown" so they
# don't accidentally trigger RP-specific gates (e.g., the tighter
# rebounder age cap for relievers).
_PITCHER_RELIEF_TOKENS = {"SIRP", "MIRP", "RP"}
_PITCHER_START_TOKENS  = {"SP"}


def _pitcher_role(position: str | None) -> str | None:
    """Return 'SP' | 'RP' | None (unknown / role-agnostic). Splits on
    '/' so 'SP/RP' resolves to 'SP' (primary listed first). Used by
    the new spotlights gates + the site-wide position filter."""
    if not position:
        return None
    head = str(position).split("/")[0].strip().upper()
    if head in _PITCHER_RELIEF_TOKENS:
        return "RP"
    if head in _PITCHER_START_TOKENS:
        return "SP"
    return None  # RHP / LHP / P — role-agnostic, treat as unknown


def _player_consensus_fv(p: dict) -> float | None:
    """Resolve a player's latest consensus FV from the points list.
    Used by the new faller FV floor + the Bayesian rebound prior.
    Tolerates either `consensus_fv` (numeric) or `consensus_fv_raw`
    on the most recent snapshot. Returns None when nothing is on file."""
    pts = p.get("points") or []
    if not pts:
        return None
    latest = pts[-1] or {}
    v = latest.get("consensus_fv")
    if v is None:
        v = latest.get("consensus_fv_raw")
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _fv_rebound_prior(fv: float | None) -> float:
    """Normalized 0-1 prior — 'how likely is this player a real prospect
    whose rebound is meaningful?' Anchored to the standard 20-80 scale:
      FV 40 → 0.00  (org-filler, weak prior)
      FV 45 → 0.25
      FV 50 → 0.50  (MLB regular projection, neutral prior)
      FV 55 → 0.75
      FV 60 → 1.00  (plus prospect — full prior weight)
    Linear interpolation between anchors; clipped at endpoints. Returns
    0.0 for missing FV (no prior signal → observation alone)."""
    if fv is None or fv <= 40.0:
        return 0.0
    if fv >= 60.0:
        return 1.0
    if fv <= 50.0:
        return (fv - 40.0) / 10.0 * 0.5
    return 0.5 + (fv - 50.0) / 10.0 * 0.5


def _faller_fv_multiplier(fv: float) -> float:
    """Steeper decline weighting for higher-FV prospects — a plus
    prospect falling off is a much bigger signal than a 45-FV depth
    piece declining at the same rate. Pairs with the FV-45 floor."""
    if fv >= 60.0:
        return 2.0
    if fv >= 55.0:
        return 1.5
    if fv >= 50.0:
        return 1.25
    return 1.0


def _exceeds_age_cap(age, level, is_pitcher: bool) -> bool:
    """True when the prospect is too old for their level to qualify
    for any spotlight bucket. Returns False (pass-through) when age is
    missing or the level lacks an aspirational baseline (rookie / DSL).
    See thresholds above."""
    if age is None:
        return False
    baseline = _SPOTLIGHT_AGE_BASELINES.get(level)
    if baseline is None:
        return False
    try:
        diff = float(age) - baseline
    except (TypeError, ValueError):
        return False
    cap = _AGE_CAP_PITCHER if is_pitcher else _AGE_CAP_HITTER
    return diff >= cap


# v12 — xMetric verification gate. AAA prospects have Statcast data on
# file (via prospect_savant CSVs at prospect_savant.py:101-131). Use
# wOBA-vs-xWOBA gap (hitters) and xFIP-vs-ERA gap (pitchers) to verify
# whether the surface signal is supported by the underlying contact /
# quality metrics. Returns one of "verified" / "unsupported" / "unknown".
# "unknown" = no Statcast on file → skip the gate, keep current behavior.
_XMETRIC_HITTER_WOBA_GAP_HOT  =  0.040   # wOBA exceeds xWOBA by 40 pts → over-performing
_XMETRIC_HITTER_WOBA_GAP_COLD = -0.040   # wOBA lags xWOBA by 40 pts → bad luck
_XMETRIC_PITCHER_XFIP_GAP_HOT =  0.80    # xFIP > ERA by 0.80 → lucky ERA suppression
_XMETRIC_PITCHER_XFIP_GAP_COLD = -0.80   # xFIP < ERA by 0.80 → unlucky ERA inflation


def _xmetric_verification(p: dict, direction: str) -> str:
    """Verify the surface signal against Statcast x-metrics.

    Args:
      p: player payload with `statline` + `prospect_savant`.
      direction: "up" (riser/rebound) or "down" (faller).

    Returns: "verified" | "unsupported" | "unknown".
    Only fires for AAA prospects with prospect_savant data; everything
    else returns "unknown" so the gate becomes a no-op (preserves the
    pre-v12 behavior for lower-level prospects).
    """
    sl = p.get("statline") or {}
    if (sl.get("level") or "") != "AAA":
        return "unknown"
    ps = p.get("prospect_savant") or {}
    if not ps:
        return "unknown"
    is_pitcher = bool(sl.get("is_pitcher"))
    if is_pitcher:
        era = _num(sl.get("era"))
        xfip = _num(ps.get("xfip"))
        if era is None or xfip is None:
            return "unknown"
        gap = xfip - era
        if direction == "up":
            # Riser/rebound for pitchers means ERA dropped. If xFIP is
            # much higher than ERA, the surface improvement isn't real.
            if gap >= _XMETRIC_PITCHER_XFIP_GAP_HOT:
                return "unsupported"
            return "verified"
        # Faller — ERA rose. If xFIP is much lower, the bad ERA is luck.
        if gap <= _XMETRIC_PITCHER_XFIP_GAP_COLD:
            return "unsupported"
        return "verified"
    # Hitter path.
    woba = _num(ps.get("woba"))
    xwoba = _num(ps.get("xwoba"))
    if woba is None or xwoba is None:
        return "unknown"
    gap = woba - xwoba
    if direction == "up":
        if gap >= _XMETRIC_HITTER_WOBA_GAP_HOT:
            return "unsupported"
        return "verified"
    if gap <= _XMETRIC_HITTER_WOBA_GAP_COLD:
        return "unsupported"
    return "verified"


def _check_possible_regressor(p: dict) -> tuple[float, list[str]] | None:
    """Classify a player as a Possible Regressor (over-performer due
    for regression). Returns (score, drivers) when triggered, else
    None.

    Triggers:
      - AAA hitter with wOBA ≥ 0.330 AND wOBA - xWOBA ≥ 0.040, OR
      - AAA pitcher with ERA ≤ 3.50 AND xFIP - ERA ≥ 0.80.

    The score is the absolute Statcast gap (larger gap = stronger
    regression candidate). Driver strings expose the math so the user
    sees the wOBA/xWOBA or ERA/xFIP pair.
    """
    sl = p.get("statline") or {}
    if (sl.get("level") or "") != "AAA":
        return None
    ps = p.get("prospect_savant") or {}
    if not ps:
        return None
    is_pitcher = bool(sl.get("is_pitcher"))
    if is_pitcher:
        era = _num(sl.get("era"))
        xfip = _num(ps.get("xfip"))
        if era is None or xfip is None:
            return None
        if era > 3.50:
            return None
        gap = xfip - era
        if gap < _XMETRIC_PITCHER_XFIP_GAP_HOT:
            return None
        drivers = [
            f"ERA {era:.2f} / xFIP {xfip:.2f} (gap +{gap:.2f})",
            "xFIP above ERA — unsustainable run prevention",
        ]
        return (round(gap, 2), drivers)
    # Hitter path.
    woba = _num(ps.get("woba"))
    xwoba = _num(ps.get("xwoba"))
    if woba is None or xwoba is None:
        return None
    if woba < 0.330:
        return None
    gap = woba - xwoba
    if gap < _XMETRIC_HITTER_WOBA_GAP_HOT:
        return None
    drivers = [
        f"wOBA {woba:.3f} / xWOBA {xwoba:.3f} (gap +{gap:.3f})",
        "wOBA over xWOBA — unsustainable production",
    ]
    return (round(gap, 3), drivers)


def _classify_movement(p: dict, perf_delta, skills_delta,
                       list_jump_score, pedigree) -> tuple[str, float, list[str]]:
    """Return (bucket, composite_score, drivers). Bucket is one of:
      'riser'              — broad surface-jump cases
      'rebound'            — pedigree-comeback narrative (Southisene)
      'faller'             — decline cases (with tight disqualify gates)
      'possible_regressor' — AAA over-performer flagged by xMetric gap
      'none'               — uneventful / insufficient data
    """
    drivers: list[str] = []
    sl = p.get("statline") or {}
    is_pitcher = bool(sl.get("is_pitcher"))
    age = p.get("age_vs_level") or {}
    tier = age.get("tier")
    # Age-cap gate (per-level + per-side). Anchored on the prospect-
    # aspirational baseline by level (see _SPOTLIGHT_AGE_BASELINES) —
    # NOT the empirical median, which is dragged up by the journeymen
    # we're trying to filter. Returns "none" before any bucket
    # classification so capped prospects never reach the riser /
    # faller / rebound paths.
    if _exceeds_age_cap(p.get("age"), sl.get("level"), is_pitcher):
        return ("none", 0.0, drivers)

    # ── Shared bucket filters (v6.1) ──
    # The user wants risers + rebounders + fallers to all carry the
    # same journeymen / RP / FV filter set so the three buckets
    # surface consistently. Two gates apply uniformly here:
    #   (1) FV ≥ 45 hard floor — drops org-fillers across the board
    #       (no FV-40 riser breakout, no FV-40 comeback story, no
    #       FV-40 collapse — bucket is reserved for graded prospects)
    #   (2) RP age < 23 — SIRP / MIRP / bare-RP must be very young to
    #       appear in ANY bucket (used to only gate rebounders;
    #       extended to risers + fallers per user ask). The
    #       "prospect-evolution" narrative only fits very young
    #       relief arms; older RPs are bullpen volatility, not
    #       prospect movement.
    _fv_for_floor = _player_consensus_fv(p)
    if _fv_for_floor is None or _fv_for_floor < 45.0:
        return ("none", 0.0, drivers)
    age_val_shared = p.get("age")
    pitcher_role_shared = _pitcher_role(p.get("position")) if is_pitcher else None
    if pitcher_role_shared == "RP" and age_val_shared is not None and age_val_shared >= 23.0:
        return ("none", 0.0, drivers)

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
    # Hitter / SP age cap stays at 25 here (the shared RP age<23 gate
    # above already excludes older relievers from every bucket).
    # v17 — Loosened from prior cycles: weak_prior thresholds eased
    # (4.50→3.80 ERA / 0.700→0.770 OPS), perf_delta floor 0.080→0.045,
    # pedigree floor 1.5→0.8, age cap 25→26 for hitters. Previously only
    # ~9 rebounders surfaced league-wide; target is now ~25-40.
    age_val = p.get("age")
    age_ok_for_rebound = age_val is None or age_val < 26
    perf_floor = 0.045 if not is_pitcher else 0.045
    if (perf_delta is not None and perf >= perf_floor and ped_pts >= 0.8
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
                weak_prior = m_era >= 3.80
                very_weak_prior = m_era >= 5.00
        else:
            prior_ops = [_ops(r) for r in priors
                         if not r.get("is_pitcher") and _hitter_ab(r) >= 30]
            prior_ops = [v for v in prior_ops if v is not None]
            if prior_ops:
                m_ops = mean(prior_ops)
                weak_prior = m_ops <= 0.770
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
            # Bayesian rebound score — weighted blend of FV prior
            # (pedigree) and the current observation (perf + skills
            # uptick). Higher-FV prospects get pulled up as stronger
            # rebound candidates even at the same observed bump,
            # mirroring the per-tool DvM+ shrinkage frame. PRIOR_WEIGHT
            # of 0.40 keeps observation dominant (60%) but lets pedigree
            # break the tie between two prospects with the same surface
            # rebound.
            PRIOR_WEIGHT = 0.40
            _fv = _player_consensus_fv(p)
            prior_score = _fv_rebound_prior(_fv) * 8.0   # peaks at 8.0 (FV 60+)
            obs_score = min(5.0, perf * 20.0)
            if skills_delta is not None:
                obs_score += min(2.0, max(0.0, skills * 0.5))
            posterior = (PRIOR_WEIGHT * prior_score
                         + (1.0 - PRIOR_WEIGHT) * obs_score)
            score = 3.0 + posterior  # 3.0 floor — rebounders are events
            if _level_repeat(p):
                score += 1.0
                drivers.append("repeating level + improving")
            # Sub-AAA level boost — same complement to the tighter age
            # cap that applies on the riser path. Surfaces real low-level
            # rebound narratives above marginal AAA ones.
            lvl_boost = _level_score_boost(sl.get("level"))
            if lvl_boost > 0:
                score += lvl_boost
                drivers.append(f"sub-AAA prospect ({sl.get('level')})")
            if _fv is not None and _fv >= 55.0:
                drivers.append(f"high-FV pedigree ({int(_fv)})")
            drivers.append("pedigree comeback")
            # v12 — same xMetric gate as risers. AAA-only.
            verif = _xmetric_verification(p, "up")
            if verif == "unsupported":
                reg_signal = _check_possible_regressor(p)
                if reg_signal is not None:
                    reg_score, reg_drivers = reg_signal
                    drivers.append("unsupported by x-metrics")
                    return ("possible_regressor", reg_score, drivers + reg_drivers)
            elif verif == "verified":
                drivers.append("x-metrics verified")
            return ("rebound", score, drivers)

    # --- Riser: perf jumped meaningfully OR list-jump fired ---
    is_riser_perf = perf_delta is not None and perf >= PERF_RISER_BAR
    is_riser_jump = list_jump_score >= 2.0
    # v27 — "+" upside added: any source ADDED a "+" upside marker in
    # the player's recent history (within the last 6 months, matching
    # the breakout window). A "55 → 55+" event is a real scout-noted
    # upside note even without a numeric FV change.
    #
    # Gate: perf must not be in collapse. The upside path BOOSTS a
    # borderline riser case (perf flat-to-slightly-positive); it does
    # NOT override a strong faller signal. A player whose K% spiked
    # 20pp and whose perf cratered (negative perf_delta past the
    # faller bar) stays in the faller path even if a source added "+".
    is_riser_upside = False
    upside_riser_sources: list[str] = []
    # Perf floor: must be at least near-flat (-0.04 for hitter OPS,
    # -0.04 for pitcher xFIP-ish). Below this we let the faller logic
    # take over. Tunable; sized to admit "the bat slumped a little but
    # scout still likes the upside" while rejecting "perf collapsed."
    _upside_perf_floor = -0.04
    if (perf_delta is None) or (perf >= _upside_perf_floor):
        try:
            _pts = p.get("points") or []
            from storage import _detect_upside_added_events as _detect_upside
            from datetime import date as _d, timedelta as _td
            _upside_events = _detect_upside(_pts)
            if _pts:
                _last_date_str = _pts[-1].get("snapshot_date")
                if _last_date_str:
                    try:
                        _last_d = _d.fromisoformat(_last_date_str)
                        _cutoff = (_last_d - _td(days=180)).isoformat()
                        _recent = [e for e in _upside_events if e.get("date") and e["date"] >= _cutoff]
                        if _recent:
                            is_riser_upside = True
                            upside_riser_sources = sorted({e["source"] for e in _recent})
                    except (ValueError, TypeError):
                        pass
        except ImportError:
            pass
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

    if is_riser_perf or is_riser_jump or is_riser_continuing or is_riser_upside:
        score = 0.0
        if is_riser_perf:
            score += min(6.0, perf * (8.0 if is_pitcher else 25.0))
        if is_riser_jump:
            score += min(3.0, list_jump_score)
            drivers.append("rank jump on baseline lists")
        if is_riser_continuing:
            score += 2.5
        if is_riser_upside:
            # v27 — Each added "+" event contributes 1.5 score (capped
            # at 4.5 across multiple sources). A single FG "+ added" is
            # a real qualitative upside note; multiple sources agreeing
            # ("+ added" from FG AND BA) is a stronger signal that
            # outranks a single-source "+ added" without breakout-class
            # FV velocity.
            score += min(4.5, 1.5 * len(upside_riser_sources or [None]))
            drivers.append(
                "+ upside added by " + ", ".join(upside_riser_sources)
                if upside_riser_sources else "+ upside added"
            )
        if young_for_level:
            score += 1.0
            drivers.append("young for level")
        if skills_delta is not None and skills > 0:
            score += min(2.0, skills * 0.4)
        # Sub-AAA level boost — complements the tighter age cap so true
        # low-level breakouts outrank marginal upper-level survivors.
        lvl_boost = _level_score_boost(sl.get("level"))
        if lvl_boost > 0:
            score += lvl_boost
            drivers.append(f"sub-AAA prospect ({sl.get('level')})")
        # v12 — current-season vs level-mean amplifier. statline carries
        # `level_plus_pct` (signed: positive = better than the level's
        # cohort mean). Strong above-mean performance lifts the riser
        # score; near-mean performance leaves it alone. Caps at ±3.0
        # points so it can break ties without dominating the score.
        lp = _num(sl.get("level_plus_pct"))
        if lp is not None and lp >= 15:
            bonus = min(3.0, (lp - 15) / 10.0 + 1.0)  # 15%→1.0, 25%→2.0, 35%→3.0
            score += bonus
            drivers.append(f"+{lp:.0f}% vs level mean")
        # v12 — xMetric verification gate for AAA risers. If the
        # surface jump isn't supported by underlying Statcast (wOBA
        # over xWOBA, ERA under xFIP), demote to Possible Regressor
        # rather than letting the unsustainable surge headline Risers.
        verif = _xmetric_verification(p, "up")
        if verif == "unsupported":
            reg_signal = _check_possible_regressor(p)
            if reg_signal is not None:
                reg_score, reg_drivers = reg_signal
                drivers.append("unsupported by x-metrics")
                return ("possible_regressor", reg_score, drivers + reg_drivers)
        elif verif == "verified":
            drivers.append("x-metrics verified")
        return ("riser", max(0.0, score), drivers)

    # --- Faller: perf declined meaningfully ---
    # FV floor is enforced at the shared-filter block at the top of
    # this function (FV >= 45 applies to every bucket). The faller-
    # specific scoring still uses _fv_for_floor for the per-tier
    # multiplier below.
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

    # Faller path. Decline magnitude is weighted by the prospect's FV
    # tier (FV 60+ ×2.0, 55 ×1.5, 50 ×1.25, 45 ×1.0) so a plus prospect
    # falling off is a much bigger signal than a 45-FV depth piece
    # declining at the same rate. Structural-breakdown penalties
    # (skills crater, age, K-rate spike) stay unweighted — they're
    # categorical red flags, not pure performance decline.
    fv_mult = _faller_fv_multiplier(_fv_for_floor)
    score = 0.0
    if perf_delta is not None and perf <= 0:
        raw_decline = max(-6.0, perf * (10.0 if is_pitcher else 30.0))
        score += raw_decline * fv_mult
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
    if _fv_for_floor >= 55.0:
        drivers.append(f"high-FV decline ({int(_fv_for_floor)})")
    # v12 — current-season vs level-mean amplifier. Strong below-mean
    # performance deepens the faller score. Caps at -3.0 points.
    lp = _num(sl.get("level_plus_pct"))
    if lp is not None and lp <= -15:
        penalty = max(-3.0, (lp + 15) / 10.0 - 1.0)  # -15→-1.0, -25→-2.0, -35→-3.0
        score += penalty
        drivers.append(f"{lp:.0f}% vs level mean")
    # v12 — xMetric verification gate for AAA fallers. If the surface
    # dip isn't supported by underlying Statcast (wOBA under xWOBA,
    # ERA over xFIP), demote to "none" — the cold streak is bad luck
    # rather than a real prospect drop. Drivers stay so the next
    # rebuild can revisit the call.
    verif = _xmetric_verification(p, "down")
    if verif == "unsupported":
        drivers.append("unsupported by x-metrics (likely bad luck)")
        return ("none", 0.0, drivers)
    if verif == "verified":
        drivers.append("x-metrics verified")
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
    if (p.get("status") or "") == "debuted":
        return {
            "direction": "debuted", "delta": 0.0,
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
    # Dedup while preserving order (strings still — dicts not yet wrapped).
    seen = set()
    drivers = [d for d in drivers if not (d in seen or seen.add(d))]

    pts = p.get("points") or []
    latest = pts[-1] if pts else {}
    prior_pt = pts[-2] if len(pts) >= 2 else latest
    # v15 — Normalize to dict shape + bump cap to 8 (was 5).
    sl_for_ctx = p.get("statline") or {}
    is_pitcher_ctx = bool(sl_for_ctx.get("is_pitcher"))
    normalized = [_normalize_driver(d, is_pitcher_context=is_pitcher_ctx)
                  for d in drivers]
    return {
        "direction": _direction_from_delta(score),
        "delta": round(score, 2),
        "from_label": prior_pt.get("consensus_fv_label") or "—",
        "to_label": latest.get("consensus_fv_label") or "—",
        "from_date": prior_pt.get("snapshot_date") or "",
        "to_date":   latest.get("snapshot_date") or "",
        "perf_delta": round(perf, 3) if perf is not None else None,
        "skills_delta": round(skills, 2) if skills is not None else None,
        "drivers": normalized[:MAX_DRIVERS_PER_CARD],
        "bucket": bucket,
    }


def build_spotlights(players: list[dict], graduates: list[dict]) -> dict:
    """Three-bucket spotlight output: Risers, Rebounders, Fallers.

    All buckets feed off the centralized compute_movement engine. The
    legacy `hot` key is aliased to `risers` for one release so cached
    payloads still render. v16 dropped `possible_regressors` — it never
    populated meaningfully and was just empty noise on the UI."""
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
