# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Organization Tendencies guards: pure helpers (z, labels, cash-direction
parsing, promotion math), the committed sidecar's shape contract (the
farm-detail Tendencies tab renders it blind), and the prospx/glossary
wiring."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

import org_tendencies as ot

ROOT = Path(__file__).parent
SIDECAR = ROOT / "data" / "org_tendencies.json"


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def test_z_and_label_bands():
    assert ot._z(12, 10, 2) == 1.0
    assert ot._z(None, 10, 2) is None
    assert ot._z(12, 10, 0) is None                      # degenerate sd
    assert ot._label(0.6, "hi", "lo") == "hi"
    assert ot._label(-0.6, "hi", "lo") == "lo"
    assert ot._label(0.2, "hi", "lo") == "typical"
    assert ot._label(None, "hi", "lo") is None


def test_league_stats_requires_population():
    assert ot._league_stats({"A": 1.0, "B": None})["mean"] is None  # < 8 orgs
    vals = {f"O{i}": float(i) for i in range(10)}
    st = ot._league_stats(vals)
    assert st["mean"] == 4.5 and st["sd"] > 0


def test_cash_direction_parses_receiving_club():
    """'A traded X to B for ... cash' — A received the cash."""
    d = "St. Louis Cardinals traded RF Adolis Garcia to Texas Rangers for cash."
    assert ot.cash_direction(d) == "St. Louis Cardinals"
    d2 = ("Colorado Rockies traded RF Raimel Tapia and 2B Adrian Pinto to "
          "Toronto Blue Jays for RF Randal Grichuk and cash.")
    assert ot.cash_direction(d2) == "Colorado Rockies"
    # no cash in the return → no receiver
    d3 = "Boston Red Sox traded SS Test Player to New York Yankees for RHP Other Guy."
    assert ot.cash_direction(d3) is None


def test_promotion_panel_math():
    """Young-for-level + frequent promotions reads aggressive; the inverse
    reads conservative — on a synthetic 10-org league."""
    today = date(2026, 6, 10)
    mk = lambda diff, promos: {
        "age_vs_level": {"diff": diff},
        "level_changes": [{"kind": "promotion", "date": "2026-01-15"}] * promos,
    }
    by_org = {f"O{i}": [mk(0.0, 1), mk(0.0, 1)] for i in range(8)}
    by_org["AGG"] = [mk(-2.0, 3), mk(-1.5, 2)]
    by_org["CON"] = [mk(2.0, 0), mk(1.5, 0)]
    panel = ot.promotion_panel(by_org, [], today)
    assert panel["orgs"]["AGG"]["label"] == "aggressive"
    assert panel["orgs"]["CON"]["label"] == "conservative"
    assert panel["orgs"]["O0"]["label"] == "typical"


def test_promotion_panel_debut_age():
    """Debut age splits pitchers vs hitters and z's vs league."""
    today = date(2026, 6, 10)
    roster = [{"age_vs_level": {"diff": 0.0}, "level_changes": []}]
    by_org = {f"O{i}": list(roster) for i in range(10)}
    # 3 pitcher + 3 hitter debuts for ORG, league debuts older
    debuts = []
    for i in range(10):
        org = f"O{i}"
        for _ in range(3):
            debuts.append({"org": org, "position": "SP",
                           "birth_date": "2000-01-01", "debut_date": "2025-01-01"})  # age ~25
            debuts.append({"org": org, "position": "SS",
                           "birth_date": "2001-01-01", "debut_date": "2025-01-01"})  # age ~24
    panel = ot.promotion_panel(by_org, debuts, today)
    o0 = panel["orgs"]["O0"]
    assert 24.5 <= o0["debutAgePit"] <= 25.5
    assert 23.5 <= o0["debutAgeHit"] <= 24.5
    assert o0["nDebutPit"] == 3 and o0["nDebutHit"] == 3


def test_filter_mlb30_drops_foreign_codes():
    panel = {"orgs": {"MIL": {}, "KOR": {}, "XXXX": {}}}
    out = ot._filter_mlb30(panel, {"MIL"})
    assert list(out["orgs"]) == ["MIL"]


