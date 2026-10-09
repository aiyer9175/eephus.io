"""aging_v3: the one aging service, built dark (docs/AGING_V3_GATE.md; task
AG_5_AGING_SERVICE_BUILD_DARK). Fixtures only: a synthetic corpus and sidecar.
No arm is scored against an outcome here; the real corpus is not read.

Pins: the registered bucket map; the shrinkage weights n / (n + k); the
out-of-window archetype raise; shape() mean 1.0 (the window mean is unchanged);
factor() follows level(); PT never above the cap under ARM T; the health
recentring keeps each season's projected exposure sum within 1e-9;
component_curve equals the v2 component curves under every arm (so
data/mlb_projections.json woba and rates_by_year cannot move); the no-arm
service reproduces v2 exactly; AGING_V3_VERSION recomputes from the fit source;
the consumer flags all read false.
"""
from __future__ import annotations

import inspect
import math
import random
import re
from pathlib import Path

import pytest

import aging_v3 as A
import fa_projection as fp

ROOT = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

def _league(season: int) -> dict:
    return {"season": season, "_total_pa": 180000.0, "woba": 0.315, "r_pa": 0.115,
            "k_pct": 0.22, "bb_pct": 0.085, "iso": 0.16, "babip": 0.295, "hr_pa": 0.032,
            "fip_constant": 3.15, "era": 4.1, "p_k_pct": 0.22, "p_bb_pct": 0.085,
            "p_hr_bf": 0.032, "lg_fip": 4.1}


def make_corpus(seed: int = 7, n_hit: int = 260, n_pit: int = 240,
                first: int = 2000, last: int = 2015) -> dict:
    """A synthetic corpus: careers of 3 to 12 seasons, debut ages 21 to 28,
    a rate that rises to 27 and falls after, exposure that grows then fades,
    attrition at the bottom. Deterministic."""
    rng = random.Random(seed)
    hit, pit = [], []
    positions = ["C", "SS", "2B", "3B", "CF", "LF", "RF", "1B", "DH", "X"]
    mlbam = 100000
    for side, n in (("hit", n_hit), ("pit", n_pit)):
        for _ in range(n):
            mlbam += 1
            debut = rng.randint(first, last - 3)
            age0 = rng.randint(21, 28)
            years = rng.randint(3, 12)
            talent = rng.gauss(2.0, 1.4)
            pos = rng.choice(positions) if side == "hit" else None
            role = ("C" if pos == "C" else "H") if side == "hit" else rng.choice(["SP", "SP", "RP"])
            expo = rng.uniform(250, 650) if side == "hit" else (rng.uniform(400, 900) if role == "SP" else rng.uniform(150, 320))
            for k in range(years):
                s, a = debut + k, age0 + k
                if s > last:
                    break
                peak = 27 if side == "hit" else 26
                shape = 1.0 - 0.035 * abs(a - peak) + rng.gauss(0, 0.25)
                expo = max(60.0, expo * rng.uniform(0.85, 1.15) * (1.03 if a < peak else 0.97))
                if side == "hit":
                    war = (talent * shape) * expo / 600.0
                    hit.append({"mlbam": mlbam, "season": s, "age": a, "role": role, "pa": round(expo, 0),
                                "k_pct": max(0.05, rng.gauss(0.22, 0.05)), "bb_pct": max(0.02, rng.gauss(0.085, 0.025)),
                                "iso": max(0.03, rng.gauss(0.16, 0.05)), "babip": rng.gauss(0.295, 0.03),
                                "hr_pa": max(0.0, rng.gauss(0.032, 0.012)), "war": round(war, 2),
                                "war_total": round(war, 2), "_pos": pos})
                else:
                    war = (talent * shape) * expo / 250.0 * 0.6
                    pit.append({"mlbam": mlbam, "season": s, "age": a, "role": role, "bf": round(expo, 0),
                                "ip": round(expo / 4.3, 1), "k_pct": max(0.05, rng.gauss(0.22, 0.06)),
                                "bb_pct": max(0.02, rng.gauss(0.085, 0.025)), "hr_bf": max(0.0, rng.gauss(0.032, 0.01)),
                                "war": round(war, 2), "war_total": round(war, 2),
                                "fip": rng.gauss(4.1, 0.8)})
    league = {s: _league(s) for s in range(first, last + 1)}
    return {"hit": hit, "pit": pit, "league": league, "first": first, "last": last,
            "war_provider": "fwar", "label_shape": fp.LABEL_SHAPE}


