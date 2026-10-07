# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""ONE control-window vocabulary, asserted (owner report 2026-09-17).

"Junior Caminero says he is signed through 2026 because he is a prearb/arb
player, but this is not accurate. He should be signed through the length of his
arbitration/pre-arbitration years across all modules."

The repair is a derived field (`salary_path.control_end` -> `ctrlThru`) plus one
vocabulary. This file pins the properties that make the vocabulary mean
something; the served cross-module coherence is its own file
(test_served_control_window_coherence.py) because that one has to run against
served artifacts in the nightly, not only in CI.

What is NOT asserted here, deliberately: that `ctrlThru` is CORRECT. Correctness
needs the horizon to be scored and it never has been - GATE C2's `gate_c2` block
is absent from the served eval artifact, the registry row reads provisional, and
clause C9' joins on a board field whose served census reports `sv_rows: 0`. This
file asserts that the site is COHERENT and never understates what its own money
says. That is a smaller claim and it is the one the evidence supports.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import salary_path as sp

ROOT = Path(__file__).parent


def _doc(name):
    p = ROOT / "data" / name
    if not p.exists():
        pytest.skip(f"data/{name} not built")
    return json.loads(p.read_text("utf-8"))


def _vets():
    return [v for v in (_doc("mlb_projections.json").get("vets") or []) if v.get("key")]


def _window():
    d = _doc("mlb_projections.json")
    return int(d["first_season"]), int(d["horizon"])


# --------------------------------------------------------------- the unit ---
def _path(last_controlled, **kw):
    p = {"last_controlled": last_controlled, "truncated": None,
         "closure_buyout": False, "src_mix": None}
    p.update(kw)
    return p


def test_control_end_is_never_shorter_than_the_guarantee():
    """THE one-line property everything else rests on. Club control cannot be
    shorter than a signed contract, and `salThru` regularly is: it is
    horizon-capped (Ohtani `thru` 2033 reads `salThru` 2031) and it stops where
    the published arbitration grid stops. 481 served rows printed a year EARLIER
    than the last season their own surplus priced before this change."""
    # the unit, at the two edges that produced the defect
    assert sp.control_end(_path(2031), 2033, 2027, 5)["end"] == 2033
    assert sp.control_end(_path(2030), 2026, 2027, 5)["end"] == 2030
    assert sp.control_end(_path(None), 2028, 2027, 5)["end"] == 2028
    assert sp.control_end(_path(None), None, 2027, 5)["end"] is None
    # and the served population
    for v in _vets():
        if v.get("ctrlThru") is None:
            assert not v.get("thru") and not v.get("salThru"), v["key"]
            continue
        assert v["ctrlThru"] >= (v.get("thru") or 0), v["key"]
        assert v["ctrlThru"] >= (v.get("salThru") or 0), v["key"]


def test_an_open_window_never_names_an_end():
    """`ctrlOpen` marks an INFORMATION failure, not a horizon failure: the
    platform knows more controlled seasons exist and cannot name them, so the
    year is a FLOOR. The cell renders `YYYY+` and the copy says "at least".

    The alternative, leaving those rows at their guarantee year, is the defect
    being fixed; the other alternative, guessing the arbitration start from age,
    is what salary_path.class_closure refuses to do without service time."""
    assert sp.control_end(_path(2028, truncated="prearb_grid"), 2026, 2027, 5)["open"] is True
    assert sp.control_end(_path(2029, truncated="no_prior_salary"), None, 2027, 5)["open"] is True
    assert sp.control_end(_path(2030), 2026, 2027, 5)["open"] is False
    # A CLOSURE BUY-OUT IS NOT AN INFORMATION FAILURE. Where a contract covers
    # the whole published grid AND the grid ended on an ARB rung, the next
    # season is FREE AGENCY: "through at least 2028" would assert controlled
    # seasons that do not exist, on a row whose surplus correctly stops. This
    # assertion used to read `is True`, so the gate defended the falsehood; it
    # cost nothing to hold because both served buy-out rows end on a
    # pre-arbitration token, and the FIRST club that extends an
    # arbitration-eligible player through his last arbitration year is the case.
    buy = sp.control_end(_path(2028, closure_buyout=True), 2028, 2027, 5)
    assert buy["open"] is False and buy["why"] == "closure_buyout", buy
    # The pre-arbitration half of the same case is still open, through the
    # reason that actually knows it: `truncated`, which salary_path stamps on
    # exactly those rows.
    both = sp.control_end(_path(2028, closure_buyout=True, truncated="prearb_grid"),
                          2028, 2027, 5)
    assert both["open"] is True and both["why"] == "prearb_grid", both
    n = 0
    for v in _vets():
        if not v.get("ctrlOpen"):
            continue
        n += 1
        assert v.get("salTrunc"), v["key"]
        assert v.get("ctrlWhy") in ("prearb_grid", "no_prior_salary"), v["key"]
        assert v.get("ctrlThru") is not None, v["key"]
    print(f"open control windows on the served board: {n}")


