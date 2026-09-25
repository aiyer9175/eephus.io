# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The A-ball whiff / FB-velo pill says whether the signal moved THIS player's grade.

WHY THIS EXISTS (audit F03-01, 2026-09-09, verified CONFIRMED). Every A/CPX pill
carried one fixed sentence: the signal "is NOT an input to the FV, the eFV grade,
the rank, or the surplus value". That was true when the S-XLINE-4 overlay was
NO-SHIP. The A4 uncapped ship then flipped efv_statcast_overlay's defaults ON, and
the same sidecar row began leaning the eFV model leg for covered active A/CPX
players. On the served data/xfv.json 478 board rows (345 hitters, 133 pitchers)
carry the "A-ball Statcast lean" driver, every one a pill-rendering card. The copy
never moved with the flag, and nothing tied the two together.

The replacement must be CONDITIONAL: on the other 218 pill cards no lean fires and
the old sentence is true. The pill reads the answer off the served eFV entry (the
lean factor exists exactly when overlay_fv fired a nonzero lean), not off a copy of
the overlay's gate, so the two cannot drift. What is pinned here:
  1. the unconditional sentence is gone and the note is computed per player;
  2. the label the client keys on IS efv_statcast_overlay.CHIP_LABEL, and the lean's
     FV size is decoded with the same convention efv_score encodes it;
  3. while either overlay default is ON, an "IS an input" branch exists;
  4. behaviour in V8 for lean, no lean, and eFV-not-loaded;
  5. on the served artifacts, every lean-carrying row is a pill card.
