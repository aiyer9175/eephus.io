# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""The game-intensity registration exists BEFORE any code, and says what it says.

Docs only. docs/diamond-betting.md carries the section "Game intensity: stakes, matchup
quality and the postseason" (owner ask 8 of 2026-09-30, plan Part 8 P8.9): a stakes index
`ix_v1`, a model-free stage 1 on 2018-2025 and a pricing stage 2 on the 2027 vintage.
Nothing here computes a number. The tests pin the section by its TITLE, never by its
letter (letters go by commit order), pin the column names, never a schema number, and
assert that:

- the frozen literals (the G_REF draft and the rule that the gate tool's commit replaces
  it, the weights, the bands, the Elo constants, the home edge, the simulation count and
  seed, the IX-A focus threshold) are the ones written in the text;
- the look-date rule is the registered one;
- the overlap list names 5c-B, 5c-C, 5d, 5k and 7e-D and not 5e or 5i-B;
- no non-test module names an `ix_` symbol before a dated "### Builder landed"
  amendment, and no serving flag exists before a stage-2 result.

LITERALS below is the one copy of the frozen values that later tests (the construction
core, the lab, the dark builder) compare code against; it is pinned here to the text.

5c rule 1: a candidate measured before its section exists is disqualified, whatever it
measured. A lab or builder written before the builder amendment that names a column is the
early look, so the scan covers every non-test .py at the root and under tools/ and every
module script under assets/.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
GATE_DOC = ROOT / "docs" / "diamond-betting.md"
ARTIFACT = ROOT / "data" / "game_intensity_eval.json"
LAB = ROOT / "tools" / "intensity_lab.py"

TITLE = "Game intensity: stakes, matchup quality and the postseason"
COLUMNS = ("ix_elo", "ix_po_pct", "ix_ws_pct", "ix_proj_wins", "ix_games")
CONSTRUCTION = "ix_v1"
FLAGS = ("SERVE_INTENSITY_STAKES", "SERVE_INTENSITY_TOTAL")
CLOSING = "No number has been computed on this candidate."
EM_DASH, EN_DASH = chr(0x2014), chr(0x2013)     # spelled so this file carries neither

# The frozen literals of `ix_v1`, as registered. G_REF is the DRAFT value: the gate
# tool's own commit (Q10_07) recomputes it once from the registered synthetic league and
# records the frozen literal by a dated amendment, which replaces this draft.
LITERALS = {
    "g_ref_draft": 0.01145,
    "g_ref_seed": 20260930,
    "g_ref_sims": 300_000,
    "g_ref_clubs": 30,
    "w_stakes": 0.60,
    "w_quality": 0.15,
    "w_starters": 0.15,
    "w_division": 0.10,
    "w_rivalry": 0.0,
    "bands": (30, 50, 70),
    "elo_base": 1500,
    "elo_k": 4,
    "elo_home_points": 24,
    "home_edge": 0.0345,
    "sims": 20_000,
    "seed": 12345,
    "focus_threshold": 0.05,
}

OVERLAP_WAITED = ("5c-B", "5c-C", "5d", "5k", "7e-D")
OVERLAP_NOT_WAITED = ("5e", "5i-B")


def _norm(text: str) -> str:
    """The document is hard-wrapped at about 90 columns, so a sentence pinned here is
    matched with every run of whitespace collapsed to one space."""
    return re.sub(r"\s+", " ", text)


def _doc() -> str:
    assert GATE_DOC.exists(), "docs/diamond-betting.md is missing"
    return GATE_DOC.read_text(encoding="utf-8")


def _section(doc: str | None = None) -> str:
    """The text of the one level-2 section whose heading carries the title, up to the
    next level-2 heading."""
    doc = _doc() if doc is None else doc
    hits = list(re.finditer(r"^## [^\n]*" + re.escape(TITLE) + r"[^\n]*$", doc, flags=re.M))
    assert len(hits) == 1, f"expected one section titled {TITLE!r}, got {len(hits)}"
    m = hits[0]
    nxt = re.search(r"^## ", doc[m.end():], flags=re.M)
    return doc[m.start():] if nxt is None else doc[m.start():m.end() + nxt.start()]


def _paragraph(sec: str, lead: str) -> str:
    """The bold-led paragraph that starts with `lead`, whitespace collapsed."""
    text = _norm(sec)
    start = text.find(f"**{lead}")
    assert start >= 0, f"the section has no paragraph led by {lead!r}"
    end = text.find(" **", start + len(lead) + 4)
    return text[start:] if end < 0 else text[start:end]


