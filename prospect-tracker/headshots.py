# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""
headshots.py — maximize prospect-photo coverage via a validated CDN fallback.

Every prospect already carries an MLBAM player id (the same id embedded in the
MiLB.com URL, e.g. Seth Hernandez = .../seth-hernandez-815825). MLB serves
headshots from img.mlbstatic.com keyed by that id under a CONTEXT segment:

    https://img.mlbstatic.com/mlb-photos/image/upload/{transform}/v1/people/{id}/headshot/{ctx}/current

  • ctx "67"   — the MLB roster set. Real for 40-man / debuted players; ABSENT
                 for most pure prospects (the site's old URL added a
                 `d_people:generic` overlay, so those silently showed the
                 generic silhouette).
  • ctx "milb" — the MiLB set (what milb.com itself renders). Fills the gaps:
                 Seth Hernandez has no "67" photo (404) but a real "milb" one.

We resolve each id by HEAD-probing the contexts in order WITHOUT the generic
overlay (so a missing photo returns 404, not a silhouette-at-200), and cache the
first context that returns a real image — '67' → 'milb' → 'none'. The resolved
map is exported to data/photo_ctx.json and consulted by the front-end's
headshot URL builder so coverage improvements show up everywhere photos render.

CLI:
    python headshots.py                 # backfill (TTL-skips fresh rows)
    python headshots.py --force         # re-probe every id
    python headshots.py --report        # coverage report only, no probing
