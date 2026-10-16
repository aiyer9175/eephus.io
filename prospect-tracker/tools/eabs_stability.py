# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The eABS stability check (docs/eabs-2026-10-15/EABS_GATE.md part 5), run ONCE.

Primary: self-persistence of per-challenge decision skill on the AAA 2022 to 2026
ledger, consecutive season pairs, batters (batter_id) and catchers of record
(catcher_id), N_MIN challenges in both seasons; Spearman rho with a player-clustered
bootstrap, Holm over the two roles, a permuted twin, a planted and a null-planted
recovery, MDE95. Secondary (deciding nothing): the overturn-rate excess, and MLB
2026 split-half.

    python tools/eabs_stability.py --dry-run   # fixtures with nulls, writes nothing under data/
    python tools/eabs_stability.py             # the look: data/_labs/eabs/stability.json

Reads the two ledger files, data/count_value.json and the 2026 corpus plays (through
eabs_export.frame). Reads no grade, FV, consensus field, prospect list, WAR series or
betting column.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import random
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import eabs as E  # noqa: E402
import eabs_export as X  # noqa: E402

AAA = ROOT / "data" / "_labs" / "abs_ledger" / "aaa.json"
OUT = ROOT / "data" / "_labs" / "eabs" / "stability.json"
ROLE_FRAMES = {"batter": ("batter", "batter_id"), "catcher": ("pitcher_or_catcher", "catcher_id")}


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def aaa_frame(aaa_doc: dict, cv_doc: dict, seasons=E.AAA_SEASONS) -> dict:
    """{role: [row]} with o, v, p (AAA season cell rate), c0 attached later."""
    rows = []
    excluded = defaultdict(int)
    tables = {}
    for r in E.as_dicts(aaa_doc):
        if r.get("season") not in seasons or r.get("game_type") != "R":
            excluded["season_or_type"] += 1
            continue
        if r.get("invariant_ok") is not True:
            excluded["invariant_not_ok"] += 1
            continue
        why = E.exclusion(r)
        if why:
            excluded[why] += 1
            continue
        s = int(r["season"])
        if s not in tables:
            tables[s] = E.season_tables(cv_doc, s)
        t288, re24 = tables[s]
        r["v"] = E.challenge_value(r, t288, re24)
        r["o"] = 1 if r["overturned"] else 0
        rows.append(r)
    by_season = defaultdict(list)
    for r in rows:
        by_season[int(r["season"])].append(r)
    for s, grp in by_season.items():
        pc = E.cell_rates(grp)
        for r in grp:
            r["p"] = pc[E.mix_cell(r)]
    out = {}
    for role, (rbs, idk) in ROLE_FRAMES.items():
        out[role] = [r for r in rows if r.get("role_by_side") == rbs and r.get(idk) is not None]
    return {"roles": out, "excluded": dict(excluded), "n_rows": len(rows)}


def by_player_season(rows: list, id_key: str, c0: float) -> dict:
    d = defaultdict(list)
    for r in rows:
        d[(int(r[id_key]), int(r["season"]))].append({"o": r["o"], "v": r["v"], "p": r["p"], "c0": c0})
    return d


def simulate(rows: list, id_key: str, sd: float, seed: int) -> list:
    """Planted outcomes on the real frame (gate 5.3): o ~ Bernoulli(expit(logit(p) + u))."""
    rng = random.Random(seed)
    players = sorted({int(r[id_key]) for r in rows})
    u = {p: (rng.gauss(0.0, sd) if sd > 0 else 0.0) for p in players}
    sim = []
    for r in rows:
        q = dict(r)
        q["o"] = 1 if rng.random() < E.expit(E.logit(r["p"]) + u[int(r[id_key])]) else 0
        q["overturned"] = bool(q["o"])
        sim.append(q)
    by_season = defaultdict(list)
    for q in sim:
        by_season[int(q["season"])].append(q)
    for grp in by_season.values():
        pc = E.cell_rates(grp)
        for q in grp:
            q["p"] = pc[E.mix_cell(q)]
    return sim


def _pair_counts(obs: list) -> dict:
    out = defaultdict(int)
    for o in obs:
        out[o[1]] += 1
    return dict(sorted(out.items()))


