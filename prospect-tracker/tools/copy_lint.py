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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from strip_emdashes import EM, ROOT, _files  # reuse the canonical surface list

# Whole-word / phrase patterns. Case-insensitive. Keep this list curated; the
# point is to catch LLM cadence, not to ban every long word.
# NOTE: "leverage" is intentionally NOT banned - it's a core baseball term
# (Leverage Index; high-leverage role; salary/playoff leverage). Same caution
# applies to "showcase" (showcase circuit) - review hits in context.
BAN = [
    r"\bseamless(ly)?\b", r"\brobust(ly|ness)?\b",
    r"\bdelve[ds]?\b", r"\bcomprehensive(ly)?\b", r"\bcrucial(ly)?\b",
    r"\butiliz\w*\b", r"\bmyriad\b", r"\bplethora\b", r"it'?s worth noting",
    r"in the realm of", r"a testament to", r"game-chang\w*", r"cutting-edge",
    r"\bdive into\b", r"(rich|vibrant) tapestry", r"\bmeticulous(ly)?\b",
    r"\bshowcases?\b",
]
BAN_RE = re.compile("|".join(BAN), re.IGNORECASE)

# Files that are pure copy (no code), so a ban-list hit is real prose to fix.
# content/articles/* is owner editorial (long-form essays where normal English
# like "crucial" is the author's own voice), so it's ADVISORY, not hard-fail.
PURE_COPY = {
    "README.md", "data/glossary.json", "content/team.json",
    "assets/team/README.md",
}


def _is_pure(rel: str) -> bool:
    return rel in PURE_COPY


def main() -> int:
    check = "--check" in sys.argv
    em_hits: list[str] = []
    ban_hard: list[str] = []
    ban_soft: list[str] = []
    for p in _files():
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        rel = str(p.relative_to(ROOT)).replace("\\", "/")
        for i, line in enumerate(text.split("\n"), 1):
            if EM in line:
                em_hits.append(f"{rel}:{i}")
            for m in BAN_RE.finditer(line):
                rec = f"{rel}:{i}: {m.group(0)!r}"
                (ban_hard if _is_pure(rel) else ban_soft).append(rec)

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