def test_a_horizon_clamped_row_never_claims_a_control_end():
    """A horizon failure is a statement about the five seasons this platform
    prices, not about the player. Those rows print a PLAIN year and the detail
    line suppresses its "club control window through YYYY" clause entirely.

    0 live rows are both horizon-clamped and estimate-basis today. One more
    class-closure rung or a longer horizon trips it, which is why this is a
    test and not a comment - and why the CELL now handles the case as well
    (`ctPill` renders `YYYY+` and "through at least" when `ctrlWhy` is horizon
    on an estimated basis), so the population staying empty is the second line
    of defence and not the only one."""
    first, H = _window()
    last = first + H - 1
    ce = sp.control_end(_path(last), last, first, H)
    assert ce["why"] == "horizon" and ce["open"] is False
    bad = [v["key"] for v in _vets()
           if v.get("ctrlWhy") == "horizon" and v.get("ctrlEst")]
    assert not bad, ("horizon-clamped rows on an estimated basis would print a "
                     f"control end the platform cannot source: {bad[:5]}")


# ------------------------------------------------------- the vocabulary ------
_JS = sorted((ROOT / "assets").glob("*.js")) + [ROOT / "prospx" / "index.html"]

#: "signed"/"guaranteed" attached to a CONTROL field, inside one interpolation.
_GUAR_ON_CTRL = re.compile(
    r"(?:signed|guaranteed)\s+(?:thru|through)[^`${]{0,12}\$\{[^}]*"
    r"(?:ctrlThru|salThru|control_thru)", re.I)
#: "club control" attached to the GUARANTEE field, inside one interpolation.
_CTRL_ON_GUAR = re.compile(
    r"club control\s+(?:thru|through)[^`${]{0,12}\$\{[^}]*"
    r"(?<![A-Za-z_])thru\b", re.I)


def test_the_guarantee_word_is_reserved():
    """The vocabulary rule, made mechanical: the words "signed" and
    "guaranteed" belong to `thru`, and "club control" belongs to `ctrlThru`.
    Neither may be attached to the other. This is the whole disclosure
    argument - a projected arbitration award is not a signed deal - reduced to
    something a future edit trips over."""
    bad = []
    for p in _JS:
        if not p.exists():
            continue
        for i, line in enumerate(p.read_text("utf-8").splitlines(), 1):
            if _GUAR_ON_CTRL.search(line):
                bad.append(f"{p.name}:{i}: guarantee word on a control field")
            if _CTRL_ON_GUAR.search(line):
                bad.append(f"{p.name}:{i}: 'club control' on the guarantee field")
    assert not bad, "\n".join(bad)


_QUALIFIED = ("club control window", "7-season valuation window",
              "6-season valuation window", "legacy 6-season valuation window",
              "controlled-core window")


#: Every surface whose STRINGS ARE SERVED VERBATIM. `_JS` alone missed four of
#: them, which is how "6yr cost-controlled", "control-window NPV" and the trade
#: machine glossary entry survived the pass that retired them.
def _copy_surfaces():
    out = sorted((ROOT / "assets").glob("*.js"))
    out += [ROOT / "prospx" / "index.html",
            ROOT / "collegesavant" / "index.html",
            ROOT / "collegesavant" / "pitcher_index.html",
            ROOT / "data" / "glossary.json"]
    return [p for p in out if p.exists()]