"""
from __future__ import annotations

import json
import re
import warnings
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
PROSPX = ROOT / "prospx" / "index.html"
DATA = ROOT / "data"


def _src() -> str:
    return PROSPX.read_text(encoding="utf-8")


def _function_source(src: str, name: str) -> str:
    m = re.search(r"^function %s\([^)]*\) \{.*?\n\}\n" % re.escape(name), src, re.S | re.M)
    assert m, f"{name} not found in prospx/index.html"
    return m.group(0)


def _overlay():
    import efv_statcast_overlay as ov
    return ov


def test_the_unconditional_not_an_input_sentence_is_gone():
    src = _src()
    pills = _function_source(src, "alevelSignalPillsHTML")
    assert "const note = alevelLeanNote(p);" in pills
    assert "it is NOT an input to the FV" not in pills, (
        "the fixed 'NOT an input' sentence is back on every A/CPX pill")
    for stale in ("S-XLINE-4 was NO-SHIP as a grade overlay",
                  "changes NO served number",
                  "nothing here feeds a grade, a rank, a"):
        assert stale not in src, f"stale claim survives in prospx/index.html: {stale!r}"


def test_the_client_keys_on_the_overlay_chip_label():
    m = re.search(r'^const ALEVEL_LEAN_LABEL = "([^"]+)";', _src(), re.M)
    assert m, "ALEVEL_LEAN_LABEL not found"
    assert m.group(1) == _overlay().CHIP_LABEL, (
        f"the pill looks for {m.group(1)!r}; efv_score writes {_overlay().CHIP_LABEL!r}. "
        "Every lean would read as 'not an input' again.")


def test_the_fv_size_is_decoded_the_way_efv_score_encodes_it():
    score = (ROOT / "efv_score.py").read_text(encoding="utf-8")
    assert '"mag": round(abs(xov) / 2.0, 2)' in score, (
        "efv_score changed how the lean chip's mag is written; alevelLeanNote doubles "
        "it back to FV and would now print the wrong size")
    assert "(2 * mag).toFixed(2)" in _function_source(_src(), "alevelLeanNote")


def test_an_input_branch_exists_while_the_overlay_ships():
    ov = _overlay()
    note = _function_source(_src(), "alevelLeanNote")
    if ov.OVERLAY_HIT_DEFAULT or ov.OVERLAY_PIT_DEFAULT:
        assert "IS an input" in note, (
            "the overlay defaults are ON but the pill has no way to say the signal is an input")
    assert "NOT an input" in note, "the no-lean branch (true on 218 cards) must survive"


# ---------------------------------------------------------------------------
# Behaviour in V8
# ---------------------------------------------------------------------------

def _make_ctx():
    mr = pytest.importorskip("py_mini_racer")
    warnings.filterwarnings("ignore")
    src = _src()
    m = re.search(r'^const ALEVEL_LEAN_LABEL = "[^"]+";', src, re.M)
    # Absent on the pre-fix source, where the served-card test below must still run
    # (and fail on the 478 leaned cards) rather than error out here.
    label = m.group(0) if m else "var ALEVEL_LEAN_LABEL;"
    ctx = mr.MiniRacer()
    ctx.eval("var __EFV = {}; function getEfv(p) { return __EFV[p.player_key] || null; }"
             " function ensureAlevelSignals() {}"
             " var _ALEVEL_SIG = {frozen_coefficients: {}, by_mlbam: {"
             "  '1': {side: 'hit', level: 'A', season: 2026, n_pitches: 400,"
             "        whiff_share: 0.312, whiff_z: 1.4},"
             "  '2': {side: 'pit', level: 'CPX', season: 2026, n_pitches: 250,"
             "        fb_velo: 95.1, velo_z: 1.1}}};")
    names = ["escapeHtml", "_alevelSigFor", "alevelLeanNote", "alevelSignalPillsHTML"]
    if "function alevelLeanNote(" not in src:
        names.remove("alevelLeanNote")
    ctx.eval(label)
    for name in names:
        ctx.eval(_function_source(src, name))
    return ctx


@pytest.fixture(scope="module")
def js():
    return _make_ctx()


def _title(ctx, player, entry) -> str:
    ctx.eval("__EFV = %s;" % json.dumps({player["player_key"]: entry} if entry else {}))
    html = ctx.eval("alevelSignalPillsHTML(%s)" % json.dumps(player))
    m = re.search(r'title="([^"]*)"', html)
    assert m, html
    return m.group(1).replace("&quot;", '"').replace("&amp;", "&").replace("&#39;", "'")


HIT = {"player_key": "h", "mlbam_id": 1}
PIT = {"player_key": "p", "mlbam_id": 2}


def test_a_leaned_hitter_is_told_the_signal_is_an_input_with_its_size(js):
    t = _title(js, HIT, {"factors": [{"label": "A-ball Statcast lean", "dir": "down", "mag": 0.14}]})
    assert "IS an input" in t and "down 0.28 FV" in t, t
    assert "NOT an input" not in t


def test_a_leaned_pitcher_reads_up(js):
    t = _title(js, PIT, {"factors": [{"label": "A-ball Statcast lean", "dir": "up", "mag": 1.14}]})
    assert "IS an input" in t and "up 2.28 FV" in t, t


def test_no_lean_keeps_the_true_sentence(js):
    t = _title(js, HIT, {"factors": [{"label": "Statcast+ quality", "dir": "up", "mag": 0.3},
                                     {"label": "AAA physics lean", "dir": "up", "mag": 0.2}]})
    assert "NOT an input" in t and "IS an input" not in t, t


def test_an_unloaded_grade_claims_neither(js):
    t = _title(js, HIT, None)
    assert "NOT an input" not in t and "IS an input" not in t, t


# ---------------------------------------------------------------------------
# The served artifacts
# ---------------------------------------------------------------------------

def test_every_served_lean_label_is_one_the_client_knows():
    path = DATA / "xfv.json"
    if not path.exists():
        pytest.skip("data/xfv.json not built")
    ov = _overlay()
    by_player = json.loads(path.read_text(encoding="utf-8")).get("by_player") or {}
    labels = {f.get("label") for v in by_player.values() for f in (v.get("factors") or [])
              if "lean" in (f.get("label") or "").lower()}
    assert labels <= {ov.CHIP_LABEL, ov.CHIP_LABEL_AAA}, (
        f"efv_score writes lean labels the pill does not recognise: {labels}")


def test_served_pill_cards_split_exactly_on_the_served_lean(timeseries_doc):
    """The real client pill over every served pill card with its real eFV factors:
    "IS an input" on exactly the cards whose entry carries the lean, "NOT an input"
    on exactly the rest. Measured 2026-09-10: 478 and 218 of 696."""
    xfv_p, sig_p = DATA / "xfv.json", DATA / "statcast_alevel_signals.json"
    if not (xfv_p.exists() and sig_p.exists()):
        pytest.skip("xfv.json / statcast_alevel_signals.json not built")
    ov = _overlay()
    by_player = json.loads(xfv_p.read_text(encoding="utf-8")).get("by_player") or {}
    sig = json.loads(sig_p.read_text(encoding="utf-8"))
    ctx = _make_ctx()
    ctx.eval("_ALEVEL_SIG = %s;" % json.dumps({"by_mlbam": sig.get("by_mlbam") or {},
                                               "frozen_coefficients": {}}))
    cards = []
    for p in timeseries_doc.get("players") or []:
        mid = p.get("mlbam_id") or (p.get("career_war") or {}).get("mlbam_id")
        if p.get("player_key") and mid and str(mid) in (sig.get("by_mlbam") or {}):
            cards.append({"player_key": p["player_key"], "mlbam_id": mid})
    if not cards:
        pytest.skip("no pill cards on this artifact")
    # getEfv returns the served entry, or null for a card with no eFV row (as in the page).
    ctx.eval("__EFV = %s;" % json.dumps(
        {c["player_key"]: {"factors": by_player[c["player_key"]].get("factors") or []}
         for c in cards if c["player_key"] in by_player}))
    notes = json.loads(ctx.eval("JSON.stringify(%s.map(p => alevelSignalPillsHTML(p)))"
                                % json.dumps(cards)))
    counts = {"in": 0, "not": 0, "neither": 0}
    wrong = []
    for c, html in zip(cards, notes):
        if not html:
            continue                                   # sidecar row carries no metric
        entry = by_player.get(c["player_key"])
        leaned = entry is not None and any(
            f.get("label") == ov.CHIP_LABEL and (f.get("mag") or 0) > 0
            for f in entry.get("factors") or [])
        want = "in" if leaned else ("not" if entry is not None else "neither")
        got = ("in" if "IS an input" in html else
               "not" if "NOT an input" in html else "neither")
        counts[got] += 1
        if got != want:
            wrong.append((c["player_key"], want, got))
    assert not wrong, (
        f"{len(wrong)} served pill cards say the wrong thing about the lean "
        f"(key, should say, says): {wrong[:10]}")
    # DS-02: under eFV V2 the lean is a labelled note (on_grade False, no magnitude) and
    # moves no grade, so every pill must say NOT an input; under v1 it moves the model leg.
    import efv_v2_serve
    if efv_v2_serve.enabled():
        assert counts["in"] == 0, f"a pill claims the lean moves a V2 grade: {counts}"
    elif ov.OVERLAY_HIT_DEFAULT or ov.OVERLAY_PIT_DEFAULT:
        assert counts["in"] > 0, f"the overlay ships but no served pill says so: {counts}"
