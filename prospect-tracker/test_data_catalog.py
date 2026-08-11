# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The /sources/ catalog guard - the fields that render BLIND.

WHY THIS FILE EXISTS. data_catalog.ARTIFACTS is a hand-written tuple of dicts
and three of its keys are read with a BARE SUBSCRIPT on the render path:

    data_catalog.counts()        r["stability"]     (data_catalog.py)
    data_catalog.rows_by_group() r["group"]         (data_catalog.py)
    build_site._artifact_card()  row["cadence"], row["stability"],
                                 row["title"], row["what"], row["url"]

A row that omits one of them does not degrade to a blank cell. It raises
KeyError inside the /sources/ page builder and the whole page stops building,
which has already cost one outage. The value matters as much as the presence:
`stability` is compared against data_catalog.STABLE to choose the tier note, so
a row that says "STABLE" or "solid" instead of the constant silently renders the
experimental warning under a stable file.

This file asserts the PROPERTY over every row, and test_the_guard_is_live
MUTATES a row to prove the assertion actually fires (a guard that cannot go red
is not a guard). The same property is also asserted from
test_betting_learning.py, which is where it landed first; the duplication is
deliberate for now, since the invariant belongs to the catalog rather than to
the betting lane and a betting-file rename must not silently drop it.
"""

from __future__ import annotations

import pytest

import data_catalog as dc

# Every key the render path subscripts with no .get() and no default.
# data_catalog.counts / rows_by_group take the first two; build_site
# ._artifact_card takes the rest off the row catalog_rows() returns.
BARE_SUBSCRIPTS_ON_ARTIFACTS = ("stability", "group")
BARE_SUBSCRIPTS_ON_RENDERED_ROWS = ("stability", "group", "cadence", "title",
                                    "what", "url", "size_label")

GROUP_KEYS = {k for k, _ in dc.GROUPS}
CADENCES = ("daily", "monthly", "on change")


def _violations(row: dict) -> list[str]:
    """The check, factored out so the mutation test can call it directly."""
    bad = []
    if row.get("stability") not in (dc.STABLE, dc.EXPERIMENTAL):
        bad.append(f"stability={row.get('stability')!r}")
    if row.get("group") not in GROUP_KEYS:
        bad.append(f"group={row.get('group')!r}")
    if row.get("cadence") not in CADENCES:
        bad.append(f"cadence={row.get('cadence')!r}")
    return bad


def test_every_row_carries_stability_group_and_cadence():
    """THE OUTAGE GUARD. A row missing any of these kills /sources/."""
    broken = {a.get("file"): _violations(a) for a in dc.ARTIFACTS if _violations(a)}
    assert not broken, (
        "catalog rows whose blind-rendered fields are missing or off-enum "
        f"(stability must be data_catalog.STABLE/EXPERIMENTAL, group one of "
        f"{sorted(GROUP_KEYS)}, cadence one of {list(CADENCES)}): {broken}")


def test_rows_carry_exactly_the_authored_key_set():
    """A stray key is a typo that the render path will never show, and a
    missing one is the outage above. Pin the set."""
    expected = {"file", "group", "title", "what", "cadence", "stability",
                "pinned_by", "note"}
    for a in dc.ARTIFACTS:
        assert set(a) == expected, (a.get("file"), sorted(set(a) ^ expected))


def test_rendered_rows_carry_every_bare_subscript():
    """catalog_rows() is what build_site actually renders. Assert on the
    OUTPUT, not only on the authored tuple: url/bytes/size_label are added
    there, and _artifact_card subscripts them bare too."""
    rows = dc.catalog_rows()
    assert rows, "catalog rendered zero rows"
    for r in rows:
        for key in BARE_SUBSCRIPTS_ON_RENDERED_ROWS:
            assert key in r, (r.get("file"), key)
        assert not _violations(r), (r.get("file"), _violations(r))


def test_the_guard_is_live(monkeypatch):
    """MUTATION. Drop `stability` from one row and prove three things go red:
    the property check above, data_catalog.counts(), and rows_by_group() (the
    two functions /sources/ calls before it renders anything).

    If this test ever passes without the pytest.raises firing, the guard has
    stopped guarding."""
    good = next(a for a in dc.ARTIFACTS if a["file"] == "timeseries.json")

    # 1. the property check catches a dropped key
    mutated = {k: v for k, v in good.items() if k != "stability"}
    assert _violations(mutated) == ["stability=None"]

    # 2. and an off-enum VALUE, which is the subtler defect: present, renders,
    #    and silently flips the tier note under the file.
    assert _violations({**good, "stability": "STABLE"}) == ["stability='STABLE'"]
    assert _violations({**good, "group": "prospect"}) == ["group='prospect'"]
    assert _violations({**good, "cadence": "nightly"}) == ["cadence='nightly'"]

    # 3. the real render path dies rather than degrading
    monkeypatch.setattr(dc, "ARTIFACTS", (mutated,) + tuple(dc.ARTIFACTS[1:]))
    with pytest.raises(KeyError):
        dc.counts()

    monkeypatch.setattr(
        dc, "ARTIFACTS",
        ({k: v for k, v in good.items() if k != "group"},) + tuple(dc.ARTIFACTS[1:]))
    with pytest.raises(KeyError):
        dc.rows_by_group()


# Rows that DECLARE a pinned_by whose named test does not mention the artifact
# by name, so _pin_receipt returns "" and the page renders no receipt at all.
# Measured 2026-08-10. This is not the outage class: the page degrades to
# silence exactly as designed, and it is the right degradation. It is a
# documentation defect, because the tuple in data_catalog.py claims a pin that
# the rendered page cannot show.
#
# A RATCHET, not an allowlist to grow. The fix for a line here is one of two
# things, and neither of them is repointing pinned_by at whatever test happens
# to mention the filename: either make the named test assert the shape and name
# the artifact while it does so, or clear the claim to "". test_publish_manifest
# names xfv_ungraded.json and test_betting_learning names betting_shadow.json,
# but a publish-manifest check and a sibling lane's fixture are not shape pins,
# and pointing the receipt at them would manufacture the exact citation this
# mechanism exists to prevent.
#
# EMPTIED 2026-08-10. All four were healed the way the paragraph above demands:
# each named test gained a real shape assertion that names its artifact, so the
# /sources/ receipt now resolves. None was repointed at a test that merely
# happened to mention the filename. The set stays here, empty, because it is the
# ratchet - a new entry is how a regression would announce itself, and deleting
# the mechanism because it currently holds nothing would delete the guard.
PINS_THAT_RENDER_AS_NOTHING: frozenset[str] = frozenset()


def test_no_new_pin_receipt_that_is_a_citation_to_nothing():
    """`pinned_by` is only rendered when the named test exists AND mentions the
    artifact by name. A row that declares one and gets an empty receipt back is
    claiming a shape pin the page cannot show."""
    empty = {a["file"] for a in dc.ARTIFACTS
             if (a.get("pinned_by") or "")
             and not dc._pin_receipt(a["pinned_by"], a["file"])}
    new = sorted(empty - PINS_THAT_RENDER_AS_NOTHING)
    assert not new, (
        "catalog rows whose pinned_by does not resolve (the named test never "
        f"mentions the artifact, so the receipt renders as nothing): {new}. "
        "Name the artifact in the test that pins it, or clear the claim.")
    healed = sorted(PINS_THAT_RENDER_AS_NOTHING - empty)
    assert not healed, (
        f"these pins now resolve: {healed}. Delete them from "
        "PINS_THAT_RENDER_AS_NOTHING so the ratchet keeps tightening.")


def test_a_catalogued_file_is_never_one_the_deploy_withholds():
    """A row for an excluded file advertises a URL that 404s in production."""
    withheld = dc.excluded_files()
    bad = [a["file"] for a in dc.ARTIFACTS if a["file"] in withheld]
    assert not bad, bad


def test_the_source_accuracy_measurement_is_catalogued():
    """Served at /glossary/#view=source-accuracy and fetched by the client, so
    it is a published artifact and belongs in the table."""
    row = next((a for a in dc.ARTIFACTS
                if a["file"] == "source_cohort_accuracy.json"), None)
    assert row is not None, "source_cohort_accuracy.json is not catalogued"
    assert row["stability"] == dc.EXPERIMENTAL
    assert row["group"] == "prospects"
    assert dc._pin_receipt(row["pinned_by"], row["file"]) == "test_source_cohort_accuracy.py"