def _names(text: str, label: str) -> bool:
    return re.search(r"(?<![\w-])" + re.escape(label) + r"(?![\w-])", text) is not None


def _builder_landed(sec: str) -> bool:
    return re.search(r"^### Builder landed 20\d\d-\d\d-\d\d", sec, flags=re.M) is not None


def _stage2_recorded(sec: str) -> bool:
    if re.search(r"^### Stage 2 result", sec, flags=re.M):
        return True
    if ARTIFACT.exists():
        try:
            return "stage2" in json.loads(ARTIFACT.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return False
    return False


def _non_test_modules() -> list[Path]:
    out = []
    for base, pat in ((ROOT, "*.py"), (ROOT / "tools", "*.py"), (ROOT / "assets", "*.js")):
        if not base.exists():
            continue
        for p in sorted(base.glob(pat)):
            if p.name.startswith("test_") or p.name == "conftest.py":
                continue
            out.append(p)
    return out


# A quoted string that starts with ix_ (a column, a block or payload key), other than the
# construction id. numpy's np.ix_ and local names are not quoted, so they never match.
_IX_STRING = re.compile(r"""["'`]ix_(?!v\d+["'`])[a-z][a-z0-9_]*""")


def _ix_offenders() -> list[str]:
    hits = []
    for p in _non_test_modules():
        src = p.read_text(encoding="utf-8", errors="replace")
        if any(re.search(r"\b" + c + r"\b", src) for c in COLUMNS) or _IX_STRING.search(src):
            hits.append(p.relative_to(ROOT).as_posix())
    return hits


def _first_commit_date(needle: str, path: Path) -> str | None:
    """ISO committer date of the earliest commit whose diff adds or removes `needle`
    in `path` (git log -S), or None when git cannot say."""
    if shutil.which("git") is None:
        return None
    try:
        out = subprocess.run(
            ["git", "log", "--reverse", "--format=%cI", "-S", needle, "--",
             path.relative_to(ROOT).as_posix()],
            cwd=ROOT, capture_output=True, text=True, timeout=120, check=True).stdout
    except (subprocess.SubprocessError, OSError):
        return None
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    return lines[0] if lines else None


# ---------------------------------------------------------------------------
# the section and what it names
# ---------------------------------------------------------------------------
def test_the_section_exists_with_its_title_and_date():
    sec = _section()
    head = sec.splitlines()[0]
    assert re.search(r"pre-registered 20\d\d-\d\d-\d\d", head), (
        "the game-intensity heading must carry its pre-registration date")
    assert CLOSING in _norm(sec), "the section must close with its no-number sentence"
    assert f"`{CONSTRUCTION}`" in sec


def test_the_frozen_literals_equal_the_text():
    sec = _norm(_section())
    L = LITERALS
    formula = (f"II = round(100 x ({L['w_stakes']:.2f} S + {L['w_quality']:.2f} Q + "
               f"{L['w_starters']:.2f} A + {L['w_division']:.2f} D))")
    assert formula in sec, formula
    assert f"draft value {L['g_ref_draft']}" in sec
    assert f"{L['g_ref_clubs']} equal clubs" in sec
    assert f"{L['g_ref_sims']:,} simulations at seed {L['g_ref_seed']}" in sec
    assert f"({L['elo_base']}, K {L['elo_k']}, {L['elo_home_points']} points of home field" in sec
    assert f"home edge of {L['home_edge']}" in sec
    assert f"{L['sims']:,} simulations at seed {L['seed']}" in sec
    assert f"`|ds| >= {L['focus_threshold']}`" in sec
    lo, mid, hi = L["bands"]
    assert f"the bands ({lo}, {mid}, {hi})" in sec
    assert (f"under {lo} routine, {lo} to {mid - 1} raised, {mid} to {hi - 1} high, "
            f"{hi} and over peak") in sec
    assert L["w_rivalry"] == 0.0 and "with weight 0 (INT-A4" in sec
    assert abs(L["w_stakes"] + L["w_quality"] + L["w_starters"] + L["w_division"] - 1) < 1e-12


def test_the_gate_tool_commit_replaces_the_g_ref_draft():
    sec = _norm(_section())
    for needle in ("the gate tool's own commit (Q10_07) recomputes it once from that league",
                   "records the frozen literal here by a dated amendment, which replaces "
                   "the draft value",
                   "it is never computed at a look"):
        assert needle in sec, needle


def test_the_look_date_rule():
    sec = _norm(_section())
    when = _paragraph(_section(), "When each stage is read.")
    for needle in ("the later of 2026-11-02 and the day after the 2026 World Series ends",
                   "in one run with every block written before any is opened",
                   "never on another look's date",
                   "the first nightly after the last scheduled 2027 regular-season game",
                   "kill date 2027-11-30",
                   "The gate tool refuses an earlier date and a second run"):
        assert needle in when, needle
    assert "A dry run of any fit, score or twin on real data before its stage's look is " \
           "that stage's look" in sec
    assert "one-run guard reads both the artifact and this section's result block" in sec


def test_the_overlap_list():
    sec = _section()
    ov = _paragraph(sec, "The overlap list")
    waits = ov[ov.index("Stage 1 waits for"):ov.index("It does NOT wait")]
    for look in OVERLAP_WAITED:
        assert _names(waits, look), f"the overlap list does not wait for {look}"
    for look in OVERLAP_NOT_WAITED:
        assert not _names(waits, look), f"the overlap list must not wait for {look}"
        assert _names(ov[ov.index("It does NOT wait"):], look)
    assert "2026-10-31 at the latest" in waits
    when = _paragraph(sec, "When each stage is read.")
    stage1 = when[when.index("Stage 1:"):when.index("It does not wait")]
    for look in OVERLAP_WAITED:
        assert _names(stage1, look), look
    for look in OVERLAP_NOT_WAITED:
        assert not _names(stage1, look), look
    assert "No 2026 game, regular season or postseason, is in stage 1's sample" in _norm(sec)


def test_owner_answers_artifact_and_postseason_cache_are_named():
    sec = _norm(_section())
    for qid in ("INT-A1", "INT-A2", "INT-A4", "INT-B1", "INT-B2", "INT-B4", "Q901-1"):
        assert qid in sec, qid
    for needle in ("`data/game_intensity_eval.json`", "`game_intensity_effects`",
                   "Neither look writes `data/betting_model_eval.json`",
                   "`.cache/win_prob_post/`, never in `.cache/win_prob/`",
                   "Only the intensity lab reads them",
                   "763 graded games", "No betting Postseason tab is built",
                   "No Franchise \"playoff performance\" leaf is built"):
        assert needle in sec, needle
    for col in COLUMNS:
        assert f"`{col}`" in sec, f"the section does not name the column {col!r}"


def test_no_dashes_in_the_section():
    sec = _section()
    assert EM_DASH not in sec and EN_DASH not in sec


# ---------------------------------------------------------------------------
# no code, no column, no flag, no number
# ---------------------------------------------------------------------------
def test_no_ix_symbol_before_its_builder_is_dated():
    """Until a dated '### Builder landed' amendment exists, no non-test module may name
    an `ix_` column or key: a lab or builder written before it is the early look 5c
    rule 1 forbids. The construction id `ix_v1` is not a column."""
    if _builder_landed(_section()):
        return
    offenders = _ix_offenders()
    assert not offenders, (
        "these non-test modules name an ix_ symbol before the game-intensity builder "
        "landed: " + ", ".join(offenders))


def test_the_section_predates_any_builder_by_git_date():
    """Every non-test module that names a column first did so in a commit no earlier
    than the commit that added the section."""
    sec_date = None
    for p in _non_test_modules():
        src = p.read_text(encoding="utf-8", errors="replace")
        for col in COLUMNS:
            if not re.search(r"\b" + col + r"\b", src):
                continue
            if sec_date is None:
                sec_date = _first_commit_date(TITLE, GATE_DOC)
                if sec_date is None:
                    pytest.skip("git cannot date the section here")
            col_date = _first_commit_date(col, p)
            if col_date is None:
                pytest.fail(f"{p.name} names {col} in an uncommitted change while the "
                            "registration test cannot date it")
            assert col_date >= sec_date, (
                f"{p.name} named {col} at {col_date}, before the section ({sec_date})")


def test_no_serve_flag_exists_before_a_stage_2_result():
    if _stage2_recorded(_section()):
        return
    offenders = []
    for p in _non_test_modules():
        src = p.read_text(encoding="utf-8", errors="replace")
        if any(f in src for f in FLAGS):
            offenders.append(p.relative_to(ROOT).as_posix())
    assert not offenders, (
        "a game-intensity serving flag exists before any stage-2 result: "
        + ", ".join(offenders))


def test_no_artifact_exists_without_its_lab():
    """The section's own artifact is written by the stage-1 lab and nothing else; a file
    without the lab is a number computed outside the registered run."""
    if ARTIFACT.exists():
        assert LAB.exists(), (
            "data/game_intensity_eval.json exists but tools/intensity_lab.py does not")
