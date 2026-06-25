"""Fetch and normalize player-news snippets for the static site.

RotoWire's MLB API exposes a feed-level News/Injuries endpoint, so the
collector fetches date slices and filters them down to tracked prospects by
name. Output is a static sidecar consumed by the frontend:

    data/player_news.json

Usage:
    ROTOWIRE_API_KEY=... python player_news.py --player "Carlos Lagrange"
"""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from scrapers import canonical_player_key

BASE_URL = "https://api.rotowire.com/Baseball/MLB/News/Injuries.php"
OUT_PATH = Path(__file__).parent / "data" / "player_news.json"


def _flatten_feed(payload: Any) -> list[dict]:
    """Return likely news dicts from an unknown RotoWire JSON wrapper."""
    if isinstance(payload, list):
        out: list[dict] = []
        for item in payload:
            out.extend(_flatten_feed(item))
        return out
    if not isinstance(payload, dict):
        return []
    child_keys = ("news", "injuries", "players", "items", "data", "results")
    found: list[dict] = []
    for key in child_keys:
        val = payload.get(key)
        if isinstance(val, (list, dict)):
            found.extend(_flatten_feed(val))
    if found:
        return found
    text_blob = " ".join(str(payload.get(k) or "") for k in (
        "player", "name", "firstname", "lastname", "headline", "news", "note", "analysis"
    ))
    return [payload] if text_blob.strip() else []


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


def _matches_player(item: dict, player_name: str) -> bool:
    target = _norm(player_name)
    first_last = _norm(f"{item.get('firstname', '')} {item.get('lastname', '')}")
    candidates = [
        item.get("player"),
        item.get("name"),
        item.get("player_name"),
        item.get("full_name"),
        first_last,
        item.get("headline"),
        item.get("news"),
        item.get("note"),
        item.get("analysis"),
    ]
    return any(target and target in _norm(c) for c in candidates)


def _pick(item: dict, *keys: str) -> Any:
    for key in keys:
        val = item.get(key)
        if val not in (None, ""):
            return val
    return None


def normalize_item(item: dict, player_name: str) -> dict:
    published_at = _pick(item, "date", "time", "updated", "published", "published_at")
    headline = _pick(item, "headline", "title")
    summary = _pick(item, "news", "note", "injury", "analysis", "description", "body")
    analysis = _pick(item, "analysis", "impact")
    return {
        "source": "RotoWire",
        "player_name": player_name,
        "published_at": str(published_at or ""),
        "headline": str(headline or summary or "RotoWire update"),
        "summary": str(summary or ""),
        "analysis": str(analysis or ""),
        "url": str(_pick(item, "url", "link") or ""),
        "raw": item,
    }


def fetch_rotowire_news(api_key: str, day: str) -> list[dict]:
    params = urllib.parse.urlencode({"format": "json", "date": day, "key": api_key})
    with urllib.request.urlopen(f"{BASE_URL}?{params}", timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return _flatten_feed(payload)


def collect_player_news(player_name: str, days: int, api_key: str) -> list[dict]:
    rows: list[dict] = []
    seen = set()
    today = date.today()
    for offset in range(max(1, days)):
        day = (today - timedelta(days=offset)).isoformat()
        for item in fetch_rotowire_news(api_key, day):
            if not _matches_player(item, player_name):
                continue
            norm = normalize_item(item, player_name)
            key = (norm["published_at"], norm["headline"], norm["summary"])
            if key in seen:
                continue
            seen.add(key)
            rows.append(norm)
    rows.sort(key=lambda r: r.get("published_at") or "", reverse=True)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--player", required=True, help="Player name to filter, e.g. Carlos Lagrange")
    ap.add_argument("--days", type=int, default=30, help="Date windows to scan backward")
    ap.add_argument("--out", type=Path, default=OUT_PATH)
    args = ap.parse_args()

    api_key = os.environ.get("ROTOWIRE_API_KEY") or os.environ.get("MLB_API_KEY")
    if not api_key:
        raise SystemExit("ROTOWIRE_API_KEY is not set; cannot call RotoWire.")

    player_key = canonical_player_key(args.player)
    news = collect_player_news(args.player, args.days, api_key)

    existing: dict[str, list[dict]] = {}
    if args.out.exists():
        existing = json.loads(args.out.read_text(encoding="utf-8") or "{}")
    existing[player_key] = news
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(existing, indent=2, sort_keys=True), encoding="utf-8")
    print(f"wrote {len(news)} RotoWire item(s) for {args.player} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
