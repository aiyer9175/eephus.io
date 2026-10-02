# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Copy voice linter (owner rule): flag em-dashes + LLM-ish phrasing in
user-facing copy. Companion to strip_emdashes.py, whose TARGETS list (the
canonical copy-surface set) this reuses.

Voice standard: terse, math-first, direct, human; no LLM cadence; no em-dashes.

Two severities so the gate stays meaningful without code false-positives:
  - em-dashes: hard fail anywhere (mirrors strip_emdashes --check).
  - LLM ban-list terms: hard fail in PURE-COPY files (glossary.json, README,
    content/*); advisory-only elsewhere (HTML/JS/PY also hold code, where words
    like "ensures"/"robust" are legitimate identifiers/comments).

Run: python tools/copy_lint.py [--check]
  --check: exit 1 on any hard finding (used by the copy-audit test).
"""

from __future__ import annotations

import re
import sys
from bisect import bisect_right
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from strip_emdashes import EM, ROOT, _files, escaped_dash_count  # reuse the canonical surface list

# Whole-word / phrase patterns. Case-insensitive. Keep this list curated; the
# point is to catch LLM cadence, not to ban every long word.
# NOTE: the NOUN "leverage" is intentionally NOT banned - it's a core baseball
# term (Leverage Index; high-leverage role; the leverage of the moment). The
# owner's rule bans the marketing VERB, so only its verb forms are listed
# ("leverages", "leveraged", "leveraging"). "showcase" is banned in pure copy
# and advisory elsewhere, where "showcase circuit" is third-party scouting prose.
# Census X07-05 (2026-09-25) added the rest of the owner's list: essential,
# powerful, unlock, elevate, underscore, harness. "elevation" (a park's
# altitude) and "essentially" stay legal: the patterns are whole-word.
BAN = [
    r"\bseamless(ly)?\b", r"\brobust(ly|ness)?\b",
    r"\bdelve[ds]?\b", r"\bcomprehensive(ly)?\b", r"\bcrucial(ly)?\b",
    r"\butiliz\w*\b", r"\bmyriad\b", r"\bplethora\b", r"it'?s worth noting",
    r"in the realm of", r"a testament to", r"game-chang\w*", r"cutting-edge",
    r"\bdive into\b", r"(rich|vibrant) tapestry", r"\bmeticulous(ly)?\b",
    r"\bshowcases?\b",
    r"\bessential\b", r"\bpowerful(ly)?\b", r"\bunlock(s|ed|ing)?\b",
    r"\belevat(e|es|ed|ing)\b", r"\bunderscor(e|es|ed|ing)\b",
    r"\bharness(es|ed|ing)?\b", r"\bleverag(es|ed|ing)\b",
]
BAN_RE = re.compile("|".join(BAN), re.IGNORECASE)

# Perf (2026-07-17): the surfaces total ~95MB and running the 17-branch
# case-insensitive BAN_RE on every line took 30s+ per gate run. Every BAN
# alternative contains at least one of these literal lowercase needles, so
# a C-speed substring scan over a casefolded copy of the whole file finds
# every line that could possibly match; BAN_RE then runs on just those
# candidate lines (complete lines, so per-line match semantics and the
# report output are unchanged). Keep this tuple in sync with BAN: every
# alternative must contain at least one needle case-insensitively, or the
# prefilter could skip a real finding.
_NEEDLES = (
    "seamless", "robust", "delve", "comprehensive", "crucial", "utiliz",
    "myriad", "plethora", "worth noting", "in the realm of",
    "a testament to", "game-chang", "cutting-edge", "dive into",
    "tapestry", "meticulous", "showcase",
    "essential", "powerful", "unlock", "elevat", "underscor", "harness",
    "leverag",
)

# Files that are pure copy (no code), so a ban-list hit is real prose to fix.
# content/articles/* is owner editorial (long-form essays where normal English
# like "crucial" is the author's own voice), so it's ADVISORY, not hard-fail.
PURE_COPY = {
    "README.md", "data/glossary.json", "data/team.json",
    "assets/team/README.md",
}


def _is_pure(rel: str) -> bool:
    return rel in PURE_COPY


def _scan_lines(rel: str, text: str, em_hits: list[str], ban: list[str]) -> None:
    """The original exact per-line scan. Kept as the fallback for the rare
    file where casefolding changes the text length (a char like U+0130 with
    a multi-char casefold would shift the fast path's offsets)."""
    for i, line in enumerate(text.split("\n"), 1):
        if EM in line:
            em_hits.append(f"{rel}:{i}")
        for m in BAN_RE.finditer(line):
            ban.append(f"{rel}:{i}: {m.group(0)!r}")


def _scan(rel: str, text: str, em_hits: list[str], ban: list[str]) -> None:
    """Prefiltered scan. Output (records + order) is identical to
    _scan_lines: em-dash hits are one record per line in line order; BAN
    records run line-ascending then match-position-ascending, exactly like
    the old per-line finditer."""
    low = text.casefold()
    if len(low) != len(text):
        # Casefold moved offsets; take the exact per-line path instead.
        _scan_lines(rel, text, em_hits, ban)
        return
    has_em = EM in text
    cand: set[int] = set()
    for needle in _NEEDLES:
        j = low.find(needle)
        while j != -1:
            cand.add(j)
            j = low.find(needle, j + 1)
    if not has_em and not cand:
        return
    # Line-start offsets; a "\n"-split line number is bisect_right(starts, i).
    starts = [0]
    j = text.find("\n")
    while j != -1:
        starts.append(j + 1)
        j = text.find("\n", j + 1)
    n_lines = len(starts)
    if has_em:
        last_line = 0
        j = text.find(EM)
        while j != -1:
            ln = bisect_right(starts, j)
            if ln != last_line:  # one record per line, like `if EM in line`
                em_hits.append(f"{rel}:{ln}")
                last_line = ln
            j = text.find(EM, j + 1)
    if cand:
        # No BAN pattern (or needle) can span a newline, so running BAN_RE
        # over each complete candidate line reproduces per-line matching.
        for ln in sorted({bisect_right(starts, j) for j in cand}):
            lo = starts[ln - 1]
            hi = starts[ln] - 1 if ln < n_lines else len(text)
            for m in BAN_RE.finditer(text[lo:hi]):
                ban.append(f"{rel}:{ln}: {m.group(0)!r}")


def _rel(p: Path) -> str:
    try:
        return str(p.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(p).replace("\\", "/")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    check = "--check" in argv
    # Positional paths replace the TARGETS list (the gate's own tests use it).
    # An explicit file is judged as pure copy when its NAME is one of the
    # pure-copy names, so a fixture glossary.json fails like the real one.
    explicit = [Path(a).resolve() for a in argv if not a.startswith("--")]
    pure_names = {Path(r).name for r in PURE_COPY}
    em_hits: list[str] = []
    ban_hard: list[str] = []
    ban_soft: list[str] = []
    for p in (explicit or _files()):
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        rel = _rel(p)
        pure = _is_pure(rel) or (bool(explicit) and p.name in pure_names)
        _scan(rel, text, em_hits, ban_hard if pure else ban_soft)
        if p.suffix == ".json" and escaped_dash_count(text):
            # ensure_ascii dumps store the dash as an escape; it still renders.
            em_hits.append(f"{rel}: {escaped_dash_count(text)} ASCII-escaped em/en-dash(es)")

    if em_hits:
        print("EM-DASHES (fail):", *em_hits[:60], sep="\n  ")
    if ban_hard:
        print("\nLLM TERMS in pure-copy (fail):", *ban_hard[:100], sep="\n  ")
    if ban_soft:
        print(f"\nLLM TERMS in code/copy files (advisory, review) - {len(ban_soft)} total:",
              *ban_soft[:60], sep="\n  ")

    fail = bool(em_hits or ban_hard)
    if check:
        print("\ncopy_lint: FAIL" if fail else
              "\ncopy_lint: clean (no em-dashes; no LLM terms in pure-copy)")
        return 1 if fail else 0
    print(f"\ncopy_lint: {len(em_hits)} em-dash, {len(ban_hard)} hard, "
          f"{len(ban_soft)} advisory")
    return 0


if __name__ == "__main__":
    sys.exit(main())
