# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""REM+ (Reliever Evaluation Metric +) - the model core.

REM+ is a ratio-to-league rate index (100 = the average reliever, 110 = 10%
better at run prevention), the ERA+/wRC+ family, NOT a z-score. The headline
number is PURE SKILL: a sample-shrunk, reliever-pool-anchored FIP built from the
components that stabilize fastest for relievers (K%, BB%, HBP, a heavily
regressed HR rate). Leverage (gmLI / WPA / WPA-LI / SD-MD) rides SEPARATE Impact
columns and never moves the talent number - the two-number design the research
settled on (the most recent and rigorous sources, Rosen 2026 + the FanGraphs
library, treat leverage as a deployment/price layer, not repeatable skill; Moore
2011 shows reliever gmLI tracks salary, not merit).

Design notes (all validated / to be validated in tools/rem_plus_backtest.py):
  - v1 anchors on FIP, not xFIP: FIP needs only K/BB/HBP/HR/IP (all in the
    season statline), while xFIP needs a fly-ball walk of the play feed. xFIP is
    a v2 follow-up.
  - HR is heavily regressed toward the pool HR rate (HR stabilizes very slowly),
    which is the small-sample blow-up guard and pulls FIP toward xFIP behavior
    without needing fly-ball data.
  - Empirical-Bayes shrink recipe: rate_adj = (n*rate + K*mean)/(n+K), matching
    storage.py / the RPS+ calibration. K constants are the published reliever
    stabilization points (K% ~70 BF, BB% ~170 BF).
  - The pool mean is re-normalized over RELIEVERS only, so 100 = average
    reliever (not average pitcher).

This module is PURE (no network, no I/O). mlb_leverage.py supplies the leverage
fields; bullpen_export.py assembles inputs, calls score_pool(), and writes the
sidecar. Every threshold here is a module constant so the backtest can tune it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

# ---- shrinkage constants (batters faced, unless noted) ---------------------- #
K_STRIKEOUT = 70.0      # K% stabilizes ~70 BF (Carleton / FanGraphs sample-size)
K_WALK = 170.0          # BB% ~170 BF
K_HBP = 170.0           # HBP: treat like the walk term
K_HOMERUN = 400.0       # HR stabilizes very slowly - regress hard (xFIP-like guard)

# FIP linear weights (the standard constants).
FIP_HR, FIP_BBHBP, FIP_K = 13.0, 3.0, 2.0

# ---- reliever population + tiering ------------------------------------------ #
# "True reliever" (owner: Standard): no real starting role, mostly relief work.
POOL_MIN_TBF = 50.0     # minimum sample to CONTRIBUTE to the league anchor
QUALIFY_MIN_TBF = 100.0  # leaderboard-qualified threshold (backtest-tunable)
QUALIFY_MIN_IP = 20.0
QUALIFY_MIN_G = 20
MAX_START_SHARE = 0.10  # GS/G at or below this still counts as a reliever

# ---- RIV+ (Reliever Impact Value) ------------------------------------------- #
# The SEPARATE realized-VALUE companion to REM+ (skill). RIV+ is a 100-anchored
# standardized index of the leverage-weighted value a reliever actually produced:
# WPA-primary (win probability added ALREADY encodes the leverage he was given),
# with a lower-variance shutdowns-minus-meltdowns overlay. It is a deployment /
# value number, NOT a repeatable-skill number - by design it is less stable year
# to year than REM+ (validated X-R3: riv_plus Y->Y+1 rho 0.209 vs REM+ 0.352),
# which is exactly why leverage stays OUT of the REM+ talent scale and rides here
# instead. gmLI is shown as context, never added as free credit for being handed
# leverage. (data/riv_plus_eval.json is the accountability artifact.)
RIV_W_WPA = 0.70        # WPA is the primary realized-value signal
RIV_W_SDMD = 0.30       # SD-MD: a lower-variance consistency overlay
RIV_SCALE = 10.0        # 100 + SCALE*z (the "+"-family standardized index)

