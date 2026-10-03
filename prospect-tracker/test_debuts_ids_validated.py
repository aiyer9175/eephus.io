# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Every id the fWAR epoch's identity join landed (E2, tools/efv_epoch_id_join.py) carries
StatsAPI evidence whose debut year and, where the record's birth date is a valid
validator, birth date match the record; the landed ids are the ones debuts.json serves;
zero ambiguous hits were accepted. Offline: the evidence is stored beside each entry in
data/sources/mlbam_id_label_join.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "tools"))

LABEL_JOIN = HERE / "data" / "sources" / "mlbam_id_label_join.json"
DEBUTS = HERE / "data" / "debuts.json"
OVERRIDES = HERE / "data" / "sources" / "mlbam_id_overrides.json"


@pytest.fixture(scope="module")
def blob():
    if not LABEL_JOIN.exists():
        pytest.skip("data/sources/mlbam_id_label_join.json not built")
    return json.loads(LABEL_JOIN.read_text(encoding="utf-8"))


def _entries(blob):
    return blob.get("entries") or {}


def test_every_entry_carries_statsapi_evidence_that_matches_the_record(blob):
    import efv_epoch_id_join as J
    bad = []
    for k, e in _entries(blob).items():
        s, r = e.get("statsapi") or {}, e.get("record") or {}
        if not (s.get("fullName") and s.get("mlbDebutDate") and s.get("fetched_at")):
            bad.append((k, "no evidence"))
            continue
        if s["mlbDebutDate"][:4] != str(r.get("debut_year")):
            # an exact birth-date acceptance may sit one year off a debut year that was
            # read off the first career_war season (not a debut date): that year is a
            # first WAR season, and the pattern's birth-date rule accepted the id
            lenient = (e.get("route") == "birth_date"
                       and r.get("debut_year_source") == "first career_war season"
                       and abs(int(s["mlbDebutDate"][:4]) - int(r.get("debut_year"))) <= 1)
            if not lenient:
                bad.append((k, "debut year", s["mlbDebutDate"], r.get("debut_year")))
        v = r.get("birth_validator")
        if v == "record":
            if not J.birth_plausible(r.get("birth_date"), r.get("debut_year")):
                bad.append((k, "validator says record but the date is implausible"))
            if s.get("birthDate") != r.get("birth_date"):
                bad.append((k, "birth date", s.get("birthDate"), r.get("birth_date")))
        elif v == "void":
            assert not J.birth_plausible(r.get("birth_date"), r.get("debut_year")), k
        elif v == "collision":
            # the record's birth date is the photos-bound human's, read from StatsAPI
            c = r.get("collision") or {}
            assert e.get("set") == "photos_no_feed_row" and c.get("photos_mlbam") == e.get("replaces_photos"), k
            assert c.get("birthDate") == r.get("birth_date") and s.get("birthDate") != r.get("birth_date"), k
        else:
            bad.append((k, "no birth validator recorded"))
        assert int(e["mlbam"]) > 0
    assert not bad, bad[:12]


def test_no_ambiguous_hit_was_accepted(blob):
    routes = {e.get("route") for e in _entries(blob).values()}
    assert routes <= {"override_revalidated", "debut_year", "birth_date",
                      "birth_date+debut_year", "record_id_validated"}, routes
    for r in blob.get("manual_review") or []:
        assert r.get("status") and r.get("player_key")
        assert r["player_key"] not in _entries(blob)


def test_the_override_asset_was_revalidated_in_full(blob):
    if not OVERRIDES.exists():
        pytest.skip("override asset absent")
    ov = json.loads(OVERRIDES.read_text(encoding="utf-8"))
    reval = {k: e for k, e in _entries(blob).items() if e.get("set") == "override_asset"}
    assert reval
    assert all(int(ov[k]) == int(e["mlbam"]) for k, e in reval.items())
    c = (blob.get("counts") or {}).get("override_asset") or {}
    assert c.get("validated") == len(reval) and c.get("rejected", 0) == \
        sum(1 for r in blob.get("manual_review") or [] if r.get("set") == "override_asset")


def test_a_replaced_photos_binding_names_the_id_it_replaces(blob):
    for k, e in _entries(blob).items():
        if e.get("set") == "photos_no_feed_row":
            assert e.get("replaces_photos") and int(e["replaces_photos"]) != int(e["mlbam"]), k
            assert e.get("landed_in_debuts") is False, k   # the label join only, never the record


def test_the_landed_ids_are_the_ones_debuts_json_serves(blob):
    """Where the served sidecar is on disk: each landed entry's record carries that id and
    the record's debut year is the one the evidence was checked against."""
    if not DEBUTS.exists():
        pytest.skip("data/debuts.json not built")
    import efv_dataset as D
    rec_by = {r.get("player_key"): r for r in json.loads(DEBUTS.read_text(encoding="utf-8"))}
    landed = {k: e for k, e in _entries(blob).items() if e.get("landed_in_debuts")}
    assert landed
    bad = []
    for k, e in landed.items():
        rec = rec_by.get(k)
        if rec is None:
            bad.append((k, "not in debuts.json"))
            continue
        if int(rec.get("mlbam_id") or 0) != int(e["mlbam"]):
            bad.append((k, "record id", rec.get("mlbam_id"), e["mlbam"]))
        dd, _ph, _frm = D.debut_day_for_cutoff(rec)
        if not dd or int(dd[:4]) != int(e["record"]["debut_year"]):
            bad.append((k, "record debut year", dd, e["record"]["debut_year"]))
    assert not bad, bad[:12]
    assert (blob.get("landed") or {}).get("landed") == len(landed)


def test_the_file_has_no_dash_copy(blob):
    text = LABEL_JOIN.read_text(encoding="utf-8")
    assert chr(0x2014) not in text and chr(0x2013) not in text
