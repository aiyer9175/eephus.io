# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Add innings, outs, games and starts to the frozen fWAR vintage, once (EWAR_P0B_VINTAGE_IP).

    python tools/amend_fwar_vintage_ip.py --fetch     # the pitching lines and team totals, into .cache
    python tools/amend_fwar_vintage_ip.py             # PLAN: amend in memory, check, no write
    python tools/amend_fwar_vintage_ip.py --write     # check, then write data/fwar_vintage.json

WHY. The frozen vintage (2026-10-02-57bf90f7143e after the PA amendment) carries
no innings on any pitching row because MLB's sabermetrics feed does not publish
them, and the eWAR v3 skill look's precondition (2) (EBR_GATE.md 7.3 item 2)
requires fWAR, PA, innings and gmLI on the vintage. The method is the PA
amendment's (tools/amend_fwar_vintage_pa.py, owner answer EW3-19: a NEW VINTAGE
ID): the columns are filled in place, the hashes and the vintage_id recomputed by
fwar_vintage's own rules, and every reader that names the id re-reads under the
new one.

WHAT MOVES. The pitching groups gain fwar_vintage.IP_FIELDS (inningsPitched as
true innings, outs / 3; outs; gamesPitched; gamesStarted), appended to each
group's `fields` and filled from StatsAPI's official season pitching line
(fwar_vintage.IP_LINE_URL) joined by MLBAM id (fwar_vintage.ip_from_lines). No
fresh fWAR fetch is made (FWAR_LABEL_EPOCH_GATE.md part 3, E3): every published
value of every row, the hitting groups whole, and every group's url, fetched_at
and raw_sha256 stay as frozen. Each pitching group gains an `ip_join` receipt,
the file's top-level `fields.pitching` the four names, and the file an
`amendments` entry naming the previous id.

THE INVARIANTS, all checked before a write and any failure refuses the write:
  1. every hitting block is unchanged, key for key;
  2. every pitching block is unchanged except `fields` (the four names appended),
     `rows` (the four columns appended), `content_sha256` and the new `ip_join`;
     the first len(old fields) values of every row are unchanged (so every fWAR
     value, which `war_identical` then states);
  3. war_source's maps (side_targets for both sides, season_totals) are equal;
  4. no pitching row of a season 2000 to 2026 is left without the four columns;
  5. per season, outs and games started summed over the vintage's rows, over the
     season lines and over StatsAPI's thirty team totals (TEAM_URL) are equal
     (innings are outs / 3, so the innings sums agree with them);
  6. fwar_vintage.verify passes and war_lineage chains the new id to the old.

FETCHES. --fetch makes two polite calls per season (one second apart) to
statsapi.mlb.com, a public, unauthenticated source, and keeps each raw body under
.cache/ewar_p0b_vintage_ip/ with a manifest (url, fetched_at, HTTP status,
sha256). A body already there is not fetched again. The plan and the write read
only those bodies.

ONCE. A vintage whose pitching groups already carry `ip_join`, or whose
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

TASK = "EWAR_P0B_VINTAGE_IP"
DECISION = ("EW3-19 precedent (owner 2026-10-15: a NEW VINTAGE ID); orchestrator option (b) of "
            "EWV3-VINTAGE-IP (2026-10-19): innings on the vintage")
GATE = ("docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md part 9, entry "
        "'2026-10-19: amendment, innings, outs, games and starts added to the frozen vintage'")
CACHE_DIR = ROOT / ".cache" / "ewar_p0b_vintage_ip"
MANIFEST = "manifest.json"
TEAM_URL = ("https://statsapi.mlb.com/api/v1/teams/stats?stats=season&group=pitching"
            "&season={season}&sportIds=1")
#: Seasons whose every pitching row must carry the four columns after the amendment.
REQUIRED_SEASONS = range(2000, 2027)
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


def pitching_seasons(blob: dict) -> list[int]:
    """Seasons whose pitching group is frozen (an absent group has no rows)."""
    return sorted(int(s) for s, sb in (blob.get("seasons") or {}).items()
                  if ((sb or {}).get("pitching") or {}).get("status") == "frozen")


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
        for kind, tpl in (("lines", FV.IP_LINE_URL), ("teams", TEAM_URL)):
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