# ---- gmLI role bands (FanGraphs LI bands + PitcherList taxonomy) ------------ #
ROLE_ORDER = ["Closer", "High-leverage", "Setup", "Middle", "Long", "Mop-up"]
GMLI_HIGH = 1.50
GMLI_SETUP = 1.15
GMLI_MIDDLE = 0.85
LONG_IP_PER_G = 1.6     # multi-inning workload marks a long reliever
CLOSER_MIN_SV = 3


def _safe_div(a: Optional[float], b: Optional[float]) -> Optional[float]:
    a = _num(a); b = _num(b)
    if a is None or b is None or b == 0:
        return None
    return a / b


def _num(v) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return f


def _shrink(rate: Optional[float], n: Optional[float], k: float,
            pool_mean: float) -> float:
    """Empirical-Bayes shrink toward the reliever-pool mean by sample size."""
    r = _num(rate)
    nn = _num(n) or 0.0
    if r is None:
        return pool_mean
    return (nn * r + k * pool_mean) / (nn + k)


@dataclass
class Reliever:
    """One reliever-season. Counts are season totals; leverage fields optional
    (filled by mlb_leverage.py). Rates are derived in derive_rates()."""
    key: str
    name: str = ""
    team: str = ""
    mlbam: Optional[int] = None
    g: float = 0.0
    gs: float = 0.0
    ip: float = 0.0
    tbf: float = 0.0
    so: float = 0.0
    bb: float = 0.0
    hbp: float = 0.0
    hr: float = 0.0
    er: float = 0.0
    r: float = 0.0          # total runs allowed (for RA9)
    pit: float = 0.0        # pitches (for SwStr%)
    sts: Optional[float] = None   # swinging strikes; None = no bref enrichment (swstr_pct -> null)
    sv: float = 0.0
    hld: float = 0.0
    # leverage / context (optional, from the winProbability walk)
    gmli: Optional[float] = None
    wpa: Optional[float] = None
    wpa_li: Optional[float] = None
    sd: Optional[float] = None
    md: Optional[float] = None
    entry_inning: Optional[float] = None   # median entry inning (opener detection)
    # computed
    rates: dict = field(default_factory=dict)
    fip_skill: Optional[float] = None
    rem_plus: Optional[int] = None
    rem_plus_raw: Optional[float] = None
    riv_plus: Optional[int] = None          # realized-impact index (separate from skill)
    riv_plus_raw: Optional[float] = None
    role: str = ""
    qualified: bool = False


def is_true_reliever(r: Reliever) -> bool:
    """No real starting role and (mostly) relief innings. Openers are dropped in
    score_pool() once entry-inning data exists; the season-agg filter here keys
    on the start share."""
    if r.ip <= 0 or r.g <= 0:
        return False
    if r.gs <= 0:
        return True
    return (r.gs / r.g) <= MAX_START_SHARE


def _is_opener(r: Reliever) -> bool:
    """Opener heuristic: enters the 1st inning on most appearances and throws
    short stints. Only fires when entry-inning data is present."""
    if r.entry_inning is None:
        return False
    ip_per_g = _safe_div(r.ip, r.g) or 0.0
    return r.entry_inning <= 1.2 and ip_per_g <= 1.5 and r.gs == 0


def derive_rates(r: Reliever) -> None:
    r.rates = {
        "k_pct": _safe_div(r.so, r.tbf),
        "bb_pct": _safe_div(r.bb, r.tbf),
        "hbp_pct": _safe_div(r.hbp, r.tbf),
        "hr_rate": _safe_div(r.hr, r.tbf),
        "swstr_pct": _safe_div(r.sts, r.pit),
        "k_bb_pct": (None if _safe_div(r.so, r.tbf) is None or _safe_div(r.bb, r.tbf) is None
                     else _safe_div(r.so, r.tbf) - _safe_div(r.bb, r.tbf)),
        "era": _safe_div((r.er or 0.0) * 9.0, r.ip),
        "ra9": _safe_div((r.r or 0.0) * 9.0, r.ip),
    }


@dataclass
class Pool:
    n: int = 0
    mean_k_pct: float = 0.20
    mean_bb_pct: float = 0.085
    mean_hbp_pct: float = 0.010
    mean_hr_rate: float = 0.028
    pool_era: float = 4.20
    cfip: float = 3.10
    mean_fip: float = 4.20


