# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV v2 labels for the list-vintage frame (docs/efv-v2/PROGRAM.md s2.2, s3.3, EV-04).

LABEL ONLY. This module reads outcomes and nothing else: it takes no grade, fits
nothing, scores nothing and summarises nothing by grade. A caller joins its output to
efv_vintage_frame rows. The WAR series is war_source.DEFAULT_PROVIDER (eWAR v2 today;
the fWAR epoch moves it, and these labels move with it on the next build).

For a player first read at list vintage V, with effective debut year dy:

    W3   WAR summed over dy, dy+1, dy+2 when V <= dy <= V+3; 0.0 when he did not debut
         in V..V+3. Resolved once V + 5 <= RESOLVED_THROUGH, so a V+3 debut has three
         observed seasons. The SCORING label of F-LV (PROGRAM.md s2.2).
    W2   The same over dy, dy+1; resolved once V + 4 <= RESOLVED_THROUGH. A hazard
         component, not a scoring label.
    R3   1.0 when REACHED with dy <= V+3, else 0.0; resolved once V + 3 <= RESOLVED_THROUGH.
    L6   efv_dataset._label_6yr on the debut (the v1 training label, same censoring
         rule), 0.0 for a resolved BUST-NEVER, None for CENSORED-NEVER.
    REACHED, per BUST2 (docs/master-plan-2026-09-11-war-epoch-drivers-betting.md s3.2):
         at least one MLB regular-season appearance, a sport-1 stat line or a WAR
         season on the provider; a debut date alone does not count. Not reached splits
         into "never" (resolved: id known and no affiliated line in either of the two
         latest seasons with MiLB data on disk, OR age 27 or older on July 1 of
         RESOLVED_THROUGH, OR neither id nor birth date and last list year at or before
         RESOLVED_THROUGH - 5) and "censored_never" (kept, excluded from fit and score).

W3 is the 3-season window WAR, so "W3 = 0.0 because no debut" is carried as
w3_debut False; a debuted player can also sum to exactly 0.0, and the flag, not the
value, says which.

Effective debut year: the first MLB season on the evidence (the earliest WAR season or
id-matched sport-1 line). The published debut year is used when it agrees; a September or
later published debut whose first MLB season is the next year is re-dated to it
(efv_dataset guard b); a published date LATER than an id-matched sport-1 line is a
placeholder (many read YYYY-07-01) and the stat line wins. A WAR season before the
published debut with no id-matched line to back it (efv_dataset guard a, a name
collision), a gap after the published debut, or a debut before V marks the row
"identity_conflict" and every WAR label is None, never a fabricated 0.

RESERVED. A reserved list vintage raises through efv_vintage_frame.guard_score_request
unless the committed gate sha is passed. A WAR label on a debut in
R_VM_FIRST_DEBUT_YEAR or later is withheld (None, status "reserved_vm"): those cohorts
are the prospective vintage-matched looks.

