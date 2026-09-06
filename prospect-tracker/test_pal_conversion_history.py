"""The Alchemy Lab conversion history: the arithmetic a reader can do on screen.

THE DEFECT. `pre_war` and `post_war` were each rounded to a tenth for display while
`war_delta` was computed on the UNROUNDED pair and rounded afterwards. On 23 of 115 served
rows a reader subtracting the two numbers in front of them got a different answer from the
coloured delta between them. Reynaldo Lopez read 3.8 to 0.5 with a delta of -3.2, and one
row showed the same number twice with a red loss between them.

It is the same shape as the playoff-odds defect fixed the same day: parts rounded
independently of the whole, and nothing asserting they agree.

THE SECOND HALF. The display-rounded delta was ALSO what fed the rank correlation. Rounding
an outcome to a tenth manufactures tie groups, and this is the outcome variable behind the
one direction that carries this model's PASS verdict, so the fix splits them: the DISPLAYED
delta is the difference of the DISPLAYED parts, and the STATISTIC gets the exact value.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

ART = ROOT / "data" / "pal.json"


@pytest.fixture(scope="module")
def hist():
    if not ART.exists():
        pytest.skip("run python pal_export.py")
    d = json.loads(ART.read_text(encoding="utf-8"))
    h = d.get("history") or []
    if not h:
        pytest.skip("no conversion history")
    return h


def test_the_printed_delta_is_the_difference_of_the_printed_numbers(hist):
    """THE DEFECT. A reader subtracting the two WAR numbers on screen must get
    the delta shown between them."""
    bad = []
    for r in hist:
        pre, post, dlt = r.get("pre_war"), r.get("post_war"), r.get("war_delta")
        if None in (pre, post, dlt):
            continue
        if abs((post - pre) - dlt) > 1e-9:
            bad.append((r.get("name"), pre, post, dlt, round(post - pre, 3)))
    assert not bad, (
        f"{len(bad)} rows print a delta that is not the difference of the two "
        f"numbers beside it: {bad[:5]}")


def test_the_exact_delta_is_carried_separately_for_the_statistic(hist):
    """Rounding an outcome to a tenth manufactures ties, and this is the outcome
    variable behind the model's only PASS verdict."""
    have = [r for r in hist if r.get("war_delta_exact") is not None]
    assert len(have) > 50, "the exact delta is not being carried"
    unrounded = [r for r in have
                 if abs(r["war_delta_exact"] - round(r["war_delta_exact"], 1)) > 1e-9]
    assert unrounded, (
        "every exact delta is already a round tenth, which means the display "
        "value is being copied into the statistic again")


def test_the_correlation_reads_the_exact_delta_and_not_the_display_value():
    src = (ROOT / "pal_export.py").read_text(encoding="utf-8")
    i = src.index('per_dir[e["direction"]]["war"].append')
    assert 'war_delta_exact' in src[i:i + 120], (
        "the rank correlation is being fed the display-rounded delta, which "
        "manufactures tie groups in its own outcome variable")


def test_a_row_never_shows_two_equal_numbers_with_a_nonzero_delta(hist):
    """The most visible form of the defect: 0.3 to 0.3 with a red -0.1."""
    bad = [(r.get("name"), r.get("pre_war"), r.get("war_delta"))
           for r in hist
           if r.get("pre_war") is not None
           and r.get("pre_war") == r.get("post_war")
           and (r.get("war_delta") or 0) != 0]
    assert not bad, f"equal WAR numbers with a non-zero delta between them: {bad[:5]}"


def test_the_in_progress_rows_are_flagged(hist):
    """A partial 2026 season deflates WAR mechanically, and the exporter already
    excludes those rows from its own correlation for exactly that reason. The
    flag has to reach the payload so the renderer can say so too."""
    assert any(r.get("in_progress") for r in hist), (
        "no row is flagged in_progress, so a partial season is being coloured "
        "as a completed result")


# --------------------------------------------------------------------------
# The published rho, its basis, and the sign that changes between them
# --------------------------------------------------------------------------

def _entry(gid):
    import json
    g = json.loads((ROOT / "data" / "glossary.json").read_text(encoding="utf-8"))
    for e in g["entries"]:
        if e["id"] == gid:
            return e
    pytest.skip(f"glossary entry {gid} is absent")


def test_the_glossary_names_both_bases_wherever_it_quotes_a_rho():
    """THE DEFECT. These entries named the eWAR basis in their own methodology
    sentence and then quoted the bWAR gate figures. On the RP to SP direction
    that published MINUS 0.21 for a statistic that is PLUS 0.024 on the series
    named beside it: opposite signs, wrong attribution.

    Neither figure is wrong in itself. The gate really was run on bWAR and that
    is the registered gate; the page really does serve eWAR v2. Only the
    attribution was wrong, so the fix is to name both.
    """
    for gid in ("pal_conversion", "rp_sp_fit", "sp_rp_fit"):
        m = _entry(gid).get("methodology") or ""
        assert "bWAR" in m and "eWAR" in m, (
            f"{gid} quotes a correlation without naming which WAR series it was "
            "measured on")


def test_the_reliever_to_starter_entry_says_the_sign_changes():
    m = _entry("rp_sp_fit").get("methodology") or ""
    assert "+0.024" in m, "the eWAR value is not published beside the bWAR one"
    assert "SIGN" in m or "sign" in m


def test_the_two_bases_really_do_disagree_in_sign():
    """The artifact check behind the copy. If a re-run ever brings the two into
    agreement, this fails and the wording can be simplified deliberately."""
    import json
    d = json.loads((ROOT / "data" / "pal.json").read_text(encoding="utf-8"))
    bt = d.get("backtest") or {}
    live = ((bt.get("per_direction") or {}).get("RP->SP") or {}).get(
        "rho_prefit_vs_war_delta")
    gate = (((bt.get("gate") or {}).get("per_direction") or {}).get("RP->SP") or {}).get(
        "rho_fit_war_delta")
    if live is None or gate is None:
        pytest.skip("one of the two rhos is absent")
    assert live * gate < 0, (
        f"the two bases now agree in sign (live {live}, gate {gate}); the "
        "glossary wording about a sign change should be revisited")


def test_the_module_records_that_the_bases_differ():
    import json
    d = json.loads((ROOT / "data" / "pal.json").read_text(encoding="utf-8"))
    gate = (d.get("backtest") or {}).get("gate") or {}
    assert gate.get("same_basis_as_live") is False, (
        "the gate and the live series now share a basis, which would make the "
        "two-basis disclosure unnecessary")
