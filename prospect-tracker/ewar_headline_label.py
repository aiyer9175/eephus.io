# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The headline eWAR label vintage (docs/efv-2026-10-22/EWAR_HEADLINE_LABEL_GATE.md part 3;
task EFV_LABEL_HEADLINE_EWAR_CHECK, owner answer EWLE-Q2).

THE LABEL IS THE HEADLINE eWAR: published fWAR from the frozen vintage plus the headline
departures of data/ewar_v3.json (the eABS part, 2026 on), frozen here so that a later
rebuild of data/ewar_v3.json cannot move a label value without a new vintage id (the
EW3-19 precedent). eWAR realized (the realized departures, R2 from 2016 plus eABS) is kept
beside it as a sensitivity; it trains nothing and anchors nothing.

    build()         the payload tools/build_ewar_headline_label.py writes; refuses on any
                    missed identity (gate part 3)
    write()         writes ONCE: an existing file with other content is refused
    load()          the frozen file (memoised; its content hash is re-checked)
    departures()    {(mlbam, season): {"bat": wins, "pit": wins}} for one series
    vintage_id()    'ewar-headline-<fWAR vintage id>-<first 12 hex of content_sha256>', the
                    build identity the fingerprint's label term names under the switch
    label_series()  one stored career_war row's {year: war} on the label (the switch's
                    read; an fwar row moves, any other row is returned as stored)

The switch (war_source.EFV_LABEL_EWAR_HEADLINE) is scoped to eFV's label: efv_dataset reads
its series through label_series() (gate amendment 9.2; efv_labels' development frames stay on
published fWAR). Display doors never read this module.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data" / "ewar_headline_label.json"
GATE_DOC = "docs/efv-2026-10-22/EWAR_HEADLINE_LABEL_GATE.md"
VERSION = "ewar_headline_label_v1"
BUILD_CMD = "python tools/build_ewar_headline_label.py --write"
SERIES = ("headline", "realized")
SIDES = ("bat", "pit")
#: The first season a headline departure may carry (the eABS part's; gate part 3, identity 4).
FIRST_HEADLINE_SEASON = 2026

#: Identity tolerance (gate part 3 and amendment 9.1), in wins.
TOL_ROW = 1e-9
#: Storage precision of a departure.
NDP = 6

#: The per-season keys of each series in the stored file.
_KEYS = {"headline": {"bat": "bat", "pit": "pit"}, "realized": {"bat": "real_bat", "pit": "real_pit"}}


class EwarHeadlineLabelRefusal(RuntimeError):
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
    return f"ewar-headline-{fwar_vintage_id}-{content_sha[:12]}"


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------