"""
from __future__ import annotations

import argparse
import concurrent.futures as _cf
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import requests

import storage

log = logging.getLogger("headshots")

DATA_DIR = Path(__file__).parent / "data"
CDN = "https://img.mlbstatic.com/mlb-photos/image/upload"
# Probe order: MLB roster set first (canonical "current" headshot), then the
# MiLB set (fills prospect gaps). Add more contexts here if MLB introduces them.
CONTEXTS = ("67", "milb")
HEADSHOT_TTL_DAYS = 30      # don't re-probe a resolved '67'/'milb' id this often
NONE_TTL_DAYS = 7           # re-check "no photo" ids more aggressively
_UA = {"User-Agent": "Mozilla/5.0 (eephus.io headshot resolver)"}


def probe_url(mlbam_id: int, ctx: str) -> str:
    """No-generic-fallback URL: a missing photo 404s instead of returning a
    silhouette at 200, so a 200 here means a REAL image exists in that context."""
    return f"{CDN}/w_120,q_auto:best/v1/people/{int(mlbam_id)}/headshot/{ctx}/current"


def _head(session: requests.Session, url: str, timeout: float = 8.0):
    """HEAD with one retry; returns status code or None on network failure."""
    for _ in range(2):
        try:
            r = session.head(url, timeout=timeout, allow_redirects=True)
            return r.status_code
        except requests.RequestException:
            continue
    return None


def resolve_ctx(session: requests.Session, mlbam_id: int) -> str:
    """First context returning a real image, else 'none'."""
    for ctx in CONTEXTS:
        if _head(session, probe_url(mlbam_id, ctx)) == 200:
            return ctx
    return "none"


# --------------------------------------------------------------------------
# Player-id collection (from the exported JSON — the full graded universe)
# --------------------------------------------------------------------------
def _collect_ids(data_dir: Path = DATA_DIR) -> dict[int, dict]:
    """{mlbam_id: {player_key, cohort}} across active + debuted (+ draft /
    overseas / ifa where they carry an mlbam_id). cohort ∈ active|debuted|other."""
    out: dict[int, dict] = {}

    def add(players, cohort, key_field="player_key"):
        for p in players or []:
            mid = p.get("mlbam_id")
            if not mid:
                continue
            mid = int(mid)
            # active/debuted win over 'other' if an id appears in multiple sets
            if mid not in out or (cohort != "other" and out[mid]["cohort"] == "other"):
                out[mid] = {"player_key": p.get(key_field) or p.get("name_slug"), "cohort": cohort}

    ts = data_dir / "timeseries.json"
    if ts.exists():
        add(json.loads(ts.read_text(encoding="utf-8")).get("players"), "active")
    deb = data_dir / "debuts.json"
    if deb.exists():
        d = json.loads(deb.read_text(encoding="utf-8"))
        add(d if isinstance(d, list) else d.get("players"), "debuted")
    # Best-effort extra cohorts (draft prospects / overseas / IFA) — many lack
    # an MLBAM id, but resolve the ones that have one so their photos fill too.
    for fname, getter in (("draft_timeseries.json", lambda j: [pp for c in (j.get("classes") or []) for pp in (c.get("prospects") or [])]),
                          ("overseas_timeseries.json", lambda j: [pp for l in (j.get("leagues") or []) for pp in (l.get("prospects") or [])]),
                          ("ifa_timeseries.json", lambda j: [pp for c in (j.get("classes") or []) for pp in (c.get("signings") or [])])):
        fp = data_dir / fname
        if fp.exists():
            try:
                add(getter(json.loads(fp.read_text(encoding="utf-8"))), "other")
            except Exception:
                pass
    return out


def _is_fresh(checked_at: str | None, max_age_days: int) -> bool:
    if not checked_at:
        return False
    try:
        ts = datetime.fromisoformat(checked_at.replace(" ", "T"))
    except ValueError:
        return False
    return (datetime.now(timezone.utc).replace(tzinfo=None) - ts).days < max_age_days


# --------------------------------------------------------------------------
# Backfill
# --------------------------------------------------------------------------
def backfill(data_dir: Path = DATA_DIR, *, workers: int = 16, force: bool = False,
             write_json: bool = True) -> dict:
    """Resolve+cache the headshot context for every player id, then export
    data/photo_ctx.json. Idempotent + incremental: TTL-skips already-resolved
    ids (re-checks 'none' ids more often, in case a photo has since appeared)."""
    storage.init_db()
    id_map = _collect_ids(data_dir)
    existing = storage.load_photo_ctx()
    meta = storage.load_photo_meta()

    todo = []
    for mid in id_map:
        if force:
            todo.append(mid); continue
        cur = existing.get(mid)
        if cur is None:
            todo.append(mid)
        elif cur == "none" and not _is_fresh(meta.get(mid), NONE_TTL_DAYS):
            todo.append(mid)
        elif cur in ("67", "milb") and not _is_fresh(meta.get(mid), HEADSHOT_TTL_DAYS):
            todo.append(mid)
    log.info("headshots: %d ids total, %d to (re)probe (%d cached fresh)",
             len(id_map), len(todo), len(id_map) - len(todo))

    resolved: dict[int, dict] = {}
    if todo:
        with requests.Session() as session:
            session.headers.update(_UA)
            # Size the connection pool to the worker count so concurrent HEADs
            # reuse keep-alive sockets instead of churning ("pool is full").
            _adapter = requests.adapters.HTTPAdapter(pool_connections=workers, pool_maxsize=workers)
            session.mount("https://", _adapter)
            with _cf.ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
                futs = {ex.submit(resolve_ctx, session, mid): mid for mid in todo}
                done = 0
                for fut in _cf.as_completed(futs):
                    mid = futs[fut]
                    try:
                        ctx = fut.result()
                    except Exception:
                        ctx = "none"
                    resolved[mid] = {"ctx": ctx, "player_key": id_map[mid]["player_key"]}
                    done += 1
                    if done % 500 == 0:
                        log.info("  …probed %d/%d", done, len(todo))
        storage.upsert_photo_ctx(resolved)

    if write_json:
        export_photo_ctx_json(data_dir / "photo_ctx.json")

    rep = coverage(data_dir, id_map=id_map)
    log.info("headshots: coverage %.1f%% (%d/%d real) — active %.1f%%, debuted %.1f%%",
             rep["pct"], rep["with_photo"], rep["total"],
             rep["active"]["pct"], rep["debuted"]["pct"])
    rep["probed_this_run"] = len(resolved)
    return rep


def export_photo_ctx_json(path: Path) -> int:
    """Write {mlbam_id: ctx} for every resolved id. The front-end loads this and
    its headshot URL builder uses it to pick the real-photo context per player."""
    ctx_map = storage.load_photo_ctx()
    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ctx": {str(mid): c for mid, c in ctx_map.items()},
    }
    path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    return len(ctx_map)


# --------------------------------------------------------------------------
# Coverage reporting
# --------------------------------------------------------------------------
def coverage(data_dir: Path = DATA_DIR, id_map: dict | None = None) -> dict:
    if id_map is None:
        id_map = _collect_ids(data_dir)
    ctx_map = storage.load_photo_ctx()

    def bucket(cohort):
        ids = [mid for mid, v in id_map.items() if v["cohort"] == cohort]
        real = sum(1 for mid in ids if ctx_map.get(mid) in ("67", "milb"))
        milb = sum(1 for mid in ids if ctx_map.get(mid) == "milb")
        n = len(ids)
        return {"total": n, "with_photo": real, "via_milb": milb,
                "pct": round(100 * real / n, 1) if n else 0.0}

    active, debuted, other = bucket("active"), bucket("debuted"), bucket("other")
    total = len(id_map)
    real = sum(1 for mid in id_map if ctx_map.get(mid) in ("67", "milb"))
    via_milb = sum(1 for mid in id_map if ctx_map.get(mid) == "milb")
    # Players still missing a photo (resolved 'none' OR not yet resolved).
    missing = [{"mlbam_id": mid, "player_key": id_map[mid]["player_key"],
                "cohort": id_map[mid]["cohort"]}
               for mid in id_map if ctx_map.get(mid) not in ("67", "milb")]
    return {
        "total": total, "with_photo": real, "via_milb": via_milb,
        "pct": round(100 * real / total, 1) if total else 0.0,
        "active": active, "debuted": debuted, "other": other,
        "missing_count": len(missing), "missing": missing,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Resolve + cache MLB/MiLB headshot contexts.")
    ap.add_argument("--force", action="store_true", help="re-probe every id (ignore cache TTL)")
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--report", action="store_true", help="coverage report only; no probing")
    args = ap.parse_args()

    if args.report:
        rep = coverage()
    else:
        rep = backfill(workers=args.workers, force=args.force)

    print("\n=== HEADSHOT COVERAGE ===")
    print(f"  overall : {rep['with_photo']}/{rep['total']} = {rep['pct']}%  (via MiLB: {rep['via_milb']})")
    for k in ("active", "debuted", "other"):
        b = rep[k]
        print(f"  {k:<8}: {b['with_photo']}/{b['total']} = {b['pct']}%  (via MiLB: {b['via_milb']})")
    print(f"  still missing: {rep['missing_count']}")