def primary(roles: dict, c0: float, boot: int = E.BOOT, b_plant: int = E.B_PLANT) -> dict:
    res = {}
    for role, rows in roles.items():
        idk = ROLE_FRAMES[role][1]
        bps = by_player_season(rows, idk, c0)
        obs = E.pair_observations(bps)
        real = E.bootstrap_rho(obs, boot, E.SEED)
        twin = E.bootstrap_rho(E.permuted_twin(obs, E.SEED_TWIN), boot, E.SEED)
        plant_obs = E.pair_observations(by_player_season(simulate(rows, idk, E.PLANT_SD, E.SEED_PLANT), idk, c0))
        plant = E.bootstrap_rho(plant_obs, b_plant, E.SEED)
        null_obs = E.pair_observations(by_player_season(simulate(rows, idk, 0.0, E.SEED_NULL_PLANT), idk, c0))
        null_plant = E.bootstrap_rho(null_obs, b_plant, E.SEED)
        rate_obs = E.pair_observations(bps, rate=True)
        rate = E.bootstrap_rho(rate_obs, boot, E.SEED)
        res[role] = {"rows": len(rows), "pairs": _pair_counts(obs), "real": real, "twin": twin,
                     "plant": plant, "null_plant": null_plant, "secondary_rate": rate}
    adj = E.holm({role: res[role]["real"].get("p") for role in res})
    for role in res:
        r = res[role]
        r["p_holm"] = adj.get(role)
        r["disposition"] = E.disposition(r["real"], r["twin"], r["plant"], r["null_plant"], r["p_holm"])
    return res


def split_half(mlb_rows: list, boot: int = E.BOOT) -> dict:
    out = {}
    for role in ("batter", "catcher"):
        by_p = defaultdict(list)
        for r in mlb_rows:
            if r.get("role") == role and r.get("challenger_id") is not None:
                by_p[int(r["challenger_id"])].append(r)
        obs = []
        for pid, grp in by_p.items():
            grp = sorted(grp, key=lambda r: (str(r.get("official_date") or ""), int(r["game_pk"]),
                                             int(r["at_bat_index"]), int(r.get("event_index") or 0)))
            a = [{"o": r["o"], "v": r["v"], "p": r["p"], "c0": r["c_fail"]} for r in grp[0::2]]
            b = [{"o": r["o"], "v": r["v"], "p": r["p"], "c0": r["c_fail"]} for r in grp[1::2]]
            if len(a) >= E.N_MIN_HALF and len(b) >= E.N_MIN_HALF:
                obs.append((pid, "2026", E.skill(a), E.skill(b)))
        bt = E.bootstrap_rho(obs, boot, E.SEED)
        r = bt.get("rho")
        bt["spearman_brown"] = (2 * r / (1 + r)) if (r is not None and 1 + r > 1e-6) else None
        out[role] = bt
    return out


def run(aaa_path: Path = AAA, ledger_path: Path = X.LEDGER, cv_path: Path = X.COUNT_VALUE,
        plays_path: Path = X.CORPUS_PLAYS, halves: dict | None = None, boot: int = E.BOOT,
        b_plant: int = E.B_PLANT) -> dict:
    cv_doc = json.loads(Path(cv_path).read_text(encoding="utf-8"))
    fr = X.frame(ledger_path, cv_path, plays_path, halves)
    c0 = fr["c0"]
    aaa = aaa_frame(json.loads(Path(aaa_path).read_text(encoding="utf-8")), cv_doc)
    prim = primary(aaa["roles"], c0, boot, b_plant)
    sh = split_half(fr["rows"], boot)
    return {"schema": 1, "version": E.EABS_VERSION, "generated_at": _now(), "registration": E.GATE_DOC,
            "constants": {"n_min": E.N_MIN, "n_min_half": E.N_MIN_HALF, "boot": boot, "b_plant": b_plant,
                          "seed": E.SEED, "seed_twin": E.SEED_TWIN, "seed_plant": E.SEED_PLANT,
                          "seed_null_plant": E.SEED_NULL_PLANT, "plant_sd": E.PLANT_SD, "alpha": E.ALPHA,
                          "z95": E.Z95, "c0": c0, "seasons": list(E.AAA_SEASONS)},
            "aaa_frame": {"rows": aaa["n_rows"], "excluded": aaa["excluded"],
                          "by_role": {k: len(v) for k, v in aaa["roles"].items()}},
            "primary": prim, "secondary_mlb_split_half": sh}