def test_no_surface_uses_control_window_unqualified():
    """"Control window" named a 4-season, a 6-season and a 7-season window on
    three surfaces of the same player on the same afternoon. Nobody was lying;
    the phrase was doing three jobs. Every occurrence now carries the qualifier
    that says which object it means.

    PER OCCURRENCE, AND BOTH SPELLINGS. The first version of this gate skipped
    an entire LINE whenever it contained the hyphenated form, which is true of
    exactly the lines that were wrong - the trade machine glossary entry used
    "control-window NPV" and "the control window" in one sentence and the gate
    read the first, shrugged, and passed the second."""
    bad = []
    for p in _copy_surfaces():
        for i, line in enumerate(p.read_text("utf-8").splitlines(), 1):
            stripped = line.strip()
            # Source COMMENTS are not served copy, and this rule is about what a
            # reader is SHOWN: a comment that names the phrase in order to
            # explain the rule would be the rule eating itself.
            if stripped[:2] in ("//", "/*") or stripped[:1] == "*":
                continue
            # A glossary ALIAS is a lookup key, not a sentence. A reader who
            # types "control window" has to find the entry that defines it.
            if stripped.rstrip(",").strip('"').lower() in (
                    "control window", "club control", "control window salary",
                    "club control thru"):
                continue
            low = line.lower()
            for form in ("control window", "control-window"):
                start = 0
                while True:
                    j = low.find(form, start)
                    if j < 0:
                        break
                    start = j + 1
                    seg = low[max(0, j - 34):j + len(form)]
                    if any(q in seg or q.replace(" ", "-") in seg
                           for q in _QUALIFIED):
                        continue
                    bad.append(f"{p.name}:{i}: {line.strip()[:120]}")
    assert not bad, "unqualified 'control window':\n" + "\n".join(bad[:12])