def team_totals(splits: list) -> dict[str, int]:
    """outs and games started summed over StatsAPI's team season lines."""
    tot = {"outs": 0, "gamesStarted": 0}
    for t in splits or []:
        st = t.get("stat") or {}
        for k in tot:
            v = st.get(k)
            if isinstance(v, bool) or not isinstance(v, int):
                raise AmendError(f"a team line carries no integer {k}")
            tot[k] += v
    return tot


# ---------------------------------------------------------------------------
# the amendment and its invariants
# ---------------------------------------------------------------------------

def already_amended(blob: dict) -> bool:
    if any((a or {}).get("task") == TASK for a in blob.get("amendments") or []):
        return True
    return any("ip_join" in ((sb or {}).get("pitching") or {})
               for sb in (blob.get("seasons") or {}).values())


def amend(blob: dict, sources: dict, *, date: str, previous_file_sha256: str | None) -> dict:
    """The amended vintage (a new dict). Raises AmendError when already amended."""
    if already_amended(blob):
        raise AmendError("the vintage already carries the IP amendment (it runs once)")
    new = copy.deepcopy(blob)
    seasons = pitching_seasons(blob)
    league: dict[str, dict] = {}
    for s in seasons:
        sb = new["seasons"][str(s)]
        splits, meta = sources[s]["lines"]
        ip, receipt = FV.ip_from_lines(splits)
        receipt = {"url": meta["url"], "fetched_at": meta["fetched_at"],
                   "http_status": meta["http_status"], "raw_sha256": meta["raw_sha256"],
                   **receipt}
        sb["pitching"] = FV.apply_ip(sb["pitching"], ip, receipt)
        sb["content_sha256"] = FV.season_content_sha(sb)
        tsplits, tmeta = sources[s]["teams"]
        tt = team_totals(tsplits)
        j = sb["pitching"]["ip_join"]
        league[str(s)] = {"outs_rows": j["outs_sum_rows"], "outs_lines": j["outs_sum_lines"],
                          "outs_teams": tt["outs"],
                          "gs_rows": j["gs_sum_rows"], "gs_lines": j["gs_sum_lines"],
                          "gs_teams": tt["gamesStarted"], "n_teams": len(tsplits),
                          "teams_url": tmeta["url"], "teams_fetched_at": tmeta["fetched_at"],
                          "teams_raw_sha256": tmeta["raw_sha256"]}
    old_fields = list((blob.get("fields") or {}).get("pitching") or [])
    new.setdefault("fields", {})["pitching"] = old_fields + [f for f in FV.IP_FIELDS
                                                             if f not in old_fields]
    new["vintage_id"] = FV.vintage_id(new)
    new.setdefault("amendments", []).append({
        "date": date, "task": TASK, "decision": DECISION, "gate": GATE,
        "tool": "python tools/amend_fwar_vintage_ip.py --write",
        "what": ("inningsPitched (true innings, outs / 3), outs, gamesPitched and gamesStarted "
                 "appended to the frozen pitching rows from StatsAPI's season pitching line, "
                 "joined by MLBAM id; no fresh fWAR fetch; every other value of every row "
                 "unchanged"),
        "fields_added": {"pitching": list(FV.IP_FIELDS)}, "source": FV.IP_LINE_URL,
        "previous_vintage_id": blob.get("vintage_id"),
        "previous_file_sha256": previous_file_sha256,
        "vintage_id": new["vintage_id"],
        "war_identical": True,
        "fields_unchanged": {"hitting": list((blob.get("fields") or {}).get("hitting") or []),
                             "pitching": old_fields},
        "seasons": seasons,
        "league_ip": league,
    })
    return new


