# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""MLB Projections module — sidecar export (data/mlb_projections.json).

The FA module's Gate-1-validated projection engine, applied to the WHOLE
league: every player with recent MLB history gets a multi-year bWAR path
(mean + P10/P90 probability buckets), and PROSPX prospects get post-ETA
paths from the calibrated FV outcome model. One surface, two clearly
labeled sources:

  VETERANS   the FA Marcel engine (components -> composites -> fitted WAR
             map), decayed along the survivorship-corrected aging curves;
             buckets are the Gate-1 empirical year-1 residual quantiles
             decayed through the same curves (identical machinery to the
             FA class board — fa_market.contract_war_path).
  PROSPECTS  the value_framework outcome model: P(bucket|FV) x per-bucket
             WAR trajectories (FV-scaled, aging-shaped from projected
             debut age), starting at the PROSPX ETA. Floor/ceiling are
             the 10th/90th percentile OUTCOME BUCKETS of the categorical
             — a prospect's downside is busting, not a residual ribbon.

Dollars: each projected season is priced through the platform's convex
tier curve at the winter's ex-ante FA $/WAR level, escalated by the
configured $/WAR inflation per season — the same pricing the FA rational
value and the (re-anchored) prospect surplus use. Veteran SURPLUS only
exists where a real contract exists: salary-known seasons (Spotrac
contract pages) net against production value and discount at the platform
9%; arb/pre-arb seasons carry projections but no surplus claim. Prospect
surplus IS the platform surplus value (control-window, service-time
aware) — never a parallel number.

Run: python proj_export.py   (also wired into run_monthly after the FA
refresh). Reads only caches + committed artifacts; never writes PROSPX
data (read-only consumer, same contract as the FA module).
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import date
from pathlib import Path

import fa_class
import fa_ident
import fa_market as fm
import fa_projection as fp
import value_framework as vf
from scrapers import normalize_key

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
FIRST_SEASON = 2027          # first fully projected season (2026 is in progress)
HORIZON = 5                  # 2027..2031
# Exposure floor for the veteran universe: at least one of the last three
# seasons with a real sample (sub-cup-of-coffee players add noise, not
# signal, and the engine's reliability buckets were fitted above this).
MIN_PA, MIN_IP = 100, 30

_BUCKET_ORDER = ("bust", "bench", "regular", "good", "star")


def _clean(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None and v != [] and v != {}}


def _display_names() -> dict[int, str]:
    """{mlbam: display name} — the war_daily index inverted (the same
    identity source fa_ident resolves against, read in reverse)."""
    out: dict[int, str] = {}
    for _norm, cands in fa_ident.war_daily_index().items():
        for mid in cands:
            out.setdefault(mid, "")
    # second pass for the raw display string: war_daily_index normalizes
    # names away, so rebuild from pybaseball directly (cached by pybaseball).
    import pybaseball as pyb
    for fn in (pyb.bwar_bat, pyb.bwar_pitch):
        try:
            df = fn(return_all=True)
        except Exception:                                     # noqa: BLE001
            continue
        sub = df[df["mlb_ID"].notna()]
        for row in sub.itertuples(index=False):
            try:
                out[int(row.mlb_ID)] = str(row.name_common)
            except (TypeError, ValueError):
                continue
    return {k: v for k, v in out.items() if v}


def _season_value_usd(war: float, t: int, dpw_level: float) -> float:
    """One projected season priced on the platform's convex tier curve at
    the winter's ex-ante $/WAR level, escalated t seasons out."""
    base_flat = float(vf._config()["dollars_per_war"]["flat"])
    infl = float(vf._config().get("dollars_per_war_inflation", 0.05))
    return vf.tiered_war_value_usd(war) * (dpw_level / base_flat) * ((1 + infl) ** t)


def _winter_dpw(first_season: int) -> float:
    """Ex-ante $/WAR level for the first projected season, from the
    committed signings-implied series (last prior winter escalated)."""
    try:
        series = json.loads((DATA_DIR / "fa_dpw_series.json").read_text(encoding="utf-8"))
        by = {int(k): float(v) for k, v in series["usd_per_war_by_winter"].items()}
    except (OSError, ValueError, KeyError):
        return fa_class._flat_dpw_usd()
    return fm.winter_dpw(by, first_season)


# ============================================================================
# Veterans — the FA engine over the whole league
# ============================================================================

