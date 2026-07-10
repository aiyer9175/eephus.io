# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""eephus.io — FV-change notification job (Part 5).

After the monthly grade refresh, this diffs each prospect's consensus FV (the two
most recent points in data/timeseries.json) and inserts an `fv_change`
notification for every user who watches a moved prospect — tying the social layer
to the data layer so "tracking a prospect" means something concrete.

Runs SERVER-SIDE ONLY with the Supabase **service-role** key (never shipped to
the browser). It is a NO-OP when the env vars are absent, so it's safe to call
unconditionally at the end of the monthly pipeline:

    SUPABASE_URL=...                      # project URL
    SUPABASE_SERVICE_ROLE_KEY=...         # service-role key (CI secret only)

Talks to Supabase via the PostgREST API (stdlib + requests) so it adds no new
heavyweight dependency. Respects notification_prefs.fv_change (users who toggled
FV alerts off are skipped) and dedupes one alert per (user, prospect) per run.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).parent
TIMESERIES = ROOT / "data" / "timeseries.json"


def _players(ts: dict | list) -> list[dict]:
    """timeseries.json has varied across versions — accept a top-level list, or
    a dict with a `players` list, or a {player_key: player} mapping."""
    if isinstance(ts, list):
        return ts
    if isinstance(ts, dict):
        if isinstance(ts.get("players"), list):
            return ts["players"]
        # mapping of key -> player object
        vals = [v for v in ts.values() if isinstance(v, dict) and v.get("points")]
        if vals:
            return vals
    return []


def _fv(point: dict):
    for k in ("consensus_fv", "consensus_fv_raw", "fv"):
        if point.get(k) is not None:
            return point[k]
    return None


def compute_fv_changes(ts: dict | list) -> dict[str, dict]:
    """Return {player_key: {"name","old","new"}} for prospects whose two most
    recent consensus-FV points differ (i.e. the latest grade update moved them)."""
    out: dict[str, dict] = {}
    for p in _players(ts):
        key = p.get("player_key") or p.get("key")
        pts = p.get("points") or []
        if not key or len(pts) < 2:
            continue
        new, old = _fv(pts[-1]), _fv(pts[-2])
        if new is None or old is None or new == old:
            continue
        out[key] = {"name": p.get("player_name") or p.get("name") or key,
                    "old": old, "new": new}
    return out


def _rest(session, method, url, key, **kw):
    headers = kw.pop("headers", {})
    headers.update({"apikey": key, "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json"})
    return session.request(method, url, headers=headers, timeout=30, **kw)


def notify_fv_changes(dry_run: bool = False) -> int:
    """Insert fv_change notifications for watchers of moved prospects.
    Returns the number of notifications written (0 when unconfigured)."""
    base = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not base or not key:
        print("forum_notify: SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY unset — skipping (no-op).")
        return 0
    try:
        import requests  # local import so the no-op path needs nothing
    except ImportError:
        print("forum_notify: `requests` not installed — skipping.")
        return 0
    if not TIMESERIES.exists():
        print("forum_notify: data/timeseries.json missing — skipping.")
        return 0

    changes = compute_fv_changes(json.loads(TIMESERIES.read_text(encoding="utf-8")))
    if not changes:
        print("forum_notify: no FV changes this run.")
        return 0
    print(f"forum_notify: {len(changes)} prospect(s) moved this run.")

    rest = base.rstrip("/") + "/rest/v1"
    s = requests.Session()

    # Who watches the moved prospects? (entity_type=prospect, entity_key in set)
    keys = list(changes.keys())
    watchers: list[dict] = []
    # PostgREST `in` list — chunk to keep the URL sane.
    for i in range(0, len(keys), 100):
        chunk = keys[i:i + 100]
        in_list = "(" + ",".join('"' + k.replace('"', '') + '"' for k in chunk) + ")"
        r = _rest(s, "GET", f"{rest}/watchlist", key,
                  params={"entity_type": "eq.prospect", "entity_key": f"in.{in_list}",
                          "select": "user_id,entity_key"})
        r.raise_for_status()
        watchers.extend(r.json())
    if not watchers:
        print("forum_notify: no watchers for the moved prospects.")
        return 0

    # Users who turned FV alerts OFF.
    r = _rest(s, "GET", f"{rest}/notification_prefs", key,
              params={"fv_change": "eq.false", "select": "user_id"})
    r.raise_for_status()
    muted = {row["user_id"] for row in r.json()}

    rows, seen = [], set()
    for w in watchers:
        uid, ekey = w["user_id"], w["entity_key"]
        if uid in muted or (uid, ekey) in seen:
            continue
        seen.add((uid, ekey))
        ch = changes[ekey]
        rows.append({"user_id": uid, "type": "fv_change",
                     "payload": {"player_name": ch["name"], "entity_key": ekey,
                                 "old": ch["old"], "new": ch["new"]}})
    if not rows:
        print("forum_notify: all watchers muted FV alerts.")
        return 0
    if dry_run:
        print(f"forum_notify: DRY RUN — would insert {len(rows)} notification(s).")
        return len(rows)

    for i in range(0, len(rows), 500):
        r = _rest(s, "POST", f"{rest}/notifications", key,
                  headers={"Prefer": "return=minimal"}, data=json.dumps(rows[i:i + 500]))
        r.raise_for_status()
    print(f"forum_notify: inserted {len(rows)} fv_change notification(s).")
    return len(rows)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Insert FV-change forum notifications for watchlisted prospects.")
    ap.add_argument("--dry-run", action="store_true", help="compute + report without inserting")
    notify_fv_changes(dry_run=ap.parse_args().dry_run)
