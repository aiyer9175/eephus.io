# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Offline tests for draft_bonus (official MLB slot/bonus ingest).

Fully offline: every assertion runs off saved /draft/{year} sample payloads in
data/sources/samples/ and the module's pure parsing helpers -- no network. The
coverage boundary is the point of the module, so it is pinned explicitly: 2017+
picks carry the official slot/bonus, 2016 does not.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import draft_bonus as db

_SAMPLES = Path(__file__).resolve().parent / "data" / "sources" / "samples"

# The 2024 (money era) and 2016 (pre-coverage) recon payloads. Accept either the
# slot/bonus probe names or the original recon names, so the test survives a
# sample-file rename.
_Y2024 = ("draft_2024_slotbonus_probe.json", "draft_2024_01.json")
_Y2016 = ("draft_2016_slotbonus_probe.json", "draft_2016_coverage_03.json")


def _load_sample(names):
    for n in names:
        p = _SAMPLES / n
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
    pytest.skip(f"draft sample not present: {names}")


def _records(raw, year):
    """Build landed records off a raw payload using the module's own parser."""
    out = {}
    for pick in db.iter_picks(raw):
        rec = db._pick_record(pick, year)
        if rec is not None:
            mlbam, body = rec
            out[mlbam] = body
    return out


# --------------------------------------------------------------------------- #
# coverage boundary: 2017+ carries slot/bonus, 2016 does not
# --------------------------------------------------------------------------- #
def test_2024_person_id_present_on_essentially_every_pick():
    raw = _load_sample(_Y2024)
    picks = list(db.iter_picks(raw))
    assert len(picks) > 400, "expected a full 2024 draft board"
    with_id = sum(1 for p in picks if (p.get("person") or {}).get("id"))
    assert with_id / len(picks) >= 0.99, "person.id is the MLBAM join spine (~100%)"


def test_2024_signing_bonus_high_rate():
    """signingBonus lands on nearly every signed pick in the money era."""
    raw = _load_sample(_Y2024)
    recs = _records(raw, 2024)
    n = len(recs)
    with_bonus = sum(1 for r in recs.values() if r["bonus_usd"] is not None)
    assert with_bonus / n >= 0.85, f"only {with_bonus}/{n} carry signingBonus"


def test_2024_slot_present_and_full_within_slotted_rounds():
    """pickValue (slot) exists only where MLB assigns one -- rounds 1-10 plus the
    compensation/CB/PPI picks -- but within those it is essentially complete."""
    raw = _load_sample(_Y2024)
    recs = _records(raw, 2024)
    with_slot = sum(1 for r in recs.values() if r["slot_usd"] is not None)
    # A meaningful share of the whole board carries a slot...
    assert with_slot / len(recs) >= 0.40
    # ...and among the first ten (numeric) rounds it is near-total.
    early = [r for r in recs.values() if isinstance(r["round"], int) and r["round"] <= 10]
    assert early, "expected numeric rounds 1-10"
    early_slotted = sum(1 for r in early if r["slot_usd"] is not None)
    assert early_slotted / len(early) >= 0.95, "rounds 1-10 should be fully slotted"


def test_2016_is_the_pre_coverage_boundary():
    """2016 carries person + pick but NULL slot and NULL bonus (the boundary)."""
    raw = _load_sample(_Y2016)
    recs = _records(raw, 2016)
    assert len(recs) > 800, "expected a full 2016 draft board"
    assert all(r["slot_usd"] is None for r in recs.values()), "2016 has no slot"
    assert all(r["bonus_usd"] is None for r in recs.values()), "2016 has no bonus"
    assert all(r["pool_pct"] is None for r in recs.values())
    # person.id still present -- only the money is absent pre-2017.
    with_pick = sum(1 for r in recs.values() if r["pick_overall"] is not None)
    assert with_pick / len(recs) >= 0.95


# --------------------------------------------------------------------------- #
# pool_pct sanity
# --------------------------------------------------------------------------- #
def test_pool_pct_sane():
    """pool_pct = bonus/slot. It is non-negative, mostly within 0-3x, and its
    median sits near 1.0. A small tail above 3x is legitimate (a late-round pick
    signed well over its tiny slot from pool savings), so we bound the tail
    rather than forbid it."""
    raw = _load_sample(_Y2024)
    recs = _records(raw, 2024)
    ratios = [r["pool_pct"] for r in recs.values() if r["pool_pct"] is not None]
    assert len(ratios) >= 100, "expected a healthy set of slotted+signed picks"
    assert all(x >= 0 for x in ratios), "pool_pct is never negative"
    # No single pick is absurd (guards against a slot/bonus units mismatch).
    assert max(ratios) < 20, f"implausible pool_pct max {max(ratios)}"
    # The overwhelming majority sit inside the 0-3x band.
    in_band = sum(1 for x in ratios if 0 < x <= 3)
    assert in_band / len(ratios) >= 0.90, "bulk of pool_pct should be within 0-3x"
    # Median signs near slot (teams cluster around the assigned value).
    med = sorted(ratios)[len(ratios) // 2]
    assert 0.5 <= med <= 1.5, f"median pool_pct {med} outside a sane band"


# --------------------------------------------------------------------------- #
# parsing + dedup unit checks
# --------------------------------------------------------------------------- #
def test_num_parses_string_dollars():
    assert db._num("10570600") == 10570600.0
    assert db._num("8,950,000") == 8950000.0
    assert db._num(None) is None
    assert db._num("") is None
    assert db._num("0") is None          # zero-as-string reads as missing, not 0
    assert db._num("n/a") is None


def test_prefer_keeps_signed_then_latest():
    unsigned_new = {"year": 2021, "bonus_usd": None}
    signed_old = {"year": 2019, "bonus_usd": 500000.0}
    # A signed record beats a later unsigned one.
    assert db._prefer(unsigned_new, signed_old) is signed_old
    assert db._prefer(signed_old, unsigned_new) is signed_old
    # Among two signed records, the later year wins.
    signed_new = {"year": 2022, "bonus_usd": 100.0}
    assert db._prefer(signed_old, signed_new) is signed_new


# --------------------------------------------------------------------------- #
# offline join helper
# --------------------------------------------------------------------------- #
def test_bonus_slot_for_reads_landed_json(tmp_path, monkeypatch):
    """bonus_slot_for is a pure read of the landed JSON: int/str ids resolve,
    unknown ids return None, and it never touches the network."""
    raw = _load_sample(_Y2024)
    recs = {str(k): v for k, v in _records(raw, 2024).items()}
    landed = tmp_path / "draft_bonus_slot.json"
    landed.write_text(json.dumps(recs), encoding="utf-8")

    monkeypatch.setattr(db, "DATA_OUT", landed)
    monkeypatch.setattr(db, "_CACHE", {"mtime": None, "data": None})

    known = int(next(iter(recs)))
    assert db.bonus_slot_for(known) is not None
    assert db.bonus_slot_for(str(known)) == db.bonus_slot_for(known)
    rec = db.bonus_slot_for(known)
    assert set(rec) == {"year", "pick_overall", "round", "slot_usd", "bonus_usd", "pool_pct"}
    assert db.bonus_slot_for(-1) is None
    assert db.bonus_slot_for(None) is None


def test_bonus_slot_for_missing_file_is_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATA_OUT", tmp_path / "does_not_exist.json")
    monkeypatch.setattr(db, "_CACHE", {"mtime": None, "data": None})
    assert db.bonus_slot_for(683953) is None