def build_pool(relievers: Iterable[Reliever]) -> Pool:
    """League-reliever means (over pool-contributing arms) + the FIP constant."""
    pool_rel = [r for r in relievers if r.tbf >= POOL_MIN_TBF and r.ip > 0]
    if not pool_rel:
        return Pool()
    tbf = sum(r.tbf for r in pool_rel)
    ip = sum(r.ip for r in pool_rel)
    er = sum((r.er or 0.0) for r in pool_rel)
    so = sum(r.so for r in pool_rel)
    bb = sum(r.bb for r in pool_rel)
    hbp = sum(r.hbp for r in pool_rel)
    hr = sum(r.hr for r in pool_rel)

    p = Pool()
    p.n = len(pool_rel)
    p.mean_k_pct = so / tbf
    p.mean_bb_pct = bb / tbf
    p.mean_hbp_pct = hbp / tbf
    p.mean_hr_rate = hr / tbf
    p.pool_era = er * 9.0 / ip
    # FIP constant so the raw (unshrunk) pool FIP equals the pool ERA.
    raw_fip = (FIP_HR * hr + FIP_BBHBP * (bb + hbp) - FIP_K * so) / ip
    p.cfip = p.pool_era - raw_fip
    # Anchor REM+ to the IP-weighted mean of the SHRUNK skill FIP, so the pool
    # average scores exactly 100 by construction.
    num = 0.0
    den = 0.0
    for r in pool_rel:
        f = fip_skill(r, p)
        if f is not None:
            num += f * r.ip
            den += r.ip
    p.mean_fip = (num / den) if den else p.pool_era
    return p


def fip_skill(r: Reliever, pool: Pool) -> Optional[float]:
    """Sample-shrunk FIP (ERA scale, lower = better). Component rates are
    regressed toward the reliever pool by sample size, then converted back to
    expected counts over the pitcher's actual innings."""
    if r.ip <= 0 or r.tbf <= 0:
        return None
    if not r.rates:
        derive_rates(r)
    k = _shrink(r.rates["k_pct"], r.tbf, K_STRIKEOUT, pool.mean_k_pct)
    bb = _shrink(r.rates["bb_pct"], r.tbf, K_WALK, pool.mean_bb_pct)
    hbp = _shrink(r.rates["hbp_pct"], r.tbf, K_HBP, pool.mean_hbp_pct)
    hr = _shrink(r.rates["hr_rate"], r.tbf, K_HOMERUN, pool.mean_hr_rate)
    # expected counts at the shrunk rates over this pitcher's batters faced
    k_c, bb_c, hbp_c, hr_c = k * r.tbf, bb * r.tbf, hbp * r.tbf, hr * r.tbf
    fip = (FIP_HR * hr_c + FIP_BBHBP * (bb_c + hbp_c) - FIP_K * k_c) / r.ip + pool.cfip
    # floor guards against a degenerate tiny-denominator blow-up
    return max(fip, 1.0)


def rem_plus(r: Reliever, pool: Pool) -> Optional[int]:
    """100 * pool_mean_FIP / player_FIP, rounded to nearest int (the +stat
    convention). Higher = better; 110 = 10% better run prevention than average."""
    f = fip_skill(r, pool)
    if f is None or f <= 0:
        return None
    raw = 100.0 * pool.mean_fip / f
    r.fip_skill = f
    r.rem_plus_raw = raw
    r.rem_plus = int(round(raw))
    return r.rem_plus


