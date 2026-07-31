# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""WAR/PA+ and WAR/IP+ (the 2026-07-29 Arkmetric lane).

Pins the parts of the design that a later reader is most likely to break:

  * the scale is 100 + 10z, so the ANCHOR POOL's spread is exactly ten points
    per sigma. This is the aStuff+ defect class (an index advertising ten points
    per sigma while delivering 7.16 because mu/sd came from a different pool),
    so it gets a direct test rather than a comment.
  * batting and pitching bWAR stay on SEPARATE keys, so a two-way player's
    pitching WAR is never divided by his plate appearances.
  * a silent bWAR failure is REFUSED, never served as a board of zeros.
  * a player with no bWAR row gets NO field, not a zero.
  * two-tier volume floors: the pool floor anchors, the display gate publishes.
  * no clamp (true-to-model policy): a real outlier prints past 160.
  * the 3-year companion is a FROZEN vintage read verbatim, carrying its
    generated_at disclosure, and it is dropped from the history boards.

Offline: every test builds its own rows and its own bWAR map. Nothing fetches.
"""
from __future__ import annotations

import json
from pathlib import Path

import bullpen_export as be
import hitter_export as he
import starter_export as se

ROOT = Path(__file__).parent


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _war_map(season: int, bat=None, pit=None) -> dict:
    out: dict = {}
    for side, src in (("bat", bat or {}), ("pit", pit or {})):
        for mid, w in src.items():
            out.setdefault(int(mid), {}).setdefault(int(season), {})[side] = w
    return out


def _patch_war(monkeypatch, war):
    monkeypatch.setattr(be, "_side_war_by_season", lambda: war)


# --------------------------------------------------------------------------- #
# the scale claim
# --------------------------------------------------------------------------- #
def test_anchor_pool_delivers_exactly_ten_points_per_sigma(monkeypatch):
    """The whole point of convention 3. mu/sd come from the pool the index is
    anchored on, so the pool's plus values have SD 10.0. If a future change takes
    mu/sd from anywhere else, this fails - which is what the aStuff+ row on
    GATED_CANDIDATES.md is about."""
    n = 60
    rows = [{"mlbam": 1000 + i, "pa": 300.0 + i} for i in range(n)]
    bat = {1000 + i: (i - n / 2) * 0.01 for i in range(n)}   # spread of WAR
    _patch_war(monkeypatch, _war_map(2026, bat=bat))
    meta = he._join_war_pa_plus(rows, 2026)
    assert meta["available"] and meta["n_stamped"] == n
    # *_raw is serialized at one decimal (the rem_plus_raw / hem_plus_raw house
    # convention), so the tolerance is the serialization step, not slack in the
    # scale. The lab never reads this field: it recomputes from bWAR, which is how
    # the harness-v2 unrounded-predictor rule is satisfied.
    vals = [r["war_pa_plus_raw"] for r in rows]
    mu = sum(vals) / n
    sd = (sum((v - mu) ** 2 for v in vals) / (n - 1)) ** 0.5
    assert abs(mu - 100.0) < 0.02, mu
    assert abs(sd - 10.0) < 0.02, f"{sd} points per anchor-pool sigma, want 10"
    assert meta["per_sigma"] == 10.0


def test_adj_companion_delivers_exactly_ten_points_per_sigma(monkeypatch):
    """The _adj column re-standardises on the SHRUNK pool. Taking mu/sd from the
    unshrunk pool instead would leave it advertising ten points per sigma while
    delivering fewer, which is precisely the aStuff+ 7.16 defect (GATED_CANDIDATES
    C3). Shipped 2026-07-30 when the owner closed the shrink call."""
    n = 60
    rows = [{"mlbam": 1000 + i, "pa": 300.0 + i * 10} for i in range(n)]
    bat = {1000 + i: (i - n / 2) * 0.01 for i in range(n)}
    _patch_war(monkeypatch, _war_map(2026, bat=bat))
    meta = he._join_war_pa_plus(rows, 2026)
    assert meta["available"]
    vals = [r["war_pa_plus_adj_raw"] for r in rows if "war_pa_plus_adj_raw" in r]
    assert len(vals) == n
    mu = sum(vals) / n
    sd = (sum((v - mu) ** 2 for v in vals) / (n - 1)) ** 0.5
    assert abs(mu - 100.0) < 0.02, mu
    assert abs(sd - 10.0) < 0.02, f"{sd} points per SHRUNK-pool sigma, want 10"


def test_adj_pulls_thin_samples_toward_average(monkeypatch):
    """The whole reason the column exists: a hot short sample must not outrank a
    strong full season once the rate is regressed for playing time."""
    rows = [{"mlbam": 1, "pa": 110.0},            # hot but thin
            {"mlbam": 2, "pa": 600.0}]            # strong and full
    rows += [{"mlbam": 100 + i, "pa": 300.0 + i} for i in range(40)]
    bat = {1: 1.9, 2: 6.0}
    bat.update({100 + i: 1.0 + i * 0.01 for i in range(40)})
    _patch_war(monkeypatch, _war_map(2026, bat=bat))
    he._join_war_pa_plus(rows, 2026)
    thin, full = rows[0], rows[1]
    assert thin["war_pa_plus"] > full["war_pa_plus"], (
        "precondition: unadjusted must favour the hot thin sample")
    assert full["war_pa_plus_adj"] > thin["war_pa_plus_adj"], (
        "adjusted must favour the full season")
    # and the raw column must be untouched by the companion's existence
    assert thin["war_pa_plus"] == int(round(thin["war_pa_plus_raw"]))


def test_raw_column_still_reproduces_the_rate_on_the_row(monkeypatch):
    """The reason _adj got its own NAME rather than replacing the column: the raw
    index must stay checkable from the row's own war and denominator against the
    published pool_mean_rate / pool_sd_rate. The adjusted one deliberately does
    not reproduce anything on the row, which is exactly why it is a new column.

    The check is approximate, and its error bound is not slack: TWO display
    roundings sit between the row and the identity. The served `war` is rounded
    to one decimal, so the recomputed rate can be off by up to 0.05 WAR over the
    denominator (10 * 0.05 / (denom * pool_sd) index points), and `*_raw` is
    itself rounded to one decimal (another 0.05). The bound is derived from both
    rather than hardcoded, so if a rounding convention or the scale ever changes
    the bound moves with it instead of silently going slack."""
    n = 40
    rows = [{"mlbam": 1000 + i, "pa": 400.0 + i} for i in range(n)]
    bat = {1000 + i: 1.0 + i * 0.05 for i in range(n)}
    _patch_war(monkeypatch, _war_map(2026, bat=bat))
    meta = he._join_war_pa_plus(rows, 2026)
    for r in rows:
        expect = (100.0 + 10.0 * ((r["war"] / r["pa"]) - meta["pool_mean_rate"])
                  / meta["pool_sd_rate"])
        bound = 10.0 * 0.05 / (r["pa"] * meta["pool_sd_rate"]) + 0.05
        assert abs(r["war_pa_plus_raw"] - expect) <= bound, (
            r["mlbam"], r["war_pa_plus_raw"], expect, bound)


def test_one_year_percentile_chip_is_midrank_over_served_rows(monkeypatch):
    """Mirrors war_rate_plus_lab._pct_map so the 1yr chip and the 3yr chip mean
    the same thing on the same row. Added because a 10-points-per-sigma scale
    hides how rare a modest-looking number is."""
    n = 50
    rows = [{"mlbam": 1000 + i, "pa": 400.0} for i in range(n)]
    bat = {1000 + i: 0.5 + i * 0.1 for i in range(n)}       # strictly increasing
    _patch_war(monkeypatch, _war_map(2026, bat=bat))
    he._join_war_pa_plus(rows, 2026)
    pcts = [r["war_pa_plus_pct"] for r in rows]
    assert all(p is not None for p in pcts)
    assert min(pcts) >= 0 and max(pcts) <= 100
    # monotone in the underlying value, and the best row is at the top
    best = max(rows, key=lambda r: r["war_pa_plus_raw"])
    assert best["war_pa_plus_pct"] >= 99, best["war_pa_plus_pct"]


def test_no_clamp_a_real_outlier_prints_past_the_band(monkeypatch):
    """True-to-model policy: no silent clamp. If a display cap is ever wanted it
    goes in as the AP+ two-field pattern, not as a clamp here."""
    rows = [{"mlbam": 1, "pa": 500.0}] + [
        {"mlbam": 100 + i, "pa": 500.0} for i in range(40)]
    bat = {1: 9.0}
    bat.update({100 + i: 1.0 + i * 0.01 for i in range(40)})
    _patch_war(monkeypatch, _war_map(2026, bat=bat))
    he._join_war_pa_plus(rows, 2026)
    assert rows[0]["war_pa_plus"] > 160, rows[0]["war_pa_plus"]


# --------------------------------------------------------------------------- #
# the WAR source
# --------------------------------------------------------------------------- #
def test_two_way_player_keeps_the_sides_apart(monkeypatch):
    """A two-way player carries BATTING WAR over his PA on the hitter board and
    PITCHING WAR over his IP on a pitcher board. Never a summed side: summing is
    what fa_projection._war_age_maps does, and it would divide his pitching WAR by
    his plate appearances."""
    two_way = 660271
    war = _war_map(2026,
                   bat={two_way: 4.0, **{i: 1.0 + i * 0.001 for i in range(40)}},
                   pit={two_way: 3.0, **{i: 1.0 + i * 0.001 for i in range(40)}})
    _patch_war(monkeypatch, war)
    hit_rows = [{"mlbam": two_way, "pa": 500.0}] + [
        {"mlbam": i, "pa": 400.0} for i in range(40)]
    sp_rows = [{"mlbam": two_way, "ip": 100.0}] + [
        {"mlbam": i, "ip": 120.0} for i in range(40)]
    he._join_war_pa_plus(hit_rows, 2026)
    se._join_war_ip_plus(sp_rows, 2026)
    # the hitter row used batting WAR, the starter row used pitching WAR
    assert hit_rows[0]["war"] == 4.0
    assert sp_rows[0]["war"] == 3.0
    # and both boards carry him, with two different indexes
    assert hit_rows[0]["war_pa_plus"] is not None
    assert sp_rows[0]["war_ip_plus"] is not None


def test_missing_bwar_row_leaves_the_field_absent(monkeypatch):
    """Absent is not zero. A player with no bWAR row must render blank, never as
    a real replacement-level season."""
    rows = [{"mlbam": 500 + i, "pa": 400.0} for i in range(40)]
    rows.append({"mlbam": 999999, "pa": 400.0})       # no bWAR row
    rows.append({"pa": 400.0})                        # no mlbam at all
    bat = {500 + i: 1.0 + i * 0.05 for i in range(40)}
    _patch_war(monkeypatch, _war_map(2026, bat=bat))
    meta = he._join_war_pa_plus(rows, 2026)
    assert meta["n_stamped"] == 40
    assert "war_pa_plus" not in rows[-1] and "war" not in rows[-1]
    assert "war_pa_plus" not in rows[-2] and "war" not in rows[-2]


def test_degenerate_bwar_fetch_is_refused(monkeypatch):
    """A silent bwar failure must be DETECTED and refused, never served as a
    board of zeros (the fa_projection.py:191-201 pattern)."""
    rows = [{"mlbam": 500 + i, "pa": 400.0} for i in range(40)]
    _patch_war(monkeypatch, {})                     # empty map = failed fetch
    meta = he._join_war_pa_plus(rows, 2026)
    assert meta["available"] is False and meta["n_stamped"] == 0
    assert "refused" in meta
    assert all("war_pa_plus" not in r for r in rows)

    # a raising fetch is refused the same way, and never propagates
    def _boom():
        raise RuntimeError("pybaseball down")
    monkeypatch.setattr(be, "_side_war_by_season", _boom)
    meta = he._join_war_pa_plus(rows, 2026)
    assert meta["available"] is False and "refused" in meta


def test_thin_coverage_is_refused_not_anchored(monkeypatch):
    """Coverage under the floor means the pool would be anchored on a handful of
    rows. Refuse instead."""
    rows = [{"mlbam": 500 + i, "pa": 400.0} for i in range(40)]
    bat = {500 + i: 1.0 + i * 0.05 for i in range(5)}   # 5 of 40 covered
    _patch_war(monkeypatch, _war_map(2026, bat=bat))
    meta = he._join_war_pa_plus(rows, 2026)
    assert meta["available"] is False and "refused" in meta


# --------------------------------------------------------------------------- #
# two-tier volume floors
# --------------------------------------------------------------------------- #
def test_two_tier_floors_pool_anchors_display_gate_publishes(monkeypatch):
    """Pool floor 50 PA contributes to mu/sd; only 100+ PA gets a value. Two
    tiers, not one unified floor, and never no gate at all (the registered SC+
    defect)."""
    rows = ([{"mlbam": 100 + i, "pa": 400.0} for i in range(30)]
            + [{"mlbam": 200 + i, "pa": 70.0} for i in range(10)]     # pool only
            + [{"mlbam": 300 + i, "pa": 20.0} for i in range(10)])    # neither
    bat = {}
    bat.update({100 + i: 1.0 + i * 0.05 for i in range(30)})
    bat.update({200 + i: 0.2 for i in range(10)})
    bat.update({300 + i: 0.1 for i in range(10)})
    _patch_war(monkeypatch, _war_map(2026, bat=bat))
    meta = he._join_war_pa_plus(rows, 2026)
    assert meta["pool_n"] == 40, meta["pool_n"]        # 30 regulars + 10 part-time
    assert meta["n_stamped"] == 30                      # only the 100+ PA rows
    assert all("war_pa_plus" not in r for r in rows if r["pa"] < 100)
    assert meta["pool_min"] == 50.0 and meta["display_min"] == 100.0


def test_pitcher_floors_differ_by_role():
    assert be.WAR_RATE_POOL_MIN_IP == 20.0
    assert be.WAR_RATE_DISPLAY_MIN_SP_IP == 40.0
    assert be.WAR_RATE_DISPLAY_MIN_RP_IP == 30.0
    # the two pitcher surfaces must not share one gate or one pool
    assert be.WAR_RATE_DISPLAY_MIN_SP_IP != be.WAR_RATE_DISPLAY_MIN_RP_IP


def test_starter_and_reliever_pools_are_anchored_separately(monkeypatch):
    """Same field name, two payloads, two anchor pools. The identical raw rate
    must index differently on the two boards, because a reliever banks more WAR
    per inning than a starter of equal talent
    (ARKMETRIC_SCALE_CONVENTIONS.md:77)."""
    war = _war_map(2026,
                   pit={**{100 + i: 2.0 + i * 0.05 for i in range(30)},
                        **{200 + i: 1.0 + i * 0.02 for i in range(30)},
                        7: 1.0})
    _patch_war(monkeypatch, war)
    sp = [{"mlbam": 7, "ip": 100.0}] + [{"mlbam": 100 + i, "ip": 150.0}
                                        for i in range(30)]
    rp = [{"mlbam": 7, "ip": 100.0}] + [{"mlbam": 200 + i, "ip": 60.0}
                                        for i in range(30)]
    m_sp = se._join_war_ip_plus(sp, 2026)
    m_rp = be._join_war_ip_plus(rp, 2026)
    assert m_sp["anchor"] != m_rp["anchor"]
    assert "starters" in m_sp["anchor"] and "relievers" in m_rp["anchor"]
    # the SAME player at the SAME rate scores differently on the two boards
    assert sp[0]["war_ip_plus"] != rp[0]["war_ip_plus"]


# --------------------------------------------------------------------------- #
# the frozen 3-year vintage
# --------------------------------------------------------------------------- #
def test_frozen_3yr_join_stamps_and_discloses(tmp_path, monkeypatch):
    art = {"generated_at": "2026-07-29",
           "proposed_values": {"hit": {
               "season": 2026, "window": [2024, 2025, 2026],
               "anchor_pool": "hitters with 50+ PA",
               "players": {"670541": {"war_pa_plus_3yr": 131, "pct": 97,
                                      "tag": "established"},
                           "111111": {"war_pa_plus_3yr": 104, "pct": 60,
                                      "tag": "provisional"}}}}}
    p = tmp_path / "war_rate_plus_multiyear_eval.json"
    p.write_text(json.dumps(art), encoding="utf-8")
    monkeypatch.setattr(be, "WAR_RATE_MULTIYR_PATH", p)

    rows = [{"mlbam": 670541}, {"mlbam": 111111}, {"mlbam": 222222}, {}]
    meta = he._join_war_pa_plus_3yr(rows)
    assert meta["available"] and meta["n_stamped"] == 2
    assert rows[0]["war_pa_plus_3yr"] == 131
    assert rows[0]["war_pa_plus_3yr_pct"] == 97
    assert rows[0]["war_pa_plus_3yr_tag"] == "established"
    assert rows[1]["war_pa_plus_3yr_tag"] == "provisional"
    assert "war_pa_plus_3yr" not in rows[2] and "war_pa_plus_3yr" not in rows[3]
    # the vintage block must disclose that this is FROZEN and as-of generated_at
    assert meta["generated_at"] == "2026-07-29"
    assert meta["window"] == [2024, 2025, 2026]
    assert "FROZEN" in meta["note"] and "generated_at" in meta["note"]
    assert meta["n_in_artifact"] == 2

    # missing artifact is a clean no-op, never an exception
    monkeypatch.setattr(be, "WAR_RATE_MULTIYR_PATH", tmp_path / "nope.json")
    assert he._join_war_pa_plus_3yr(rows)["available"] is False


def test_three_blocks_are_three_metrics(tmp_path, monkeypatch):
    """One artifact, three blocks, because the three anchor pools are three
    metrics. A join must read its OWN block."""
    art = {"generated_at": "2026-07-29", "proposed_values": {
        "hit": {"players": {"1": {"war_pa_plus_3yr": 120, "pct": 90, "tag": "established"}}},
        "sp": {"players": {"1": {"war_ip_plus_3yr": 80, "pct": 10, "tag": "established"}}},
        "rp": {"players": {"1": {"war_ip_plus_3yr": 111, "pct": 70, "tag": "established"}}},
    }}
    p = tmp_path / "war_rate_plus_multiyear_eval.json"
    p.write_text(json.dumps(art), encoding="utf-8")
    monkeypatch.setattr(be, "WAR_RATE_MULTIYR_PATH", p)
    h, s, r = [{"mlbam": 1}], [{"mlbam": 1}], [{"mlbam": 1}]
    he._join_war_pa_plus_3yr(h)
    se._join_war_ip_plus_3yr(s)
    be._join_war_ip_plus_3yr(r)
    assert h[0]["war_pa_plus_3yr"] == 120
    assert s[0]["war_ip_plus_3yr"] == 80
    assert r[0]["war_ip_plus_3yr"] == 111


# --------------------------------------------------------------------------- #
# plumbing: the ship checklist
# --------------------------------------------------------------------------- #
_JS = (ROOT / "assets" / "mlbstats.js").read_text(encoding="utf-8")
_GLOSSARY_IDS = {e["id"] for e in json.loads(
    (ROOT / "data" / "glossary.json").read_text(encoding="utf-8"))["entries"]}
_WAR_RATE_TERMS = ("war_pa_plus", "war_pa_plus_3yr", "war_ip_plus_sp",
                   "war_ip_plus_sp_3yr", "war_ip_plus_rp", "war_ip_plus_rp_3yr",
                   # sample-adjusted companions, owner call closed 2026-07-30
                   "war_pa_plus_adj", "war_ip_plus_sp_adj", "war_ip_plus_rp_adj")


def test_every_column_term_slug_has_a_glossary_entry():
    for slug in _WAR_RATE_TERMS:
        assert f'term: "{slug}"' in _JS, f"no column wired to {slug}"
        assert slug in _GLOSSARY_IDS, f"column term {slug} has no glossary entry"


def test_glossary_entries_name_their_anchor_pool():
    """The two WAR/IP+ entries exist precisely so a reader is told WHICH pool the
    100 refers to. If either stops saying so, the pair becomes ambiguous."""
    g = json.loads((ROOT / "data" / "glossary.json").read_text(encoding="utf-8"))
    by = {e["id"]: e for e in g["entries"]}
    for slug in _WAR_RATE_TERMS:
        e = by[slug]
        assert e["category"] == "custom-index" and e["shelf"] == "ark"
        assert "eephus.io" in e["origin"]
        assert "mlbstats" in e["module"]
        blob = (e["definition"] + " " + e.get("methodology", "")).lower()
        # the compound adjective form ("ten-points-per-standard-deviation") counts
        assert "standard deviation" in blob or "standard-deviation" in blob, slug
    assert "starter" in by["war_ip_plus_sp"]["definition"].lower()
    assert "reliever" in by["war_ip_plus_rp"]["definition"].lower()


def test_war_rate_columns_are_dropped_from_history_boards():
    """History rows carry no bWAR join, so the columns must drop rather than
    render as a blank column."""
    hit = _JS.split("var HITTER_HISTORY_DROP =")[1].split(";")[0]
    sp = _JS.split("var STARTER_HISTORY_DROP =")[1].split(";")[0]
    rel = _JS.split("var REL_HISTORY_KEYS =")[1].split(";")[0]
    for k in ("war_pa_plus", "war_pa_plus_adj", "war_pa_plus_3yr", "war"):
        assert k + ": 1" in hit, f"{k} not dropped from the hitter history board"
    for k in ("war_ip_plus", "war_ip_plus_adj", "war_ip_plus_3yr", "war"):
        assert k + ": 1" in sp, f"{k} not dropped from the starter history board"
    # the reliever map is an ALLOW-list: the keys must be ABSENT from it
    for k in ("war_ip_plus", "war_ip_plus_adj", "war_ip_plus_3yr"):
        assert k not in rel, f"{k} leaked into the reliever history allow-list"


def test_war_rate_columns_use_remcell_not_hemcell():
    """100 + 10z has SD exactly 10, so the +-2-sigma read is 80/120 (remClass).
    hemCell bands for the wRC+-width ratio family and would call a 1.2-sigma
    hitter average. The hitter board is the trap: every column around WAR/PA+
    uses hemCell."""
    for key in ("war_pa_plus", "war_pa_plus_3yr", "war_ip_plus", "war_ip_plus_3yr"):
        marker = 'key: "%s", label:' % key
        starts = [i for i in range(len(_JS))
                  if _JS.startswith(marker, i)]
        assert starts, f"no column definition for {key}"
        for i in starts:
            # the column object ends at the next definition or the array close
            nxt = _JS.find('{ key: "', i)
            body = _JS[i:nxt if nxt > i else i + 1200]
            assert "remCell(" in body, f"{key} column not on remCell"
            assert "hemCell(" not in body, f"{key} column uses hemCell"


def test_registry_rows_and_glossary_map():
    import model_registry as mr
    import test_methodology_freshness as tmf
    ids = {m["model_id"] for m in mr.load()["models"]}
    for mid in ("war_pa_plus", "war_ip_plus_sp", "war_ip_plus_rp",
                "war_rate_plus_3yr"):
        assert mid in ids, f"registry row missing: {mid}"
        assert mid in tmf.MODEL_GLOSSARY, f"MODEL_GLOSSARY mapping missing: {mid}"


def test_registry_verdict_matches_the_measured_gate():
    """A display index with no forward win ships `unvalidated` with a null
    artifact, and the measurement ledger is cited on the row instead. Validated
    if and only if the artifact is attached, in both directions."""
    import model_registry as mr
    rows = {m["model_id"]: m for m in mr.load()["models"]}
    art = json.loads((ROOT / "data" / "war_rate_plus_eval.json")
                     .read_text(encoding="utf-8"))
    g2 = art["verdict"]["g2_by_pool"]
    pool_of = {"war_pa_plus": "hit", "war_ip_plus_sp": "SP",
               "war_ip_plus_rp": "RP"}
    for mid, pool in pool_of.items():
        row = rows[mid]
        if g2.get(pool):
            assert row["eval_artifact"], f"{mid} passed G2 but carries no artifact"
            assert row["verdict"] in ("validated", "provisional")
        else:
            assert row["verdict"] == "unvalidated", mid
            assert not row["eval_artifact"], mid
            assert "war_rate_plus_eval.json" in row["notes"], (
                f"{mid}: the ledger must be cited so the artifact stays "
                f"registered (test_model_registry.py globs data/*_eval*.json)")


def test_eval_artifact_proves_the_scale():
    """The artifact carries the measured points-per-anchor-pool-sigma for each of
    the three pools, so the scale claim on the board is checkable."""
    art = json.loads((ROOT / "data" / "war_rate_plus_eval.json")
                     .read_text(encoding="utf-8"))
    assert art["conventions"]["shrink"].startswith("NONE")
    assert art["conventions"]["clamp"] == "none (true-to-model policy)"
    for pool in ("hit", "SP", "RP"):
        chk = art["pools"][pool]["live_season_scale_check"]
        assert abs(chk["measured_points_per_anchor_pool_sigma"] - 10.0) < 0.01, pool
        assert chk["advertised_points_per_sigma"] == 10.0
