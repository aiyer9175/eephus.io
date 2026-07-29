# AUDIT LANE `fa` scratch lab. READ-ONLY against the FA stack.
# Caches the expensive corpus build so every downstream probe is cheap.
"""Shared helpers for the fa-lane audit (accuracy / redundancy / coherence)."""
from __future__ import annotations

import json
import os
import pickle
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
SCRATCH = Path(os.environ.get(
    "AM_FA_SCRATCH",
    r"C:\Users\noah\AppData\Local\Temp\claude\c--Users-noah-baseball-projects-BaseballR"
    r"\c6ce73e3-6700-473f-beea-01f160967961\scratchpad"))
SCRATCH.mkdir(parents=True, exist_ok=True)


def cached(name: str, fn):
    p = SCRATCH / (name + ".pkl")
    if p.exists():
        with open(p, "rb") as fh:
            return pickle.load(fh)
    v = fn()
    with open(p, "wb") as fh:
        pickle.dump(v, fh)
    return v


def signings():
    """enriched_signings(2015, 2026) - the Gate-2 corpus, cached."""
    def build():
        import fa_market as fm
        return fm.enriched_signings(2015, 2026)
    return cached("fa_enriched_signings", build)


def artifact(name: str) -> dict:
    return json.loads((ROOT / "data" / f"{name}.json").read_text(encoding="utf-8"))


def mae(pairs):
    return sum(abs(a - b) for a, b in pairs) / len(pairs) if pairs else float("nan")