def make_sidecar(corpus: dict, seed: int = 11) -> dict:
    """A synthetic sidecar: the row's position, run parts, innings and IL
    features; TJ years for a few pitchers."""
    rng = random.Random(seed)
    rows = {}
    for r in corpus["hit"]:
        rows[(r["mlbam"], r["season"])] = {
            "pos": r.get("_pos"), "two_way": False, "pa": r["pa"], "sb": 0.0, "cs": 0.0,
            "go": 0.0, "ao": 0.0, "bat": rng.gauss(0, 10), "bsr": rng.gauss(0, 3),
            "fld": rng.gauss(0, 6), "inn": r["pa"] * 1.4,
            "il_days": float(rng.choice([0, 0, 0, 12, 30, 65])), "il_stints": rng.choice([0, 0, 1, 2]),
            "il60": rng.choice([0, 0, 0, 1])}
    for r in corpus["pit"]:
        rows[(r["mlbam"], r["season"])] = {
            "pos": "P", "two_way": False, "gs": 20.0 if r["role"] == "SP" else 0.0, "g": 30.0,
            "ip": r["ip"], "bf": r["bf"], "bat": None, "bsr": None, "fld": None, "inn": None,
            "il_days": float(rng.choice([0, 0, 15, 45, 120])), "il_stints": rng.choice([0, 0, 1, 1, 2]),
            "il60": rng.choice([0, 0, 0, 1])}
    tj = {r["mlbam"]: [r["season"] - 1] for r in corpus["pit"][::37]}
    return {"rows": rows, "tj": tj, "meta": {"sig": "fixture", "il_coverage": list(range(2000, 2016))}}


@pytest.fixture(scope="module")
def corpus():
    return make_corpus()


@pytest.fixture(scope="module")
def sidecar(corpus):
    return make_sidecar(corpus)


def cfg_with(**arms) -> dict:
    cfg = A.default_config()
    for a, v in arms.items():
        if a in A.ARMS:
            cfg["arms"][a] = bool(v)
        else:
            cfg[a] = v
    return cfg


ALL_ARMS = [cfg_with(), cfg_with(T=True), cfg_with(S=True), cfg_with(P=True), cfg_with(R=True),
            cfg_with(T=True, S=True, P=True, R=True)]


# ---------------------------------------------------------------------------
# the bucket map
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("pos,is_pit,expect", [
    ("C", False, "C"), ("SS", False, "SS"), ("2B", False, "2B/3B"), ("3B", False, "2B/3B"),
    ("CF", False, "CF"), ("LF", False, "LF/RF"), ("RF", False, "LF/RF"), ("OF", False, "LF/RF"),
    ("1B", False, "1B"), ("DH", False, "DH"), ("C/1B", False, "C"), ("ss", False, "SS"),
    ("IF", False, None), ("UT", False, None), ("TWP", False, None), ("X", False, None),
    ("P", False, None), (None, False, None), ("", False, None),
    ("SP", True, "SP"), ("RP", True, "RP"), ("SIRP", True, "RP"), ("MIRP", True, "RP"),
    ("RHP", True, None), ("LHP", True, None), ("SS", True, None), ("SP", False, None),
])
def test_bucket_map(pos, is_pit, expect):
    assert A.bucket_from_position(pos, is_pit) == expect


def test_two_way_hitting_side_is_dh():
    assert A.bucket_from_position("TWP", False, two_way_hitting=True) == "DH"
    assert A.bucket_from_position("SP", False, two_way_hitting=True) == "DH"


