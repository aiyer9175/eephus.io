# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Official MLB draft slot values + signing bonuses, keyed to the MLBAM spine.

The eFV training matrix has THIN draft coverage: `bonus_usd` lands on ~28% of
rows and `pick_overall` on ~40%, because the only draft money we ingest today
rides in on the scraped Pipeline results. This module adds the AUTHORITATIVE
slot/bonus spine straight from the MLB Stats API and keys it by the MLBAM
player id (`person.id`, present on ~100% of picks), so eFV / PROSPX can fill
`bonus_usd` and `pick_overall` from the source of record rather than a scrape.

SOURCE (verified live 2026-07-24, HTTP 200 application/json, no robots block;
MLBAM copyright applies, same terms as the StatsAPI we already run on):

    https://statsapi.mlb.com/api/v1/draft/{year}

    drafts.rounds[].picks[] carries, per pick:
      person.id        the MLBAM spine id (join key)
      pickNumber       overall selection number  -> pick_overall
      pickRound        round label (int, or "CB-A"/"PPI"/... for special rounds)
      pickValue        official assigned SLOT value in whole dollars (STRING)
      signingBonus     the actual bonus paid       in whole dollars (STRING)

    Both dollar fields are STRING-typed ("10570600"), NOT numbers, and are only
    populated from 2017 on: 2016 and earlier carry person/pick but null
    pickValue and null signingBonus. Slot values exist only where MLB assigns
    one (rounds 1-10 plus the compensation / competitive-balance / PPI picks);
    signing bonuses exist for essentially every signed pick. Picks reach back to
    1965 but this module defaults to 2017+ (the money-coverage boundary).

WHAT WE LAND: data/draft_bonus_slot.json, a flat map

    { "<mlbam>": {year, pick_overall, round, slot_usd, bonus_usd, pool_pct}, ... }

where slot_usd = pickValue, bonus_usd = signingBonus, and pool_pct =
bonus_usd / slot_usd when both are present and slot_usd > 0 (how far over/under
the assigned slot the pick signed for). A companion report lands at
data/draft_bonus_slot_report.json.

CACHING: raw year payloads are disk-cached under .cache/draft_bonus/{year}.json.
A completed draft is immutable, so past years cache effectively forever; the
current year keeps a short TTL because bonuses trickle in across the July-August
signing window. Every network fetch is fail-soft (a dead year is skipped, never
fatal) and rate-limited to <= 1 request/second.

This module is standalone and read-only with respect to the rest of the site.
It does NOT wire itself into run_monthly.py / efv_dataset.py / draft_export.py;
integration is a deliberate, owner-gated step. Downstream consumers should use
the offline `bonus_slot_for(mlbam)` helper, which only reads the landed JSON.

Run: python draft_bonus.py            # build 2017..current
     python draft_bonus.py --years 2017-2023
     python draft_bonus.py --rebuild  # ignore cached year payloads
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import tempfile
import time
from datetime import date
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

_log = logging.getLogger(__name__)

DRAFT_API = "https://statsapi.mlb.com/api/v1/draft"

_HERE = Path(__file__).parent
CACHE_DIR = _HERE / ".cache" / "draft_bonus"
DATA_OUT = _HERE / "data" / "draft_bonus_slot.json"
REPORT_OUT = _HERE / "data" / "draft_bonus_slot_report.json"

# The money-coverage boundary: pickValue/signingBonus are populated 2017+.
FIRST_MONEY_YEAR = 2017

# A finished draft's slot/bonus record is immutable, so past years cache
# effectively forever; the current year keeps a short TTL because signings post
# across the summer window.
SHORT_TTL = 12 * 3600          # 12h  -- current year, still signing
FINAL_TTL = 3650 * 86400       # ~10y -- completed drafts, immutable

# Politeness: hard-cap the network fetch rate at <= 1 req/sec (cache hits skip).
_MIN_FETCH_INTERVAL = 1.1
_last_fetch = {"t": 0.0}

_UA = "eephus-io-datasourcing/1.0 (arkndjl@gmail.com)"

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": _UA})
_retries = Retry(
    total=4,
    backoff_factor=0.6,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=frozenset({"GET"}),
    respect_retry_after_header=True,
)
_adapter = HTTPAdapter(max_retries=_retries)
SESSION.mount("https://", _adapter)
SESSION.mount("http://", _adapter)


# --------------------------------------------------------------------------- #
# parsing helpers
# --------------------------------------------------------------------------- #
def _num(x):
    """Parse a StatsAPI dollar field (string like "10570600", or None) to float.

    Returns None for None / "" / non-numeric so an absent slot or unsigned pick
    reads cleanly as missing rather than as zero.
    """
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x) if x else None
    s = str(x).strip().replace(",", "").replace("$", "")
    if not s:
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    return v if v else None