def _mean_std(xs) -> tuple:
    xs = [x for x in xs if x is not None]
    if len(xs) < 2:
        return (None, None)
    mu = sum(xs) / len(xs)
    sd = (sum((x - mu) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5
    return (mu, sd)


def score_riv_plus(relievers: list[Reliever]) -> None:
    """Stamp RIV+ (realized-impact index) onto each reliever, in place. Pool-
    standardized WPA-primary composite: 100 + RIV_SCALE * z, where z is the
    weighted average of the standardized WPA and standardized SD-MD (weights
    renormalized when only one is present). Only relievers with WPA get a value
    (leverage feed present); the rest stay None and render blank. Standardized
    over the arms with WPA in THIS pool so 100 = average deployed value."""
    arms = [r for r in relievers if _num(r.wpa) is not None]
    if len(arms) < 10:
        return
    mu_w, sd_w = _mean_std([r.wpa for r in arms])
    mu_s, sd_s = _mean_std([((r.sd or 0.0) - (r.md or 0.0)) for r in arms])
    for r in arms:
        parts = []
        if sd_w:
            parts.append((RIV_W_WPA, (r.wpa - mu_w) / sd_w))
        if sd_s:
            parts.append((RIV_W_SDMD, (((r.sd or 0.0) - (r.md or 0.0)) - mu_s) / sd_s))
        if not parts:
            continue
        z = sum(w * v for w, v in parts) / sum(w for w, _ in parts)
        r.riv_plus_raw = z
        r.riv_plus = int(round(100.0 + RIV_SCALE * z))


def assign_roles(team_relievers: list[Reliever]) -> None:
    """Bucket a team's relievers into the gmLI leverage ladder. Closer is the
    team's save leader (fallback: highest gmLI); the rest key off gmLI, with a
    multi-inning workload marking a long reliever."""
    if not team_relievers:
        return
    closer = None
    saves = [(r.sv or 0.0, r) for r in team_relievers]
    top_sv, top_r = max(saves, key=lambda t: t[0])
    if top_sv >= CLOSER_MIN_SV:
        closer = top_r
    else:
        with_li = [r for r in team_relievers if r.gmli is not None]
        if with_li:
            closer = max(with_li, key=lambda r: r.gmli)
    for r in team_relievers:
        if r is closer:
            r.role = "Closer"
            continue
        gmli = r.gmli
        ip_per_g = _safe_div(r.ip, r.g) or 0.0
        if gmli is None:
            r.role = "Long" if ip_per_g >= LONG_IP_PER_G else "Middle"
        elif gmli >= GMLI_HIGH:
            r.role = "High-leverage"
        elif gmli >= GMLI_SETUP:
            r.role = "Setup"
        elif gmli >= GMLI_MIDDLE:
            r.role = "Middle"
        elif ip_per_g >= LONG_IP_PER_G:
            r.role = "Long"
        else:
            r.role = "Mop-up"


def _role_rank(role: str) -> int:
    try:
        return ROLE_ORDER.index(role)
    except ValueError:
        return len(ROLE_ORDER)


def team_bullpen(team: str, relievers: list[Reliever]) -> dict:
    """Team bullpen aggregates. Bullpen+ is RELIEF-IP-weighted REM+ (talent of
    the innings thrown), keeping leverage OUT of the quality number - the same
    two-number philosophy as REM+. leverage_deploy_plus is the IP*gmLI-weighted
    companion (how much leverage those innings carried)."""
    scored = [r for r in relievers if r.rem_plus is not None and r.ip > 0]
    out = {"team": team, "n_relievers": len(scored)}
    if not scored:
        return out

    def _wmean(weight_fn) -> Optional[float]:
        num = den = 0.0
        for r in scored:
            w = weight_fn(r)
            if w and w > 0:
                num += r.rem_plus * w
                den += w
        return (num / den) if den else None

    bp = _wmean(lambda r: r.ip)
    ld = _wmean(lambda r: r.ip * (r.gmli if r.gmli is not None else 1.0))
    out["bullpen_plus"] = None if bp is None else int(round(bp))
    out["bullpen_plus_raw"] = bp
    out["leverage_deploy_plus"] = None if ld is None else int(round(ld))
    out["relief_ip"] = round(sum(r.ip for r in scored), 1)
    out["n_above_avg"] = sum(1 for r in scored if r.rem_plus >= 100)
    out["team_wpa"] = _sum_opt(r.wpa for r in scored)
    out["sd"] = _sum_opt(r.sd for r in scored)
    out["md"] = _sum_opt(r.md for r in scored)
    # high-leverage core = mean REM+ of the top-3 arms by gmLI
    by_li = sorted([r for r in scored if r.gmli is not None],
                   key=lambda r: r.gmli, reverse=True)[:3]
    core = by_li or sorted(scored, key=lambda r: r.rem_plus, reverse=True)[:3]
    out["high_lev_core_rem"] = int(round(sum(r.rem_plus for r in core) / len(core))) if core else None
    # depth ladder, ordered by role then gmLI
    ladder = sorted(scored, key=lambda r: (_role_rank(r.role), -(r.gmli or 0.0)))
    out["depth"] = [{"role": r.role, "key": r.key, "name": r.name,
                     "rem_plus": r.rem_plus, "gmli": _round(r.gmli, 2), "ip": round(r.ip, 1)}
                    for r in ladder]
    return out


def _sum_opt(vals) -> Optional[float]:
    xs = [_num(v) for v in vals]
    xs = [v for v in xs if v is not None]
    return round(sum(xs), 2) if xs else None


def _round(v, n):
    v = _num(v)
    return None if v is None else round(v, n)


def score_pool(relievers: list[Reliever]) -> dict:
    """End to end: filter to true relievers, derive rates, build the pool, score
    REM+, assign roles per team, and roll up team bullpens. Returns a dict with
    'relievers', 'teams', and a 'pool' summary. Pure - callers supply the data."""
    pool_input = [r for r in relievers if is_true_reliever(r) and not _is_opener(r)]
    for r in pool_input:
        derive_rates(r)
    pool = build_pool(pool_input)
    for r in pool_input:
        rem_plus(r, pool)
        r.qualified = (r.tbf >= QUALIFY_MIN_TBF) or (r.ip >= QUALIFY_MIN_IP and r.g >= QUALIFY_MIN_G)
    # RIV+ realized-impact index, standardized over the scored pool (separate
    # from the REM+ skill scale; only arms with a leverage feed get a value).
    score_riv_plus([r for r in pool_input if r.rem_plus is not None])

    # roles + team rollups
    by_team: dict[str, list[Reliever]] = {}
    for r in pool_input:
        by_team.setdefault(r.team or "", []).append(r)
    teams = []
    for team, tr in by_team.items():
        assign_roles(tr)
        if team:
            teams.append(team_bullpen(team, tr))
    teams.sort(key=lambda t: (t.get("bullpen_plus") or -999), reverse=True)

    scored = [r for r in pool_input if r.rem_plus is not None]
    scored.sort(key=lambda r: (r.rem_plus, r.rem_plus_raw or 0), reverse=True)
    return {
        "relievers": [reliever_row(r) for r in scored],
        "teams": teams,
        "pool": {"n": pool.n, "pool_era": round(pool.pool_era, 2),
                 "mean_fip": round(pool.mean_fip, 2),
                 "n_qualified": sum(1 for r in scored if r.qualified),
                 "n_provisional": sum(1 for r in scored if not r.qualified)},
    }


def reliever_row(r: Reliever) -> dict:
    """The per-reliever record the frontend/export consumes."""
    return {
        "key": r.key, "mlbam": r.mlbam, "name": r.name, "team": r.team,
        "rem_plus": r.rem_plus, "rem_plus_raw": _round(r.rem_plus_raw, 1),
        "riv_plus": r.riv_plus, "riv_plus_raw": _round(r.riv_plus_raw, 2),
        "qualified": r.qualified, "role": r.role,
        "ip": round(r.ip, 1), "g": int(r.g), "tbf": int(r.tbf),
        "k_pct": _round(r.rates.get("k_pct"), 4),
        "bb_pct": _round(r.rates.get("bb_pct"), 4),
        "k_bb_pct": _round(r.rates.get("k_bb_pct"), 4),
        "fip": _round(r.fip_skill, 2),
        "swstr_pct": _round(r.rates.get("swstr_pct"), 4),
        "era": _round(r.rates.get("era"), 2),
        "hr9": _round(_safe_div((r.hr or 0.0) * 9.0, r.ip), 2),
        "gmli": _round(r.gmli, 2), "wpa": _round(r.wpa, 2),
        "wpa_li": _round(r.wpa_li, 2),
        "sd": None if r.sd is None else int(r.sd),
        "md": None if r.md is None else int(r.md),
        "saves": int(r.sv or 0), "holds": int(r.hld or 0),
    }