def _veteran_rows(corpus: dict, names: dict[int, str],
                  contracts: dict[str, dict], dpw: float) -> list[dict]:
    league = corpus["league"]
    curves, war_map = fp.fitted_models(corpus, FIRST_SEASON - 1)
    frac = fp.season_fraction(league, FIRST_SEASON - 1)
    in_prog = (FIRST_SEASON - 1, frac)
    r = float(vf._config()["discount_rate"])

    by_player: dict[str, dict[int, dict[int, dict]]] = {
        "hit": defaultdict(dict), "pit": defaultdict(dict)}
    for side in ("hit", "pit"):
        for row in corpus[side]:
            if row.get("mlbam") and row["season"] >= FIRST_SEASON - 3:
                by_player[side][row["mlbam"]][row["season"]] = row

    out: list[dict] = []
    for mlbam in set(by_player["hit"]) | set(by_player["pit"]):
        sides = {}
        for side, expo_key, floor in (("hit", "pa", MIN_PA), ("pit", "bf", 0)):
            seasons = by_player[side].get(mlbam) or {}
            hist = [seasons[t] for t in (FIRST_SEASON - 1, FIRST_SEASON - 2,
                                         FIRST_SEASON - 3) if t in seasons]
            if not hist:
                continue
            if side == "hit":
                if max(h.get("pa") or 0 for h in hist) < MIN_PA:
                    continue
            elif max(h.get("ip") or 0 for h in hist) < MIN_IP:
                continue
            sides[side] = hist
        if not sides:
            continue
        # Two-way: project the larger recent exposure, disclose the cut.
        if len(sides) == 2:
            pa = max(h.get("pa") or 0 for h in sides["hit"])
            ip = max(h.get("ip") or 0 for h in sides["pit"])
            side = "hit" if pa >= ip * 4.3 else "pit"
            two_way = True
        else:
            side, two_way = next(iter(sides)), False
        hist = sides[side]
        age_prev = next((h.get("age") for h in hist if h.get("age")), None)
        if age_prev is None:
            continue
        age = age_prev + (FIRST_SEASON - hist[0]["season"])
        path = fm.contract_war_path(hist, side, FIRST_SEASON, HORIZON, age,
                                    curves, war_map, league, in_progress=in_prog)
        if path is None:
            continue
        name = names.get(mlbam)
        if not name:
            continue
        ct = contracts.get(normalize_key(name))
        m = {
            "key": normalize_key(name), "name": name, "age": age,
            "src": "vet", "twoWay": True if two_way else None,
            "pos": (ct or {}).get("position") or path["role"],
            "team": (ct or {}).get("team_code"),
            "war": path["war_by_year"][:HORIZON],
            "warP10": (path.get("war_by_year_p10") or [None])[:HORIZON] or None,
            "warP90": (path.get("war_by_year_p90") or [None])[:HORIZON] or None,
        }
        m["warTotal"] = round(sum(m["war"]), 1)
        if path.get("war_by_year_p10"):
            m["warTotalP10"] = round(sum(path["war_by_year_p10"][:HORIZON]), 1)
            m["warTotalP90"] = round(sum(path["war_by_year_p90"][:HORIZON]), 1)
        if ct:
            sal = {int(y): int(v) for y, v in (ct.get("salary_by_year") or {}).items()}
            m["thru"] = ct.get("signed_through")
            m["aav"] = ct.get("aav_usd")
            sur = []
            npv = 0.0
            any_sal = False
            for t in range(HORIZON):
                season = FIRST_SEASON + t
                s_usd = sal.get(season)
                if s_usd is None:
                    sur.append(None)
                    continue
                any_sal = True
                v_usd = _season_value_usd(m["war"][t], t, dpw)
                d_usd = v_usd - s_usd
                sur.append(round(d_usd / 1e6, 1))
                npv += d_usd / ((1 + r) ** t)
            if any_sal:
                m["sur"] = sur
                m["surNpv"] = int(npv)
        out.append(_clean(m))
    out.sort(key=lambda m: -(m.get("warTotal") or 0))
    return out


# ============================================================================
# Prospects — the calibrated FV outcome model, post-ETA
# ============================================================================