def test_registered_bucket_set():
    assert A.HIT_BUCKETS == ("C", "SS", "2B/3B", "CF", "LF/RF", "1B", "DH")
    assert A.PIT_BUCKETS == ("SP", "RP")
    assert A.PARENT == {"hit": "HALL", "pit": "PALL"}
    assert A.HIT_ARCHETYPES == ("OLD_SKILLS", "YOUNG_SKILLS", "NEUTRAL")
    assert A.PIT_ARCHETYPES == ("POWER", "COMMAND", "NEUTRAL")


def test_arm_p_assigns_every_fit_row_a_bucket_or_the_pooled_parent(corpus, sidecar):
    m = A.fit(corpus, 2014, cfg_with(P=True), sidecar=sidecar)
    hit_cells = set(m.cells["hit"])
    assert "HALL" in hit_cells and "PALL" in set(m.cells["pit"])
    assert hit_cells - {"HALL"} <= set(A.HIT_BUCKETS)
    assert set(m.cells["pit"]) - {"PALL"} <= set(A.PIT_BUCKETS)
    # a row whose position is X (Unknown) is assigned None: the pooled side curve
    unknown = [(r["mlbam"], r["season"]) for r in corpus["hit"] if r.get("_pos") == "X"][:5]
    assert unknown and all(m.assign["hit"]["bucket"][k] is None for k in unknown)
    assert m.rate_delta("hit", "war_rate", 30, bucket=None) == m.rate_delta("hit", "war_rate", 30, bucket="IF")


# ---------------------------------------------------------------------------
# shrinkage
# ---------------------------------------------------------------------------

def test_shrinkage_weight_is_n_over_n_plus_k():
    parent = {30: {"delta": 0.10, "raw": 0.1, "n": 500, "attrition": 0.1, "w": 1.0},
              31: {"delta": -0.20, "raw": -0.2, "n": 500, "attrition": 0.1, "w": 1.0}}
    child = {30: {"delta": 0.50, "raw": 0.5, "n": 100, "attrition": 0.2, "w": 1.0}}
    out = A._shrink(child, parent, k=100.0)
    w = 100.0 / (100.0 + 100.0)
    assert out[30]["delta"] == pytest.approx(w * 0.50 + (1 - w) * 0.10, abs=1e-5)
    assert out[30]["w_shrink"] == pytest.approx(0.5)
    # an age the child lacks is the parent's value (w = 0)
    assert out[31]["delta"] == pytest.approx(-0.20) and out[31]["w_shrink"] == 0.0


def test_bucket_cells_shrink_toward_the_pooled_parent(corpus, sidecar):
    cfg = cfg_with(P=True)
    cfg["P"]["k"] = 10 ** 9                       # k so large every bucket IS its parent
    m = A.fit(corpus, 2014, cfg, sidecar=sidecar)
    for b in A.HIT_BUCKETS:
        if b not in m.cells["hit"]:
            continue
        for age in (24, 28, 33):
            assert m.rate_delta("hit", "war_rate", age, bucket=b) == pytest.approx(
                m.rate_delta("hit", "war_rate", age, bucket=None), abs=2e-5)
    cfg["P"]["k"] = 1e-9                          # k about zero: a bucket is its own raw cell
    m2 = A.fit(corpus, 2014, cfg, sidecar=sidecar)
    moved = sum(1 for b in A.HIT_BUCKETS if b in m2.cells["hit"]
                for age in (26, 30)
                if abs(m2.rate_delta("hit", "war_rate", age, bucket=b)
                       - m2.rate_delta("hit", "war_rate", age, bucket=None)) > 1e-4)
    assert moved > 0


# ---------------------------------------------------------------------------
# the out-of-window archetype rule
# ---------------------------------------------------------------------------