# ---------------------------------------------------------------------------
# Sidecar shape contract
# ---------------------------------------------------------------------------

def _payload():
    if not SIDECAR.exists():
        pytest.skip("org_tendencies.json not exported on this machine")
    return json.loads(SIDECAR.read_text(encoding="utf-8"))


PANELS = ("promotion", "promotionTiming", "draftPos", "draftTraits", "slot", "arsenal",
          "toolDev", "ifa", "trades", "health",
          "graduation", "hitterApproach", "similarFarms")


def test_sidecar_covers_all_30_orgs_every_panel():
    d = _payload()
    for panel in PANELS:
        orgs = d[panel]["orgs"]
        assert len(orgs) == 30, f"{panel}: {len(orgs)} orgs"
        assert all(len(o) <= 3 for o in orgs), f"{panel}: non-MLB code leaked"


def test_new_panel_shapes():
    """The expanded panels carry their new fields with sane ranges."""
    d = _payload()
    # draft: college/HS + position buckets sum to ~1
    for org, r in d["draftPos"]["orgs"].items():
        bk = r.get("posBuckets") or {}
        if bk:
            assert abs(sum(bk.values()) - 1.0) < 0.02, org
            assert set(bk) == {"P", "C", "MI", "CI", "OF"}, org
        if r.get("collShare") is not None:
            assert 0 <= r["collShare"] <= 1, org
    # arsenal: blended arm counts + full usage matrix with ratios
    for org, r in d["arsenal"]["orgs"].items():
        assert r["nArms"] == r["nArmsMlb"] + r["nArmsAaa"], org
        for pt, cell in (r.get("usage") or {}).items():
            assert 0 <= cell["share"] <= 1, (org, pt)
    # pitchStuff present when AAA cache exists; shape-check when so
    for org, r in d.get("pitchStuff", {}).get("orgs", {}).items():
        for pt, cell in (r.get("pitches") or {}).items():
            assert cell["n"] >= 1, (org, pt)
    # promotion debut ages in a sane window
    for org, r in d["promotion"]["orgs"].items():
        for k in ("debutAgePit", "debutAgeHit"):
            if r.get(k) is not None:
                assert 20 <= r[k] <= 28, (org, k)
    # graduation hit rate is a rate
    for org, r in d["graduation"]["orgs"].items():
        if r.get("draftHitRate") is not None:
            assert 0 <= r["draftHitRate"] <= 1, org
    # similar farms: top-N descending, scores in [-1, 1]
    for org, r in d["similarFarms"]["orgs"].items():
        scores = [s["score"] for s in r["similar"]]
        assert scores == sorted(scores, reverse=True), org
        assert all(-1.001 <= s <= 1.001 for s in scores), org


def test_sidecar_values_are_sane():
    d = _payload()
    for org, r in d["promotion"]["orgs"].items():
        if r.get("avlDiff") is not None:
            assert -6 <= r["avlDiff"] <= 6, org
        assert r.get("label") in ("aggressive", "conservative", "typical", None)
    for org, r in d["ifa"]["orgs"].items():
        if r.get("top1Share") is not None:
            assert 0 < r["top1Share"] <= 1, org
        if r.get("hhi") is not None:
            assert 0 < r["hhi"] <= 1, org
    for org, r in d["trades"]["orgs"].items():
        assert r["volume"] == r["in"] + r["out"], org
        if r.get("acqTopShare") is not None:
            assert 0 <= r["acqTopShare"] <= 1, org
        assert r.get("cashInvolved", 0) >= r.get("cashReceived", 0), org
    # tool-dev rates are grade points per year — drifts beyond ±10 would be
    # source churn, not development
    for org, r in d["toolDev"]["orgs"].items():
        for k, v in (r.get("tools") or {}).items():
            assert -10 <= v["rate"] <= 10, (org, k)