GATE COMPLIANCE (docs/PROSPECT_ANCHOR_GATE.md): no grade is read here at all.
"""
from __future__ import annotations

import efv_dataset as D
import efv_vintage_frame as F
import milb_history as mh

W_DEBUT_WINDOW = 3          # debut in V..V+3 counts ("within 3 seasons of V")
W3_SEASONS = 3
W2_SEASONS = 2
NEVER_AGE = 27              # BUST2 age rule, on July 1 of RESOLVED_THROUGH
NEVER_LIST_LAG = 5          # BUST2 no-id rule: last list year <= RT - 5


def resolved_through() -> int:
    return int(D.RESOLVED_THROUGH)


def provider() -> str:
    import war_source
    return str(war_source.DEFAULT_PROVIDER)


def war_seasons_table() -> dict[str, dict[int, float]]:
    """{player_key: {season: WAR}} on war_source.DEFAULT_PROVIDER, as stored."""
    import war_source
    out: dict[str, dict[int, float]] = {}
    for pk, agg in war_source.career_war_table(provider=war_source.DEFAULT_PROVIDER).items():
        seasons = (agg or {}).get("seasons") or {}
        try:
            out[pk] = {int(y): float(w) for y, w in seasons.items() if w is not None}
        except (TypeError, ValueError):
            continue
    return out


# ---------------------------------------------------------------------------
# REACHED and the never-resolution rule
# ---------------------------------------------------------------------------

_SPORT1: dict[int, frozenset[int]] = {}
_AFFIL: dict[int, frozenset[int]] = {}


def _sport1_ids(season: int) -> frozenset[int]:
    if season not in _SPORT1:
        ids = set()
        for g in ("hitting", "pitching"):
            ids |= {int(r["mlbam"]) for r in mh.season_splits(1, season, g, fetch=False)
                    if r.get("mlbam")}
        _SPORT1[season] = frozenset(ids)
    return _SPORT1[season]


def _affiliated_ids(season: int) -> frozenset[int]:
    if season not in _AFFIL:
        ids = set()
        for g in ("hitting", "pitching"):
            for m, rows in mh.player_index(season, g, fetch=False).items():
                if any(r.get("level") != "MLB" for r in rows):
                    ids.add(int(m))
        _AFFIL[season] = frozenset(ids)
    return _AFFIL[season]


def latest_milb_seasons(n: int = 2) -> tuple[int, ...]:
    """The n latest seasons with MiLB data on disk."""
    out = []
    for s in range(D.CURRENT_SEASON, 2013, -1):
        if _affiliated_ids(s):
            out.append(s)
            if len(out) == n:
                break
    return tuple(out)


def first_mlb_line(mlbam) -> int | None:
    try:
        mid = int(mlbam)
    except (TypeError, ValueError):
        return None
    for s in range(2014, D.CURRENT_SEASON + 1):
        if mid in _sport1_ids(s):
            return s
    return None


def reached_class(rec: dict, seasons: dict[int, float] | None) -> str:
    """'reached', 'never' or 'censored_never' (BUST2 s3.2)."""
    mlbam = rec.get("mlbam_id")
    if seasons or first_mlb_line(mlbam) is not None:
        return "reached"
    rt = resolved_through()
    try:
        mid = int(mlbam) if mlbam else None
    except (TypeError, ValueError):
        mid = None
    if mid is not None:
        if not any(mid in _affiliated_ids(s) for s in latest_milb_seasons(2)):
            return "never"
    bd = str(rec.get("birth_date") or "")
    if len(bd) >= 10 and bd[:4].isdigit():
        by, md = int(bd[:4]), bd[5:10]
        age_jul1 = rt - by - (1 if md > "07-01" else 0)
        if age_jul1 >= NEVER_AGE:
            return "never"
    if mid is None and not bd:
        years = [int(p["snapshot_date"][:4]) for p in (rec.get("points") or [])
                 if str(p.get("snapshot_date") or "")[:4].isdigit()]
        if years and max(years) <= rt - NEVER_LIST_LAG:
            return "never"
    return "censored_never"


def effective_debut(rec: dict, seasons: dict[int, float] | None
                    ) -> tuple[int | None, str | None, str]:
    """(debut_year, label_date, status). status: 'ok', 'not_reached',
    'identity_conflict'. label_date is what efv_dataset._label_6yr reads."""
    s = seasons or {}
    # DS-12: the re-dated day where one exists; a placeholder day is no label date.
    _dd, _dd_placeholder, _ = D.resolved_debut_date(rec)
    dd = str(_dd or "")[:10]
    first_line = first_mlb_line(rec.get("mlbam_id"))
    if not s and first_line is None:
        return None, None, "not_reached"
    first = min([y for y in (min(s) if s else None, first_line) if y is not None])
    if not (len(dd) >= 4 and dd[:4].isdigit()):
        return first, None, "ok"
    dy = int(dd[:4])
    if dy == first:
        return dy, (None if _dd_placeholder else dd), "ok"
    if dy > first:
        # The published date is LATER than the first MLB season. When the id-matched
        # sport-1 line says so, the date is the placeholder kind (many read YYYY-07-01)
        # and the stat line is the debut. A WAR season alone is keyed by player_key and
        # can be a name collision (efv_dataset guard a), so it is not trusted.
        if first_line is not None and first_line == first:
            return first, None, "ok"
        return None, None, "identity_conflict"
    if first == dy + 1 and dd[5:7] >= "09":
        return first, None, "ok"                     # guard b: postseason-only debut
    return None, None, "identity_conflict"           # a gap after the published debut


# ---------------------------------------------------------------------------
# the labels
# ---------------------------------------------------------------------------

def window_war(seasons: dict[int, float] | None, debut_year: int | None, vintage: int,
               n_seasons: int) -> tuple[float, bool]:
    """(WAR over the first n_seasons from debut, debuted-in-window flag). The value is
    0.0 exactly when the flag is False, or when a debuted player's seasons sum to 0."""
    V = int(vintage)
    if debut_year is None or not (V <= int(debut_year) <= V + W_DEBUT_WINDOW):
        return 0.0, False
    s = seasons or {}
    return round(sum(s.get(y, 0.0) for y in range(int(debut_year),
                                                   int(debut_year) + n_seasons)), 3), True