def test_archetype_window_containing_the_start_season_raises(corpus, sidecar):
    cfg = cfg_with(R=True)
    cfg["R"]["window"] = [-2, 0]
    with pytest.raises(ValueError, match="start season"):
        A.fit(corpus, 2014, cfg, sidecar=sidecar)
    cfg["R"]["window"] = [-3, 1]
    with pytest.raises(ValueError, match="start season"):
        A.normalize_config(cfg)
    with pytest.raises(ValueError):
        A.window_seasons(2010, {"R": {"window": [-1, 0]}})
    assert A.window_seasons(2010, A.default_config()) == [2007, 2008, 2009]


def test_arm_r_assignments_read_only_earlier_seasons(corpus, sidecar):
    m = A.fit(corpus, 2014, cfg_with(R=True), sidecar=sidecar)
    for side in ("hit", "pit"):
        arch = m.assign[side]["archetype"]
        assert arch and set(arch.values()) <= set(A.ARCHETYPES[side])
    # the serve rule: the archetype of a pair starting at B reads B-3..B-1
    some = next(iter(m.assign["hit"]["archetype"]))
    assert A.window_seasons(some[1], m.cfg) == [some[1] - 3, some[1] - 2, some[1] - 1]


# ---------------------------------------------------------------------------
# shape, level, factor
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cfg", ALL_ARMS)
def test_shape_mean_is_one_under_every_arm(corpus, sidecar, cfg):
    m = A.fit(corpus, 2014, cfg, sidecar=sidecar)
    for side, buckets in (("hit", (None, "C", "SS", "DH", "IF")), ("pit", (None, "SP", "RP"))):
        for debut in (19.0, 21.0, 23.5, 26.0, 30.0):
            for n in (6, 7):
                for reliever in (False, True):
                    s = m.shape(side, debut, n, bucket=buckets[0], reliever=reliever)
                    assert len(s) == n
                    assert sum(s) / n == pytest.approx(1.0, abs=1e-12)
                    assert all(v > 0 for v in s)
            for b in buckets:
                s = m.shape(side, debut, 7, bucket=b)
                assert sum(s) / 7 == pytest.approx(1.0, abs=1e-12)
    assert m.shape("hit", 22.0, 0) == []


def test_level_peaks_at_one_and_floors(corpus, sidecar):
    m = A.fit(corpus, 2014, cfg_with(P=True), sidecar=sidecar)
    for side in ("hit", "pit"):
        for b in (None,) + A.BUCKETS[side]:
            vals = [m.level(side, a, b) for a in range(18, 50)]
            assert max(vals) == pytest.approx(1.0)
            assert min(vals) >= A.MIN_MULTIPLIER - 1e-12
    assert A.MIN_MULTIPLIER == 0.25


@pytest.mark.parametrize("cfg", ALL_ARMS)
def test_factor_follows_level(corpus, sidecar, cfg):
    m = A.fit(corpus, 2014, cfg, sidecar=sidecar)
    for side in ("hit", "pit"):
        for b in (None,) + A.BUCKETS[side]:
            for age in (22.0, 25.0, 29.0, 34.0):
                for k in (0, 1, 3, 6):
                    assert m.factor(age, k, side, b) == pytest.approx(
                        m.level(side, age + k, b) / m.level(side, age, b))
    assert m.factor(None, 3, "hit") == 1.0
    assert m.factor(25.0, 0, "pit", "SP") == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# ARM T: the cap
# ---------------------------------------------------------------------------

def test_caps_are_the_99_5th_percentile_by_side_and_role(corpus):
    import numpy as np
    caps = A._caps(corpus, 2014)
    for side, ek in (("hit", "pa"), ("pit", "bf")):
        for role in (("C", "H") if side == "hit" else ("SP", "RP")):
            vals = [r[ek] for r in corpus[side] if r["season"] <= 2014
                    and A.base_role(side, None, r["role"]) == role and r[ek] > 0]
            assert caps[f"{side}:{role}"] == pytest.approx(np.percentile(vals, 99.5))
    assert A.CAP_PERCENTILE == 99.5


