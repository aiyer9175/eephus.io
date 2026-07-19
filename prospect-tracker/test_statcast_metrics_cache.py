# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Tests for statcast_metrics._get_json cache hardening.

Pins two properties that mirror feed_cache:
  1. A corrupt / crash-truncated cache file (fresh mtime, within TTL) is
     re-fetched instead of raising a hard JSONDecodeError.
  2. The cache write is atomic (writer-unique temp + os.replace), so a killed
     process never leaves a half-written file and no stray .tmp lingers.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import requests

sys.path.insert(0, str(Path(__file__).parent))

import statcast_metrics


def _patch(monkeypatch, tmp_path, payload):
    monkeypatch.setattr(statcast_metrics, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(statcast_metrics.time, "sleep", lambda *_: None)
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status = MagicMock()
    session = MagicMock()
    session.get.return_value = resp
    monkeypatch.setattr(statcast_metrics, "SESSION", session)
    return session


def _cache_path(tmp_path, url, params=None):
    key = requests.Request("GET", url, params=params).prepare().url or url
    versioned = f"{statcast_metrics.CACHE_VERSION}|{key}"
    safe = hashlib.md5(versioned.encode("utf-8")).hexdigest()
    return tmp_path / f"{safe}.json"


def test_corrupt_cache_is_refetched(monkeypatch, tmp_path):
    url = "https://statsapi.mlb.com/api/v1/people/12345/stats"
    payload = {"stats": [{"ok": True}]}
    session = _patch(monkeypatch, tmp_path, payload)

    # A half-written file with a fresh mtime would previously raise
    # JSONDecodeError with no re-fetch for the whole TTL window.
    p = _cache_path(tmp_path, url)
    p.write_text("{ half-written", encoding="utf-8")

    out = statcast_metrics._get_json(url)
    assert out == payload
    assert session.get.call_count == 1
    assert json.loads(p.read_text(encoding="utf-8")) == payload  # cache healed


def test_write_is_atomic_no_leftover_tmp(monkeypatch, tmp_path):
    url = "https://statsapi.mlb.com/api/v1/people/777/stats"
    payload = {"stats": [1, 2, 3]}
    session = _patch(monkeypatch, tmp_path, payload)

    out = statcast_metrics._get_json(url)
    assert out == payload

    p = _cache_path(tmp_path, url)
    assert json.loads(p.read_text(encoding="utf-8")) == payload
    assert list(tmp_path.glob("*.tmp")) == []  # writer temp cleaned up

    # Second call is served from disk with no new network fetch.
    statcast_metrics._get_json(url)
    assert session.get.call_count == 1
