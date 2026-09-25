"""The provisional-grade freeze of 2026-09-25 is a prospective prediction ledger.

WHY THIS FILE EXISTS. The owner asked (2026-09-25) for provisional grades that are
"ahead of the industry": a grade for a prospect no source has graded yet. The only
honest proof is prospective. On 2026-09-25 the served provisional grade and the
research challenger's P(first grade) and predicted first FanGraphs FV were frozen for
6,066 ungraded players, and the freeze is scored when FanGraphs, MLB Pipeline, Baseball
America, ESPN and Just Baseball publish first grades (windows 2027-04-15 and
2027-10-15; spec PROVISIONAL_V2.md section 4, research bundle
_finalpass_2026-09-24/provisional/).

A freeze is only evidence if nobody can edit it after the grades arrive. The git
commit date is the timestamp; these pins make any later rewrite of the file, or of any
row inside it, fail the suite. Nothing regenerates these files.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
D = ROOT / "data" / "provisional_freeze"
FREEZE = D / "FREEZE_provisional_2026-09-25.json"
MANIFEST = D / "FREEZE_provisional_2026-09-25.manifest.json"
SERVED = D / "xfv_ungraded_2026-09-24.json"

FILE_SHA256 = "39e4d46060706a529b08d36363d379201ff472037b44d21552245f8d7eef7d4f"
ROWS_SHA256 = "1bddcc1ae2ea010645647a9707cae6f6cad90ff6b2d8b31de4eb9b00d1890112"
SERVED_SHA256 = "b048218aaf369a7b063e75e2aec7047bf55396ae530d4cd2d818df7d1e76df49"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canon_rows(rows: list) -> str:
    # The research scorer's canonical form (score_freeze.canon_rows), verbatim.
    return hashlib.sha256(json.dumps(sorted(rows, key=lambda r: str(r["key"])), sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def test_the_freeze_file_is_byte_identical_to_the_one_built_on_2026_09_25():
    assert _sha(FREEZE) == FILE_SHA256


def test_no_row_inside_the_freeze_has_changed():
    doc = json.loads(FREEZE.read_text(encoding="utf-8"))
    assert doc["frozen_at"] == "2026-09-25"
    assert len(doc["rows"]) == 6066
    assert _canon_rows(doc["rows"]) == ROWS_SHA256
    assert doc["sha256_rows"] == ROWS_SHA256


def test_the_served_artifact_it_was_taken_from_is_kept_and_pinned():
    # data/xfv_ungraded.json is gitignored and rewritten nightly, so this copy is the
    # only record of the served provisional grades the freeze was taken from.
    assert _sha(SERVED) == SERVED_SHA256
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert m["inputs"]["served"]["file_sha256"] == SERVED_SHA256
    assert m["sha256_file"] == FILE_SHA256 and m["sha256_rows"] == ROWS_SHA256
    assert m["windows"] == {"W6": "2027-04-15", "W12": "2027-10-15"}


def test_the_freeze_is_evidence_not_a_served_payload():
    # Nothing on the site fetches it, and the deploy step does not ship it.
    publish = (ROOT / "deploy" / "publish_paths.txt").read_text(encoding="utf-8")
    assert "provisional_freeze" not in publish
