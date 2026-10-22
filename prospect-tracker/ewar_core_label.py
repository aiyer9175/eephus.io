# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The core eWAR label vintage (docs/efv-2026-10-22/EWAR_CORE_LABEL_EPOCH_GATE.md part 3;
task EFV_LABEL_EPOCH_EWAR, owner decisions EW3-17, EW3-19 and EW3-20).

THE LABEL IS CORE eWAR. Published fWAR from the frozen vintage, less the parts that are
not present in every season 2000 to 2026: per hitting row the re-centred rest of
baserunning and the framing term, in wins at FanGraphs' own per-season RPW, exactly as
docs/ewar/EWAR_HISTORY_GATE.md part 3 defines CORE under its amendment 9.1
(ewar_history.core_full is the one implementation). Pitching rows equal published fWAR.
The realized-core sensitivity adds the realized pitching departure R2 of
data/ewar_v3.json (seasons 2016 on); it trains nothing and anchors nothing.

The file stores DEPARTURES from published fWAR, so a provider builds the label the way
'ewar_v3' builds eWAR: the 'fwar' answer plus the departure of each listed
(mlbam, season, side).

    build()        the payload tools/build_ewar_core_label.py writes; refuses on any
                   missed identity (gate part 3)
    write()        writes ONCE: an existing file with other content is refused, never
                   overwritten (a new label value needs a new vintage id by amendment)
    load()         the frozen file (memoised)
    departures()   {(mlbam, season): {"bat": wins}} on the headline series (the label),
                   with "pit": R2 added on the realized series (the sensitivity)
    vintage_id()   'ewar-core-<fWAR vintage id>-<first 12 hex of content_sha256>', the
                   build identity the fingerprint's label term names

Display doors never read this module: the label is not the displayed eWAR.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data" / "ewar_core_label.json"
GATE_DOC = "docs/efv-2026-10-22/EWAR_CORE_LABEL_EPOCH_GATE.md"
VERSION = "ewar_core_label_v1"
FORMULA = ("docs/ewar/EWAR_HISTORY_GATE.md part 3 under amendment 9.1 (ewar_history.core_full): "
           "core_i = war_i - (B_i + Fr_i) for hitting rows, core_j = war_j for pitching rows")
BUILD_CMD = "python tools/build_ewar_core_label.py --write"
SERIES = ("headline", "realized")

#: Identity tolerances (gate part 3), in wins.
TOL_ROW = 1e-9
TOL_SEASON = 1e-6
#: Storage precision of a departure.
NDP = 6


class EwarCoreLabelRefusal(RuntimeError):
    """A build or write that must not happen: the message names the identity or file."""


def _sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _sha_file(path: Path) -> str | None:
    try:
        return _sha_bytes(Path(path).read_bytes())
    except OSError:
        return None


def content_sha256(seasons_block: dict) -> str:
    """sha256 over the canonical JSON of the per-season departures."""
    return _sha_bytes(json.dumps(seasons_block, sort_keys=True, separators=(",", ":"),
                                 ensure_ascii=True, allow_nan=False).encode("ascii"))


def make_vintage_id(fwar_vintage_id: str, content_sha: str) -> str:
    return f"ewar-core-{fwar_vintage_id}-{content_sha[:12]}"


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------

def _v3_r2(v3: dict, season: int) -> dict[int, float]:
    """{mlbam: dr - dh} on the pitching side of data/ewar_v3.json for one season,
    read straight from the artifact (the cross-check of identity 4)."""
    out: dict[int, float] = {}
    for mid_s, seasons in (v3.get("players") or {}).items():
        blk = seasons.get(str(int(season)))
        if not blk:
            continue
        dr = (blk.get("dr") or {}).get("pit")
        dh = (blk.get("dh") or {}).get("pit")
        if dr is None and dh is None:
            continue
        out[int(mid_s)] = float(dr or 0.0) - float(dh or 0.0)
    return out


