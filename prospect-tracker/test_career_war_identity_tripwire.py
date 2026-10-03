# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The fWAR label epoch's E2 tripwire (docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md part 3
row E2): every nonzero window season of a label row has a feed row under its bound id,
reported per side and debut cohort band.

Two halves. The fixture half pins the tripwire's mechanics offline (a kept row, a row whose
bound id has no feed row, an unbound row, an identity exclusion, the step C binding order).
The live half runs the tripwire on the tree (debuts.json, prospects.db career_war, the
frozen vintage) and fails on any failing label row that is not on the label-join file's
manual review list: a new label row with no id, or a binding to the wrong human, trips it.
Coverage only, never accuracy (clause (l)).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "tools"))

import efv_epoch_id_join as J   # noqa: E402


def _rec(key, debut, pos="RHP", mlbam=None, birth="1995-01-01"):
    return {"player_key": key, "player_name": key.replace("_", " ").title(),
            "mlbam_id": mlbam, "position": pos, "debut_date": debut, "birth_date": birth,
            "statline": {"is_pitcher": pos.endswith("HP")}}


DEBUTS = [
    _rec("kept_pit", "2018-06-01"),                    # bound, every nonzero season fed
    _rec("wrong_human", "2013-05-03", mlbam=830052),   # photos binds a 2020s prospect
    _rec("no_id", "2019-04-02", pos="OF"),             # no route at all
    _rec("zero_only", "2020-08-01", pos="OF"),         # nonzero seasons: none
    _rec("excluded", "2015-04-01"),                    # TRAINING_IDENTITY exclude
    _rec("outside", "2009-04-01"),                     # not a DEBUT_YEARS cohort
    _rec("no_row", "2021-04-01", pos="C"),             # no career_war row
]
CW = {
    "kept_pit": {"seasons": {"2018": 0.5, "2019": 1.2, "2020": 0.0, "2021": 2.0}, "source": "ewar_v2"},
    "wrong_human": {"seasons": {"2013": 1.1, "2014": 3.0, "2015": 2.2}, "source": "ewar_v2"},
    "no_id": {"seasons": {"2019": 0.4}, "source": "bbref"},
    "zero_only": {"seasons": {"2020": 0.0, "2021": 0.0}, "source": "ewar_v2"},
    "excluded": {"seasons": {"2015": 9.0}, "source": "ewar_v2"},
    "outside": {"seasons": {"2011": 1.0}, "source": "bbref"},
}
TOTALS = {(1001, 2018): 0.5, (1001, 2019): 1.2, (1001, 2021): 2.0,
          (593372, 2013): 1.1, (593372, 2014): 3.0, (593372, 2015): 2.2}
YEARS = list(range(2011, 2027))
IDENTITY = {"excluded": {"action": "exclude"}}


def _run(label_join=None, durable=None, overrides=None):
    return J.tripwire(DEBUTS, CW, TOTALS, YEARS, label_join or {}, durable or {},
                      overrides or {}, debut_years=tuple(range(2011, 2025)),
                      target_seasons=6, resolved_through=2025, identity=IDENTITY)


def test_fixture_before_repair_fires_on_the_wrong_human_and_the_unbound_row():
    out = _run(durable={"kept_pit": 1001, "wrong_human": 830052})
    assert out["label_rows"] == 4               # kept_pit, wrong_human, no_id, zero_only
    why = {r["player_key"]: r["why"] for r in out["rows"]}
    assert why == {"wrong_human": "bound id has no feed row", "no_id": "unbound"}
    wrong = next(r for r in out["rows"] if r["player_key"] == "wrong_human")
    assert wrong["seasons"] == [2013, 2014, 2015] and wrong["bound"] == 830052
    by = out["by"]
    assert by["pit|2017-2021"]["rows_kept"] == 1 and by["pit|2017-2021"]["nonzero_window_seasons"] == 3
    assert by["pit|2011-2016"]["rows_bound_no_feed"] == 1 and by["pit|2011-2016"]["seasons_bound_no_feed"] == 3
    assert by["hit|2017-2021"]["rows_unbound"] == 1 and by["hit|2017-2021"]["rows_no_nonzero_season"] == 1
    assert by["hit|2017-2021"]["rows_kept"] == 1          # zero_only is kept: nothing to feed
    assert by["hit|2017-2021"]["rows_no_career_war"] == 1  # no_row
    assert by["excluded_by_identity"]["rows"] == 1
    assert "pit|pre-2011" not in by                        # outside is not a label row


