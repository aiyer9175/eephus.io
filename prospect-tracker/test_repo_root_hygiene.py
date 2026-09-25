# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The git root (the parent of prospect-tracker/) must not offer JSON to a
blanket `git add`. On 2026-09-24 the untracked, unignored _pre_epoch_2026-09/
snapshot held withheld label files (star_label_view.json, both xfv matrices)
beside 150 MB of served artifacts; one root `git add -A` would have written
them into the history the port pushes."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None or not (REPO / ".git").exists(),
    reason="needs a git checkout")


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(REPO), *args], check=True,
                          capture_output=True, text=True).stdout


def test_pre_epoch_snapshots_are_ignored_at_the_root():
    """Pinned on paths, so it holds whether or not the snapshot is on disk."""
    for rel in ("_pre_epoch_2026-09/star_label_view.json",
                "_pre_epoch_2026-09/xfv_hitter_matrix.json",
                "_pre_epoch_2027-01/prospects.db"):
        out = subprocess.run(["git", "-C", str(REPO), "check-ignore", "-q", rel])
        assert out.returncode == 0, f"{rel} is not ignored by the root .gitignore"


def test_no_untracked_json_outside_the_data_dir():
    """Untracked, unignored JSON anywhere but prospect-tracker/data/ is a
    file a blanket add would commit. Ignore it or move it out of the tree."""
    stray = [p for p in _git("ls-files", "--others", "--exclude-standard")
             .splitlines()
             if p.endswith((".json", ".json.gz"))
             and not p.startswith("prospect-tracker/data/")]
    assert not stray, f"untracked, unignored JSON outside data/: {stray[:20]}"