@pytest.mark.parametrize("cfg", [cfg_with(T=True), cfg_with(T=True, P=True), cfg_with(T=True, S=True, P=True, R=True)])
def test_pt_never_above_the_cap_under_arm_t(corpus, sidecar, cfg):
    m = A.fit(corpus, 2014, cfg, sidecar=sidecar)
    for side, roles in (("hit", ("C", "H")), ("pit", ("SP", "RP"))):
        for role in roles:
            cap = m.cap(side, role)
            assert cap is not None and cap > 0
            for pt_prev in (0.0, 50.0, 300.0, 480.0, cap, cap * 1.5, cap * 3):
                for age in range(20, 45):
                    for b in (None,) + A.BUCKETS[side]:
                        nxt = m.pt_next(side, role, pt_prev, age, bucket=b)
                        assert 0.0 <= nxt <= cap + 1e-9
    # tiers
    assert m.tier("hit", "H", 450.0) == "regular" and m.tier("hit", "H", 449.9) == "part"
    assert m.tier("pit", "SP", 500.0) == "regular" and m.tier("pit", "RP", 200.0) == "regular"
    assert m.tier("pit", "RP", 199.0) == "part"


def test_comparator_cap_is_call_scoped_and_off_by_default(corpus):
    cfg = cfg_with(); cfg["pt_cap"] = True
    m_cap = A.fit(corpus, 2014, cfg)
    m_off = A.fit(corpus, 2014, cfg_with())
    cap = m_cap.cap("hit", "H")
    assert m_off.pt_next("hit", "H", cap * 2, 27) > cap
    assert m_cap.pt_next("hit", "H", cap * 2, 27) <= cap
    assert m_off.meta["pt_cap"] is False and m_cap.meta["pt_cap"] is True
    assert A.config_hash(cfg) != A.config_hash(cfg_with())


# ---------------------------------------------------------------------------
# health: the recentring and the clip
# ---------------------------------------------------------------------------

def test_health_recentring_keeps_each_seasons_projected_exposure_sum(corpus, sidecar):
    rng = random.Random(3)
    for _ in range(25):
        n = rng.randint(5, 400)
        pts = [rng.uniform(50, 700) for _ in range(n)]
        mult = [min(1.05, max(0.80, math.exp(rng.gauss(0, 0.08)))) for _ in range(n)]
        out = A.recentre_health(pts, mult)
        assert abs(sum(p * m for p, m in zip(pts, out)) - sum(pts)) < 1e-9
    assert A.recentre_health([100.0, 200.0], [0.0, 0.0]) == [1.0, 1.0]


def test_health_multiplier_is_clipped_and_inert_until_gamma_exists(corpus, sidecar):
    cfg = cfg_with(); cfg["health"] = True
    m = A.fit(corpus, 2014, cfg, sidecar=sidecar)
    assert m.health["gamma"] is None
    assert m.health_multiplier([3.0, 3.0, 3.0, 3.0, 3.0]) == 1.0
    assert m.health["z"] and all(set(v) == set(A.HEALTH_FEATURES) for v in m.health["z"].values())
    m.health["gamma"] = [0.5, 0.0, 0.0, 0.0, 0.0]
    assert m.health_multiplier([4.0, 0, 0, 0, 0]) == 1.05
    assert m.health_multiplier([-4.0, 0, 0, 0, 0]) == 0.80
    assert m.health_multiplier([0.05, 0, 0, 0, 0]) == pytest.approx(math.exp(0.025))
    assert m.health_multiplier([0.1, 0, 0, 0, 0]) == 1.05        # exp(0.05) is above the clip
    assert m.health_multiplier(None) == 1.0
    off = A.fit(corpus, 2014, cfg_with(), sidecar=sidecar)
    off.health["gamma"] = [5.0, 0, 0, 0, 0]
    assert off.health_multiplier([4.0, 0, 0, 0, 0]) == 1.0     # the flag is off
    # the z tables are within season
    feats = m.health_features("pit", 28, sidecar["rows"], sidecar["tj"], corpus["pit"][40]["mlbam"],
                              corpus["pit"][40]["season"])
    assert feats is None or len(feats) == 5
    assert m.health_features("hit", 25, {}, {}, 1, 2010) is None
    g = m.fit_health_gamma([[1.0, 0, 0, 0, 0], [-1.0, 0, 0, 0, 0], [0.5, 0, 0, 0, 0]], [0.1, -0.1, 0.05])
    assert len(g) == 5 and g[0] > 0


