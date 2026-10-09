# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Owner answer M23-4 (2026-09-25, census X07-09): the Beta go/no-go list and
the review queue moved from the repository root to docs/archive/ with their
ARCHIVED banners, every file that cited them was repointed, and
docs/LAUNCH_READINESS.md is the current checklist for the port."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ARCHIVED = ("BETA_READINESS.md", "REVIEW_QUEUE.md")

# A bare citation: the name not already prefixed by a path.
_BARE = re.compile(r"(?<![\w/])(REVIEW_QUEUE|BETA_READINESS)(\.md)?\b")

# Served artifacts whose producer carries the new path but cannot be re-run
# today; hand-editing a generated artifact is not allowed, so each waits for
# its producer. Remove the entry once the artifact is regenerated.
# data/sc_plus_component_eval.json left this set on 2026-10-08 when its
# producer's parity defect was repaired and it was regenerated.
PENDING_REGEN: dict[str, str] = {}


def test_both_files_live_in_docs_archive_with_their_banner():
    for name in ARCHIVED:
        assert not (ROOT / name).exists(), f"{name} is back at the repository root"
        head = (ROOT / "docs" / "archive" / name).read_text(encoding="utf-8")[:1500]
        assert "ARCHIVED 2026-09-25" in head, f"{name} lost its archived banner"


def test_launch_readiness_is_the_current_checklist():
    text = (ROOT / "docs" / "LAUNCH_READINESS.md").read_text(encoding="utf-8")
    for must in ("DEFERRED", "docs/port/PORT_SPEC.md", "disjoint history",
                 "schema", "Push", "RECORD_PUBLISH_ARMED"):
        assert must in text, f"LAUNCH_READINESS.md no longer says {must!r}"
    assert "—" not in text and "–" not in text


def _scanned() -> list[Path]:
    files = list(ROOT.glob("*.md")) + list(ROOT.glob("*.py"))
    files += list(ROOT.glob("tools/*.py")) + list(ROOT.glob("assets/*.js"))
    files += [p for p in ROOT.glob("docs/**/*.md")
              if "archive" not in p.relative_to(ROOT / "docs").parts[:1]]
    files += [ROOT / "data" / "model_registry.json", ROOT / "data" / "glossary.json"]
    me = Path(__file__).resolve()
    return [p for p in files if p.is_file() and p.resolve() != me]


def test_no_file_cites_the_old_root_paths():
    offenders = []
    for p in _scanned():
        for i, line in enumerate(p.read_text(encoding="utf-8", errors="ignore")
                                 .splitlines(), 1):
            if "docs/archive/" in line:
                continue
            if _BARE.search(line):
                offenders.append(f"{p.relative_to(ROOT)}:{i}")
    assert not offenders, (
        "cite docs/archive/BETA_READINESS.md or docs/archive/REVIEW_QUEUE.md: "
        f"{offenders[:12]}")


def test_pending_regen_artifacts_are_still_pending():
    """An entry is removed once its artifact carries the new path."""
    for rel in PENDING_REGEN:
        p = ROOT / rel
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        assert _BARE.search(text.replace("docs/archive/", "")) and \
            "docs/archive/REVIEW_QUEUE.md" not in text, (
                f"{rel} now cites the archive path; drop it from PENDING_REGEN")


# LIBRARY_8 (2026-10-07): the 2026-06-10 glossary copy ledger moved from docs/
# to docs/archive/ under the same convention, and its two by-path citations
# (build_glossary_data.py and docs/audit-2026-07/AUDIT_FINDINGS.md) moved with it.
_OLD_COPY_AUDIT = re.compile(r"(?<!archive/)glossary-copy-audit\.md")


def test_the_glossary_copy_ledger_lives_in_docs_archive_with_its_banner():
    assert not (ROOT / "docs" / "glossary-copy-audit.md").exists(), \
        "glossary-copy-audit.md is back in docs/"
    text = (ROOT / "docs" / "archive" / "glossary-copy-audit.md").read_text(encoding="utf-8")
    assert "ARCHIVED 2026-10-07" in text[:1500], "the copy ledger lost its archived banner"
    assert chr(0x2014) not in text and chr(0x2013) not in text


def test_no_file_cites_the_old_copy_ledger_path():
    offenders = [f"{p.relative_to(ROOT)}:{i}"
                 for p in _scanned()
                 for i, line in enumerate(p.read_text(encoding="utf-8", errors="ignore")
                                          .splitlines(), 1)
                 if _OLD_COPY_AUDIT.search(line)]
    assert not offenders, f"cite docs/archive/glossary-copy-audit.md: {offenders[:12]}"
    for rel in ("build_glossary_data.py", "docs/audit-2026-07/AUDIT_FINDINGS.md"):
        assert "docs/archive/glossary-copy-audit.md" in (ROOT / rel).read_text(encoding="utf-8"), rel