def test_the_page_shells_name_the_window_too():
    """/projections/ and /sources/ are SERVER-RENDERED: the subtitle a reader
    sees and the three meta descriptions a link preview shows live in
    build_site.py and data_catalog.py, where no grep over assets/ could reach
    them. All four said "surplus over the control window" on a page whose own
    board prices a club control window and whose prospects are priced over a
    7-season valuation window."""
    bad = []
    for rel in ("build_site.py", "data_catalog.py"):
        p = ROOT / rel
        if not p.exists():
            continue
        for i, line in enumerate(p.read_text("utf-8").splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            low = line.lower()
            for form in ("control window", "control-window"):
                j = low.find(form)
                while j >= 0:
                    seg = low[max(0, j - 34):j + len(form)]
                    if not any(q in seg or q.replace(" ", "-") in seg
                               for q in _QUALIFIED):
                        bad.append(f"{rel}:{i}: {line.strip()[:120]}")
                    j = low.find(form, j + 1)
    assert not bad, "unqualified 'control window' in a served shell:\n" + "\n".join(bad[:8])


def test_the_valuation_curve_label_is_qualified_at_both_ends():
    """The /glossary/ Methodology view prints `war_window` from
    data/xfv_valuation_curve.json VERBATIM, and that artifact said "7yr control
    window (published ctrl_war basis)" - the bare phrase, on the page a reader
    reaches from the board that prices a different window. Fixing the renderer
    alone would strand the served artifact until the next eFV export; fixing
    the writer alone would strand every reader until then. Both halves are
    asserted, because either one alone leaves the string on the page."""
    ef = (ROOT / "efv_export.py").read_text("utf-8")
    assert '"war_window": "7-season valuation window' in ef, (
        "efv_export still stamps the bare phrase into the valuation curve")
    gj = (ROOT / "assets" / "glossary.js").read_text("utf-8")
    assert "_windowLabel" in gj and "yr control window" in gj, (
        "the glossary no longer maps the legacy war_window label")


# ------------------------------------------------------------- the payload ---
def test_prospects_have_no_control_end():
    """A prospect has no salary path (GATE C2 clause C6'), so he has no control
    END either: club control starts at a debut that has not happened. The cell
    says "Prospect / control starts at debut" and the platform does not invent
    a year for him."""
    proj = _doc("mlb_projections.json")
    for p in proj.get("prospects") or []:
        for k in ("ctrlThru", "ctrlOpen", "ctrlEst", "ctrlWhy"):
            assert p.get(k) is None, (p.get("key"), k)


def test_every_control_reason_is_one_of_the_named_five():
    """`ctrlWhy` drives the second sentence of every tip. An unknown value
    would render the generic sentence for a case nobody wrote copy for."""
    ok = {"prearb_grid", "no_prior_salary", "closure_buyout", "horizon",
          "contract_only", None}
    bad = [(v["key"], v.get("ctrlWhy")) for v in _vets() if v.get("ctrlWhy") not in ok]
    assert not bad, bad[:5]


def test_the_caminero_row_is_the_owners_report_answered():
    """The named case, end to end, on whatever the current regen produced. The
    dollars move every pass, so nothing here pins one; the STRUCTURE is the
    claim: a guarantee that ends before the control window, a control window
    that reaches the last season the path prices, and a basis that names both
    halves.

    RE-PINNED 2026-10-04 (the 2026-10-03 Spotrac refetch, whose year columns
    start at 2027). Caminero's only guarantee was his 2026 salary, which is now
    history: his Spotrac row carries PRE-ARB / ARB tokens and no money year, so
    he has no guarantee at all and his window is the arbitration projection's
    alone. The structure is therefore asserted, in full, on every served row
    that still has a guarantee ending before its control end (3 at the re-pin:
    bryce_miller, cole_ragans, vinnie_pasquantino; 2 after the 2026-10-07
    refetch, which took bryce_miller's 2027 money off his page), and Caminero
    is asserted as the roll-off left him."""
    rows = [v for v in _vets()
            if v.get("thru") is not None and v.get("ctrlThru") is not None
            and v["thru"] < v["ctrlThru"]]
    assert rows, "no served row has a guarantee ending before its control end"
    for row in rows:
        assert row.get("salThru") is not None, row["key"]
        assert row["ctrlThru"] == max(row["thru"], row["salThru"]), row["key"]
        assert row["ctrlThru"] > row["thru"], ("the owner's report, unrepaired", row["key"])
        assert row.get("ctrlEst") is True, row["key"]
        assert row.get("salSrc") == "contract+arb", (row["key"], row.get("salSrc"))
    print(f"guarantee before control end: {len(rows)} rows "
          f"({', '.join(sorted(r['key'] for r in rows))})")
    row = next((v for v in _vets() if v["key"] == "junior_caminero"), None)
    if row is None:
        pytest.skip("junior_caminero not on the served board")
    assert row.get("salSrc") == "arb_projection", row.get("salSrc")
    assert row.get("thru") is None, "a guarantee came back: re-pin to the structure above"
    assert row.get("aav") is None, "a status-only Spotrac row served as an AAV"
    assert row.get("ctrlEst") is True
    assert row["ctrlThru"] == row["salThru"] == 2030
    print(f"caminero: no guarantee (2026 rolled off), club control {row['ctrlThru']}, "
          f"basis {row['salSrc']}, surplus {row.get('surTotal')}")


def test_every_guarantee_past_the_horizon_is_priced_to_its_end():
    """Owner answer 2026-09-25 (M05-01 step 2, proj_export.PRICE_CONTRACT_TAIL).
    Every served guarantee that runs past the last projected season is priced
    through its last guaranteed season, so no row is left clamped by the
    horizon with a control end past it, the tail carries contract dollars only,
    and `warTail` names one WAR per tail season."""
    import proj_export as pe
    if not pe.PRICE_CONTRACT_TAIL:
        pytest.skip("contract tail off")
    first, H = _window()
    last = first + H - 1
    clamped = [v["key"] for v in _vets()
               if v.get("ctrlWhy") == "horizon" and (v.get("ctrlThru") or 0) > last]
    assert not clamped, clamped[:5]
    n = 0
    for v in _vets():
        tail = [c for c in (v.get("salPath") or []) if c[0] > last]
        if not tail:
            assert not v.get("warTail"), v["key"]
            continue
        n += 1
        assert all(c[5] == "contract" for c in tail), v["key"]
        assert tail[-1][0] == v["thru"] == v["ctrlThru"], v["key"]
        assert len(v["warTail"]) == tail[-1][0] - last, v["key"]
        assert v.get("ctrlWhy") != "horizon", v["key"]
    acc = _doc("mlb_projections.json")["accountability"]["salary_path"]["contract_tail"]
    assert n == acc["rows"] and acc["capped_rows"] == 0