def test_labels_are_league_relative_not_unanimous():
    """z-based labels can't all fire one way — a league where everyone is
    'aggressive' means the baseline is wrong."""
    d = _payload()
    promo = [r.get("label") for r in d["promotion"]["orgs"].values()]
    assert "typical" in promo
    assert not all(v == "aggressive" for v in promo)


def test_prospx_and_glossary_wiring():
    src = (ROOT / "prospx" / "index.html").read_text(encoding="utf-8")
    assert "org-tendencies-mount" in src and "_renderOrgTendencies" in src
    assert '"tendencies"' in src or "'tendencies'" in src
    assert "org_tendencies.json" in src
    gl = json.loads((ROOT / "data" / "glossary.json").read_text(encoding="utf-8"))
    assert any(e["id"] == "org_tendencies" for e in gl["entries"])
    rm = (ROOT / "run_monthly.py").read_text(encoding="utf-8")
    # rebuild_only exports it, and main() chains rebuild_only nightly (the
    # duplicate monthly 6c export was merged away 2026-07-14 - it was
    # overwritten by the chained rebuild ~15 min later every monthly night).
    assert rm.count("org_tendencies import export") >= 1
    assert "6c/6d SKIP" in rm


# ---------------------------------------------------------------------------
# Promotion timing (rookie cutoff, service-year window, age for level)
# ---------------------------------------------------------------------------

PT_ORG_KEYS = {"nDebuts", "medianDebutAge", "medianAgeCi", "lateShare", "lateCi", "qLate",
               "svcShare", "svcCi", "qSvc", "aggrYears", "aggrCi", "nAggrPlayers", "qAggr",
               "labelTiming", "labelAggr", "thin"}
PT_LEAGUE_KEYS = {"nDebuts", "years", "aggrSeasons", "nAggrPlayers", "lateShare", "svcShare",
                  "medianDebutAge", "aggrYears", "rookieCutoff", "cutoffRulePre2020",
                  "serviceYearDays", "svcWindowDays", "labelRule", "rule"}


def _pt_league(n_orgs=30, n_each=40, late_every=4, extra=None):
    """Synthetic league: each org has n_each debuts, one in late_every after the
    rookie cutoff; `extra` maps org -> list of debut dicts appended."""
    debuts = []
    for i in range(n_orgs):
        org = f"O{i:02d}"
        for j in range(n_each):
            debuts.append({"year": 2022 + j % 5, "org": org, "age": 24.0 + (j % 7) * 0.3,
                           "late": j % late_every == 0, "svc": j % 6 == 0})
    for org, rows in (extra or {}).items():
        debuts.extend(rows)
    return debuts


def _pt_aggr_rows(orgs, n_players=60, shift=None):
    rows = []
    for o in orgs:
        for k in range(n_players):
            age = 21.0 + (k % 9) * 0.25 - (shift or {}).get(o, 0.0)
            rows.append((f"{o}_{k}", o, 2024, "AA", k % 2 == 0, age, 50.0))
    return rows


def test_promotion_timing_panel_schema():
    """The panel carries n, CI95 and a BH q for every figure, the league
    block names the rule, the cutoffs and the label rule (owner ask 2026-09-25)."""
    debuts = _pt_league()
    orgs = {d["org"] for d in debuts}
    panel = ot.promotion_timing_panel(debuts, _pt_aggr_rows(orgs), {"2026": "2026-08-14"}, orgs)
    assert set(panel["league"]) == PT_LEAGUE_KEYS
    assert len(panel["orgs"]) == 30
    for org, r in panel["orgs"].items():
        assert set(r) == PT_ORG_KEYS, org
        assert r["nDebuts"] == 40 and r["nAggrPlayers"] == 60, org
        for k in ("lateCi", "svcCi", "aggrCi", "medianAgeCi"):
            lo, hi = r[k]
            assert lo is not None and lo <= hi, (org, k)
        assert 0 <= r["qLate"] <= 1 and 0 <= r["qAggr"] <= 1, org
    lg = panel["league"]
    assert lg["rookieCutoff"] == {"2026": "2026-08-14"}
    assert lg["serviceYearDays"] == 172 and lg["cutoffRulePre2020"] == "07-18"
    assert lg["aggrYears"]["mean"] == 0.0
    assert abs(lg["lateShare"]["mean"] - 0.25) < 1e-9          # the pooled league share
    urls = [s["url"] for s in lg["rule"]["sources"]]
    assert any("mlb.com/glossary/rules/rookie-eligibility" in u for u in urls)
    assert any("mlb.com/glossary/transactions/service-time" in u for u in urls)
    assert any("baseballamerica.com" in u for u in urls)
    assert "45" in lg["rule"]["text"] and "172" in lg["rule"]["text"]