def test_fixture_after_repair_is_clean_and_the_label_join_wins_over_photos():
    out = _run(label_join={"wrong_human": 593372, "no_id": 777},
               durable={"kept_pit": 1001, "wrong_human": 830052})
    assert out["rows_failing"] == 1                        # no_id is bound to 777: no feed row
    assert out["rows"][0]["player_key"] == "no_id" and out["rows"][0]["how"] == "label_join"
    out = _run(label_join={"wrong_human": 593372},
               durable={"kept_pit": 1001, "wrong_human": 830052}, overrides={"no_id": 1002})
    assert out["rows_failing"] == 1 and out["rows"][0]["player_key"] == "no_id"
    assert out["rows"][0]["how"] == "override" and out["rows"][0]["bound"] == 1002
    # zero_only has no binding and nothing to feed: counted unbound, kept
    assert out["binding"] == {"photos": 1, "label_join": 1, "override": 1, "unbound": 1}


def test_the_step_c_binding_order_is_label_join_then_photos_then_override():
    assert J.resolve_bound("k", {"k": 1}, {"k": 2}, {"k": 3}) == (1, "label_join")
    assert J.resolve_bound("k", {}, {"k": 2}, {"k": 3}) == (2, "photos")
    assert J.resolve_bound("k", {}, {}, {"k": 3}) == (3, "override")
    assert J.resolve_bound("k", {}, {}, {}) == (None, None)


def test_bands_and_the_birth_validator():
    assert [J.band(y) for y in (2010, 2011, 2016, 2017, 2021, 2022, 2024, 2025)] == [
        "pre-2011", "2011-2016", "2011-2016", "2017-2021", "2017-2021", "2022-2024",
        "2022-2024", "2025+"]
    assert J.birth_plausible("1991-09-21", 2013) is True
    assert J.birth_plausible("2005-12-16", 2013) is False     # the collided record's date
    assert J.birth_plausible(None, 2013) is False


def test_pick_accepts_no_ambiguous_hit():
    cands = [{"id": 1, "mlbDebutDate": "2013-05-03", "birthDate": "1991-09-21"},
             {"id": 2, "mlbDebutDate": "2013-09-01", "birthDate": "1990-01-01"}]
    assert J.pick(cands, 2013, "2005-12-16")[0] == "ambiguous"   # implausible birth: void
    assert J.pick(cands, 2013, "1991-09-21") == ("accepted", (cands[0], "birth_date+debut_year"))
    assert J.pick(cands[:1], 2013, None) == ("accepted", (cands[0], "debut_year"))
    assert J.pick(cands, 2014, None)[0] == "none"


def test_the_receipt_reports_coverage_never_accuracy():
    path = HERE / "data" / "efv_epoch_id_join.json"
    if not path.exists():
        pytest.skip("data/efv_epoch_id_join.json not built")
    text = path.read_text(encoding="utf-8")
    doc = json.loads(text)
    assert doc["schema"] == J.SCHEMA
    assert not re.search(r"spearman|auc|\brho\b|ci95|delta\b", text, re.I)
    assert chr(0x2014) not in text and chr(0x2013) not in text
    kept = doc["kept"]["by_side_and_band"]
    assert kept and all({"before", "after"} <= set(v) for v in kept.values())
    assert all(re.fullmatch(r"(hit|pit)\|(2011-2016|2017-2021|2022-2024)", k) for k in kept)
    assert doc["kept"]["total"]["after"] >= doc["kept"]["total"]["before"]


def test_efv_identity_never_reads_the_label_join():
    src = (HERE / "efv_identity.py").read_text(encoding="utf-8")
    assert "mlbam_id_label_join" not in src and "efv_epoch_id_join" not in src


# ---------------------------------------------------------------------------
# the live tripwire

def _live_ready():
    import storage
    if not (J.DEBUTS.exists() and (HERE / "data" / "fwar_vintage.json").exists()):
        return False
    try:
        return bool(storage.load_career_war())
    except Exception:
        return False


def test_live_every_nonzero_window_season_has_a_feed_row_under_its_bound_id():
    """The E2 tripwire on the tree. A failing label row is allowed only when the
    label-join file lists it under manual review (no candidate debuted that year)."""
    if not _live_ready():
        pytest.skip("debuts.json, prospects.db career_war or data/fwar_vintage.json absent")
    out = J.run_tripwire_live()
    assert out["label_rows"] > 1000
    review = set()
    if J.LABEL_JOIN.exists():
        blob = json.loads(J.LABEL_JOIN.read_text(encoding="utf-8"))
        review = {r.get("player_key") for r in blob.get("manual_review") or []}
    unexplained = [r for r in out["rows"] if r["player_key"] not in review]
    assert not unexplained, (
        f"{len(unexplained)} label rows have a nonzero window season with no feed row under "
        f"their bound id and are not on the manual review list: "
        f"{[(r['player_key'], r['side'], r['debut_year'], r['bound'], r['seasons']) for r in unexplained[:12]]}")
    # every band and side reports; no band hides a failure the count missed
    for k, c in out["by"].items():
        if "|" in k and not k.startswith("unknown"):
            assert c.get("rows_unbound", 0) + c.get("rows_bound_no_feed", 0) == \
                sum(1 for r in out["rows"] if f"{r['side']}|{r['band']}" == k)
