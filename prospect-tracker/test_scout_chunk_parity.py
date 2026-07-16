"""The scout-report chunk split is a two-sided contract: storage.py buckets
each player_key into scout_reports_<i>.json with sum(ord(ch)) % N, and
prospx/index.html's _scoutChunkOf must compute the SAME index or card opens
fetch the wrong chunk and the scouting tab silently never loads. This pins
both sides to the shared algorithm (N=8 today; the meta block carries it)."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parent

SAMPLE_KEYS = [
    "jesus_made", "ryan_vilade", "konnor_griffin", "a", "",
    "sebastian_walcott", "jj_wetherholt", "zyhir_hope", "x" * 63,
]


def _storage_chunk(key: str, n: int) -> int:
    # The exact expression storage.py uses at the split site.
    return sum(ord(c) for c in key) % n


def _js_chunk(key: str, n: int) -> int:
    # _scoutChunkOf keeps a running modulo; equivalent by modular arithmetic.
    s = 0
    for ch in key:
        s = (s + ord(ch)) % n
    return s


def test_chunk_algorithms_agree():
    for key in SAMPLE_KEYS:
        for n in (2, 8, 16):
            assert _storage_chunk(key, n) == _js_chunk(key, n), (key, n)


def test_storage_split_site_uses_the_pinned_expression():
    src = (ROOT / "storage.py").read_text(encoding="utf-8")
    assert "sum(ord(_c) for _c in _k) % _SCOUT_CHUNKS" in src, (
        "storage.py's scout chunk expression changed - update _scoutChunkOf "
        "in prospx/index.html and this pin together")


def test_prospx_scout_chunk_fn_matches():
    src = (ROOT / "prospx" / "index.html").read_text(encoding="utf-8")
    m = re.search(r"function _scoutChunkOf\(playerKey, nChunks\) \{(.*?)\}", src, re.S)
    assert m, "prospx _scoutChunkOf missing - the chunked scout fetch contract broke"
    body = m.group(1)
    # Running-modulo charCodeAt sum: the JS side of the pinned algorithm.
    assert "charCodeAt" in body and "% nChunks" in body, body