def build(vintage: dict | None = None, v3: dict | None = None, log=print) -> dict:
    """The label payload. Refuses (EwarCoreLabelRefusal) on any missed identity:
      1. per hitting row, core - war equals -(B + Fr) within TOL_ROW;
      2. per season, the hitting departures sum to zero within TOL_SEASON (CORE keeps
         each season's published fWAR total);
      3. a season whose stamp carries neither bsr_rest nor framing departs nowhere;
      4. per pitching row, R2 equals data/ewar_v3.json's dr - dh within TOL_ROW."""
    import ewar_history as H
    vin, pay = H._inputs(vintage, v3)
    seasons = H.seasons(vin)
    if not seasons:
        raise EwarCoreLabelRefusal("the frozen fWAR vintage has no season from the first season on")
    block: dict[str, dict] = {}
    counts: dict[str, dict] = {}
    for s in seasons:
        stp = H._stamp(vin, pay, s)
        cf = H.core_full(s, vin, pay, stp)
        bat, pit = {}, {}
        tot = 0.0
        for m, r in cf["bat"].items():
            d = float(r["core"]) - float(r["war"])
            want = -(float(r["bsr_rest"]) + float(r["framing"]))
            if abs(d - want) > TOL_ROW:
                raise EwarCoreLabelRefusal(f"identity 1: {s} hitter {m}: core - war {d!r} != {want!r}")
            tot += d
            dr = round(d, NDP)
            if dr != 0.0:
                bat[str(m)] = dr
        if abs(tot) > TOL_SEASON:
            raise EwarCoreLabelRefusal(f"identity 2: {s} hitting departures sum to {tot!r}")
        carries = {"bsr_rest", "framing"} & set(stp["headline"])
        if not carries and bat:
            raise EwarCoreLabelRefusal(f"identity 3: {s} carries no non-core part but {len(bat)} rows depart")
        want_r2 = _v3_r2(pay, s)
        for m, r in cf["pit"].items():
            r2 = float(r["r2"])
            if abs(r2 - want_r2.get(int(m), 0.0)) > TOL_ROW:
                raise EwarCoreLabelRefusal(f"identity 4: {s} pitcher {m}: R2 {r2!r} != artifact "
                                           f"{want_r2.get(int(m), 0.0)!r}")
            rr = round(r2, NDP)
            if rr != 0.0:
                pit[str(m)] = rr
        block[str(s)] = {"rpw_fg": round(float(cf["rpw_fg"]), NDP), "bat": bat, "pit_r2": pit}
        counts[str(s)] = {"hitting_rows": len(cf["bat"]), "hitting_departures": len(bat),
                          "pitching_rows": len(cf["pit"]), "r2_departures": len(pit),
                          "parts_removed": sorted(carries)}
        log(f"  {s}: {len(bat)} of {len(cf['bat'])} hitting rows depart "
            f"({'+'.join(sorted(carries)) or 'none'}); R2 rows {len(pit)}; identities hold")
    sha = content_sha256(block)
    fid = str(vin.get("vintage_id") or "")
    import fwar_vintage
    return {
        "schema": 1,
        "model": "ewar_core_label",
        "version": VERSION,
        "vintage_id": make_vintage_id(fid, sha),
        "content_sha256": sha,
        "built_at": _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat(),
        "registration": GATE_DOC,
        "formula": FORMULA,
        "fwar_vintage_id": fid,
        "fwar_vintage_sha256": _sha_file(fwar_vintage.VINTAGE_PATH),
        "ewar_v3_generated_at": pay.get("generated_at"),
        "ewar_v3_sha256": _sha_file(ROOT / "data" / "ewar_v3.json"),
        "first_season": min(seasons), "last_season": max(seasons),
        "field_key": {
            "seasons.<s>.bat": ("{mlbam: core - published fWAR} on the hitting group, wins, "
                                "6 decimals; a row not listed departs by 0 (the label is fWAR there)"),
            "seasons.<s>.pit_r2": ("{mlbam: R2} on the pitching group, wins: the realized-core "
                                   "sensitivity only, never the label"),
            "seasons.<s>.rpw_fg": "FanGraphs' own runs per win that season (sum rar / sum war)",
        },
        "counts": counts,
        "seasons": block,
        "note": ("The training label of eFV once the epoch run flips war_source.LABEL_EWAR_CORE; "
                 "never displayed, never a column or a sort key on a served surface."),
    }


# ---------------------------------------------------------------------------
# write once, load
# ---------------------------------------------------------------------------

def write(payload: dict, path: Path | None = None) -> tuple[Path, str]:
    """(path, 'written' | 'unchanged'). Refuses when a file with other content exists."""
    import os
    path = Path(path or OUT)
    if path.exists():
        try:
            have = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise EwarCoreLabelRefusal(f"{path} exists and is unreadable ({e}); it is never overwritten")
        if have.get("content_sha256") == payload.get("content_sha256"):
            return path, "unchanged"
        raise EwarCoreLabelRefusal(
            f"{path} is frozen at {have.get('vintage_id')}; the build reads {payload.get('vintage_id')}. "
            f"A new label value needs a new vintage id through a dated amendment ({GATE_DOC} part 11).")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    tmp.write_text(json.dumps(payload, indent=1, ensure_ascii=True, allow_nan=False) + "\n",
                   encoding="utf-8")
    os.replace(tmp, path)
    return path, "written"


_MEMO: dict = {}


def reset() -> None:
    """Drop the memoised file and departures (the test seam)."""
    _MEMO.clear()


def available(path: Path | None = None) -> bool:
    return Path(path or OUT).exists()


def load(path: Path | None = None) -> dict:
    p = Path(path or OUT)
    key = ("blob", str(p))
    if key not in _MEMO:
        blob = json.loads(p.read_text(encoding="utf-8"))
        if content_sha256(blob.get("seasons") or {}) != blob.get("content_sha256"):
            raise EwarCoreLabelRefusal(f"{p}: content_sha256 does not match its departures")
        _MEMO[key] = blob
    return _MEMO[key]


def vintage_id(payload: dict | None = None) -> str:
    blob = load() if payload is None else payload
    return str(blob.get("vintage_id") or "")


def departures(payload: dict | None = None, series: str = "headline") -> dict:
    """{(mlbam, season): {"bat": wins}} on the headline series (the label), plus
    {"pit": R2} on the realized series (the sensitivity). Not listed: departs by 0."""
    if series not in SERIES:
        raise ValueError(f"unknown core label series {series!r}; use one of {SERIES}")
    blob = load() if payload is None else payload
    key = ("dep", id(blob), series)
    if key in _MEMO:
        return _MEMO[key]
    out: dict = {}
    for s_str, blk in (blob.get("seasons") or {}).items():
        s = int(s_str)
        for m, d in (blk.get("bat") or {}).items():
            if d is not None and math.isfinite(float(d)):
                out.setdefault((int(m), s), {})["bat"] = float(d)
        if series == "realized":
            for m, d in (blk.get("pit_r2") or {}).items():
                if d is not None and math.isfinite(float(d)):
                    out.setdefault((int(m), s), {})["pit"] = float(d)
    _MEMO[key] = out
    return out
