# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Published payloads carry no absolute paths from the build machine.

The 2026-08-16 session removed dev-machine absolute paths from
data/betting.json (4), data/betting_preview.json (3), the betting_learning
shadow storage, data/consensus_rank_eval.json (a prospects.db path) and
data/fbhr_csw_eval.json (a scratchpad path). Every one of those shipped: a
public JSON payload that names C:\\Users\\<user>\\... discloses the operator's
username and directory layout to anyone who opens the network tab.

This guard scans the RAW TEXT of every data/*.json in the publish set. The
publish set is derived, not assumed: deploy/publish_paths.txt documents that
data/ ships its top-level *.json wholesale (plus the pitch_plots/ and
player_detail/ splits), and deploy/data_exclude.txt lists the files held
back. So publish set = glob(data/*.json) minus the exclude list, which is
exactly what rsync serves. Eval artifacts ship ON PURPOSE (the exclude
list's own header says so), which is why *_eval.json files are in scope -
two of them are today's remaining offenders.

BURN_DOWN below is the debt ledger for offenders found on 2026-08-16 that
the session did not already fix. Both directions are asserted: a file not
on the ledger must be clean, and a ledger entry must still be dirty, so a
healed file has to leave the list in the same change that heals it.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / "data"
EXCLUDE_LIST = ROOT / "deploy" / "data_exclude.txt"

# ---------------------------------------------------------------------------
# The patterns. Raw-text scan, so a Windows path inside a JSON string reads
# as C:\\Users\\... (the backslashes arrive escaped).
# ---------------------------------------------------------------------------

PATTERNS = {
    # Drive letter + escaped backslash, the JSON-encoded Windows path form.
    # The lookbehind requires the drive letter to be a STANDALONE letter:
    # without it, prose like "aesthetic:\\\n" in glossary.json (the letter c
    # of a word, a colon, then an escaped backslash) is a false positive,
    # measured on the live tree 2026-08-16.
    "drive_backslash": re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:\\\\"),
    # Drive letter + forward slash (C:/Users/...). The negative lookahead
    # keeps every protocol form (https://, file://) out: in "https://" the
    # candidate ":/" is followed by a second "/", so it never matches. The
    # lookbehind again requires a standalone letter, so the s of https:/
    # cannot start a match either.
    "drive_forward": re.compile(r"(?<![A-Za-z0-9/])[A-Za-z]:/(?!/)"),
    # Unix home prefixes.
    "unix_home": re.compile(r"/home/"),
    "unix_users": re.compile(r"/Users/"),
    # Windows profile internals.
    "appdata": re.compile(r"AppData"),
    # The OS username as a standalone PATH SEGMENT (bounded by separators),
    # so player names like "Noah Schultz" or slugs like /noah-schultz/ never
    # match, but \\noah\\ and /noah/ do.
    "username_segment": re.compile(r"(?i)[/\\]noah(?=[/\\\"\s]|$)"),
}

# ---------------------------------------------------------------------------
# The burn-down ledger: offenders found 2026-08-16 that the session did not
# already fix. filename -> dated reason. A file on this list is asserted
# STILL DIRTY; fixing it means deleting its entry here in the same change.
# ---------------------------------------------------------------------------

# EMPTY as of 2026-08-16, the same day it was created: the two offenders it
# opened with (betting_market_blend_eval.json basis.source and
# betting_model_eval.json vintage_coverage.dir, both dev absolute paths) were
# healed within the hour, in the writers (betting_market_blend_lab,
# leaderboard_vintages._relative_or_verbatim) and in the stored artifacts.
# A new leak has no grace period: it fails the clean assertion outright.
BURN_DOWN: dict[str, str] = {
    # 2026-10-14 (DVM-4, Q10_15): the one scored look of
    # docs/dvm-difficulty-2026-09-30/DVM_DIFFICULTY_GATE.md wrote receipt.frozen_db as
    # an absolute path. The look cannot run twice and the artifact is not hand-edited;
    # the writer is fixed (dvm_difficulty_lab._rel), so the next registered refit heals it.
    "dvm_difficulty_eval.json": ("2026-10-14: receipt.frozen_db from the one look; "
                                 "writer fixed, artifact frozen until the next refit"),
}


def publish_set() -> list[Path]:
    """glob(data/*.json) minus deploy/data_exclude.txt, i.e. what rsync ships."""
    excluded = set()
    for line in EXCLUDE_LIST.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            excluded.add(line)
    return sorted(p for p in DATA.glob("*.json") if p.name not in excluded)


def scan_text(text: str) -> dict[str, str]:
    """pattern name -> a short context snippet around the first hit."""
    hits = {}
    for name, pat in PATTERNS.items():
        m = pat.search(text)
        if m:
            start = max(0, m.start() - 60)
            hits[name] = text[start:m.end() + 80].replace("\n", " ")
    return hits


# ---------------------------------------------------------------------------
# Derivation sanity: if the publish set collapses, every assertion below
# passes vacuously, so the set itself is pinned first.
# ---------------------------------------------------------------------------

def test_publish_set_derivation_is_sane():
    pub = {p.name for p in publish_set()}
    assert len(pub) > 300, (
        f"publish set collapsed to {len(pub)} files; the data/*.json glob or "
        "deploy/data_exclude.txt parse is broken")
    # A file every page fetches must be in, a listed exclude must be out.
    assert "glossary.json" in pub
    assert "betting_model_eval.json" in pub, (
        "eval artifacts ship on purpose (data_exclude.txt header); if this "
        "moved to the exclude list, retire its BURN_DOWN entry too")
    assert "xfv_scored.json" not in pub, "data_exclude.txt entry leaked into the publish set"


# ---------------------------------------------------------------------------
# The guard itself, both directions.
# ---------------------------------------------------------------------------

def test_published_payloads_carry_no_absolute_paths():
    offenders = {}
    for p in publish_set():
        if p.name in BURN_DOWN:
            continue
        hits = scan_text(p.read_text(encoding="utf-8", errors="replace"))
        if hits:
            offenders[p.name] = hits
    assert not offenders, (
        "published data/*.json carrying absolute build-machine paths (fix the "
        "exporter, or add a DATED BURN_DOWN entry if it cannot be fixed today): "
        + "; ".join(f"{n} -> {h}" for n, h in sorted(offenders.items())))


def test_burn_down_entries_are_still_dirty():
    """A healed file must leave the ledger, or the ledger rots into an
    allowlist that silently permits the leak to come back."""
    for name, reason in BURN_DOWN.items():
        p = DATA / name
        assert p.exists(), f"BURN_DOWN names {name}, which no longer exists; delete the entry"
        hits = scan_text(p.read_text(encoding="utf-8", errors="replace"))
        assert hits, (
            f"{name} is clean now: delete its BURN_DOWN entry "
            f"(ledger reason was: {reason})")


def test_burn_down_reasons_are_dated():
    for name, reason in BURN_DOWN.items():
        assert re.search(r"20\d\d-\d\d-\d\d", reason), (
            f"BURN_DOWN[{name!r}] carries no date; an undated debt never gets paid")


# ---------------------------------------------------------------------------
# Mutation proofs: the scanner detects a seeded leak, and the https
# exemption is load-bearing rather than decorative.
# ---------------------------------------------------------------------------

def test_mutation_seeded_leak_is_detected(tmp_path):
    # Temp copy of a real, currently-clean publish file with a leak seeded in.
    # The scanner reads raw text, so appending is a faithful tamper.
    donor = next(p for p in publish_set() if not scan_text(
        p.read_text(encoding="utf-8", errors="replace")))
    seeded = tmp_path / donor.name
    seeded.write_text(
        donor.read_text(encoding="utf-8", errors="replace")
        + '\n"leak": "C:\\\\Users\\\\noah\\\\prospects.db"',
        encoding="utf-8")
    hits = scan_text(seeded.read_text(encoding="utf-8"))
    assert "drive_backslash" in hits and "username_segment" in hits, (
        f"seeded fixture leak in a temp copy of {donor.name} not detected: {hits}")


def test_mutation_forward_slash_and_unix_forms_are_detected():
    assert "drive_forward" in scan_text('{"p": "C:/Users/noah/prospects.db"}')
    assert "unix_home" in scan_text('{"p": "/home/deploy/app"}')
    assert "unix_users" in scan_text('{"p": "/Users/somebody/app"}')
    assert "appdata" in scan_text('{"p": "..\\\\AppData\\\\Local"}')


def test_https_exemption_holds_and_is_load_bearing():
    # The exemption: URLs never match.
    assert not scan_text('{"u": "https://example.com/a/b.json"}')
    assert not scan_text('{"u": "http://x.io/C//nope"}')
    # Prose false-positive from the live tree (glossary.json): a word ending
    # in a letter, a colon, then an escaped line continuation.
    assert not scan_text('{"t": "the refractor aesthetic:\\\\\\n bullet one"}')
    # Tamper: strip the guards off the pattern and https:// DOES match, which
    # proves the lookahead/lookbehind are what keep the exemption honest.
    tampered = re.compile(r"[A-Za-z]:/")
    assert tampered.search("https://example.com"), (
        "the tampered pattern no longer matches a URL, so the exemption test "
        "is not exercising anything")
    assert not PATTERNS["drive_forward"].search("https://example.com")


def test_mutation_username_is_only_flagged_as_a_path_segment():
    assert not scan_text('{"name": "Noah Schultz"}')
    assert not scan_text('{"u": "https://site.io/players/noah-schultz/"}')
    assert "username_segment" in scan_text('{"p": "/tmp/noah/x"}')