def test_promotion_timing_no_label_on_thin_data():
    """An org with every debut after the cutoff but fewer than 20 debuts is
    thin and carries no label; the same rate on 40 debuts earns one. An age-
    for-level gap on fewer than 40 players carries no label either."""
    thin = [{"year": 2024, "org": "THIN", "age": 25.0, "late": True, "svc": False} for _ in range(12)]
    wide = [{"year": 2024, "org": "WIDE", "age": 25.0, "late": True, "svc": False} for _ in range(40)]
    debuts = _pt_league(extra={"THIN": thin, "WIDE": wide})
    orgs = {d["org"] for d in debuts}
    rows = _pt_aggr_rows(orgs - {"THIN"}, shift={"WIDE": 1.5})
    rows += _pt_aggr_rows({"THIN"}, n_players=25, shift={"THIN": 3.0})
    panel = ot.promotion_timing_panel(debuts, rows, {}, orgs)
    t, w = panel["orgs"]["THIN"], panel["orgs"]["WIDE"]
    assert t["thin"] is True and t["labelTiming"] is None
    assert t["nAggrPlayers"] == 25 and t["labelAggr"] is None and t["aggrYears"] > 2
    assert w["thin"] is False and w["labelTiming"] == "waits past the rookie cutoff"
    assert w["labelAggr"] == "young for level"
    # league-typical orgs: no label at all
    assert all(r["labelTiming"] is None and r["labelAggr"] is None
               for o, r in panel["orgs"].items() if o.startswith("O"))


def test_promotion_timing_label_needs_q_and_ci():
    """A difference the 30-org test cannot separate from the league gets no
    label, however it reads on a z cut."""
    mild = [{"year": 2024, "org": "MILD", "age": 25.0, "late": j % 3 == 0, "svc": False} for j in range(40)]
    debuts = _pt_league(extra={"MILD": mild})
    orgs = {d["org"] for d in debuts}
    panel = ot.promotion_timing_panel(debuts, _pt_aggr_rows(orgs), {}, orgs)
    m = panel["orgs"]["MILD"]
    assert m["lateShare"] > panel["league"]["lateShare"]["mean"]
    assert m["qLate"] >= 0.10 and m["labelTiming"] is None


def test_rookie_cutoff_rule():
    """45 days before the final scheduled game, both days counted, since
    2020; July 18 before (Baseball America 2024-08-28 names Aug 16 for 2024)."""
    assert ot.pt_rookie_cutoff(2026, date(2026, 9, 27)) == date(2026, 8, 14)
    assert ot.pt_rookie_cutoff(2024, date(2024, 9, 29)) == date(2024, 8, 16)
    assert ot.pt_rookie_cutoff(2025, date(2025, 9, 28)) == date(2025, 8, 15)
    assert ot.pt_rookie_cutoff(2019, None) == date(2019, 7, 18)
    assert ot.pt_rookie_cutoff(2026, None) is None