def _round_label(pick):
    """Normalize a pick's round to int where numeric, else the raw label.

    Regular rounds come back as 1..N; compensation / competitive-balance /
    prospect-promotion picks use labels like "1C", "CB-A", "PPI" which we keep
    verbatim so the special-round provenance is not lost.
    """
    r = pick.get("pickRound")
    if r is None:
        r = pick.get("round")
    if r is None:
        return None
    s = str(r).strip()
    if not s:
        return None
    return int(s) if s.isdigit() else s


def _pick_record(pick, year):
    """Build the landed record for one pick, or None if it has no MLBAM id.

    slot_usd = pickValue, bonus_usd = signingBonus (both parsed from strings);
    pool_pct = bonus/slot only when both are present and slot > 0.
    """
    person = pick.get("person") or {}
    mlbam = person.get("id")
    if not mlbam:
        return None
    slot = _num(pick.get("pickValue"))
    bonus = _num(pick.get("signingBonus"))
    pool_pct = round(bonus / slot, 4) if (slot and bonus) else None
    pick_overall = pick.get("pickNumber")
    try:
        pick_overall = int(pick_overall) if pick_overall is not None else None
    except (TypeError, ValueError):
        pick_overall = None
    return int(mlbam), {
        "year": int(year),
        "pick_overall": pick_overall,
        "round": _round_label(pick),
        "slot_usd": slot,
        "bonus_usd": bonus,
        "pool_pct": pool_pct,
    }


def iter_picks(raw):
    """Yield every pick dict from a raw /draft/{year} payload (empty if malformed)."""
    if not isinstance(raw, dict):
        return
    drafts = raw.get("drafts")
    if not isinstance(drafts, dict):
        return
    for rnd in drafts.get("rounds") or []:
        if not isinstance(rnd, dict):
            continue
        for pick in rnd.get("picks") or []:
            if isinstance(pick, dict):
                yield pick


# --------------------------------------------------------------------------- #
# disk cache + fetch (fail-soft, rate-limited)
# --------------------------------------------------------------------------- #
def _ttl_for_year(year):
    """Past drafts are immutable (FINAL_TTL); the current year keeps SHORT_TTL."""
    return SHORT_TTL if int(year) >= date.today().year else FINAL_TTL