def report(doc: dict) -> str:
    def f(x, d=4):
        return "null" if x is None else f"{x:.{d}f}"
    lines = [f"eABS stability check ({doc['registration']}), constants {json.dumps(doc['constants'])}",
             f"AAA frame: {doc['aaa_frame']}"]
    for role, r in doc["primary"].items():
        re_, tw, pl, nu = r["real"], r["twin"], r["plant"], r["null_plant"]
        lines.append(f"[{role}] rows {r['rows']}, pair observations {re_['n_obs']} ({r['pairs']}), players {re_['n_players']}")
        lines.append(f"[{role}] MDE95 {f(re_.get('mde95'))}")
        lines.append(f"[{role}] rho {f(re_.get('rho'))} lo95 {f(re_.get('lo95'))} p {f(re_.get('p'))} "
                     f"p_holm {f(r.get('p_holm'))}")
        lines.append(f"[{role}] twin rho {f(tw.get('rho'))} lo95 {f(tw.get('lo95'))}; planted rho {f(pl.get('rho'))} "
                     f"lo95 {f(pl.get('lo95'))}; null plant rho {f(nu.get('rho'))} lo95 {f(nu.get('lo95'))}")
        lines.append(f"[{role}] secondary (overturn-rate excess) rho {f(r['secondary_rate'].get('rho'))} "
                     f"lo95 {f(r['secondary_rate'].get('lo95'))}")
        lines.append(f"[{role}] DISPOSITION {r['disposition']}")
    for role, b in doc["secondary_mlb_split_half"].items():
        lines.append(f"[MLB 2026 split-half, {role}] players {b['n_players']} rho {f(b.get('rho'))} "
                     f"lo95 {f(b.get('lo95'))} Spearman-Brown {f(b.get('spearman_brown'))}")
    return "\n".join(lines)


def _fixture(tmp: Path) -> dict:
    """A small ledger pair with null fields, for the dry run."""
    fields = ["game_pk", "season", "level", "game_type", "official_date", "inning", "half", "at_bat_index",
              "event_index", "pitch_number", "source", "kind", "review_type", "challenge_team_id", "challenge_org",
              "challenger_id", "role", "challenge_side", "role_by_side", "batter_id", "pitcher_id", "catcher_id",
              "overturned", "final_call", "original_call", "balls_before", "strikes_before", "outs_before",
              "bases_before", "bat_score_before", "fld_score_before", "count_after_final", "count_after_original",
              "li_pa", "px", "pz", "sz_top", "sz_bot", "flags", "invariant_ok", "invariant_zone_ok"]
    rng = random.Random(7)
    aaa_rows, mlb_rows = [], []
    for season in E.AAA_SEASONS:
        for g in range(60):
            for j in range(6):
                side = "batting" if j % 2 == 0 else "fielding"
                over = rng.random() < 0.5
                oc = "C" if side == "batting" else "B"
                fc = ("B" if oc == "C" else "C") if over else oc
                bat = 100 + rng.randrange(12)
                cat = 200 + rng.randrange(6)
                aaa_rows.append([season * 1000 + g, season, 11, "R", f"{season}-05-01", 1 + j, "top", j, 0, 1,
                                 "event", "zone", "MJ", 1, "AAA", None, "unresolved", side,
                                 "batter" if side == "batting" else "pitcher_or_catcher", bat, 300, cat,
                                 over, fc, oc, rng.randrange(4), rng.randrange(3), rng.randrange(3),
                                 rng.choice(["___", "1__", "_2_", "123"]), rng.randrange(4), rng.randrange(4),
                                 None, None, None, None, None, None, None, None, True, True])
    for g in range(40):
        for j in range(5):
            side = "batting" if j % 2 == 0 else "fielding"
            over = (rng.random() < 0.5) if j < 2 else True
            oc = "C" if side == "batting" else "B"
            fc = ("B" if oc == "C" else "C") if over else oc
            bat = 100 + rng.randrange(8)
            cat = 200 + rng.randrange(4)
            mlb_rows.append([900000 + g, 2026, 1, "R", None, 1 + j, "top" if j < 3 else "bottom", j, 0, 1,
                             "event", "zone", "MJ", 1, "NYY", bat if side == "batting" else cat,
                             "batter" if side == "batting" else "catcher", side,
                             "batter" if side == "batting" else "pitcher_or_catcher", bat, 300, cat,
                             over, fc, oc, rng.randrange(4), rng.randrange(3), rng.randrange(3), "___",
                             None, None, None, None, None, None, None, None, None, None])
    mlb_fields = fields[:-2]
    (tmp / "aaa.json").write_text(json.dumps({"fields": fields, "rows": aaa_rows, "names": {}}), encoding="utf-8")
    (tmp / "mlb.json").write_text(json.dumps({"fields": mlb_fields, "rows": mlb_rows, "names": {}}), encoding="utf-8")
    halves = {900000 + g: [((i, h), (0, 0)) for i in range(1, 10) for h in ("top", "bottom")] for g in range(40)}
    return {"aaa": tmp / "aaa.json", "mlb": tmp / "mlb.json", "halves": halves}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    if a.dry_run:
        with tempfile.TemporaryDirectory() as td:
            fx = _fixture(Path(td))
            doc = run(fx["aaa"], fx["mlb"], X.COUNT_VALUE, halves=fx["halves"], boot=50, b_plant=20)
            print(report(doc))
            print("dry run: the reporting path ran on fixtures with nulls; nothing written")
        return 0
    doc = run()
    print(report(doc))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    os.replace(tmp, OUT)
    print(f"written {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
