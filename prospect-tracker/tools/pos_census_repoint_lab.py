# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""LANE P measurement: repointing efv_model._observed_pos_map at the as-of census.

READ-ONLY. Writes nothing under data/. Every number in
docs/efv-pos-census-repoint-2026-08-07/RESULTS.md comes from here:

    python tools/pos_census_repoint_lab.py            # all sections
    python tools/pos_census_repoint_lab.py cover      # coverage + label gap only
    python tools/pos_census_repoint_lab.py miss       # why each uncovered row is uncovered
    python tools/pos_census_repoint_lab.py idsrc      # row mlbam_id vs the lab binding
    python tools/pos_census_repoint_lab.py flips      # what the flag would change

Sections are independent; each prints its own JSON block.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DATA = ROOT / "data"

import efv_model as E              # noqa: E402
import fielding_positions as FP    # noqa: E402
from efv_dataset import matrix_path  # noqa: E402


def _j(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def _mtime(p):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(Path(p).stat().st_mtime))


def _train():
    raw = _j(matrix_path("hit"))
    return raw, {"all": raw,
                 "debuted": [r for r in raw if r["kind"] == "debuted"],
                 "bust": [r for r in raw if r["kind"] == "bust"]}


def _live():
    return [r for r in _j(DATA / "xfv_live_hitter_matrix.json") if not r.get("is_pitcher")]


def _lab_binding():
    """The census-scoped player_key -> mlbam binding the driver lane used."""
    try:
        return _j(DATA / "fielding_census_ids.json")
    except (OSError, ValueError):
        return {}


def _asof_map(rows, *, use_lab_binding: bool, scope: str):
    """{player_key: observed pos at that row's own as-of date} via the as-of census."""
    census = FP.load_season_census()
    bind = (_lab_binding().get(scope) or {}) if use_lab_binding else {}
    mlbam_by_key, asof_by_key = {}, {}
    for r in rows:
        pk = r["player_key"]
        mid = (bind.get(pk) or {}).get("mlbam") or r.get("mlbam_id")
        if mid:
            mlbam_by_key[pk] = int(mid)
        if r.get("asof_date"):
            asof_by_key[pk] = r["asof_date"]
    return FP.observed_positions_as_of(census, asof_by_key, mlbam_by_key), mlbam_by_key


def _cov(groups, obs, ids=None):
    out = {}
    for g, rows in groups.items():
        n = len(rows)
        c = sum(1 for r in rows if obs.get(r["player_key"]))
        d = {"n": n, "covered": c, "frac": round(c / n, 4) if n else None}
        if ids is not None:
            idc = sum(1 for r in rows if ids.get(r["player_key"]))
            d["id_resolved"] = idc
            d["frac_of_id_resolved"] = round(c / idc, 4) if idc else None
        out[g] = d
    return out


# ── section 1: artifacts + coverage + label gap ──────────────────────────────
def cover():
    raw, groups = _train()
    live = _live()
    lg = {"live": live}

    old = FP.load_observed_positions(DATA / "positions_played.json")
    seasons_doc = _j(DATA / "positions_played_seasons.json")
    out = {
        "artifacts": {
            "positions_played.json": {
                "players_in_file": len(_j(DATA / "positions_played.json").get("players") or {}),
                "players_with_an_observation": len(old),
                "mtime": _mtime(DATA / "positions_played.json"),
                "generated_at": _j(DATA / "positions_played.json").get("generated_at"),
            },
            "positions_played_seasons.json": {
                "players_in_file": len(seasons_doc.get("players") or {}),
                "mtime": _mtime(DATA / "positions_played_seasons.json"),
                "generated_at": seasons_doc.get("generated_at"),
                "seasons": seasons_doc.get("seasons"),
                "sports": seasons_doc.get("sports"),
                "season_end": seasons_doc.get("season_end"),
            },
        },
        "old_route": {"train": _cov(groups, old), "live": _cov(lg, old)["live"]},
    }
    out["old_route"]["label_gap_debuted_minus_bust"] = round(
        out["old_route"]["train"]["debuted"]["frac"]
        - out["old_route"]["train"]["bust"]["frac"], 4)

    for tag, lab in (("asof_route_row_id", False), ("asof_route_lab_binding", True)):
        obs, ids = _asof_map(raw, use_lab_binding=lab, scope="matrix")
        lobs, lids = _asof_map(live, use_lab_binding=lab, scope="live")
        d = {"train": _cov(groups, obs, ids), "live": _cov(lg, lobs, lids)["live"]}
        d["label_gap_debuted_minus_bust"] = round(
            d["train"]["debuted"]["frac"] - d["train"]["bust"]["frac"], 4)
        d["label_gap_conditional_on_id"] = round(
            d["train"]["debuted"]["frac_of_id_resolved"]
            - d["train"]["bust"]["frac_of_id_resolved"], 4)
        out[tag] = d
    return out


# ── section 2: why each uncovered row is uncovered ───────────────────────────
_MISS_REASONS = ("no_mlbam_id", "id_not_in_census", "no_season_complete_by_asof",
                 "below_exposure_floor_or_all_dh", "no_asof_date")


