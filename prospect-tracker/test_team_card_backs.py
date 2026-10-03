# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The Masthead card backs (owner ask TEAM_2, 2026-10-02).

The owner's back is a resume in groups; every other back credits the modules
its person touched ('Assisted with development of ...') from the git record
and the watermarks. Pins: the copy rules on every line (copy_lint's ban list,
no em or en dash, no marketing word, no hedge or intensifier, no exclamation
or question mark); every accuracy figure arrives through a team_facts token
read off its artifact, never typed; every token resolves in this tree and a
line whose source is missing is dropped, not printed with a hole; the
watermark count is repository wide; and each card's back shows its lines,
in the HTML and in headless Chromium after the card is turned."""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

import pytest

import build_site as B
import team_facts as T

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "tools"))
from copy_lint import BAN_RE  # noqa: E402
from strip_emdashes import EM, EN  # noqa: E402

TEAM = json.loads((ROOT / "data" / "team.json").read_text(encoding="utf-8"))
MEMBERS = {m["key"]: m for m in TEAM["members"]}
OWNER = "noah-j-dengler"
OWNER_GROUPS = ["eephus.io, founder and lead developer", "Modules", "Models and metrics",
                "Data systems", "Evaluation", "Design", "Tools"]

# The spec's marketing list (leverage only outside 'Leverage Index'), plus
# hedges and intensifiers: a card back states, it does not sell or soften.
MARKETING = re.compile(
    r"\b(seamless\w*|robust\w*|delve\w*|comprehensive\w*|crucial\w*|essential\w*|powerful\w*|"
    r"showcase\w*|utiliz\w*|unlock\w*|elevat(e|es|ed|ing)|game-chang\w*|cutting-edge|tapestry|"
    r"meticulous\w*|underscor\w*|harness\w*|innovative|world-class|best-in-class|state-of-the-art|"
    r"passion\w*|journey|spearhead\w*|synerg\w*)\b", re.I)
LEVERAGE = re.compile(r"\bleverag\w*\b(?! Index)", re.I)
HEDGES = re.compile(
    r"\b(very|extremely|highly|incredibly|truly|deeply|really|hugely|massively|significantly|"
    r"arguably|perhaps|somewhat|fairly|quite|might|maybe|possibly)\b", re.I)
# An accuracy figure typed into the roster would go stale with its artifact.
TYPED_ACCURACY = re.compile(r"\b(rho|Spearman|MAE|MdAPE|Brier|AUC|CI95|r2|log loss)\b\s*[-+$]?\d", re.I)


def _all_raw():
    for key, m in MEMBERS.items():
        for ln in T.raw_lines(m):
            yield key, ln


def _all_filled():
    for key, m in MEMBERS.items():
        for head, lines in T.back_groups(m):
            yield key, head
            for ln in lines:
                yield key, ln


# ------------------------------------------------------------------ copy

def test_every_back_line_passes_the_copy_rules():
    bad = []
    for key, ln in [*_all_raw(), *_all_filled()]:
        for rx, why in ((BAN_RE, "copy_lint ban"), (MARKETING, "marketing"),
                        (LEVERAGE, "leverage"), (HEDGES, "hedge or intensifier")):
            m = rx.search(ln)
            if m:
                bad.append(f"{key}: {why} {m.group(0)!r}: {ln}")
        if EM in ln or EN in ln:
            bad.append(f"{key}: dash: {ln}")
        if "!" in ln or "?" in ln:
            bad.append(f"{key}: exclamation or question: {ln}")
    assert not bad, "\n".join(bad)


def test_the_roster_file_passes_copy_lint():
    import copy_lint
    assert copy_lint.main(["--check", str(ROOT / "data" / "team.json")]) == 0


def test_accuracy_figures_come_from_tokens_not_typed_text():
    typed = [f"{k}: {ln}" for k, ln in _all_raw() if TYPED_ACCURACY.search(ln)]
    assert not typed, "derive these through a team_facts token:\n" + "\n".join(typed)


# ------------------------------------------------------------------ tokens

def test_every_token_resolves_in_this_tree():
    tokens = sorted({t for _k, ln in _all_raw() for t in T.TOKEN_RE.findall(ln)})
    assert tokens, "the backs carry no derived facts"
    missing = []
    for t in tokens:
        try:
            T.fact(t)
        except T.Missing as exc:
            missing.append(f"{t}: {exc}")
    assert not missing, missing
    for _k, ln in _all_filled():
        assert "{{" not in ln and "}}" not in ln, ln


def test_a_line_whose_source_is_missing_is_dropped(monkeypatch):
    real = T.fact

    def no_bet(key):
        if key == "bet.vintage":
            raise T.Missing(key)
        return real(key)

    monkeypatch.setattr(T, "fact", no_bet)
    owner = MEMBERS[OWNER]
    lines = [ln for _h, group in T.back_groups(owner) for ln in group]
    raw = [ln for ln in T.raw_lines(owner) if "{{bet.vintage}}" in ln]
    assert raw and not any("Betting model" in ln for ln in lines)
    assert any(ln.startswith("REM+") for ln in lines)
    assert T.fill("x {{no.such.token}} y") is None


def test_figures_match_their_artifacts():
    bet = json.loads((ROOT / "data" / "betting_model_eval.json").read_text(encoding="utf-8"))["vintage"]
    assert f"{bet['brier']:.4f}" in T.fact("bet.vintage")
    assert f"{bet['n_graded']:,}" in T.fact("bet.vintage")
    claim = json.loads((ROOT / "data" / "xfv.json").read_text(encoding="utf-8"))["meta"]["served_model"]["claim"]
    assert T.fact("efv.claim") == claim["text"].strip()
    rows = json.loads((ROOT / "data" / "model_registry.json").read_text(encoding="utf-8"))["models"]
    assert T.fact("registry.n") == f"{len(rows):,}"
    sem = json.loads((ROOT / "data" / "sem_plus_eval.json").read_text(encoding="utf-8"))
    assert f"{sem['forward_spearman_vs_RA9_next']['sem_plus']:.3f}" in T.fact("plus.sem")


# ------------------------------------------------------------------ content

def test_owner_back_is_a_resume_in_groups():
    owner = MEMBERS[OWNER]
    assert all(isinstance(item, dict) for item in owner["back"])
    assert [h for h, _l in T.back_groups(owner)] == OWNER_GROUPS
    text = " ".join(ln for _h, g in T.back_groups(owner) for ln in g)
    for name in ("PROSPX", "MLB Projections", "Free Agency", "Trade Machine", "Club Ledger",
                 "Franchises", "In-Game Management", "Arbitration", "Hall of Fame",
                 "Sports Betting", "Fantasy", "CollegeSavant", "eFV", "xFV", "eWAR v2",
                 "HEM+", "SEM+", "REM+", "DEM+", "KRP+", "RPS+", "Swing+", "Franchise Index",
                 "F-SCORE", "bracket simulator", "Model registry", "Reserved frames",
                 "Source Comparison", "Pixel icon system"):
        assert name in text, name


def test_other_backs_credit_the_modules_each_person_touched():
    for key, m in MEMBERS.items():
        if key == OWNER:
            continue
        assert all(isinstance(item, str) for item in m["back"]), key
        lines = [ln for _h, g in T.back_groups(m) for ln in g]
        assert any(ln.startswith("Assisted with") for ln in lines), key
    will = [ln for _h, g in T.back_groups(MEMBERS["will-cahoon"]) for ln in g]
    assert will[0].startswith("eWAR: instrumental") and will[2].startswith("SDR: created")
    assert "pitcher-ewar-1.1.0" in will[0] and "defense-plus" in will[1]
    assert MEMBERS["anirudh-iyer"]["back"][0].startswith("Co-created the PROSPX Spotlights")
    assert MEMBERS["joseph-gillis"]["back"][0].startswith("Co-created CollegeSavant")
    mb = " ".join(MEMBERS["michael-behrens"]["back"])
    for word in ("Webmaster", "Cloudflare", "port", "account and forum"):
        assert word in mb, word
    assert MEMBERS["charlie-mortellite"]["back"] == ["Assisted with bug testing across the site."]
    assert MEMBERS["charlie-mortellite"]["git"] == []


def test_watermark_count_is_repository_wide():
    marks = T.watermark_files()
    if not marks:
        pytest.skip("git unavailable")
    will = marks.get("@willcolqhn", [])
    assert len(will) > 100 and any(p.startswith("defense-plus/") for p in will)
    assert B._watermark_counts()["@willcolqhn"] == len(will)
    assert all(m.get("git") is not None for m in TEAM["members"])


# ------------------------------------------------------------------ render

@pytest.fixture(scope="module")
def team_html() -> str:
    return B.build_team()


def _back_of(page: str, key: str) -> str:
    art = page[page.index(f'id="member-{key}"'):]
    art = art[:art.index("</article>")]
    return art[art.index('class="tc-face tc-back"'):]


def test_each_card_back_carries_its_lines(team_html):
    for key, m in MEMBERS.items():
        back = _back_of(team_html, key)
        for head, lines in T.back_groups(m):
            assert f'<h4 class="tc-back-h">{html.escape(head)}</h4>' in back, (key, head)
            for ln in lines:
                assert f"<li>{html.escape(ln)}</li>" in back, (key, ln)
    assert "{{" not in team_html


def _pattern(raw: str) -> re.Pattern:
    """A typed line as a regex: its words literal, each {{token}} any text."""
    parts = T.TOKEN_RE.split(raw)
    return re.compile("".join(re.escape(x) if i % 2 == 0 else ".+?" for i, x in enumerate(parts)), re.S)


@pytest.fixture(scope="module")
def rendered_backs():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    from conftest import serve_site

    out: dict = {}
    with serve_site() as base, sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"chromium not installed for playwright: {exc}")
        for width in (390, 1280):
            ctx = browser.new_context(viewport={"width": width, "height": 900})
            ctx.add_init_script("try{localStorage.setItem('prospect-tracker.gate-unlocked','1')}catch(e){}")
            page = ctx.new_page()
            page.goto(base + "team/", wait_until="load", timeout=30_000)
            for key in MEMBERS:
                page.click(f"#member-{key} .tc-front .tc-flipbtn")
                page.wait_for_timeout(350)
                out[(width, key)] = page.evaluate(
                    """(k) => {
                      const back = document.querySelector('#member-' + k + ' .tc-back');
                      return {
                        visible: getComputedStyle(back).visibility,
                        items: [...back.querySelectorAll('.tc-bio li')].map((li) => li.textContent.trim()),
                        heads: [...back.querySelectorAll('.tc-back-h')].map((h) => h.textContent.trim()),
                        hscroll: document.documentElement.scrollWidth > innerWidth,
                      };
                    }""", key)
            ctx.close()
        browser.close()
    return out


@pytest.mark.parametrize("width", [390, 1280])
def test_each_turned_card_shows_its_back_lines(rendered_backs, width):
    for key, m in MEMBERS.items():
        # The served page was built before this run; a token (a commit count,
        # a nightly artifact) may have moved since, so a token matches any
        # text and every typed word must match exactly, in order.
        r = rendered_backs[(width, key)]
        heads = [str(i["head"]) for i in m["back"] if isinstance(i, dict)] or ["Record"]
        raw = [ln for i in m["back"] for ln in ([i] if isinstance(i, str) else i["lines"])]
        assert r["visible"] == "visible", (width, key)
        assert r["heads"] == heads, (width, key)
        assert len(r["items"]) == len(raw), (width, key, len(r["items"]), len(raw))
        for shown, typed in zip(r["items"], raw):
            assert _pattern(typed).fullmatch(shown), (width, key, typed, shown)
        assert not r["hscroll"], (width, key)