# ---------------------------------------------------------------------------
# the component curves never move; the no-arm service IS v2
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cfg", ALL_ARMS)
def test_component_curves_equal_v2_under_every_arm(corpus, sidecar, cfg):
    m = A.fit(corpus, 2014, cfg, sidecar=sidecar)
    v2 = fp.fit_aging_curves(corpus, max_season=2014, write=False)
    for side, roles, comps in (("hit", ("C", "H"), fp.HIT_COMPONENTS), ("pit", ("SP", "RP"), fp.PIT_COMPONENTS)):
        for comp in comps:
            table = m.component_curve(side, comp)
            assert set(table) == set(roles)
            for role in roles:
                assert table[role] == v2[side][role][comp]
                assert m.component_curve(side, comp, bucket=role if side == "pit" else ("C" if role == "C" else "SS")) == v2[side][role][comp]
            for role in roles:
                for age in range(20, 45):
                    assert m.rate_delta(side, comp, age, role=role) == fp.curve_delta(v2, side, role, comp, age)
    with pytest.raises(KeyError):
        m.component_curve("hit", "war_rate")


def test_no_arm_service_reproduces_v2_exactly(corpus):
    m = A.fit(corpus, 2014, cfg_with())
    v2 = fp.fit_aging_curves(corpus, max_season=2014, write=False)
    n = 0
    for side in ("hit", "pit"):
        for role, comps in v2[side].items():
            for comp in ("war_rate", "pt"):
                c2 = comps.get(comp) or {}
                c3 = m.cells[side].get(role, {}).get(comp, {})
                assert {int(a) for a in c2} == set(c3), (side, role, comp)
                for a, v in c2.items():
                    assert v["delta"] == c3[int(a)]["delta"] and v["delta_smooth"] == c3[int(a)]["delta_smooth"]
                    n += 1
            for age in range(18, 48):
                for comp in ("war_rate", "pt"):
                    assert m.rate_delta(side, comp, age, role=role) == fp.curve_delta(v2, side, role, comp, age)
                # the v2 additive pt step, exactly
                for pt_prev in (120.0, 480.0, 700.0):
                    assert m.pt_next(side, role, pt_prev, age) == max(0.0, pt_prev + fp.curve_delta(v2, side, role, "pt", age))
    assert n > 50
    assert not m.any_rate_arm and not m.arm_active("T")


def test_arm_s_with_incumbent_knobs_is_v2_and_the_knobs_move_it(corpus):
    cfg = cfg_with(S=True)
    v2 = fp.fit_aging_curves(corpus, max_season=2014, write=False)
    m = A.fit(corpus, 2014, cfg)
    assert m.cells["hit"]["H"]["war_rate"] == A.fit(corpus, 2014, cfg_with()).cells["hit"]["H"]["war_rate"]
    for a, v in v2["hit"]["H"]["war_rate"].items():
        assert m.rate_delta("hit", "war_rate", int(a), role="H") == v["delta_smooth"]
    cfg["S"]["lambda"] = 0.0
    m0 = A.fit(corpus, 2014, cfg)
    assert any(m0.rate_delta("hit", "war_rate", a, role="H") != m.rate_delta("hit", "war_rate", a, role="H")
               for a in range(22, 40))
    cfg["S"]["lambda"] = 1.0
    cfg["S"]["smoother"] = "pen"
    for pen in (1, 4, 16):
        cfg["S"]["penalty"] = pen
        mp = A.fit(corpus, 2014, cfg)
        assert all(math.isfinite(mp.rate_delta("hit", "war_rate", a, role="H")) for a in range(22, 40))
    assert A.config_hash(cfg) != A.config_hash(cfg_with(S=True))


