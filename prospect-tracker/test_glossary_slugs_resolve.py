# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Every glossary slug a page references resolves to an entry.

Census M13-02 (2026-09-24): /betting/ and the /fantasy/ DFS board referenced
25 slugs that data/glossary.json did not carry (devig, clv, kelly_criterion,
dfs_points_per_1k and more). eephus-gl.js degrades an unresolved [data-gl]
span to plain text, so nothing failed; the /betting/ masthead anchor
/glossary/#g=devig landed on a glossary that found nothing, under an intro
that says every number resolves to an entry. The definitions sat unmerged in
build_glossary_data.BETTING_ENTRIES since 2026-08-07.

The scan reads the page sources (assets/*.js, build_site.py and the top-level
route shells) for data-gl="slug", #g=slug, gl(label, "slug"), _gl("slug", ...)
and the DFS column `term: "slug"` key. A slug built at runtime (betting.js
builds the provisional-pick label from a variable) is pinned by name below.
Resolution follows eephus-gl.js resolve(): entry id, then term, then alias,
case-insensitive."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent

PATTERNS = [
    re.compile(r'data-gl="([a-z0-9_]+)"'),
    re.compile(r"#g=([a-z0-9_]+)"),
    re.compile(r"""\bgl\(\s*(?:"[^"]*"|'[^']*'|[^,()]+?)\s*,\s*["']([a-z0-9_]+)["']"""),
    re.compile(r"""\b_gl\(\s*["']([a-z0-9_]+)["']"""),
    re.compile(r"""\bterm:\s*["']([a-z0-9_]+)["']"""),
]

# Slugs a page builds at runtime, which no literal scan can see.
DYNAMIC_SLUGS = {"provisional_pick"}


def _sources():
    files = sorted(ROOT.glob("assets/*.js")) + [ROOT / "build_site.py"]
    files += sorted(ROOT.glob("*/index.html")) + [ROOT / "index.html"]
    return [f for f in files if f.exists()]


def _slug_aliases() -> dict[str, str]:
    """eephus-gl.js SLUG_ALIASES: a merged entry's retired slug -> its keeper."""
    js = (ROOT / "assets" / "eephus-gl.js").read_text(encoding="utf-8")
    m = re.search(r"const SLUG_ALIASES = \{([^}]*)\};", js)
    return dict(re.findall(r'([a-z0-9_]+):\s*"([a-z0-9_]+)"', m.group(1))) if m else {}


def _resolver():
    g = json.loads((ROOT / "data" / "glossary.json").read_text(encoding="utf-8"))
    keys = set()
    for e in g["entries"]:
        keys.add(e["id"].lower())
        keys.add(str(e.get("term") or "").lower())
        keys.update(str(a).lower() for a in (e.get("aliases") or []))
    ids = {e["id"] for e in g["entries"]}
    # A retired slug resolves the way eephus-gl.js resolve() reads it.
    keys.update(old for old, keep in _slug_aliases().items() if keep in ids)
    return keys, ids


def test_every_referenced_glossary_slug_resolves():
    keys, _ = _resolver()
    refs: dict[str, set] = {}
    for f in _sources():
        text = f.read_text(encoding="utf-8", errors="replace")
        for pat in PATTERNS:
            for m in pat.finditer(text):
                refs.setdefault(m.group(1), set()).add(f.relative_to(ROOT).as_posix())
    for slug in DYNAMIC_SLUGS:
        refs.setdefault(slug, set()).add("(runtime)")
    missing = {s: sorted(v) for s, v in refs.items() if s.lower() not in keys}
    assert not missing, f"glossary slugs with no entry: {missing}"


def test_betting_and_dfs_entries_carry_their_groups_and_modules():
    g = json.loads((ROOT / "data" / "glossary.json").read_text(encoding="utf-8"))
    groups = g["groups"]
    by_id = {e["id"]: e for e in g["entries"]}
    assert groups.get("betting") == "Betting & Markets"
    assert groups.get("fantasy") == "Fantasy & DFS"
    assert "betting" in by_id["devig"]["module"]
    assert "fantasy" in by_id["dfs_points_per_1k"]["module"]


def test_retired_and_unserved_terms_say_so():
    """CLV was retired on 2026-09-07 (SERVE_CLV False) and the run-dispersion
    correction and probability calibration are not served; the entries must
    not describe any of them as live."""
    g = json.loads((ROOT / "data" / "glossary.json").read_text(encoding="utf-8"))
    by_id = {e["id"]: e for e in g["entries"]}
    clv = by_id["clv"]["definition"] + " " + by_id["clv"].get("methodology", "")
    assert "stopped serving CLV on 2026-09-07" in clv
    disp = by_id["run_dispersion"].get("methodology", "")
    assert "not served" in disp
    rel = by_id["reliability_curve"].get("methodology", "")
    assert "no calibration correction is applied" in rel


def test_the_scores_entries_land_with_the_page():
    """SCORES_5a_LIVE_FLIP (2026-10-07; SCORES_PLAN 11): the four entries carry
    the plan's definitions under the scores module, and each seeAlso resolves."""
    g = json.loads((ROOT / "data" / "glossary.json").read_text(encoding="utf-8"))
    by_id = {e["id"]: e for e in g["entries"]}
    want = {
        "mlb_win_probability": "MLB's own live estimate of each team's chance to win after every plate appearance",
        "stars_of_the_game": "Three players chosen by a published rule, not by a vote",
        "biggest_plays": "The five plate appearances that moved win probability most in a game",
        "abs_challenge": "A challenge of a ball or strike call, reviewed by the automated ball-strike system.",
    }
    for slug, opening in want.items():
        e = by_id[slug]
        assert e["definition"].startswith(opening), slug
        assert e["module"] == ["scores"], slug
        for other in e.get("seeAlso") or []:
            assert other in by_id, (slug, other)
    assert "not a pregame forecast" in by_id["mlb_win_probability"]["definition"]
    assert "first star from the winning team" in by_id["stars_of_the_game"]["definition"]
    js = (ROOT / "assets" / "glossary.js").read_text(encoding="utf-8")
    assert 'scores: "SCORES / STANDINGS"' in js, "the module badge reads the renamed module"
