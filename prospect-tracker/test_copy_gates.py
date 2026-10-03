# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Copy gates, enforced by the suite (audit F-04).

The two owner-mandated copy tools existed but nothing ran them, so a copy
regression (an em-dash, an LLM-cadence word in pure copy) could land silently:

  - tools/strip_emdashes.py --check: no em- or en-dashes anywhere in the
    canonical copy-surface list (its TARGETS: generators, app HTML, JS, CSS,
    articles, and the hand-committed data files the frontend renders).
  - tools/copy_lint.py --check: same em-dash rule plus the LLM ban-list,
    hard-failing only in pure-copy files (glossary.json, README, content/*)
    so code identifiers don't false-positive.

Both are shelled out through their real CLI contract (exit 0 = clean), the
same invocation a pipeline or pre-commit hook would use, so the gate tests
the tool as shipped rather than importing internals. Read-only: --check
never rewrites files, so this test dirties nothing.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent


def _run_gate(script: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONIOENCODING="utf-8")  # findings may be non-cp1252
    return subprocess.run(
        [sys.executable, str(ROOT / "tools" / script), "--check"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
        errors="replace", env=env, timeout=120,
    )


def test_strip_emdashes_check_is_clean():
    r = _run_gate("strip_emdashes.py")
    assert r.returncode == 0, (
        "strip_emdashes --check found em/en-dashes in copy surfaces:\n"
        f"{r.stdout}\n{r.stderr}"
    )


def test_copy_lint_check_is_clean():
    r = _run_gate("copy_lint.py")
    assert r.returncode == 0, (
        "copy_lint --check failed (em-dashes or LLM terms in pure copy):\n"
        f"{r.stdout}\n{r.stderr}"
    )


def test_the_emdash_gate_covers_every_user_facing_page():
    """PLAN ITEM F2.6, closed 2026-08-06. Ten pages users load had never been
    scanned by the gate, every Diamond-era surface among them: betting, cards,
    dfs, diamond, dynasty, redraft, plus fantasy, history, parks and player.

    All ten measured clean when they were added, so nothing shipped wrong. The
    defect was the coverage, not the copy: a page nobody scans is one bad paste
    away from breaking a rule the owner treats as absolute, and it would break
    it silently because no gate was looking.

    This test fails when a NEW page appears without being added, which is the
    only way the gap recurs."""
    import fnmatch
    import re
    from pathlib import Path

    root = Path(__file__).parent
    src = (root / "tools" / "strip_emdashes.py").read_text(encoding="utf-8")
    block = src[src.index("TARGETS"):src.index("def ")]
    targets = set(re.findall(r'"([^"]+)"', block))

    pages = sorted(p.relative_to(root).as_posix()
                   for p in root.glob("*/index.html"))
    assert pages, "no section pages found; has the layout changed?"

    uncovered = [p for p in pages
                 if not any(fnmatch.fnmatch(p, t) for t in targets)]
    assert not uncovered, (
        "user-facing pages the em-dash gate does not scan: "
        f"{uncovered}\nAdd them to TARGETS in tools/strip_emdashes.py. If one "
        "genuinely must be excluded, say why there, the way the exporter "
        "exclusions are documented.")


# ---------------------------------------------------------------------------
# Census X07-05 (2026-09-25): the gates' own blind spots, each pinned with a
# fixture so the gate cannot quietly go blind again.

def _run_gate_on(script: str, *paths) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    return subprocess.run(
        [sys.executable, str(ROOT / "tools" / script), "--check",
         *[str(p) for p in paths]],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
        errors="replace", env=env, timeout=120,
    )


def _escaped_en_dash() -> str:
    # backslash + u2013, built without a literal backslash sequence
    return chr(92) + "u2013"


def test_gates_catch_an_ascii_escaped_dash_in_json(tmp_path):
    """json.dumps(ensure_ascii=True) stores a dash as an escape sequence. It
    renders as a dash, and a raw-text scan never saw it: data/source_backtest.json
    served "Preseason cohorts 2017<en-dash>2023" on /glossary/ that way."""
    bad = tmp_path / "artifact.json"
    bad.write_text('{"note": "cohorts 2017' + _escaped_en_dash() + '2023"}',
                   encoding="utf-8")
    good = tmp_path / "clean.json"
    good.write_text('{"note": "cohorts 2017-2023"}', encoding="utf-8")
    for script in ("strip_emdashes.py", "copy_lint.py"):
        r = _run_gate_on(script, bad)
        assert r.returncode == 1, f"{script} missed an escaped dash:\n{r.stdout}"
        r = _run_gate_on(script, good)
        assert r.returncode == 0, f"{script} flagged clean JSON:\n{r.stdout}"


def test_copy_lint_bans_the_owner_words_in_pure_copy(tmp_path):
    """The owner's list (harness, unlock, essential, powerful, elevate,
    underscore, the verb leverage) was missing from BAN, so five glossary
    sentences carried "harness" through a clean gate. The baseball noun
    (Leverage Index, high-leverage) and "elevation" stay legal."""
    fixture = tmp_path / "glossary.json"
    for word in ("harness", "unlocks", "essential", "powerful", "elevate",
                 "underscores", "leveraging"):
        fixture.write_text('{"d": "the tool ' + word + ' it"}', encoding="utf-8")
        r = _run_gate_on("copy_lint.py", fixture)
        assert r.returncode == 1, f"copy_lint passed {word!r} in pure copy"
    fixture.write_text('{"d": "a high-leverage reliever by Leverage Index; '
                       'the leverage of the moment; park elevation"}',
                       encoding="utf-8")
    r = _run_gate_on("copy_lint.py", fixture)
    assert r.returncode == 0, f"copy_lint flagged baseball usage:\n{r.stdout}"


def test_the_gate_scans_the_exporters_whose_copy_is_served():
    """Exporters whose copy blocks land in served JSON must be on TARGETS."""
    src = (ROOT / "tools" / "strip_emdashes.py").read_text(encoding="utf-8")
    for exporter in ("mgmt_export.py", "hof_export.py", "arb_export.py",
                     "betting_export.py", "war_board_export.py",
                     "bullpen_export.py", "pal_export.py", "source_backtest.py"):
        assert f'"{exporter}"' in src, f"{exporter} is not on TARGETS"


def test_every_module_stage_chip_renders_through_one_helper():
    """Census X07-10 (2026-09-25): eleven module shells wrote the beta chip by
    hand, so a stage rename meant eleven edits (and /arbitration/ had drifted
    to an entity form). The chip word now lives in build_site.STAGE_CHIP_TEXT
    and every masthead chip renders through _stage_chip()."""
    import re

    import build_site
    src = (ROOT / "build_site.py").read_text(encoding="utf-8")
    word = build_site.STAGE_CHIP_TEXT["\u03b2"]
    body = src.replace('STAGE_CHIP_TEXT = {"\u03b2": "' + word + '"}', "")
    assert word not in body.replace('"' + word + '" by hand', ""), (
        "a module chip writes the stage word literally; use _stage_chip(key)")
    assert "&beta; beta" not in src
    assert not re.search(r'eephus-beta" title="\{html\.escape\(MODULE_STAGE', src), (
        "a masthead builds its chip from MODULE_STAGE by hand; use _stage_chip(key)")
    for key in build_site.MODULE_STAGE:
        chip = build_site._stage_chip(key)
        assert chip.startswith('<span class="eephus-beta" title="'), key


# ---------------------------------------------------------------------------
# COPY_0 (2026-10-02): the served copy lint, docs/COPY_STYLE.md. Rules L1 to
# L12 over the sentences a reader sees, ratcheted against
# tools/copy_baseline.json (SP-D6): new copy that breaks a rule fails, and a
# baseline entry that is no longer a finding fails too, so the file only
# shrinks. Exemptions live in tools/copy_registered.json. The fixtures below
# are the before/after pairs of the sitepass copy lane (LANE_COPY.md 1.7, and
# 1.4 where 1.7 has no example of the rule).

import pytest  # noqa: E402

sys.path.insert(0, str(ROOT / "tools"))
import copy_lint as CL  # noqa: E402


@pytest.fixture(scope="module")
def served():
    return CL.run_served(), CL.load_baseline()


def test_served_copy_gate_is_clean_against_the_baseline(served):
    result, base = served
    new, _ = CL.compare(result, base)
    shown = []
    for rule, keys in new.items():
        for k in keys[:10]:
            rec = result["rules"][rule].get(k) if rule in CL.RULES else None
            shown.append(f"{rule}: " + (f"{rec['file']} {rec['anchor']}: {rec['text'][:160]}"
                                        if rec else f"{k} {result[rule][k]}"))
    assert not new, (
        "new served copy breaks docs/COPY_STYLE.md (rewrite it, or register it in "
        "tools/copy_registered.json if it is legal, credit, claim or third-party text):\n"
        + "\n".join(shown))


def test_the_copy_baseline_has_no_stale_entries(served):
    """The ratchet only shrinks: a fixed sentence leaves the baseline in the
    commit that fixes it (python tools/copy_lint.py --served --write-baseline)."""
    result, base = served
    _, stale = CL.compare(result, base)
    assert not stale, (
        "baseline entries that are no longer findings; rewrite tools/copy_baseline.json "
        f"with --write-baseline in this commit: { {r: len(v) for r, v in stale.items()} }")


def test_the_baseline_records_every_rule():
    base = CL.load_baseline()
    for rule in CL.RULES + CL.SURFACE_RULES:
        assert rule in base, rule
        assert base["_counts"][rule] == len(base[rule]), rule
    for rule in CL.RULES:
        assert all(len(h) == 40 for h in base[rule]), rule


def test_registered_entries_are_well_formed():
    entries = CL.load_registered()
    assert entries, "tools/copy_registered.json is empty or unreadable"
    for e in entries:
        assert e.get("class") in CL.REGISTERED_CLASSES, e
        assert e.get("reason"), e
        if e["class"] == "LAB_LOG":
            assert e.get("source") and e.get("field"), e
        else:
            assert e.get("text") or e.get("regex"), e
    lab = [e for e in entries if e["class"] == "LAB_LOG"]
    assert ("data/model_registry.json", "notes") in {(e["source"], e["field"]) for e in lab}
    classes = {e["class"] for e in entries}
    for cls in ("LEGAL", "CREDIT", "IMPLIED_ODDS", "REGISTERED_CLAIM", "FAQ",
                "FIELD_NAME", "OWNER_QUOTE"):
        assert cls in classes, f"no {cls} entry seeded"


def _string_constants(path):
    import ast
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def test_every_registered_claim_names_a_test_that_contains_its_text():
    """A REGISTERED_CLAIM is exempt because a test pins it as a claim. If the
    pin goes, the exemption goes with it."""
    claims = [e for e in CL.load_registered() if e["class"] == "REGISTERED_CLAIM"]
    assert claims
    for e in claims:
        test = ROOT / (e.get("pinned_by") or "")
        assert e.get("pinned_by", "").startswith("test_") and test.is_file(), e
        text = e["text"]
        consts = _string_constants(test)
        assert any(text in CL._ws(CL.flat(CL.clean(c))) for c in consts), (
            f"{test.name} no longer contains the registered claim {text!r}")


def test_copy_producers_are_on_the_dash_gate():
    """COPY_PRODUCERS is the .py part of strip_emdashes TARGETS plus the
    producers COPY_0 found writing served copy outside it; every one of them
    is on TARGETS, so the dash gate scans what the served lint reads."""
    from strip_emdashes import TARGETS
    for p in CL.EXTRA_PRODUCERS:
        assert p in CL.COPY_PRODUCERS and p in TARGETS, p
    assert "collegesavant/pitcher_index.html" in TARGETS
    assert set(CL.COPY_PRODUCERS) == {t for t in TARGETS if t.endswith(".py")}
    for p in CL.COPY_PRODUCERS:
        assert (ROOT / p).is_file(), f"COPY_PRODUCERS names a missing file: {p}"


def test_producer_coverage_catches_an_unlisted_writer(served):
    """Every shipped data/*.json a page fetches that holds an 8+ word string is
    written by a COPY_PRODUCER, or is one of the files recorded uncovered on
    2026-10-02. A new one fails: that is how the next data_catalog.py shows up."""
    result, base = served
    new = sorted(set(result["coverage"]) - set(base.get("coverage") or []))
    assert not new, (
        "data files with reader prose whose writer is not in copy_lint.COPY_PRODUCERS: "
        + ", ".join(f"{n} (writers {result['coverage'][n]})" for n in new))
    # the writer detector on a known pair: arb_export.py writes the board
    # through a path constant (BOARD_PATH).
    w = CL.data_writers("arbitration.json", CL._py_sources())
    assert "arb_export.py" in w


def test_the_style_guide_passes_its_own_rules():
    doc = ROOT / "docs" / "COPY_STYLE.md"
    hits = CL.lint_doc(doc)
    assert not hits, "\n".join(hits)


# One positive and one negative fixture per rule.
_FIX = {
    # 1.7 holds no 60+ word sentence; the positive is a served one (66 words,
    # glossary ewar.definition, 2026-10-02), the negative a condensed form.
    "L1": ("Every realized WAR a reader sees (career totals, per-season lines, current-season pills, "
           "WAG's observed leg, eFV labels, arbitration, farm WAR/yr) reads it, with one exception: "
           "the /fa/ Archive's realized ledger (WAR and surplus to date, and the realized $/WAR series) "
           "was built from war_daily before the epoch and reads bWAR until it is rebuilt; the Archive "
           "says so and names the basis it reads.",
           "Every realized WAR a reader sees reads eWAR, except the /fa/ Archive ledger, which reads bWAR."),
    "L5": ("eFV is a model trained on resolved outcomes and scored the honest way.",
           "eFV is fit on resolved outcomes and scored leakage-free and forward-chained."),
    "L6": ("A threshold invented to make a pick appear is the single most dishonest number this "
           "module could publish.",
           "No edge threshold is set to manufacture a pick; a threshold ships only after it clears its gate."),
    "L7": ("This is the SAME value shown in the board's Star Odds column.",
           "Same value as the board's Star Odds column."),
    "L8": ("The gated evaluation lives in tools/pal_backtest_lab.py and writes the eval file.",
           "No ship: +0.0092 Spearman (0.5274 vs 0.5182, n 711), lo95 -0.0014."),
    "L9": ("Live calibration monitor: Is eFV still calibrated?",
           "Calibration monitor: eFV reliability by bin."),
    "L10": ("Open a list - Prospects, Draft, Graduates, Overseas - set your filters, then generate.",
            "The board at any past snapshot, or a diff of two dates: risers, fallers, adds, graduates."),
    "L12": ("Probables are not posted for the streamer window yet - check back once lineups firm up.",
            "No probables posted for this window. Off-season: streamers return with 2027 probables."),
}


@pytest.mark.parametrize("rule", sorted(_FIX))
def test_sentence_rule_fixtures(rule):
    bad, good = _FIX[rule]
    hard, _ = CL.rule_hits({"text": bad, "kind": "html"})
    assert rule in hard, (rule, bad, hard)
    hard, _ = CL.rule_hits({"text": good, "kind": "html"})
    assert rule not in hard, (rule, good, hard)


def test_l1_advisory_band_is_not_a_failure():
    """A 41 to 60 word sentence is advisory, not a failure: the /team/ betting
    bio (LANE_COPY CP-034, 43 words)."""
    s = ("Sports Betting: a run-scoring regression on the site's own team indexes with a Skellam "
         "margin model, proportional de-vig, closing-line value, a paper shadow ledger with per-tag "
         "records, market publishability gates, and an honest vintage backtest that beats the "
         "home-team constant on out-of-sample games.")
    hard, soft = CL.rule_hits({"text": s, "kind": "html"})
    assert "L1" not in hard and "L1>40" in soft


def test_l2_attribute_fixture():
    bad = ("Time-travel the board - view rankings & grades as they stood at any past snapshot, or "
           "diff two dates for a changelog of risers, fallers, new entries & graduates.")
    good = "The board at any past snapshot, or a diff of two dates: risers, fallers, adds, graduates."
    assert "L2" in CL.rule_hits({"text": bad, "kind": "attr"})[0]
    assert "L2" not in CL.rule_hits({"text": good, "kind": "attr"})[0]


def test_l3_share_card_fixture():
    bad = ("League-average runner: the decision is scored as though the manager had a league-average "
           "runner, because the runner's speed is a roster fact and crediting a manager for having a "
           "fast team is the confound this module exists to avoid.")
    good = "Scored with a league-average runner: runner speed is a roster fact, not a manager's decision."
    assert "L3" in CL.rule_hits({"text": bad, "kind": "share"})[0]
    assert "L3" not in CL.rule_hits({"text": good, "kind": "share"})[0]


_BEFORE_AFTER = [
    ("Every public FV grade is an educated opinion about the future.",
     "Public FV grades are scouting opinions."),
    ("eFV is a model trained on resolved outcomes and scored the honest way: leakage-free, "
     "forward-chained, on the same players, the same window AND the same vintage as the sources "
     "it is measured against.",
     "eFV is fit on resolved outcomes and scored leakage-free and forward-chained, on the same "
     "players, window and vintage as each source."),
    ("League-average runner: the decision is scored as though the manager had a league-average "
     "runner, because the runner's speed is a roster fact and crediting a manager for having a "
     "fast team is the confound this module exists to avoid.",
     "Scored with a league-average runner: runner speed is a roster fact, not a manager's decision."),
    ("Very-young and young+pedigreed prospects are filtered out unless their K-rate has cratered "
     "(Bryce Rainer-style).",
     "Excludes very young and young pedigreed prospects unless K% has collapsed past the screen's cut."),
    ("Registered and serving, with no measurement yet.", "Serving, not yet measured."),
    ("Its gate has not been run, which is not the same thing as a model that is wrong.",
     "Unmeasured is not wrong."),
]


def _surface(texts, name):
    return [{"surface": name, "file": "fixture", "anchor": "x", "kind": "html", "text": t}
            for t in texts]


def test_l4_surface_mean_fixture():
    before = [b for b, _ in _BEFORE_AFTER]
    after = [a for _, a in _BEFORE_AFTER]
    r = CL.lint_records(_surface(before, "before") + _surface(after, "after"),
                        min_sentences=1, min_words=1)
    assert "before" in r["L4"] and "after" not in r["L4"], r["L4"]


def test_l5_density_fixture():
    before = ["eFV is a model trained on resolved outcomes and scored the honest way.",
              "The full method and the honest limits are all below."]
    after = ["eFV is fit on resolved outcomes and scored leakage-free and forward-chained.",
             "Method and per-source results: Source Comparison."]
    r = CL.lint_records(_surface(before, "before") + _surface(after, "after"),
                        min_sentences=1, min_words=1)
    assert "before" in r["L5_density"] and "after" not in r["L5_density"], r["L5_density"]


def test_registered_text_is_exempt_and_faq_markup_skips_l9():
    ex = CL.Exemptions([{"class": "LEGAL", "text": "Sports betting is not legal in every state",
                         "reason": "x"}])
    recs = _surface(["21+. Sports betting is not legal in every state, ever, honestly."], "s")
    assert not any(CL.lint_records(recs, ex)["rules"][r] for r in CL.RULES)
    faq = {"text": "What happens to the free site?", "kind": "html", "faq": True}
    assert "L9" not in CL.rule_hits(faq)[0]


def test_the_extractor_reads_html_inside_script_strings():
    """A block tag inside a JS string ends a sentence, so table cells do not
    run together into one long sentence, and ${...} collapses to {x}."""
    js = "var a = `<td>The first cell has six words</td><td>The second cell also has words</td>`;" \
         " var b = 'Loading the free-agency board for ${x} clubs now';"
    recs = CL.extract_js("assets/fixture.js", js)
    texts = [r["text"] for r in recs]
    assert "The first cell has six words" in texts
    assert "The second cell also has words" in texts
    assert not any("$" in t for t in texts)