def build(v3: dict | None = None, fwar_vintage_id: str | None = None, log=print) -> dict:
    """The label payload, copied from data/ewar_v3.json. Refuses (EwarHeadlineLabelRefusal)
    on any missed identity:
      1. data/ewar_v3.json is built on the frozen fWAR vintage the site serves;
      2. every stored departure equals ewar_v3.departures on its series within TOL_ROW;
      3. per season and side, the headline departures sum to zero (amendment 9.1: the
         artifact's pre-rounding sum within TOL_ROW, the stored 6-decimal departures within
         the rounding bound n x 0.5e-6);
      4. no headline departure falls in a season before FIRST_HEADLINE_SEASON."""
    import ewar_v3
    pay = ewar_v3.load() if v3 is None else v3
    if fwar_vintage_id is None:
        import fwar_vintage
        fwar_vintage_id = str(fwar_vintage.load().get("vintage_id") or "")
    have = str(pay.get("fwar_vintage_id") or "")
    if not fwar_vintage_id or have != fwar_vintage_id:
        raise EwarHeadlineLabelRefusal(
            f"identity 1: data/ewar_v3.json is on fWAR vintage {have!r}, the site serves {fwar_vintage_id!r}")
    deps = {name: ewar_v3.departures(pay, series=name) for name in SERIES}
    block: dict[str, dict] = {}
    for name in SERIES:
        for (mid, season), cell in deps[name].items():
            if name == "headline" and int(season) < FIRST_HEADLINE_SEASON and any(
                    float(v) != 0.0 for v in cell.values()):
                raise EwarHeadlineLabelRefusal(
                    f"identity 4: headline departure in {season} for {mid}, before {FIRST_HEADLINE_SEASON}")
            blk = block.setdefault(str(int(season)), {k: {} for k in
                                                      ("bat", "pit", "real_bat", "real_pit")})
            for side, v in cell.items():
                if side not in SIDES:
                    continue
                r = round(float(v), NDP)
                if r != 0.0:
                    blk[_KEYS[name][side]][str(int(mid))] = r
    # identity 2: the stored (rounded) values against the artifact, and identity 3
    for name in SERIES:
        for (mid, season), cell in deps[name].items():
            blk = block.get(str(int(season))) or {}
            for side, v in cell.items():
                if side not in SIDES:
                    continue
                got = float((blk.get(_KEYS[name][side]) or {}).get(str(int(mid)), 0.0))
                if abs(got - float(v)) > max(TOL_ROW, 0.5 * 10 ** -NDP):
                    raise EwarHeadlineLabelRefusal(
                        f"identity 2: {name} {season} {side} {mid}: stored {got!r} != artifact {float(v)!r}")
    counts: dict[str, dict] = {}
    checks = pay.get("checks") or {}
    for s in sorted(block, key=int):
        blk = block[s]
        for side in SIDES:
            # identity 3 under amendment 9.1: (a) the artifact's pre-rounding sum, (b) the
            # stored 6-decimal departures within the rounding bound n x 0.5e-6
            pre = ((checks.get(s) or {}).get("sum_departure_wins") or {}).get(f"dh_{side}")
            if blk[side] and (pre is None or abs(float(pre)) > TOL_ROW):
                raise EwarHeadlineLabelRefusal(
                    f"identity 3a: {s} headline {side} pre-rounding sum is {pre!r}")
            tot = sum(float(v) for v in blk[side].values())
            bound = len(blk[side]) * 0.5 * 10 ** -NDP + TOL_ROW
            if abs(tot) > bound:
                raise EwarHeadlineLabelRefusal(
                    f"identity 3b: {s} headline {side} departures sum to {tot!r} (bound {bound!r})")
        counts[s] = {k: len(v) for k, v in blk.items()}
        log(f"  {s}: headline bat {len(blk['bat'])}, pit {len(blk['pit'])}; realized bat "
            f"{len(blk['real_bat'])}, pit {len(blk['real_pit'])}; identities hold")
    sha = content_sha256(block)
    import fwar_vintage
    return {
        "schema": 1,
        "model": "ewar_headline_label",
        "version": VERSION,
        "vintage_id": make_vintage_id(fwar_vintage_id, sha),
        "content_sha256": sha,
        "built_at": _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat(),
        "registration": GATE_DOC,
        "fwar_vintage_id": fwar_vintage_id,
        "fwar_vintage_sha256": _sha_file(fwar_vintage.VINTAGE_PATH),
        "ewar_v3_generated_at": pay.get("generated_at"),
        "ewar_v3_sha256": _sha_file(ROOT / "data" / "ewar_v3.json"),
        "first_headline_season": FIRST_HEADLINE_SEASON,
        "field_key": {
            "seasons.<s>.bat / .pit": ("{mlbam: headline eWAR - published fWAR} per side, wins, 6 "
                                      "decimals: the label's departures; not listed departs by 0"),
            "seasons.<s>.real_bat / .real_pit": ("{mlbam: eWAR realized - published fWAR} per side: the "
                                                "realized sensitivity only, never the label"),
        },
        "counts": counts,
        "seasons": block,
        "note": ("eFV's training label once war_source.EFV_LABEL_EWAR_HEADLINE flips; never displayed "
                 "from this file (the displayed eWAR reads data/ewar_v3.json)."),
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
            raise EwarHeadlineLabelRefusal(f"{path} exists and is unreadable ({e}); it is never overwritten")
        if have.get("content_sha256") == payload.get("content_sha256"):
            return path, "unchanged"
        raise EwarHeadlineLabelRefusal(
            f"{path} is frozen at {have.get('vintage_id')}; the build reads {payload.get('vintage_id')}. "
            f"A new label value needs a new vintage id through a dated amendment ({GATE_DOC} part 9).")
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
            raise EwarHeadlineLabelRefusal(f"{p}: content_sha256 does not match its departures")
        _MEMO[key] = blob
    return _MEMO[key]


def vintage_id(payload: dict | None = None) -> str:
    blob = load() if payload is None else payload
    return str(blob.get("vintage_id") or "")


def departures(payload: dict | None = None, series: str = "headline") -> dict:
    """{(mlbam, season): {"bat": wins, "pit": wins}} for one series ('headline', the
    label, or 'realized', the sensitivity). A side or player-season not listed departs by 0."""
    if series not in SERIES:
        raise ValueError(f"unknown headline label series {series!r}; use one of {SERIES}")
    blob = load() if payload is None else payload
    key = ("dep", id(blob), series)
    if key in _MEMO:
        return _MEMO[key]
    out: dict = {}
    for s_str, blk in (blob.get("seasons") or {}).items():
        s = int(s_str)
        for side in SIDES:
            for m, d in (blk.get(_KEYS[series][side]) or {}).items():
                if d is not None and math.isfinite(float(d)):
                    out.setdefault((int(m), s), {})[side] = float(d)
    _MEMO[key] = out
    return out


def label_series(row: dict | None, payload: dict | None = None, series: str = "headline") -> dict:
    """One stored career_war row's {year: war} on the label: for an fwar row, each season
    the frozen fWAR vintage served (not in its fwar_coverage fallback years) moves by the
    player-season's departure on both sides, 2 decimals (the eWAR v3 transform,
    war_source._ewar_v3_row); any other row, or a row without an mlbam, is returned as
    stored. The input is never mutated."""
    row = row or {}
    stored = row.get("seasons") or {}
    if str(row.get("source") or "") != "fwar" or not isinstance(stored, dict):
        return dict(stored) if isinstance(stored, dict) else {}
    fcov = row.get("fwar_coverage") or {}
    mid = fcov.get("mlbam")
    if not mid:
        return dict(stored)
    keep = {int(y) for y in (fcov.get("fallback_pre_years") or [])} | {
        int(y) for y in (fcov.get("fallback_post_years") or [])}
    deps = departures(payload, series=series)
    out = {}
    for yr_s, v in stored.items():
        d = deps.get((int(mid), int(yr_s))) if int(yr_s) not in keep else None
        out[yr_s] = round(float(v) + sum(d.values()), 2) if d else v
    return out