def miss():
    raw, groups = _train()
    census = FP.load_season_census()
    obs, ids = _asof_map(raw, use_lab_binding=True, scope="matrix")
    buckets = {k: {"debuted": [], "bust": []} for k in _MISS_REASONS}
    for r in raw:
        pk = r["player_key"]
        if obs.get(pk):
            continue
        kind = r["kind"]
        if not r.get("asof_date"):
            why = "no_asof_date"
        elif not ids.get(pk):
            why = "no_mlbam_id"
        elif not census.get(str(ids[pk])):
            why = "id_not_in_census"
        elif not FP.as_of_by_pos(census[str(ids[pk])], r["asof_date"]):
            why = "no_season_complete_by_asof"
        else:
            why = "below_exposure_floor_or_all_dh"
        if kind in buckets[why]:
            buckets[why][kind].append(pk)
    out = {"totals": {k: {"debuted": len(v["debuted"]), "bust": len(v["bust"]),
                          "all": len(v["debuted"]) + len(v["bust"])}
                      for k, v in buckets.items()},
           "keys": {k: {"debuted": sorted(v["debuted"])[:60],
                        "bust": sorted(v["bust"])[:80]} for k, v in buckets.items()}}
    out["uncovered_total"] = sum(v["all"] for v in out["totals"].values())

    # composition of the two identity buckets, from timeseries
    ts = {p["player_key"]: p for p in (_j(DATA / "timeseries.json").get("players") or [])}
    comp = {}
    for why in ("no_mlbam_id", "id_not_in_census"):
        keys = buckets[why]["debuted"] + buckets[why]["bust"]
        rows = []
        for k in keys:
            p = ts.get(k) or {}
            rows.append({"player_key": k,
                         "org": p.get("org"), "status": p.get("status"),
                         "level": p.get("current_level"),
                         "acq": (p.get("acquisition") or p.get("current_acquisition")),
                         "mlbam_id": p.get("mlbam_id"),
                         "in_ts": bool(p)})
        comp[why] = {"n": len(rows), "rows": rows}
    out["identity_bucket_composition"] = comp
    return out


# ── section 3: does the row's own mlbam_id suffice, or is the lab file load-bearing? ─
def idsrc():
    raw, _ = _train()
    live = _live()
    bind = _lab_binding()
    out = {}
    for tag, rows, scope in (("train", raw, "matrix"), ("live", live, "live")):
        b = bind.get(scope) or {}
        row_only = sum(1 for r in rows if r.get("mlbam_id"))
        either = sum(1 for r in rows
                     if r.get("mlbam_id") or (b.get(r["player_key"]) or {}).get("mlbam"))
        lab_only = sum(1 for r in rows
                       if not r.get("mlbam_id") and (b.get(r["player_key"]) or {}).get("mlbam"))
        disagree = sum(1 for r in rows
                       if r.get("mlbam_id") and (b.get(r["player_key"]) or {}).get("mlbam")
                       and int(r["mlbam_id"]) != int(b[r["player_key"]]["mlbam"]))
        obs_row, _ = _asof_map(rows, use_lab_binding=False, scope=scope)
        obs_lab, _ = _asof_map(rows, use_lab_binding=True, scope=scope)
        out[tag] = {"n": len(rows), "row_mlbam_id": row_only,
                    "row_or_lab": either, "lab_adds": lab_only,
                    "id_disagreements": disagree,
                    "covered_row_id_only": len(obs_row),
                    "covered_with_lab_binding": len(obs_lab),
                    "coverage_the_lab_file_buys": len(obs_lab) - len(obs_row)}
    return out


# ── section 4: what flipping the flag would change, through the model's own path ──
def flips():
    raw, groups = _train()
    live = _live()
    out = {}
    for tag, rows in (("train", raw), ("live", live)):
        f = {"gain": 0, "lose": 0, "same": 0, "no_observation": 0, "n": len(rows)}
        for r in rows:
            base = E._pos_premium(r.get("position"), "hit")
            E.POS_PREMIUM_USES_OBSERVED = True
            try:
                got = E._pos_premium_for_row(r, "hit")
            finally:
                E.POS_PREMIUM_USES_OBSERVED = False
            seen = (E._observed_pos_as_of(r)
                    or E._observed_pos_map().get(r["player_key"]))
            if not seen:
                f["no_observation"] += 1
                continue
            f["gain" if got > base else "lose" if got < base else "same"] += 1
        f["covered"] = f["n"] - f["no_observation"]
        f["changed"] = f["gain"] + f["lose"]
        out[tag] = f
    # the flag OFF must be a byte-for-byte no-op: prove it rather than assert it
    E.POS_PREMIUM_USES_OBSERVED = False
    off = sum(1 for r in raw + live
              if E._pos_premium_for_row(r, "hit") != E._pos_premium(r.get("position"), "hit"))
    out["rows_that_move_with_the_flag_off"] = off
    return out


_MODES = {"cover": cover, "miss": miss, "idsrc": idsrc, "flips": flips}

if __name__ == "__main__":
    want = sys.argv[1:] or list(_MODES)
    for m in want:
        print(f"===== {m} =====")
        print(json.dumps(_MODES[m](), indent=1, default=str))
