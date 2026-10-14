"""aging v3 gate pins (docs/AGING_V3_GATE.md; task AG_6_AGING_V3_DEV_AND_POWER).

Fixtures only: the synthetic corpora of tools/aging_v3_lab.py, which carry
nulls (a player with no age, a bucket with no rows, a base with no CONFIRM
cells, an empty archetype). No real corpus is read and no GATE, TIER-2 or
CONFIRM number is computed here.

Pins: the DEV, GATE, TIER-2 and CONFIRM label-season sets are pairwise disjoint
and 2020 is in none; the DEV guard raises on a GATE row; the out-of-window
guard raises; the protocol hash constant equals the hash of the gate
document's frozen sections; the comparator carries the PT cap and the lab's
cap agrees with the service's on fixtures (gate section 4); the registered
grids and thresholds; the selection rule's tie direction; the plant touches
only the planted cells; the ARM R serve base reads an out-of-window archetype;
the DEV artifact, when present, names DEV label seasons only (a GATE row is a
VOID) and its selections are on the grids.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import aging_v3 as A              # noqa: E402
import aging_v3_lab as L          # noqa: E402


@pytest.fixture(scope="module")
def U():
    corpus = L.fixture_corpus(nulls=True)
    return L.Universe(corpus, L.fixture_sidecar(corpus))


@pytest.fixture(scope="module")
def dev_frame(U):
    return L.build_frame(U, "DEV", L.FRAMES["DEV"], L.DEV_GUARD)


# ---------------------------------------------------------------------------
# frames
# ---------------------------------------------------------------------------

def test_label_season_sets_are_pairwise_disjoint_and_2020_is_masked():
    names = list(L.FRAMES)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            assert not (set(L.FRAMES[a]) & set(L.FRAMES[b])), (a, b)
    assert all(L.MASKED_LABEL not in v for v in L.FRAMES.values())
    assert L.FRAMES["DEV"] == (2008, 2009, 2010)
    assert L.FRAMES["GATE"] == (2011, 2012, 2013)
    assert L.FRAMES["TIER2"] == tuple(s for s in range(2014, 2026) if s != 2020)
    assert L.FRAMES["CONFIRM"] == (2026,)
    assert L.frame_bases(L.FRAMES["DEV"]) == list(range(2004, 2011))
    assert L.frame_bases(L.FRAMES["CONFIRM"]) == list(range(2022, 2027))
    # the health frames are disjoint from each other too
    hn = list(L.H_FRAMES)
    for i, a in enumerate(hn):
        for b in hn[i + 1:]:
            assert not (set(L.H_FRAMES[a]) & set(L.H_FRAMES[b]))


def test_dev_guard_raises_on_a_gate_row(U):
    with pytest.raises(L.EarlyLookError):
        L.DEV_GUARD.check(2011)
    with pytest.raises(L.EarlyLookError):
        L.DEV_GUARD.check_rows([{"L": 2008}, {"L": 2011}])
    L.DEV_GUARD.check_rows([{"L": 2008}, {"L": 2010}])
    # a frame built with the DEV guard that is handed a GATE label season raises
    with pytest.raises(L.EarlyLookError):
        L.build_frame(U, "DEV", (2008, 2011), L.DEV_GUARD)
    # a scorer handed a frame carrying a GATE row raises before predicting
    gate = L.build_frame(U, "GATE", (2011,), L.FrameGuard("GATE", (2011,)))
    assert gate["rows"]
    with pytest.raises(L.EarlyLookError):
        L.predict(gate, U, L.comparator_cfg(), L.DEV_GUARD)
    # the DEV frame itself carries only DEV label seasons
    dev = L.build_frame(U, "DEV", L.FRAMES["DEV"], L.DEV_GUARD)
    assert {r["L"] for r in dev["rows"]} <= set(L.FRAMES["DEV"])
    assert all(r["L"] != L.MASKED_LABEL for r in dev["rows"])


def test_out_of_window_guard_raises():
    cfg = A.default_config()
    assert L.check_out_of_window(cfg, 2010) == [2007, 2008, 2009]
    bad = A.default_config()
    bad["R"]["window"] = [-2, 0]
    with pytest.raises(ValueError, match="start season"):
        L.check_out_of_window(bad, 2010)
    bad["R"]["window"] = [-3, 1]
    with pytest.raises(ValueError):
        L.check_out_of_window(bad, 2010)
    with pytest.raises(ValueError):
        A.window_seasons(2010, {"R": {"window": [-1, 0]}})


def test_rvm_rows_never_reach_a_scorer(U, dev_frame):
    assert all(not L.is_rvm(r["mlbam"], U.first) for r in dev_frame["rows"])
    # a frame row from an R-VM player raises inside the scorer
    first = dict(U.first)
    victim = dev_frame["rows"][0]["mlbam"]
    first[victim] = 2025
    saved = U.first
    U.first = first
    try:
        with pytest.raises(L.EarlyLookError, match="R-VM"):
            L.predict({"name": "DEV", "rows": dev_frame["rows"][:5]}, U, L.comparator_cfg(), L.DEV_GUARD)
    finally:
        U.first = saved
    assert L.is_rvm(1, {1: 2025}) and not L.is_rvm(1, {1: 2024})


def test_two_sided_rows_are_excluded(U):
    corpus = L.fixture_corpus(nulls=False, n_hit=60, n_pit=60)
    # make one player two-sided in one season
    h = corpus["hit"][10]
    corpus["pit"].append(dict(corpus["pit"][0], mlbam=h["mlbam"], season=h["season"], age=h["age"]))
    U2 = L.Universe(corpus, L.fixture_sidecar(corpus))
    assert (h["mlbam"], h["season"]) in U2.two_sided
    fr = L.build_frame(U2, "ALL", tuple(range(2001, 2027)), None)
    for r in fr["rows"]:
        assert (r["mlbam"], r["L"]) not in U2.two_sided
        assert all((r["mlbam"], hh["season"]) not in U2.two_sided for hh in r["hist"])


# ---------------------------------------------------------------------------
# the protocol
# ---------------------------------------------------------------------------

def test_protocol_hash_equals_the_gate_documents_frozen_sections():
    raw = L.GATE_DOC.read_bytes().replace(b"\r\n", b"\n")
    lines = raw.split(b"\n")
    s = next(i for i, l in enumerate(lines) if l.startswith(b"## G-0."))
    e = next(i for i, l in enumerate(lines) if l.startswith(b"## 18."))
    h = hashlib.sha256(b"\n".join(lines[s:e]) + b"\n").hexdigest()
    assert L.PROTOCOL_HASH == h == L.protocol_hash()
    L.assert_protocol()


def test_registered_constants():
    assert L.SEED == 20261124 and L.B_BOOT == 2000 and L.ALPHA == 0.0125
    assert L.GRID_LAMBDA == (0.0, 0.5, 1.0)
    assert L.GRID_SMOOTHER == (("ma3", 4), ("pen", 1), ("pen", 4), ("pen", 16))
    assert L.GRID_KP == (50, 100, 200, 400) and L.GRID_KR == (100, 200, 400, 800)
    assert L.PLANT_WAR == 0.05 and L.N_PLANTS == 200 and L.UNDERPOWERED_MDE == 0.03 and L.TIE == 0.002
    assert L.PLANTED_BANDS == ("24-", "31-33", "34+")
    assert [b[0] for b in L.BANDS] == ["24-", "25-27", "28-30", "31-33", "34+"]
    assert (L.G1_MAE, L.G2_STAR, L.G3_TAIL, L.G4_BUCKET, L.G4_MIN_N) == (0.003, 0.05, 0.02, 0.02, 200)
    assert L.CONFIRM_MIN_N == 1000 and L.STAR_WAR == 4.0 and L.TAIL_WAR == 3.0
    assert L.PS_COHORTS == (2014, 2015, 2016, 2017, 2018) and L.NEVER_READ_COHORTS == (2020, 2021, 2025, 2026)
    assert L.H_FRAMES == {"DEV": (2011, 2012, 2013, 2014), "GATE": (2015, 2016, 2017, 2018), "CONFIRM": (2026,)}
    assert L.MDE_FACTOR == pytest.approx(2.2414 + 1.6449, abs=2e-3)
    assert L.band_of(24) == "24-" and L.band_of(24.9) == "24-" and L.band_of(25) == "25-27"
    assert L.band_of(33) == "31-33" and L.band_of(34) == "34+"


def test_comparator_carries_the_call_scoped_cap_and_the_lab_agrees_with_the_service(U):
    comp = L.comparator_cfg()
    assert comp["pt_cap"] is True and not any(comp["arms"].values())
    _, _, m = L.attached(U.corpus, U.sidecar, 2009, comp)
    caps = A._caps(U.corpus, 2009)
    for side, ek, roles in (("hit", "pa", ("C", "H")), ("pit", "bf", ("SP", "RP"))):
        for role in roles:
            vals = [r[ek] for r in U.corpus[side] if r["season"] <= 2009
                    and A.base_role(side, None, r["role"]) == role and r[ek] > 0]
            assert caps[f"{side}:{role}"] == pytest.approx(np.percentile(vals, 99.5))
            assert m.cap(side, role) == pytest.approx(caps[f"{side}:{role}"])
            assert m.pt_next(side, role, caps[f"{side}:{role}"] * 2, 28) <= caps[f"{side}:{role}"] + 1e-9
    # the no-arm composition at the incumbent selections IS the comparator
    sel = dict(L.INCUMBENT, k_P=200, k_R=400)
    assert A.config_hash(L.composition_cfg([], sel)) == A.config_hash(comp)


# ---------------------------------------------------------------------------
# the selection rule and the plant
# ---------------------------------------------------------------------------

def test_selection_rule_takes_the_minimum_then_the_value_nearer_the_incumbent():
    near = lambda k: (abs(k[0] - 1.0), L.smoother_rank(k[1], k[2]))   # noqa: E731
    grid = [((0.0, "ma3", 4), 0.3000), ((1.0, "ma3", 4), 0.3015), ((0.5, "pen", 16), 0.3010)]
    assert L.select(grid, near) == (1.0, "ma3", 4)          # within 0.002 of the minimum, nearer 1.0
    grid = [((0.0, "ma3", 4), 0.3000), ((1.0, "ma3", 4), 0.3030)]
    assert L.select(grid, near) == (0.0, "ma3", 4)          # outside the tie band: the minimum
    grid = [((1.0, "pen", 1), 0.3000), ((1.0, "pen", 16), 0.3010), ((1.0, "ma3", 4), 0.3019)]
    assert L.select(grid, near) == (1.0, "ma3", 4)          # ma3 before a penalized fit
    grid = [((1.0, "pen", 1), 0.3000), ((1.0, "pen", 16), 0.3010)]
    assert L.select(grid, near) == (1.0, "pen", 16)         # then the larger penalty
    assert L.select([((50,), 0.2), ((400,), 0.2019)], lambda k: -k[0]) == (400,)
    assert L.select([((50,), 0.2), ((400,), 0.2021)], lambda k: -k[0]) == (50,)


def test_plant_moves_only_the_planted_cells(dev_frame, U):
    pa = L.predict(dev_frame, U, L.comparator_cfg(), L.DEV_GUARD)
    pb = L.predict(dev_frame, U, L.arm_cfg({"T": True}), L.DEV_GUARD)
    sim = L.plant(dev_frame, pa, pb)
    act = np.array([r["act"] for r in dev_frame["rows"]])
    cells, names = L.cell_index(dev_frame)
    for c, name in enumerate(names):
        ii = np.where(cells == c)[0]
        if ii.size == 0:
            continue
        band = name.split(":", 1)[1]
        bias_a = float((pa[ii] - act[ii]).mean())
        bias_s = float((sim[ii] - act[ii]).mean())
        if band in L.PLANTED_BANDS:
            assert abs(bias_s) == pytest.approx(max(0.0, abs(bias_a) - L.PLANT_WAR), abs=1e-9)
        else:
            assert bias_s == pytest.approx(bias_a, abs=1e-9)
    # ACAL of the simulated arm is lower by the planted share, never higher
    assert L.acal(sim - act, cells, len(names)) <= L.acal(pa - act, cells, len(names)) + 1e-12


def test_bootstrap_pair_is_deterministic_and_bounded(dev_frame, U):
    pa = L.predict(dev_frame, U, L.comparator_cfg(), L.DEV_GUARD)
    pb = L.predict(dev_frame, U, L.arm_cfg({"T": True}), L.DEV_GUARD)
    b1 = L.bootstrap_pair(dev_frame, pa, pb, B=100, seed=L.SEED)
    b2 = L.bootstrap_pair(dev_frame, pa, pb, B=100, seed=L.SEED)
    assert b1 == b2
    assert 0 < b1["p"] <= 1 and 0 < b1["p_reversal"] <= 1
    assert b1["D"] == pytest.approx(b1["acal_pred"] - b1["acal_arm"])
    assert b1["n_players"] == len({r["mlbam"] for r in dev_frame["rows"]})
    g = L.guards(dev_frame, pa, pb, b1)
    assert set(g) == {"G1", "G2", "G3", "G4", "all_pass"}


# ---------------------------------------------------------------------------
# ARM R at the serve base
# ---------------------------------------------------------------------------

def test_arm_r_serve_base_reads_an_out_of_window_archetype(U):
    cfg = L.arm_cfg({"T": True, "S": True, "P": True, "R": True})
    _, _, m = L.attached(U.corpus, U.sidecar, 2009, cfg)
    starts = {t for (_, t) in m.assign["hit"]["archetype"]}
    assert 2010 in starts                                   # the serve base max_season + 1
    assert max(starts) == 2010
    assert L.assert_model_out_of_window(m) > 0
    assigned = [a for (mm, t), a in m.assign["hit"]["archetype"].items() if t == 2010]
    assert assigned and set(assigned) <= set(A.HIT_ARCHETYPES)
    # the serve rule, wired: a hitter projected from base 2010 carries the bucket
    # of his 2009 row and the archetype of 2007..2009, and the walk resolves the
    # archetype cell of that bucket (AG_5 assigned neither, so every served path
    # walked the pooled parent as NEUTRAL)
    mm = next(mm for (mm, t), a in m.assign["hit"]["archetype"].items() if t == 2010 and a != A.NEUTRAL)
    b = m.bucket_of(mm, 2009, "hit")
    assert b in A.HIT_BUCKETS
    assert m._cell("hit", b, m.archetype_of(mm, 2010, "hit"), None) == f"{b}|{m.archetype_of(mm, 2010, 'hit')}"
    assert all(m.bucket_of(r["mlbam"], 2009, "hit") is not None
               for r in U.corpus["hit"] if r["season"] == 2009 and r.get("_pos") not in (None, "X"))
    # the fixture's pitcher rows carry no K% or BB%: an empty archetype
    assert set(m.assign["pit"]["archetype"].values()) == {A.NEUTRAL}
    assert all(c.rsplit("|", 1)[-1] not in ("POWER", "COMMAND") for c in m.cells["pit"])
    # the null bucket: no DH row anywhere in the fixture
    assert "DH" not in m.cells["hit"]


def test_row_archetypes_are_out_of_window(U, dev_frame):
    cfg = L.arm_cfg({"T": True, "S": True, "P": True, "R": True})
    arch = L.row_archetypes({"name": "DEV", "rows": dev_frame["rows"][:40]}, U, cfg)
    assert len(arch) == 40 and set(arch) <= set(A.HIT_ARCHETYPES) | set(A.PIT_ARCHETYPES)


# ---------------------------------------------------------------------------
# the DEV artifact, when it exists
# ---------------------------------------------------------------------------

def test_dev_artifact_names_dev_label_seasons_only_and_grid_values():
    if not L.MDE_PATH.exists():
        pytest.skip("data/aging_v3_mde.json not written yet")
    doc = json.loads(L.MDE_PATH.read_text(encoding="utf-8"))
    assert doc["protocol_hash"] == L.PROTOCOL_HASH
    seasons = L.artifact_label_seasons(doc)
    assert seasons == set(L.FRAMES["DEV"]), seasons          # a GATE, TIER-2 or CONFIRM row is a VOID
    assert doc["frame"]["name"] == "DEV"
    assert max(doc["frame"]["bases"]) <= max(L.FRAMES["DEV"])
    assert doc["cells"]["fit_through_season"] <= max(L.FRAMES["DEV"]) - 1
    sel = doc["selected"]
    assert sel["lambda"] in L.GRID_LAMBDA and (sel["smoother"], sel["penalty"]) in L.GRID_SMOOTHER
    assert sel["k_P"] in L.GRID_KP and sel["k_R"] in L.GRID_KR
    assert set(doc["arms"]) == set(L.ARMS)
    for a in L.ARMS:
        p = doc["power"][a]
        assert p["predecessor"] == ("comparator" if a == "T" else L.ARMS[L.ARMS.index(a) - 1])
        assert p["plant"]["war"] == L.PLANT_WAR and p["plant"]["n_plants"] == L.N_PLANTS
        assert p["underpowered"] == ((p["mde95"] is None) or (p["mde95"] > L.UNDERPOWERED_MDE))
    assert doc["comparator"]["cfg8"] == A.config_hash(L.comparator_cfg())
    assert set(doc["cells"]["bucket_x_age"]) >= {"hit:HALL", "pit:PALL"}
    # the artifact prints no label-season number beyond DEV: no key names one
    text = L.MDE_PATH.read_text(encoding="utf-8")
    for s in L.FRAMES["GATE"] + L.FRAMES["CONFIRM"]:
        assert f'"{s}"' not in text


def test_calendar_floor_list_and_next_free_day():
    import datetime as dt
    assert "2026-11-20" in L.FLOOR_LOOK_DAYS and "2026-12-01" in L.FLOOR_LOOK_DAYS
    assert L.calendar_blockers(dt.date(2026, 11, 20))
    assert L.next_free_day(dt.date(2026, 11, 19)) != "2026-11-20"


def test_the_owner_waiver_records_an_early_read_and_is_never_the_default():
    """EW3-5 (owner 2026-10-14): a blocked day refuses without the switch, is
    recorded (never refused) with it, the fixture path checks nothing, and the
    switch takes no value."""
    import argparse
    import datetime as dt
    blocked = dt.date(2026, 11, 20)
    args = argparse.Namespace(fixture=False, owner_waived=False, rule_day=None)
    with pytest.raises(SystemExit, match="BLOCKER: date"):
        L._stop_if_blocked(args, today=blocked)
    args.owner_waived, args.rule_day = True, "2026-10-15"
    w = L._stop_if_blocked(args, today=blocked)
    assert w["owner_waived"] is True and w["today"] == "2026-11-20" and w["rule_day"] == "2026-10-15"
    assert w["blockers_waived"] and "EW3-5" in w["waiver"]
    # a free day under the switch still records the waiver (the read may be
    # early by the gate's own section 13 rule) with no blocker to name
    free = L._stop_if_blocked(args, today=dt.date(2026, 11, 19))
    assert free["owner_waived"] is True and free["blockers_waived"] == []
    assert L._stop_if_blocked(argparse.Namespace(fixture=True, owner_waived=False), today=blocked) is None
    ns = L._parser().parse_args(["look", "--i-am-the-look", "--owner-waived-early-read", "--rule-day", "2026-10-15"])
    assert ns.owner_waived is True and ns.rule_day == "2026-10-15" and ns.look is True
    assert L._parser().parse_args(["look"]).owner_waived is False


def test_the_owner_waiver_records_an_early_read_and_is_never_the_default():
    """EW3-5 (owner 2026-10-14): a blocked day refuses without the switch, is
    recorded (never refused) with it, the fixture path checks nothing, and the
    switch takes no value."""
    import argparse
    import datetime as dt
    blocked = dt.date(2026, 11, 20)
    args = argparse.Namespace(fixture=False, owner_waived=False, rule_day=None)
    with pytest.raises(SystemExit, match="BLOCKER: date"):
        L._stop_if_blocked(args, today=blocked)
    args.owner_waived, args.rule_day = True, "2026-10-15"
    w = L._stop_if_blocked(args, today=blocked)
    assert w["owner_waived"] is True and w["today"] == "2026-11-20" and w["rule_day"] == "2026-10-15"
    assert w["blockers_waived"] and "EW3-5" in w["waiver"]
    # a free day under the switch still records the waiver (the read may be
    # early by the gate's own section 13 rule) with no blocker to name
    free = L._stop_if_blocked(args, today=dt.date(2026, 11, 19))
    assert free["owner_waived"] is True and free["blockers_waived"] == []
    assert L._stop_if_blocked(argparse.Namespace(fixture=True, owner_waived=False), today=blocked) is None
    ns = L._parser().parse_args(["look", "--i-am-the-look", "--owner-waived-early-read", "--rule-day", "2026-10-15"])
    assert ns.owner_waived is True and ns.rule_day == "2026-10-15" and ns.look is True
    assert L._parser().parse_args(["look"]).owner_waived is False


def test_copy_has_no_dash():
    src = (ROOT / "tools" / "aging_v3_lab.py").read_text(encoding="utf-8") + \
        Path(__file__).read_text(encoding="utf-8")
    assert chr(0x2014) not in src and chr(0x2013) not in src