def _prospect_rows(dpw: float) -> list[dict]:
    try:
        players = json.loads((DATA_DIR / "timeseries.json")
                             .read_text(encoding="utf-8")).get("players") or []
    except (OSError, ValueError):
        log.warning("mlb projections: timeseries.json unavailable — no prospects")
        return []
    out: list[dict] = []
    for p in players:
        fv = p.get("fv_close")
        eta = (p.get("eta") or {}).get("year")
        if (fv is None or fv < 45 or not eta or p.get("status") != "active"
                or eta > FIRST_SEASON + HORIZON - 1):
            continue
        pos = p.get("position")
        is_pit = vf.is_pitcher_position(pos)
        reliever = vf.is_reliever_position(pos)
        role = vf._role_key(is_pit)
        probs = vf.p_bucket_given_fv(float(fv), is_pit)
        if not probs:
            continue
        age = p.get("age")
        debut_age = (float(age) + max(0, int(eta) - (FIRST_SEASON - 1))) if age else None
        scale = vf._war_scale_for(float(fv), role)
        paths = [vf._bucket_season_wars(role, i, reliever, debut_age, scale)
                 for i in range(len(_BUCKET_ORDER))]
        n_yrs = len(paths[0])
        mean_path = [round(sum(pr * paths[i][t] for i, pr in enumerate(probs)), 2)
                     for t in range(n_yrs)]

        def _q_bucket(q: float) -> int:
            cum = 0.0
            for i, pr in enumerate(probs):
                cum += pr
                if cum >= q:
                    return i
            return len(probs) - 1

        lo_b, hi_b = _q_bucket(0.10), _q_bucket(0.90)
        eta_yr = max(int(eta), FIRST_SEASON)
        sv = vf.surplus_value_mm(float(fv), is_pit, pos, age=age,
                                 eta_years=max(0.0, eta_yr - (FIRST_SEASON - 1)))
        out.append(_clean({
            "key": p.get("player_key"), "name": p.get("player_name"),
            "age": age, "src": "prospect", "fv": fv, "eta": eta_yr,
            "pos": pos, "team": p.get("org"),
            "war": [round(w, 2) for w in mean_path],
            "warP10": [round(w, 2) for w in paths[lo_b]],
            "warP90": [round(w, 2) for w in paths[hi_b]],
            "warTotal": round(sum(mean_path), 1),
            "warTotalP10": round(sum(paths[lo_b]), 1),
            "warTotalP90": round(sum(paths[hi_b]), 1),
            "bucketLo": _BUCKET_ORDER[lo_b], "bucketHi": _BUCKET_ORDER[hi_b],
            "pBust": round(probs[0], 3),
            "surNpv": int(sv * 1e6) if sv is not None else None,
        }))
    out.sort(key=lambda m: -(m.get("warTotal") or 0))
    return out


# ============================================================================
# Payload
# ============================================================================

def build_payload() -> dict:
    corpus = fp.build_corpus()
    names = _display_names()
    from spotrac import scrape_all_spotrac_contracts, build_contracts_by_key, _SPOTRAC_TEAM_SLUGS
    slug_to_org = {slug: code for code, slug in _SPOTRAC_TEAM_SLUGS.items()}
    contracts = {}
    for key, c in build_contracts_by_key(scrape_all_spotrac_contracts()).items():
        contracts[key] = {**c, "team_code": slug_to_org.get(c.get("team_slug"))}
    dpw = _winter_dpw(FIRST_SEASON)
    vets = _veteran_rows(corpus, names, contracts, dpw)
    prospects = _prospect_rows(dpw)
    cfg = vf._config()
    re_anchor = (cfg["dollars_per_war"].get("_fa_reanchor") or {})
    return {
        "generated_at": date.today().isoformat(),
        "first_season": FIRST_SEASON, "horizon": HORIZON,
        "dpw_usd": int(dpw),
        "dpw_infl": float(cfg.get("dollars_per_war_inflation", 0.05)),
        "dpw_reanchor": re_anchor or None,
        "n_vets": len(vets), "n_prospects": len(prospects),
        "vets": vets, "prospects": prospects,
        "notes": [
            "veterans: the FA module's Gate-1-validated Marcel engine; bands = Gate-1 empirical year-1 residual quantiles decayed along the fitted aging curves",
            "prospects: P(bucket|FV) x calibrated per-bucket WAR trajectories from projected debut age, starting at the PROSPX ETA; floor/ceiling = 10th/90th-percentile OUTCOME buckets",
            f"dollars: convex tier pricing at the {FIRST_SEASON} ex-ante FA $/WAR level, escalated per season; veteran surplus only on salary-known (contracted) seasons, discounted at the platform rate",
            "two-way players project on their larger recent exposure (disclosed)",
            f"veteran universe: >= {MIN_PA} PA or >= {MIN_IP} IP in one of the last three seasons",
        ],
    }


def export() -> int:
    payload = build_payload()
    raw = json.dumps(payload, separators=(",", ":"))
    (DATA_DIR / "mlb_projections.json").write_text(raw, encoding="utf-8")
    log.info("mlb projections export: %dKB, %d vets + %d prospects",
             len(raw) // 1024, payload["n_vets"], payload["n_prospects"])
    return len(raw)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print(export())