def _write_json(path, data, *, sort_keys=False):
    """Atomically write JSON (writer-unique temp + os.replace) so a concurrent
    reader never sees a half-written file. Mirrors feed_cache.atomic_write_json."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, sort_keys=sort_keys, ensure_ascii=False)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f"{path.stem}.",
                               suffix=".json.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
        os.replace(tmp, path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        if not path.exists():
            raise


def fetch_draft_year(year, *, use_cache=True):
    """Return the raw /draft/{year} payload, disk-cached and fail-soft.

    Reads .cache/draft_bonus/{year}.json when fresh for the year's TTL; otherwise
    fetches once (rate-limited to <= 1 req/sec) and caches. Any network / decode
    failure returns None so a single dead year never breaks a multi-year build.
    """
    year = int(year)
    path = CACHE_DIR / f"{year}.json"
    ttl = _ttl_for_year(year)
    if use_cache and path.exists() and (time.time() - path.stat().st_mtime) <= ttl:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass  # corrupt cache -> re-fetch below

    wait = _MIN_FETCH_INTERVAL - (time.time() - _last_fetch["t"])
    if wait > 0:
        time.sleep(wait)
    try:
        resp = SESSION.get(f"{DRAFT_API}/{year}", timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        _log.warning("draft_bonus: fetch failed for %s (%s)", year, exc)
        return None
    finally:
        _last_fetch["t"] = time.time()

    try:
        _write_json(path, data)
    except OSError as exc:
        _log.warning("draft_bonus: cache write failed for %s (%s)", year, exc)
    return data


# --------------------------------------------------------------------------- #
# build
# --------------------------------------------------------------------------- #
def _prefer(existing, candidate):
    """Pick the better of two records for the same MLBAM id.

    A player can appear across years (drafted, did not sign, re-drafted). Prefer
    the SIGNED record (one that carries a bonus); break ties on the later year.
    """
    if existing is None:
        return candidate
    e_signed = existing.get("bonus_usd") is not None
    c_signed = candidate.get("bonus_usd") is not None
    if c_signed != e_signed:
        return candidate if c_signed else existing
    return candidate if candidate.get("year", 0) >= existing.get("year", 0) else existing


def build(years=None, *, use_cache=True, write=True):
    """Assemble the mlbam -> slot/bonus map for `years` (default 2017..current).

    Returns (records, report). When `write` is True, lands
    data/draft_bonus_slot.json + data/draft_bonus_slot_report.json.
    """
    if years is None:
        years = range(FIRST_MONEY_YEAR, date.today().year + 1)
    years = sorted({int(y) for y in years})

    records = {}
    per_year = {}
    years_landed = []
    total_picks = 0
    for year in years:
        raw = fetch_draft_year(year, use_cache=use_cache)
        if raw is None:
            per_year[year] = {"status": "unreachable"}
            continue
        picks = list(iter_picks(raw))
        if not picks:
            per_year[year] = {"status": "empty"}
            continue
        years_landed.append(year)
        n_pick = n_slot = n_bonus = n_person = 0
        for pick in picks:
            total_picks += 1
            n_pick += 1
            rec = _pick_record(pick, year)
            if rec is None:
                continue
            n_person += 1
            mlbam, body = rec
            if body["slot_usd"] is not None:
                n_slot += 1
            if body["bonus_usd"] is not None:
                n_bonus += 1
            records[str(mlbam)] = _prefer(records.get(str(mlbam)), body)
        per_year[year] = {
            "status": "ok",
            "picks": n_pick,
            "with_person_id": n_person,
            "with_slot": n_slot,
            "with_bonus": n_bonus,
            "slot_pct": round(100.0 * n_slot / n_pick, 1) if n_pick else 0.0,
            "bonus_pct": round(100.0 * n_bonus / n_pick, 1) if n_pick else 0.0,
            "person_pct": round(100.0 * n_person / n_pick, 1) if n_pick else 0.0,
        }

    n_rec = len(records)
    n_rec_slot = sum(1 for r in records.values() if r["slot_usd"] is not None)
    n_rec_bonus = sum(1 for r in records.values() if r["bonus_usd"] is not None)
    pool_vals = [r["pool_pct"] for r in records.values() if r["pool_pct"] is not None]
    report = {
        "source": f"{DRAFT_API}/{{year}}",
        "generated": date.today().isoformat(),
        "years_requested": years,
        "years_landed": years_landed,
        "total_picks_seen": total_picks,
        "unique_mlbam": n_rec,
        "records_with_slot": n_rec_slot,
        "records_with_bonus": n_rec_bonus,
        "pool_pct_median": round(sorted(pool_vals)[len(pool_vals) // 2], 4) if pool_vals else None,
        "per_year": {str(y): per_year[y] for y in sorted(per_year)},
    }

    if write:
        # Sort keys so the landed file is deterministic run-to-run.
        _write_json(DATA_OUT, dict(sorted(records.items(), key=lambda kv: int(kv[0]))),
                    sort_keys=True)
        _write_json(REPORT_OUT, report)
    return records, report


# --------------------------------------------------------------------------- #
# offline join helper (pure read of the landed JSON)
# --------------------------------------------------------------------------- #
_CACHE = {"mtime": None, "data": None}


def _load_landed():
    """Load data/draft_bonus_slot.json, memoized on file mtime. {} if absent."""
    try:
        mtime = DATA_OUT.stat().st_mtime
    except OSError:
        _CACHE["mtime"], _CACHE["data"] = None, {}
        return _CACHE["data"]
    if _CACHE["mtime"] != mtime:
        try:
            _CACHE["data"] = json.loads(DATA_OUT.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            _CACHE["data"] = {}
        _CACHE["mtime"] = mtime
    return _CACHE["data"]


def bonus_slot_for(mlbam):
    """Return the landed slot/bonus record for one MLBAM id, or None.

    Pure and offline: reads only the landed JSON (no network), so eFV / PROSPX
    can call it per row to fill bonus_usd / pick_overall. Accepts int or str id.
    """
    if mlbam is None:
        return None
    return _load_landed().get(str(mlbam))


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _parse_years(spec):
    """Parse a --years spec: "2017-2023" or "2017,2019,2021" or "2020"."""
    spec = spec.strip()
    if "-" in spec and "," not in spec:
        lo, hi = spec.split("-", 1)
        return range(int(lo), int(hi) + 1)
    return [int(p) for p in spec.split(",") if p.strip()]


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description="Ingest official MLB draft slot/bonus by MLBAM id.")
    ap.add_argument("--years", help='year range, e.g. "2017-2026" (default 2017..current)')
    ap.add_argument("--rebuild", action="store_true", help="ignore cached year payloads")
    args = ap.parse_args(argv)

    years = _parse_years(args.years) if args.years else None
    _, report = build(years=years, use_cache=not args.rebuild)

    print("draft_bonus: landed", DATA_OUT.name)
    print("  years landed :", report["years_landed"])
    print("  total picks  :", report["total_picks_seen"])
    print("  unique mlbam :", report["unique_mlbam"],
          f"(slot {report['records_with_slot']}, bonus {report['records_with_bonus']})")
    print("  pool_pct med :", report["pool_pct_median"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