def labels_for(rec: dict, vintage: int, seasons: dict[int, float] | None, *,
               gate_sha: str | None = None) -> dict:
    """Every F-LV label for one (player, V). None marks a label that is not resolved
    or not admissible; `status` says why."""
    V = int(vintage)
    F.guard_score_request(V, gate_sha=gate_sha, purpose="label")
    rt = resolved_through()
    rc = reached_class(rec, seasons)
    dy, label_date, status = effective_debut(rec, seasons)
    if status == "ok" and dy is not None and dy < V:
        status, dy = "identity_conflict", None
    out = {"player_key": rec.get("player_key"), "vintage": V, "provider": provider(),
           "resolved_through": rt, "reached": rc, "debut_year": dy, "status": status,
           "w3": None, "w3_debut": None, "w2": None, "w2_debut": None,
           "r3": None, "l6": None, "l6_censored_target": None, "l6_censored": None,
           "l6_weight": None}
    if status == "identity_conflict":
        return out
    reserved = dy is not None and dy >= F.R_VM_FIRST_DEBUT_YEAR
    in_window = dy is not None and V <= dy <= V + W_DEBUT_WINDOW
    if V + W_DEBUT_WINDOW <= rt:
        out["r3"] = 1.0 if (rc == "reached" and in_window) else 0.0
    for key, n, lag in (("w3", W3_SEASONS, W_DEBUT_WINDOW + W3_SEASONS - 1),
                        ("w2", W2_SEASONS, W_DEBUT_WINDOW + W2_SEASONS - 1)):
        if V + lag > rt:
            continue
        if in_window and reserved:
            out["status"] = "reserved_vm"
            continue
        val, flag = window_war(seasons if rc == "reached" else None,
                               dy if rc == "reached" else None, V, n)
        out[key], out[f"{key}_debut"] = val, flag
    if rc == "reached":
        if dy is None:
            pass
        elif reserved:
            out["status"] = "reserved_vm"
        elif dy in D.DEBUT_YEARS:
            t_res, t_cens, cflag, w, _n = D._label_6yr(seasons or {}, dy, label_date)
            out.update({"l6": t_res, "l6_censored_target": t_cens,
                        "l6_censored": bool(cflag), "l6_weight": w})
    elif rc == "never":
        out.update({"l6": 0.0, "l6_censored_target": 0.0, "l6_censored": False,
                    "l6_weight": 1.0})
    return out


def labels_for_frame(rows: list[dict], *, universe: dict[str, dict] | None = None,
                     war: dict[str, dict[int, float]] | None = None,
                     gate_sha: str | None = None) -> list[dict]:
    """labels_for over efv_vintage_frame rows (keyed by player_key and vintage)."""
    universe = universe if universe is not None else F.load_universe()
    war = war if war is not None else war_seasons_table()
    return [labels_for(universe[r["player_key"]], r["vintage"], war.get(r["player_key"]),
                       gate_sha=gate_sha) for r in rows]