# ---------------------------------------------------------------------------
# the config, the version, the cache name, the flags
# ---------------------------------------------------------------------------

def test_no_arm_is_active_by_default():
    cfg = A.default_config()
    assert cfg["arms"] == {"T": False, "S": False, "P": False, "R": False}
    assert cfg["health"] is False and cfg["pt_cap"] is False
    assert cfg["S"] == {"lambda": 1.0, "smoother": "ma3", "penalty": 4}
    assert cfg["P"]["k"] == 200 and cfg["R"]["k"] == 400
    assert A.normalize_config(None) == A.normalize_config({})
    assert A.active_config()["arms"] == cfg["arms"]


def test_version_recomputes_from_the_fit_source():
    h = __import__("hashlib").sha256()
    for fn in A._FIT_SOURCE:
        h.update(inspect.getsource(fn).encode("utf-8").replace(b"\r\n", b"\n"))
    assert A.AGING_V3_VERSION == "v3-" + h.hexdigest()[:8]
    assert A.fit in A._FIT_SOURCE and A._accumulate in A._FIT_SOURCE and A._shrink in A._FIT_SOURCE
    assert re.fullmatch(r"v3-[0-9a-f]{8}", A.AGING_V3_VERSION)


def test_cache_name_carries_version_and_cfg8(corpus):
    p = A.cache_path(corpus, 2014, A.default_config())
    sig = fp._corpus_sig(corpus)
    assert p.name == f"aging_v3_fits_2014_2000_2015_{sig}_{A.AGING_V3_VERSION}_{A.config_hash({})}.pkl"
    assert p.name.startswith("aging_v3_fits_") and not p.name.startswith("fa_fits_")
    assert len(A.config_hash({})) == 8
    assert A.config_hash(cfg_with(P=True)) != A.config_hash({})
    assert A.config_hash({}) == A.config_hash(A.default_config())


def test_fitted_with_use_cache_false_writes_nothing(corpus, tmp_path, monkeypatch):
    monkeypatch.setattr(A, "CACHE_DIR", tmp_path)
    m = A.fitted(corpus, 2014, use_cache=False)
    assert isinstance(m, A.AgingModel)
    assert list(tmp_path.iterdir()) == []
    m2 = A.fitted(corpus, 2014, use_cache=True)
    assert [p.name for p in tmp_path.iterdir()] == [A.cache_path(corpus, 2014).name]
    assert A.fitted(corpus, 2014, use_cache=True).meta == m2.meta


def test_every_consumer_flag_reads_false_and_selects_v2():
    import yaml
    blk = yaml.safe_load((ROOT / "fa_config.yaml").read_text(encoding="utf-8"))["aging_v3"]
    assert set(blk["consumers"]) == set(A.CONSUMERS)
    assert all(v is False for v in blk["consumers"].values())
    assert blk["health"] is False
    for c in A.CONSUMERS:
        assert A.consumer_enabled(c) is False and A.consumer_aging(c) == "v2"
    assert A.health_enabled() is False
    with pytest.raises(KeyError):
        A.consumer_aging("not_a_consumer")