def test_season_dates_ignore_a_makeup_after_the_finale(tmp_path, monkeypatch):
    """The 2024 finale is Sep 29 although two makeup games ran Sep 30, and a
    lone overseas opener does not open the season."""
    games, n = {}, 0
    for day, count in (("2024-03-20", 1), ("2024-03-28", 13), ("2024-06-01", 15),
                       ("2024-09-29", 15), ("2024-09-30", 2)):
        for _ in range(count):
            n += 1
            games[str(n)] = day
    corpus = tmp_path / "games.json"
    corpus.write_text(json.dumps(games), encoding="utf-8")
    monkeypatch.setattr(ot, "PT_GAME_DATES", corpus)
    cal = {"seasons": [{"seasonId": "2024", "regularSeasonStartDate": "2024-03-20",
                        "regularSeasonEndDate": "2024-09-30"}]}
    monkeypatch.setattr(ot, "_pt_fetch_json", lambda *a, **k: cal)
    got = ot._pt_season_dates({2024}, date(2026, 10, 3))
    assert got[2024] == {"open": date(2024, 3, 28), "final": date(2024, 9, 29)}


def test_align_promotion_label_reads_the_tested_label():
    promo = {"orgs": {"A": {"label": "aggressive"}, "B": {"label": "typical"}, "C": {"label": "conservative"}}}
    timing = {"orgs": {"A": {"labelAggr": "old for level"}, "B": {"labelAggr": "young for level"},
                       "C": {"labelAggr": None}}}
    ot.align_promotion_label(promo, timing)
    assert [promo["orgs"][o]["label"] for o in "ABC"] == ["conservative", "aggressive", "typical"]
    ot.align_promotion_label(promo, {"orgs": {}})              # no timing panel: untouched
    assert promo["orgs"]["A"]["label"] == "conservative"


def test_sidecar_promotion_timing_shape_and_agreement():
    """Served artifact: 30 orgs, every figure with n and CI95, labels only on
    n-sufficient rows under q 0.10, and the promotion badge never disagrees
    with the tested age-for-level label."""
    d = _payload()
    pt = d.get("promotionTiming") or {}
    if not pt.get("orgs"):
        pytest.skip("promotionTiming not exported on this machine")
    assert set(pt["league"]) == PT_LEAGUE_KEYS
    assert d["windows"]["promotionTiming"].startswith("MLB debuts 2022-present")
    for org, r in pt["orgs"].items():
        assert set(r) == PT_ORG_KEYS, org
        assert r["lateCi"][0] <= r["lateShare"] <= r["lateCi"][1], org
        if r["labelTiming"]:
            assert not r["thin"] and r["qLate"] < 0.10, org
        if r["labelAggr"]:
            assert r["nAggrPlayers"] >= 40 and r["qAggr"] < 0.10, org
            assert r["aggrCi"][0] > 0 or r["aggrCi"][1] < 0, org
        want = {"young for level": "aggressive", "old for level": "conservative"}.get(r["labelAggr"], "typical")
        assert d["promotion"]["orgs"][org]["label"] == want, org
    for y, iso in pt["league"]["rookieCutoff"].items():
        assert int(y) >= 2020 and iso.startswith(y + "-08-"), (y, iso)


def _tendencies_js():
    src = (ROOT / "prospx" / "index.html").read_text(encoding="utf-8")
    i = src.index("function _otBadge(")
    return src[i:src.index("// Warm the org_tendencies sidecar", i)]


def test_prospx_promotion_timing_card_and_a11y():
    """PROSPX farm Tendencies tab: the Promotion timing card reads the tested
    labels and prints n and CI in text; card titles are h4 headings, the z
    tables carry row headers and a badge's receipt is a keyboard stop with an
    accessible description (QREA11)."""
    js = _tendencies_js()
    assert 'data-ot-card="${key}"' in js and '"promotion-timing"' in js
    assert "<h4 " in js and "${title}</h4>" in js
    assert '<th scope="row" data-no-sort' in js
    assert 'tabindex="0" aria-describedby=' in js and 'class="visually-hidden"' in js
    card = js[js.index("const ptCard"):js.index("const POSB")]
    assert "pt.labelAggr" in card and "pt.labelTiming" in card
    assert "Not distinguishable from the league" in card
    assert "nAggrPlayers" in card and "nDebuts" in card and "Ci" in card
    assert "Rule and sources" in card and "<details" in card
    assert "ETA" not in card, "the card must not say the ETA uses these numbers"
    assert "zYoung" not in card and "_label(" not in card, "no z cut feeds a promotion-timing badge"
