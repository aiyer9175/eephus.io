# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The shown tool grades for calculations, and the eTool composite (ETOOLS_ALL_CALCS).

Owner decision EW3-30 (2026-10-15), verbatim: "Make sure we are using eTools in all
calculations for tool grades across the site, as well as making an eTool composite (we
currently are just showing tool composite grade)." Inventory, classification and the
registered re-reads: docs/tools-2026-10/ETOOLS_ALL_CALCS.md.

WHAT A SHOWN GRADE IS. Since ETOOLS_SITEWIDE_FLIP (135a0912) every surface prints, per
tool, the eTool where one passed its gate (hit, game power, pitch selection, bat control,
fastball, command) and the consensus grade otherwise. The site reads the eTools from
data/etools.json (etools.py --preview). `shown_grades` builds the same map on the server:
the consensus grade dict with each passing eTool in its place, and the one Power grade
(the `pwr` key, the v12 mean of game and raw power) replaced by game power's eTool, exactly
as prospx toolGradesShown does. A tool with no eTool, and a player with no eTool on file,
keeps the consensus grade. Amateur and international players (draft, IFA, overseas) have
no minor-league line, so there is no eTool for them and their shown grade IS the consensus
grade: nothing here changes a draft, IFA or overseas number.

`value="etool"` returns the eTool at 2 dp (the composites clean every input to the half
grade, as they always did for the consensus); `value="shown"` returns the printed whole
grade (the per-tool green and red flags, which print the grade).

THE eTOOL COMPOSITE. storage._compute_tool_composites, unchanged, run on the shown map: the
same Tool (p = 4 power mean), O-Tool (weighted mean), D-Tool (weighted p = 3 power mean),
stuff (p = 3 power mean) and command composites with the same Frame, Athleticism and
Delivery inputs. While ETOOLS_COMPOSITE_ON is True the served `tools.composite_*` fields are
the eTool composites and `tools.composite_cons` keeps the consensus ones beside them; False
reproduces the consensus composites byte for byte and adds no field.

Nothing here reads a future-value grade, groups by one or fits anything.
"""
from __future__ import annotations

import json
from pathlib import Path

#: The served basis switch. False: every composite, flag and tiebreak reads the
#: consensus grades exactly as before ETOOLS_ALL_CALCS, and no new payload field exists.
ETOOLS_COMPOSITE_ON = True

ROOT = Path(__file__).resolve().parent
SERVED_PATH = ROOT / "data" / "etools.json"

#: The composite fields _compute_tool_composites writes (the consensus copies ride
#: under tools.composite_cons with these names).
COMPOSITE_KEYS = ("composite_overall", "composite_off", "composite_def",
                  "composite_stuff", "composite_cmd")

_PAYLOAD: dict | None = None
_PAYLOAD_PATH: Path | None = None


def load_payload(path: Path | None = None, *, refresh: bool = False) -> dict:
    """data/etools.json as a dict ({} when absent or unreadable). Cached per path."""
    global _PAYLOAD, _PAYLOAD_PATH
    p = Path(path) if path is not None else SERVED_PATH
    if _PAYLOAD is not None and _PAYLOAD_PATH == p and not refresh:
        return _PAYLOAD
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        doc = {}
    if not isinstance(doc, dict):
        doc = {}
    by_mlbam = {}
    for k, rec in (doc.get("players") or {}).items():
        mid = (rec or {}).get("mlbam")
        if mid is not None:
            by_mlbam[str(mid)] = rec
    doc["_by_mlbam"] = by_mlbam
    _PAYLOAD, _PAYLOAD_PATH = doc, p
    return doc


def reset_cache() -> None:
    global _PAYLOAD, _PAYLOAD_PATH
    _PAYLOAD, _PAYLOAD_PATH = None, None


def etool_record(player_key: str | None, mlbam=None, *, payload: dict | None = None) -> dict | None:
    """The player's eTools record, matched as the site matches it: player_key first, then
    the MLBAM id. None while ETOOLS_COMPOSITE_ON is False or when nothing is on file."""
    if not ETOOLS_COMPOSITE_ON:
        return None
    doc = payload if payload is not None else load_payload()
    players = doc.get("players") or {}
    rec = players.get(player_key) if player_key else None
    if rec is None and mlbam is not None:
        by_mlbam = doc.get("_by_mlbam")
        if by_mlbam is None:
            by_mlbam = {str(r.get("mlbam")): r for r in players.values()
                        if r and r.get("mlbam") is not None}
        rec = by_mlbam.get(str(mlbam))
    return rec or None


def shown_grades(consensus: dict | None, rec: dict | None, *,
                 value: str = "etool") -> tuple[dict | None, list[str]]:
    """(the grade map a surface shows, the tool keys an eTool replaced).

    `consensus` is the per-tool consensus dict (tools_consensus or tools.grades). With no
    record, the map itself and []. The `pwr` key follows game power's eTool (prospx
    toolGradesShown sets it whether or not the consensus map carried one). value: "etool" (2 dp) or "shown" (the printed whole grade)."""
    if consensus is None:
        return None, []
    if not rec:
        return consensus, []
    out = dict(consensus)
    used: list[str] = []
    for tool, t in (rec.get("tools") or {}).items():
        v = (t or {}).get("etool" if value == "etool" else "shown")
        if v is None:
            continue
        out[tool] = float(v)
        used.append(tool)
        if tool == "game_pwr":
            out["pwr"] = float(v)
    return out, sorted(used)


def shown_for(player_key: str | None, mlbam, consensus: dict | None, *,
              value: str = "etool") -> tuple[dict | None, list[str]]:
    """shown_grades for one player, looked up in data/etools.json."""
    return shown_grades(consensus, etool_record(player_key, mlbam), value=value)


def with_consensus_reference(etool_payload: dict | None, cons_payload: dict | None,
                             used: list[str]) -> dict | None:
    """The served tools payload while the flag is on: the eTool composites in the
    composite_* fields, the consensus grades in `grades` (the site's per-tool resolver
    reads them as the consensus reference), the consensus composites under
    `composite_cons`, and the basis. A player with no eTool on file is the consensus
    payload with basis "consensus" and the same `composite_cons`."""
    if cons_payload is None and etool_payload is None:
        return None
    base = dict(cons_payload if cons_payload is not None else etool_payload)
    cons = {k: (cons_payload or {}).get(k) for k in COMPOSITE_KEYS}
    if used and etool_payload is not None:
        for k in COMPOSITE_KEYS:
            base[k] = etool_payload.get(k)
        base["composite_basis"] = "etools"
        base["etool_keys"] = list(used)
    else:
        base["composite_basis"] = "consensus"
    base["composite_cons"] = cons
    return base
