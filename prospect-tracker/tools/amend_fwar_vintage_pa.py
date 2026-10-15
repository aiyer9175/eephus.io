# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Restore plateAppearances to the frozen fWAR vintage, once (EWAR_P0_VINTAGE_PA).

    python tools/amend_fwar_vintage_pa.py --fetch     # the PA lines and team totals, into .cache
    python tools/amend_fwar_vintage_pa.py             # PLAN: amend in memory, check, no write
    python tools/amend_fwar_vintage_pa.py --write     # check, then write data/fwar_vintage.json

WHY. The 2026-10-02 freeze (EPOCH_D9_FREEZE, vintage 2026-10-02-0341299c20ec)
stored `plateAppearances` null on every hitting row because MLB's sabermetrics
feed does not carry it, which blocks every per-PA read of the label (the eBR
gate's Leg E and precondition (2), eWAR v3's re-centring). The owner chose a NEW
VINTAGE ID over a side file (EW3-19, 2026-10-15): the column is filled in place,
the hashes and the vintage_id are recomputed by fwar_vintage's own rules, and
every reader that names the id re-reads under the new one.

WHAT MOVES. Only the plateAppearances column of the frozen hitting groups, filled
from StatsAPI's official season hitting line (fwar_vintage.PA_LINE_URL) joined
by MLBAM id (fwar_vintage.pa_from_lines). No fresh fWAR fetch is made
(FWAR_LABEL_EPOCH_GATE.md part 3, E3): every published value of every row, the
pitching groups whole, and every group's url, fetched_at and raw_sha256 stay as
frozen. Each hitting group gains a `pa_join` receipt and the file an
`amendments` entry naming the previous id.

THE INVARIANTS, all checked before a write and any failure refuses the write:
  1. every pitching block is unchanged, key for key;
  2. every hitting block is unchanged except `rows`' plateAppearances column,
     `content_sha256` and the new `pa_join`; every other value of every row is
     unchanged (so every fWAR value, which `war_identical` then states);
  3. war_source's maps (side_targets for both sides, season_totals) are equal;
  4. no hitting row of a season 2011 to 2026 is left without PA;
  5. per season, the PA summed over the vintage's rows, over the season lines
     and over StatsAPI's thirty team totals (TEAM_URL) are equal;
  6. fwar_vintage.verify passes on the result.

FETCHES. --fetch makes two polite calls per season (one second apart) to
statsapi.mlb.com, a public, unauthenticated source, and keeps each raw body under
.cache/ewar_p0_vintage_pa/ with a manifest (url, fetched_at, HTTP status,
sha256). A body already there is not fetched again. The plan and the write read
only those bodies.

ONCE. A vintage whose hitting groups already carry `pa_join`, or whose
`amendments` name this task, is refused.
"""
from __future__ import annotations

import argparse
import copy
import datetime as _dt
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import fwar_vintage as FV  # noqa: E402
import saber_feed  # noqa: E402

TASK = "EWAR_P0_VINTAGE_PA"
DECISION = "EW3-19 (owner 2026-10-15): plate appearances by a NEW VINTAGE ID"
GATE = ("docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md part 9, entry "
        "'2026-10-15: amendment, plate appearances restored to the frozen vintage'")
CACHE_DIR = ROOT / ".cache" / "ewar_p0_vintage_pa"
MANIFEST = "manifest.json"
TEAM_URL = ("https://statsapi.mlb.com/api/v1/teams/stats?stats=season&group=hitting"
            "&season={season}&sportIds=1")
#: Seasons whose every hitting row must carry PA after the amendment (the spec's floor).
REQUIRED_SEASONS = range(2011, 2027)
PAUSE_SECONDS = 1.0


class AmendError(RuntimeError):
    """An amendment that must not write."""


# ---------------------------------------------------------------------------
# the source bodies
# ---------------------------------------------------------------------------

def _body_path(cache_dir: Path, kind: str, season: int) -> Path:
    return Path(cache_dir) / f"{kind}_{int(season)}.json"


def _read_manifest(cache_dir: Path) -> dict:
    p = Path(cache_dir) / MANIFEST
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def hitting_seasons(blob: dict) -> list[int]:
    """Seasons whose hitting group is frozen (an absent group has no rows)."""
    return sorted(int(s) for s, sb in (blob.get("seasons") or {}).items()
                  if ((sb or {}).get("hitting") or {}).get("status") == "frozen")


def fetch_sources(seasons, cache_dir: Path = CACHE_DIR, *, fetch=None, now=None,
                  pause=time.sleep) -> dict:
    """Fetch every missing (season, kind) body into `cache_dir`; returns the manifest."""
    fetch = fetch or FV.http_fetch
    now = now or (lambda: _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"))
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    man = _read_manifest(cache_dir)
    first = True
    for s in seasons:
        for kind, tpl in (("lines", FV.PA_LINE_URL), ("teams", TEAM_URL)):
            key = f"{kind}_{int(s)}"
            p = _body_path(cache_dir, kind, s)
            if p.exists() and key in man:
                continue
            if not first:
                pause(PAUSE_SECONDS)
            first = False
            url = tpl.format(season=int(s))
            resp = fetch(url)
            if resp.status != 200 or not resp.body:
                raise AmendError(f"{s} {kind}: HTTP {resp.status} from {url}")
            p.write_bytes(resp.body)
            man[key] = {"url": url, "fetched_at": now(), "http_status": resp.status,
                        "raw_sha256": hashlib.sha256(resp.body).hexdigest(),
                        "bytes": len(resp.body)}
            (cache_dir / MANIFEST).write_text(json.dumps(man, indent=1, sort_keys=True) + "\n",
                                              encoding="utf-8")
    return man


def load_sources(seasons, cache_dir: Path = CACHE_DIR) -> dict:
    """{season: {"lines": (splits, meta), "teams": (splits, meta)}} from the cached
    bodies; a body whose sha256 does not match its manifest entry is refused."""
    man = _read_manifest(cache_dir)
    out: dict[int, dict] = {}
    for s in seasons:
        out[int(s)] = {}
        for kind in ("lines", "teams"):
            key = f"{kind}_{int(s)}"
            p = _body_path(cache_dir, kind, s)
            if key not in man or not p.exists():
                raise AmendError(f"{s} {kind}: no cached body (run --fetch first)")
            body = p.read_bytes()
            if hashlib.sha256(body).hexdigest() != man[key]["raw_sha256"]:
                raise AmendError(f"{s} {kind}: cached body does not match its manifest sha256")
            out[int(s)][kind] = (saber_feed.parse_splits(body), dict(man[key]))
    return out


def team_pa_total(splits: list) -> int:
    """PA summed over StatsAPI's team season lines (thirty clubs)."""
    tot = 0
    for t in splits or []:
        v = (t.get("stat") or {}).get(FV.PA_FIELD)
        if isinstance(v, bool) or not isinstance(v, int):
            raise AmendError("a team line carries no integer plateAppearances")
        tot += v
    return tot