def check(old: dict, new: dict) -> list[str]:
    """Every invariant of the module docstring; [] when the write may proceed."""
    probs: list[str] = []
    for s, ob in (old.get("seasons") or {}).items():
        nb = (new.get("seasons") or {}).get(s) or {}
        if ob.get("hitting") != nb.get("hitting"):
            probs.append(f"{s}: the hitting block moved")
        for k in ("fetched_at", "basis"):
            if ob.get(k) != nb.get(k):
                probs.append(f"{s}: season {k} moved")
        op, np_ = ob.get("pitching") or {}, nb.get("pitching") or {}
        for k in set(op) | set(np_):
            if k in ("rows", "fields", "content_sha256", "ip_join"):
                continue
            if op.get(k) != np_.get(k):
                probs.append(f"{s} pitching: key {k} moved")
        if op.get("status") != "frozen":
            if op != np_:
                probs.append(f"{s} pitching: an absent block moved")
            continue
        of, nf = list(op.get("fields") or []), list(np_.get("fields") or [])
        if any(f in of for f in FV.IP_FIELDS):
            probs.append(f"{s} pitching: the old vintage already carried an IP field")
        if nf != of + list(FV.IP_FIELDS):
            probs.append(f"{s} pitching: fields are not the old fields plus IP_FIELDS")
            continue
        orows, nrows = op.get("rows") or {}, np_.get("rows") or {}
        if set(orows) != set(nrows):
            probs.append(f"{s} pitching: the row ids moved")
            continue
        k = len(of)
        moved = sum(1 for m in orows if nrows[m][:k] != orows[m] or len(nrows[m]) != len(nf))
        if moved:
            probs.append(f"{s} pitching: {moved} rows moved outside IP_FIELDS")
        n_null = sum(1 for v in nrows.values() if any(x is None for x in v[k:]))
        if int(s) in REQUIRED_SEASONS and n_null:
            probs.append(f"{s} pitching: {n_null} rows still without innings")
        io = nf.index("outs")
        bad_ip = sum(1 for v in nrows.values()
                     if v[io] is not None and v[nf.index("inningsPitched")] != v[io] / 3.0)
        if bad_ip:
            probs.append(f"{s} pitching: {bad_ip} rows whose inningsPitched is not outs / 3")
    if (old.get("fields") or {}).get("hitting") != (new.get("fields") or {}).get("hitting"):
        probs.append("the top-level hitting fields moved")
    for side in ("bat", "pit"):
        if FV.side_targets(old, side) != FV.side_targets(new, side):
            probs.append(f"side_targets({side}) moved")
    if FV.season_totals(old) != FV.season_totals(new):
        probs.append("season_totals moved")
    am = (new.get("amendments") or [{}])[-1]
    for s, lg in (am.get("league_ip") or {}).items():
        if not (lg["outs_rows"] == lg["outs_lines"] == lg["outs_teams"]):
            probs.append(f"{s}: outs rows {lg['outs_rows']} lines {lg['outs_lines']} "
                         f"teams {lg['outs_teams']} disagree")
        if not (lg["gs_rows"] == lg["gs_lines"] == lg["gs_teams"]):
            probs.append(f"{s}: starts rows {lg['gs_rows']} lines {lg['gs_lines']} "
                         f"teams {lg['gs_teams']} disagree")
    probs += FV.verify(new)
    if FV.war_lineage(new)[:2] != [new.get("vintage_id"), old.get("vintage_id")]:
        probs.append("war_lineage does not chain the new id to the previous one")
    return probs


def _ip_text(outs: int) -> str:
    """Baseball notation for a printed total (e.g. 43,456.1)."""
    return f"{outs // 3:,}.{outs % 3}"


def summary(new: dict) -> str:
    am = new["amendments"][-1]
    lines = [f"previous vintage_id {am['previous_vintage_id']}",
             f"new vintage_id      {am['vintage_id']}",
             "season  rows  joined  unjoined  IP(rows)    outs(rows) outs(lines) outs(teams)"
             "  GS(rows) GS(teams)"]
    for s in am["seasons"]:
        j = new["seasons"][str(s)]["pitching"]["ip_join"]
        lg = am["league_ip"][str(s)]
        lines.append(f"{s}  {j['n_rows']:5d}  {j['n_joined']:6d}  {len(j['unjoined_ids']):8d}  "
                     f"{_ip_text(lg['outs_rows']):>10}  {lg['outs_rows']:10d} {lg['outs_lines']:11d} "
                     f"{lg['outs_teams']:11d}  {lg['gs_rows']:8d} {lg['gs_teams']:9d}")
    return "\n".join(lines)


def _file_sha(p: Path) -> str:
    """sha256 of the file as committed (a CRLF checkout read back to LF bytes)."""
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
    seasons = pitching_seasons(old)
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
