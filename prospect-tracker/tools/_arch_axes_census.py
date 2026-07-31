"""Scratch: ARCHETYPE AXIS CENSUS. For every axis the owner named, measure join
coverage on the eFV FIT pool and on the SERVED board, per side. Read-only."""
from __future__ import annotations
import json, sys, sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DATA = ROOT / "data"
import storage  # noqa: E402


def _j(p):
    try:
        return json.loads((DATA / p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def pools():
    out = {}
    for side, mp, lp in (("hit", "xfv_hitter_matrix.json", "xfv_live_hitter_matrix.json"),
                         ("pit", "xfv_pitcher_matrix.json", "xfv_live_pitcher_matrix.json")):
        rows = _j(mp)
        is_pit = side == "pit"
        fit = [r for r in rows if bool(r.get("is_pitcher")) == is_pit
               and not (r.get("kind") == "bust" and r.get("bust_recent"))
               and r.get("target_censored") is not None
               and r.get("consensus_fv_raw") is not None]
        live = _j(lp)
        served = [r for r in live if r.get("milb") and r.get("consensus_fv_raw") is not None]
        out[side] = {"FIT": fit, "SERVED": served}
    return out


def keyset_mlbam(d, path=None, pred=None):
    """Return a set of int mlbam ids present in a by_mlbam-style artifact."""
    if d is None:
        return set()
    node = d
    for p in (path or []):
        node = (node or {}).get(p)
    out = set()
    if isinstance(node, dict):
        for k, v in node.items():
            if pred and not pred(v):
                continue
            try:
                out.add(int(k))
            except (TypeError, ValueError):
                pass
    elif isinstance(node, list):
        for v in node:
            mid = v.get("mlbam_id") or v.get("mlbam") or v.get("id")
            if mid is None:
                continue
            if pred and not pred(v):
                continue
            try:
                out.add(int(mid))
            except (TypeError, ValueError):
                pass
    return out


def keyset_pk(d, path=None):
    node = d
    for p in (path or []):
        node = (node or {}).get(p)
    if isinstance(node, dict):
        return set(node.keys())
    if isinstance(node, list):
        return {v.get("player_key") for v in node if v.get("player_key")}
    return set()


def main():
    P = pools()
    bio = _j("../tools/_arch_bio_cache.json")
    if bio is None:
        bio = json.loads((ROOT / "tools" / "_arch_bio_cache.json").read_text(encoding="utf-8"))
    con = sqlite3.connect(f"file:{storage.DB_PATH}?mode=ro", uri=True)
    dp_ht = {r[0] for r in con.execute(
        "select promoted_key from draft_players where promoted_key is not null "
        "and height is not null and weight is not null")}
    dp_ht |= {r[0] for r in con.execute(
        "select player_key from draft_players where height is not null and weight is not null")}
    ov_ht = {r[0] for r in con.execute(
        "select coalesce(promoted_key, player_key) from overseas_players "
        "where height is not null and weight is not null")}
    dp_ht |= ov_ht
    pos_played = _j("positions_played.json")

    # ---- artifact key sets --------------------------------------------------
    A = {}
    A["savant_oaa"] = ("mlbam", keyset_mlbam(_j("savant_oaa.json"), ["by_mlbam"]))
    pf = _j("positional_fit.json")
    A["positional_fit"] = ("mlbam", keyset_mlbam(pf, ["players"]))
    mpr = _j("milb_pitch_rates.json")
    A["milb_pitch_rates(CSW/SwStr)"] = ("mlbam", keyset_mlbam(mpr, ["features"]))
    A["tj_surgery"] = ("mlbam", keyset_mlbam(_j("tj_surgery.json"), ["players"]))
    A["swing_plus"] = ("mlbam", keyset_mlbam(_j("swing_plus.json"), ["players"]))
    A["statcast_aaa_hitters"] = ("mlbam", keyset_mlbam(_j("statcast_aaa_hitters.json"), ["by_mlbam"]))
    A["advancement_pace(AP+)"] = ("mlbam", keyset_mlbam(_j("advancement_pace.json"), ["by_mlbam"]))
    A["draft_bonus_slot"] = ("mlbam", keyset_mlbam(_j("draft_bonus_slot.json"), []))
    pv = _j("pipeline_vintages.json")
    pvs = set()
    if pv:
        for yr, lst in (pv.get("vintages") or {}).items():
            for row in (lst if isinstance(lst, list) else []):
                if row.get("mlbam"):
                    pvs.add(int(row["mlbam"]))
                elif row.get("mlbam_id"):
                    pvs.add(int(row["mlbam_id"]))
    A["pipeline_vintage"] = ("mlbam", pvs)
    A["collegesavant(CS+)"] = ("pk", keyset_pk(_j("collegesavant_milb_equiv.json"), ["by_player_key"]))
    al = _j("amateur_leagues.json")
    if al is not None:
        node = al.get("players") if isinstance(al, dict) else al
        s = set()
        if isinstance(node, dict):
            s = set(node.keys())
        elif isinstance(node, list):
            s = {str(v.get("player_key") or v.get("name")) for v in node}
        A["amateur_leagues"] = ("pk", s)
    A["biometrics(StatsAPI now)"] = ("mlbam", {int(k) for k, v in bio.items() if v and v.get("weight" if False else "w")})
    A["biometrics(draft-time,as-of)"] = ("pk", dp_ht)
    if pos_played:
        node = pos_played.get("by_player_key") or pos_played.get("players") or pos_played
        A["positions_played(actual pos)"] = ("pk", set(node.keys()) if isinstance(node, dict) else set())

    print(f"{'axis':32s} {'key':6s} {'hitFIT':>10s} {'hitSRV':>10s} {'pitFIT':>10s} {'pitSRV':>10s}")
    for name, (kind, ks) in A.items():
        cells = []
        for side in ("hit", "pit"):
            for pool in ("FIT", "SERVED"):
                rows = P[side][pool]
                if kind == "mlbam":
                    c = sum(1 for r in rows if r.get("mlbam_id") and int(r["mlbam_id"]) in ks)
                else:
                    c = sum(1 for r in rows if r.get("player_key") in ks)
                cells.append(f"{100*c/len(rows):.1f}% ({c})")
        print(f"{name:32s} {kind:6s} {cells[0]:>10s} {cells[1]:>10s} {cells[2]:>10s} {cells[3]:>10s}")

    print()
    for side in ("hit", "pit"):
        for pool in ("FIT", "SERVED"):
            rows = P[side][pool]
            print(f"{side} {pool} n={len(rows)}")


if __name__ == "__main__":
    main()