# ---------------------------------------------------------------------------
# the amendment and its invariants
# ---------------------------------------------------------------------------

def already_amended(blob: dict) -> bool:
    if any((a or {}).get("task") == TASK for a in blob.get("amendments") or []):
        return True
    return any("pa_join" in ((sb or {}).get("hitting") or {})
               for sb in (blob.get("seasons") or {}).values())


def amend(blob: dict, sources: dict, *, date: str, previous_file_sha256: str | None) -> dict:
    """The amended vintage (a new dict). Raises AmendError when already amended."""
    if already_amended(blob):
        raise AmendError("the vintage already carries the PA amendment (it runs once)")
    new = copy.deepcopy(blob)
    seasons = hitting_seasons(blob)
    league: dict[str, dict] = {}
    for s in seasons:
        sb = new["seasons"][str(s)]
        splits, meta = sources[s]["lines"]
        pa, receipt = FV.pa_from_lines(splits)
        receipt = {"url": meta["url"], "fetched_at": meta["fetched_at"],
                   "http_status": meta["http_status"], "raw_sha256": meta["raw_sha256"],
                   **receipt}
        sb["hitting"] = FV.apply_pa(sb["hitting"], pa, receipt)
        sb["content_sha256"] = FV.season_content_sha(sb)
        tsplits, tmeta = sources[s]["teams"]
        league[str(s)] = {"pa_rows": sb["hitting"]["pa_join"]["pa_sum_rows"],
                          "pa_lines": receipt["pa_sum_lines"],
                          "pa_teams": team_pa_total(tsplits), "n_teams": len(tsplits),
                          "teams_url": tmeta["url"], "teams_fetched_at": tmeta["fetched_at"],
                          "teams_raw_sha256": tmeta["raw_sha256"]}
    new["vintage_id"] = FV.vintage_id(new)
    other = [f for f in (blob.get("fields") or {}).get("hitting") or [] if f != FV.PA_FIELD]
    new.setdefault("amendments", []).append({
        "date": date, "task": TASK, "decision": DECISION, "gate": GATE,
        "tool": "python tools/amend_fwar_vintage_pa.py --write",
        "what": ("plateAppearances filled on the frozen hitting rows from StatsAPI's season "
                 "hitting line, joined by MLBAM id; no fresh fWAR fetch; every other value "
                 "of every row unchanged"),
        "field": FV.PA_FIELD, "source": FV.PA_LINE_URL,
        "previous_vintage_id": blob.get("vintage_id"),
        "previous_file_sha256": previous_file_sha256,
        "vintage_id": new["vintage_id"],
        "war_identical": True,
        "fields_unchanged": {"hitting": other,
                             "pitching": list((blob.get("fields") or {}).get("pitching") or [])},
        "seasons": seasons,
        "league_pa": league,
    })
    return new


