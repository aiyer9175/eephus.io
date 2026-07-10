"""Glossary reclamation invariants (Section B): every entry declares a shelf,
every Arkmetric and every industry metric carries an origin line, and the shelf
values stay in the three-shelf enum. This closes the "reclaim the glossary" loop
so a reader always knows whether a metric is ours or borrowed.
"""
import json
import io

SHELVES = {"ark", "industry", "foundation"}


def _glossary():
    return json.load(io.open("data/glossary.json", encoding="utf-8"))


def test_every_entry_has_a_valid_shelf():
    g = _glossary()
    bad = [e["id"] for e in g["entries"] if e.get("shelf") not in SHELVES]
    assert not bad, f"entries missing a valid shelf: {bad}"


def test_ark_and_industry_entries_are_credited():
    g = _glossary()
    missing = [e["id"] for e in g["entries"]
               if e.get("shelf") in ("ark", "industry") and not e.get("origin")]
    assert not missing, (
        "ark/industry entries with no origin credit (must say 'Arkmetric, "
        f"original to eephus.io' or name the creator): {missing}")


def test_arkmetric_origin_names_the_platform():
    g = _glossary()
    for e in g["entries"]:
        if e.get("shelf") == "ark":
            assert "eephus.io" in (e.get("origin") or ""), e["id"]


def test_added_missing_entries_present():
    g = _glossary()
    ids = {e["id"] for e in g["entries"]}
    for slug in ("xwoba", "babip", "vaa"):
        assert slug in ids, f"missing displayed-metric entry: {slug}"