def test_fitted_models_v3_attaches_the_model_and_keeps_v2(corpus, tmp_path, monkeypatch):
    monkeypatch.setattr(fp, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(A, "CACHE_DIR", tmp_path)
    c2, w2 = fp.fitted_models(corpus, 2014, use_cache=False)
    c3, w3 = fp.fitted_models(corpus, 2014, use_cache=False, aging="v3")
    assert isinstance(c3["_aging_v3"], A.AgingModel)
    assert {k: v for k, v in c3.items() if k != "_aging_v3"} == c2
    assert w3 == w2
    assert list(tmp_path.iterdir()) == []
    with pytest.raises(ValueError):
        fp.fitted_models(corpus, 2014, use_cache=False, aging="v4")
    assert A.model_of(c2) is None and A.model_of(c3) is c3["_aging_v3"]


def test_serialization_round_trip(corpus, sidecar):
    m = A.fit(corpus, 2014, cfg_with(T=True, P=True, R=True), sidecar=sidecar)
    d = m.to_dict()
    m2 = A.AgingModel.from_dict(__import__("json").loads(__import__("json").dumps(d)))
    for side in ("hit", "pit"):
        for b in (None,) + A.BUCKETS[side]:
            for age in (22.0, 27.0, 33.0):
                assert m2.level(side, age, b) == pytest.approx(m.level(side, age, b))
                assert m2.shape(side, age, 7, b) == pytest.approx(m.shape(side, age, 7, b))
                assert m2.pt_next(side, "H" if side == "hit" else "SP", 500.0, int(age), b) == pytest.approx(
                    m.pt_next(side, "H" if side == "hit" else "SP", 500.0, int(age), b))
    assert m2.meta == m.meta and m2.cfg == m.cfg


def test_served_model_absent_raises_and_injection_serves(corpus, monkeypatch, tmp_path):
    monkeypatch.setattr(A, "SERVED_CURVES_PATH", tmp_path / "absent.json")
    A.set_served_model(None)
    with pytest.raises(A.AgingV3Unavailable):
        A.served_model()
    m = A.fit(corpus, 2014, cfg_with())
    A.set_served_model(m)
    try:
        assert A.served_model() is m
    finally:
        A.set_served_model(None)


def test_check_corpus_names_the_blockers(corpus):
    assert A.check_corpus({"war_provider": "fwar",
                           "hit": [{"season": s, "war": 1.0} for s in range(2000, 2027)],
                           "pit": [{"season": s, "war": 1.0} for s in range(2000, 2027)]}) == []
    probs = A.check_corpus({"war_provider": "ewar_v2", "hit": [], "pit": []})
    assert any("BLOCKER: task EPOCH_RUN" in p for p in probs)
    assert any("pre-2011 fWAR absent" in p for p in probs)


def test_u5_run_part_curves_fit_with_the_incumbent_estimator(corpus, sidecar):
    m = A.fit(corpus, 2014, cfg_with(), sidecar=sidecar)
    for comp in ("bsr", "fld"):
        table = m.component_curve("hit", comp)
        assert set(table) <= {"C", "H"} and table.get("H")
        for a, v in table["H"].items():
            assert {"delta", "raw", "n", "attrition", "delta_smooth"} <= set(v)
        with pytest.raises(KeyError):
            m.component_curve("pit", comp)
    # without a sidecar the curves are simply absent, never filled
    assert A.fit(corpus, 2014, cfg_with()).extra == {}
    # fld is per 1,000 innings and bsr per 600 PA
    r = {"season": 2010, "pa": 600.0, "_bsr": 3.0, "_fld": 5.0, "_inn": 1000.0}
    assert A._value(r, "hit", "bsr", {}, 100, 600) == pytest.approx(3.0)
    assert A._value(r, "hit", "fld", {}, 100, 600) == pytest.approx(5.0)
    assert A._value({"season": 2010, "pa": 600.0, "_bsr": None}, "hit", "bsr", {}, 100, 600) is None


def test_arms_needing_the_sidecar_refuse_without_it(corpus):
    for cfg in (cfg_with(P=True), cfg_with(R=True)):
        with pytest.raises(ValueError, match="sidecar"):
            A.fit(corpus, 2014, cfg)


def test_copy_has_no_dash_or_banned_word():
    src = (ROOT / "aging_v3.py").read_text(encoding="utf-8") + \
          (ROOT / "aging_v3_sidecar.py").read_text(encoding="utf-8") + \
          Path(__file__).read_text(encoding="utf-8")
    assert chr(0x2014) not in src and chr(0x2013) not in src