def check(old: dict, new: dict) -> list[str]:
    """Every invariant of the module docstring; [] when the write may proceed."""
    probs: list[str] = []
    for s, ob in (old.get("seasons") or {}).items():
        nb = (new.get("seasons") or {}).get(s) or {}
        if ob.get("pitching") != nb.get("pitching"):
            probs.append(f"{s}: the pitching block moved")
        for k in ("fetched_at", "basis"):
            if ob.get(k) != nb.get(k):
                probs.append(f"{s}: season {k} moved")
        oh, nh = ob.get("hitting") or {}, nb.get("hitting") or {}
        for k in set(oh) | set(nh):
            if k in ("rows", "content_sha256", "pa_join"):
                continue
            if oh.get(k) != nh.get(k):
                probs.append(f"{s} hitting: key {k} moved")
        fields = list(oh.get("fields") or [])
        if oh.get("status") != "frozen":
            if oh.get("rows") != nh.get("rows"):
                probs.append(f"{s} hitting: an absent block's rows moved")
            continue
        i = fields.index(FV.PA_FIELD)
        orows, nrows = oh.get("rows") or {}, nh.get("rows") or {}
        if set(orows) != set(nrows):
            probs.append(f"{s} hitting: the row ids moved")
            continue
        moved = sum(1 for m in orows
                    if orows[m][:i] + orows[m][i + 1:] != nrows[m][:i] + nrows[m][i + 1:])
        if moved:
            probs.append(f"{s} hitting: {moved} rows moved outside {FV.PA_FIELD}")
        if any(v[i] is not None for v in orows.values()):
            probs.append(f"{s} hitting: the old vintage already carried PA")
        n_null = sum(1 for v in nrows.values() if v[i] is None)
        if int(s) in REQUIRED_SEASONS and n_null:
            probs.append(f"{s} hitting: {n_null} rows still without PA")
    for side in ("bat", "pit"):
        if FV.side_targets(old, side) != FV.side_targets(new, side):
            probs.append(f"side_targets({side}) moved")
    if FV.season_totals(old) != FV.season_totals(new):
        probs.append("season_totals moved")
    am = (new.get("amendments") or [{}])[-1]
    for s, lg in (am.get("league_pa") or {}).items():
        if not (lg["pa_rows"] == lg["pa_lines"] == lg["pa_teams"]):
            probs.append(f"{s}: PA rows {lg['pa_rows']} lines {lg['pa_lines']} "
                         f"teams {lg['pa_teams']} disagree")
    probs += FV.verify(new)
    if FV.war_lineage(new)[:2] != [new.get("vintage_id"), old.get("vintage_id")]:
        probs.append("war_lineage does not chain the new id to the previous one")
    return probs


def summary(new: dict) -> str:
    am = new["amendments"][-1]
    lines = [f"previous vintage_id {am['previous_vintage_id']}",
             f"new vintage_id      {am['vintage_id']}",
             "season  rows  joined  unjoined  PA(rows)  PA(lines)  PA(teams)"]
    for s in am["seasons"]:
        h = new["seasons"][str(s)]["hitting"]["pa_join"]
        lg = am["league_pa"][str(s)]
        lines.append(f"{s}  {h['n_rows']:5d}  {h['n_joined']:6d}  {len(h['unjoined_ids']):8d}  "
                     f"{lg['pa_rows']:8d}  {lg['pa_lines']:9d}  {lg['pa_teams']:9d}")
    return "\n".join(lines)


def _file_sha(p: Path) -> str:
    """sha256 of the file as committed: a CRLF checkout (core.autocrlf) is read
    back to the LF bytes fwar_vintage.write produces, so the hash is the one the
    gate's LABEL FREEZE RECEIPT quotes (the compact JSON holds no raw CR)."""
    return hashlib.sha256(Path(p).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fetch", action="store_true", help="fetch the missing source bodies")
    ap.add_argument("--write", action="store_true", help="write the amended vintage")
    ap.add_argument("--date", default=_dt.date.today().isoformat())
    ap.add_argument("--vintage", type=Path, default=FV.VINTAGE_PATH)
    ap.add_argument("--cache-dir", type=Path, default=CACHE_DIR)
    args = ap.parse_args(argv)
    old = FV.load(args.vintage)
    seasons = hitting_seasons(old)
    if args.fetch:
        fetch_sources(seasons, args.cache_dir)
        print(f"fetched into {args.cache_dir}")
    try:
        new = amend(old, load_sources(seasons, args.cache_dir), date=args.date,
                    previous_file_sha256=_file_sha(args.vintage))
    except AmendError as exc:
        print(f"REFUSED, nothing written: {exc}")
        return 2
    print(summary(new))
    probs = check(old, new)
    if probs:
        print("\nREFUSED, nothing written:\n  " + "\n  ".join(probs))
        return 2
    print("\nall invariants hold")
    if not args.write:
        print("PLAN ONLY: nothing written. Pass --write to amend the vintage.")
        return 0
    FV.write(new, args.vintage)
    print(f"wrote {args.vintage} vintage_id {new['vintage_id']} sha256 {_file_sha(args.vintage)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
