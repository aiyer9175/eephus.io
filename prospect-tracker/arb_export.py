# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""The /arbitration/ payloads.

  data/arbitration.json  - the projections board. First paint, so it is capped
                           and carries object rows (a third party will open it).
  data/arb_history.json  - per-season actual vs ours vs Swartz. Lazily fetched
                           on first #history open, so it may be bigger, and it
                           uses flat positional tuples.

CONVENTIONS THAT ARE LOAD-BEARING
  * Dollars are WHOLE INTEGERS rounded to the nearest $1,000. Never 4.2.
  * Service time is a STRING ("5.043"). A float lies about .043 being 43/1000.
  * The five honesty flags are ONE BITFIELD, not five booleans.
  * Both payloads carry a field_key block, because a two-letter key with no
    legend is a private format.
  * data/cba_rules.json and data/contract_options.json are on
    deploy/data_exclude.txt and NEVER reach the webroot, so every CBA fact the
    page shows is baked into the `rules` block here or server-rendered.

THE TWO RESIDUALS ARE NEVER COMBINED. `ou_mkt` is the model residual - what the
arbitration system paid relative to comparable players - and sums to roughly
zero by construction. `ou_war` is salary minus WAR priced at that season's
dollars-per-win, and does not. Averaging a number centred on zero with one that
is not gives neither, so no combined column is emitted and a test asserts the
client never adds them.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

_log = logging.getLogger(__name__)

ROOT = Path(__file__).parent
BOARD_PATH = ROOT / "data" / "arbitration.json"
HISTORY_PATH = ROOT / "data" / "arb_history.json"

BOARD_CAP_BYTES = 220_000
HISTORY_CAP_BYTES = 320_000

# Flag bits, published in field_key and mirrored in the client.
F_SERVICE_EST = 1     # arbitration step did not come from published service time
F_CLASS_EST = 2       # step came from the weakest source (debut heuristic)
F_NO_SALARY = 4       # no salary on file for that season
F_CARRY_FWD = 8       # season is past the 2026-12-01 CBA expiry
F_PRORATED = 16       # 2020, paid at 60/162 of contract

CBA_EXPIRES = "2026-12-01"


def _k(usd) -> int | None:
    """Whole dollars to the nearest thousand."""
    if usd is None:
        return None
    try:
        return int(round(float(usd) / 1000.0) * 1000)
    except (TypeError, ValueError):
        return None


def _flags(row: dict, season: int) -> int:
    f = 0
    src = row.get("arb_year_source")
    if src != "mlbtr_service":
        f |= F_SERVICE_EST
    if src == "debut_heuristic":
        f |= F_CLASS_EST
    if not row.get("salary"):
        f |= F_NO_SALARY
    if season > 2026:
        f |= F_CARRY_FWD
    if season == 2020:
        f |= F_PRORATED
    return f


def _f0(v) -> float:
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _projected_war() -> dict[int, list[float]]:
    """{mlbam: [war per future season]} from the MLB projection board."""
    p = ROOT / "data" / "mlb_projections.json"
    if not p.exists():
        return {}
    try:
        doc = json.loads(p.read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    first = int(doc.get("first_season") or 0)
    out = {}
    for v in doc.get("vets") or []:
        m = v.get("mlbam")
        w = v.get("war")
        if m and isinstance(w, list):
            out[int(m)] = [first, [float(x) if x is not None else 0.0 for x in w]]
    return out


_STEP_RE = None


def _token_step(tok: str):
    """('ARB 2 (S2)') -> (2, True). PRE-ARB -> (0, False)."""
    import re
    global _STEP_RE
    if _STEP_RE is None:
        _STEP_RE = re.compile(r"^ARB\s*([1-4])(\s*\(S2\))?$")
    t = (tok or "").strip().upper()
    if t == "PRE-ARB":
        return 0, False
    m = _STEP_RE.match(t)
    return (int(m.group(1)), bool(m.group(2))) if m else (None, False)


def _number_bare_arb(ladder: list, base: dict) -> list:
    """Give a bare "ARB" rung its arbitration step from the panel label.

    Spotrac's own arbitration estimate pill reads "ARB" with no step, and
    spotrac._resolve_bare_arb numbers it only when the same row carries a
    numbered token (42 players on 2026-10-01 had none, nearly all in their
    final arbitration year with 2028 UFA). The step then comes from the
    player's latest panel season: arbitration step a in that season makes the
    rung a plus the seasons between, carrying the Super Two marker when the
    label says so; no step there makes the first bare rung ARB 1 and each
    later one a step up from the rung before. A step past 4 is held at 4:
    Spotrac says he is still arbitration-eligible that season, and 4 is the
    last step there is. A numbered rung is never touched."""
    if not any(tok == "ARB" for _y, tok in ladder):
        return ladder
    a = base.get("arb_year")
    bs = int(base.get("season") or 0)
    s2 = base.get("super_two") is True
    out = []
    prev = None
    for y, tok in ladder:
        if tok == "ARB":
            if a:
                step = int(a) + (int(y) - bs)
            elif prev:
                step = prev + 1
            else:
                step = 1
            step = max(1, min(4, step))
            tok = f"ARB {step}" + (" (S2)" if s2 else "")
        st, _ = _token_step(tok)
        prev = st if st else prev
        out.append((y, tok))
    return out


def build_board(panel_rows, model_doc, metrics, dpw, *, season: int,
                s1=None, s2=None, defl=None, banded=None) -> dict:
    """The projections board: every player with remaining arbitration years,
    with the ladder PRICED by chaining the model forward.

    The chain is the point. arb-1 is a level prediction; arb-2 then takes that
    PREDICTION as its prior and raises off it; arb-3 raises off arb-2. So a
    later rung inherits the earlier rung's error, which is why the interval has
    to widen down the ladder rather than being a per-year residual quantile
    applied independently.
    """
    import arb_dataset as A
    import arb_model as Mod

    status = A.spotrac_status_by_mlbam()
    proj = _projected_war()
    # Latest observed row per player, for the salary anchor and the features.
    by_player: dict[int, dict] = {}
    # Realized WAR per player-season over the WHOLE panel, not only the scored
    # rows. export() stamps war3/career_war on scored rows alone, and `base`
    # below is usually an unscored pre-arb season, so a forward rung used to
    # read war3 = career_war = 0 through features()' default.
    war_by: dict[int, dict[int, float]] = {}
    for r in sorted(panel_rows, key=lambda x: x["season"]):
        by_player[int(r["mlbam"])] = r
        war_by.setdefault(int(r["mlbam"]), {})[int(r["season"])] = float(r.get("war") or 0.0)
    last_obs = max((int(r["season"]) for r in panel_rows), default=season - 1)
    lm = A.league_min_by_year()

    rows = []
    for mlbam, sby in status.items():
        # REMAINING seasons only (defect RVA01, 2026-10-01). The board prices
        # `season` onward; a status token for a season already played (a
        # 2026 PRE-ARB cell on a club-control table) is history, and pricing
        # it put a completed season's league minimum into `tot` and from there
        # into the Club Ledger's remaining arbitration figure.
        ladder = sorted((y, s) for y, s in sby.items()
                        if int(y) >= int(season)
                        and (s.startswith("ARB") or s == "PRE-ARB"))
        if not ladder:
            continue
        base = by_player.get(mlbam)
        if not base:
            continue
        ladder = _number_bare_arb(ladder, base)
        pw = proj.get(mlbam)
        prior = base.get("salary")
        steps = []
        total = 0
        wars = []
        hist = war_by.get(mlbam, {})
        base_season = int(base["season"])

        def _proj_war(yr: int):
            if pw:
                first, arr = pw
                i = int(yr) - first
                if 0 <= i < len(arr):
                    return arr[i]
            return None

        def _war_at(yr: int) -> float:
            """Realized WAR through the last observed season, projected WAR
            after it, base WAR where no projection exists (the same fallback
            the rung's own `war` uses)."""
            if yr <= last_obs:
                return hist.get(int(yr), 0.0)
            v = _proj_war(yr)
            return float(v) if v is not None else _f0(base.get("war"))

        for y, tok in ladder:
            step, s2flag = _token_step(tok)
            war = _proj_war(y)
            wars.append(round(war, 2) if war is not None else None)
            if step == 0:
                # Pre-arb years are the league minimum by rule, not a prediction.
                usd = lm.get(int(y)) or lm.get(max(lm)) if lm else None
                steps.append([int(y), _k(usd), _k(usd), _k(usd), tok])
                if usd:
                    total += _k(usd) or 0
                    prior = usd
                continue
            row = dict(base)
            row["season"] = int(y)
            row["arb_year"] = step
            row["super_two"] = s2flag
            # A first arbitration trip with no salary on file raises off the
            # prior season's league minimum, which is what a pre-arb player is
            # paid and what the training rows carry (their prior is season-1's
            # salary). None here set has_prior = 0 on every class-1 row.
            if prior is None and step == 1:
                prior = lm.get(int(y) - 1) or (lm.get(max(lm)) if lm else None)
            row["prior_salary"] = prior
            row["war"] = war if war is not None else base.get("war")
            # The forward row is built the way a training row is: war3 is the
            # award season plus the two before it and career_war runs through
            # the award season inclusive, realized WAR where it exists and the
            # projection after it. Age advances with the season.
            row["war3"] = round(sum(_war_at(int(y) - k) for k in (0, 1, 2)), 2)
            row["career_war"] = round(
                sum(v for yr, v in hist.items() if yr <= min(int(y), last_obs))
                + sum(_war_at(yr) for yr in range(last_obs + 1, int(y) + 1)), 2)
            if base.get("age") is not None:
                row["age"] = float(base["age"]) + (int(y) - base_season)
            # Training reads hem/sem/rem from the award season itself, which
            # has not been played. The latest observed season's block is the
            # stated proxy; keying on the future season found nothing and
            # every forward rung defaulted to 100.
            rung_metrics = {int(y): (metrics or {}).get(base_season) or {}}
            row["league_min"] = lm.get(int(y))
            pred = None
            if defl is not None:
                try:
                    # WHICH ESTIMATOR SERVES WHICH STEP IS A GATE RESULT, not a
                    # design preference. GATE A: arb-1 PASSED at 3.25x its
                    # floor, so the model serves it. arb-2-and-later is a NULL -
                    # the model does not beat an empirical step multiplier by
                    # more than the floor - so the multiplier serves those, and
                    # serving the model there would be shipping a more complex
                    # estimator the evidence does not support.
                    if step == 1:
                        d = Mod.predict(row, rung_metrics, defl, s1, None)
                    else:
                        d = Mod.banded_predict(row, banded, defl)
                    pred = d * (defl.get(int(y)) or defl[max(defl)]) if d else None
                except Exception:
                    pred = None
            # No major league salary is below the league minimum, so neither is
            # an award. A rule, like the pre-arb rung, and it binds only on a
            # fringe arb-1 rung whose built features are all below average.
            floor = (lm.get(int(y)) or lm.get(max(lm))) if lm else None
            if pred and floor and pred < floor:
                pred = float(floor)
            if pred:
                # The band widens down the chain: each rung inherits the
                # previous rung's error. 22% at arb-1 growing 8 points a rung
                # is the observed champion MdAPE, and it is DELIBERATELY not
                # published as a calibrated interval - see the eval artifact.
                k = max(0, (step or 1) - 1)
                spread = 0.22 + 0.08 * k
                steps.append([int(y), _k(pred), _k(pred * (1 - spread)),
                              _k(pred * (1 + spread)), tok])
                total += _k(pred) or 0
                prior = pred
            else:
                steps.append([int(y), None, None, None, tok])
        rows.append({
            "m": mlbam,
            "n": base.get("name"),
            "t": base.get("team"),
            "sv": base.get("service_time"),
            # AS OF WHICH SEASON. `base` is the player's LATEST observed panel
            # row, and the MLBTR ledger entry resolves against that row's
            # season, so a player last seen in 2022 carries a 2022 service-time
            # string. Without this field the only external check on the control
            # horizon (GATE C2 clause C9') compares a four-year-old service
            # figure with a 2027 grid and reads 63 of 130 rows as disagreeing
            # when what disagrees is the vintage. Nothing reads either field on
            # a surface; both exist to let a lab say how old its evidence is.
            "svy": base.get("season") if base.get("service_time") else None,
            "c": _token_step(ladder[0][1])[0],
            "e": _flags(base, season),
            "yl": len(ladder),
            "l": steps,
            "tot": total or None,
            "w": wars,
        })
    rows.sort(key=lambda r: -(r.get("tot") or 0))
    carry_from = 2027
    return {
        "model": model_doc.get("model", "arb_award_v1"),
        "generated_at": date.today().isoformat(),
        "season": season,
        "field_key": {
            "m": "MLBAM id", "n": "name", "t": "team",
            "sv": "service time, years.days, as a STRING",
            "svy": "the season that service-time string is as of, or null",
            "c": ("arbitration class at the first remaining ladder season: "
                  "0 pre-arb, 1..4 arbitration year"),
            "e": ("flag bits: 1 step not from published service time, "
                  "2 step from the debut heuristic, 4 no salary on file, "
                  "8 past the CBA expiry, 16 2020 prorated"),
            "yl": "club-control years remaining",
            "l": "ladder, one tuple per remaining season: [season, proj_usd, lo_usd, hi_usd, token]",
            "tot": ("sum of the ladder, usd: projected arbitration rungs plus "
                    "PRE-ARB rungs at the league minimum"),
            "w": "projected WAR (fWAR basis, the training label since the 2026-10 epoch) per remaining season, aligned to l",
        },
        "rules": {
            "regime": "cba_2022",
            "expires": CBA_EXPIRES,
            "carry_forward_from": carry_from,
            "note": (f"Projected seasons from {carry_from} assume the 2022 CBA "
                     "arbitration structure survives unchanged. Not estimated "
                     "from data; no interval covers it."),
        },
        "dpw": dpw,
        "rows": rows,
    }


def build_history(recs, panel_rows, ledger, dpw) -> dict:
    """Per-season actual vs ours vs the MLBTR/Swartz projection."""
    by = {(r["mlbam"], r["season"]): r for r in recs}
    # bbref -> mlbam, from the panel. The ledger keys most entries by Baseball
    # Reference id (that is what the MLBTR hrefs carry) and only the
    # name-resolved pre-2023 rows carry an mlbam, so joining on mlbam alone
    # matched 23 of about 1,400 available projections and made the Swartz
    # comparison look far thinner than it is.
    bref2mlbam = {}
    for r in panel_rows:
        if r.get("bbref"):
            bref2mlbam[str(r["bbref"])] = int(r["mlbam"])
    swartz = {}
    for key, per_year in (ledger or {}).items():
        for cy, ent in per_year.items():
            if ent.get("kind") != "projection" or not ent.get("projected_usd"):
                continue
            m = ent.get("mlbam") or bref2mlbam.get(str(ent.get("bbref_id") or key))
            if m:
                swartz[(int(m), int(cy))] = ent["projected_usd"]

    out = []
    for r in panel_rows:
        rec = by.get((r["mlbam"], r["season"]))
        if not rec or not r.get("salary"):
            continue
        act = _k(r["salary"])
        pred = _k(rec.get("served"))
        swz = _k(swartz.get((int(r["mlbam"]), int(r["season"]))))
        war = r.get("war") or 0.0
        d = dpw.get(str(r["season"])) or dpw.get(r["season"])
        ou_mkt = (act - pred) if (act and pred) else None
        ou_war = (act - int(war * d)) if (act and d) else None
        out.append([
            int(r["season"]), int(r["mlbam"]), r.get("name"), r.get("team"),
            int(r["arb_year"]), act, pred, swz, ou_mkt, ou_war,
            round(float(war), 2), _flags(r, int(r["season"])),
        ])
    out.sort(key=lambda x: (-x[0], -(x[5] or 0)))
    return {
        "model": "arb_award_v1",
        "generated_at": date.today().isoformat(),
        "field_key": {
            "rows": "[season, mlbam, name, team, arb_year, actual_usd, "
                    "ours_usd, swartz_usd, ou_mkt_usd, ou_war_usd, war, flags]",
            "ou_mkt": ("actual minus OUR model: what the arbitration system paid "
                       "relative to comparable players. Sums to roughly zero by "
                       "construction."),
            "ou_war": ("actual minus WAR (fWAR basis) priced at that season's dollars per "
                       "win. Does NOT sum to zero, because arbitration "
                       "systematically pays below the open market."),
            "never_combine": ("The two residuals measure different things and are "
                              "never averaged or summed."),
        },
        "dpw": dpw,
        "seasons": sorted({r[0] for r in out}),
        "rows": out,
    }


def _write(path: Path, doc: dict, cap: int, log) -> int:
    body = json.dumps(doc, separators=(",", ":"))
    n = len(body.encode("utf-8"))
    if n > cap:
        log(f"  arb_export: WARNING {path.name} is {n} bytes, cap {cap}")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(body, encoding="utf-8")
    tmp.replace(path)
    log(f"  arb_export: wrote {path.name} ({n} bytes, {len(doc.get('rows') or [])} rows)")
    return n


def export(*, write: bool = True, log=print) -> dict:
    """Build both payloads. Offline: reads the committed panel inputs only."""
    import arb_dataset as A
    import arb_metrics as M
    import arb_model as Mod

    panel = A.build_panel(log=None)
    rows = panel["rows"]
    sc = A.scored_rows(rows)
    war_by: dict[int, dict[int, float]] = {}
    for r in rows:
        war_by.setdefault(r["mlbam"], {})[r["season"]] = r["war"]
    for r in sc:
        hist = war_by.get(r["mlbam"], {})
        r["war3"] = round(sum(hist.get(r["season"] - k, 0.0) for k in (0, 1, 2)), 2)
        r["career_war"] = round(sum(v for y, v in hist.items()
                                    if y <= r["season"]), 2)
    metrics = M.metric_panel(2018, 2026)
    seasons = sorted({r["season"] for r in sc})
    recs = Mod.forward_chain(sc, metrics, seasons=seasons)

    try:
        import value_framework as vf
        cfg = vf._config()
        dpw = {str(k): int(float(v.get("overall", 0)) * 1e6) if isinstance(v, dict)
               else int(float(v) * 1e6)
               for k, v in (cfg.get("historical_dollars_per_war") or {}).items()}
    except Exception as exc:
        _log.warning("arb_export: dollars-per-win unavailable: %s", exc)
        dpw = {}

    eval_doc = {}
    p = ROOT / "data" / "arbitration_eval.json"
    if p.exists():
        try:
            eval_doc = json.loads(p.read_text("utf-8"))
        except (OSError, ValueError):
            pass

    # The SERVED model is fit on the whole scored pool. The forward-chained
    # folds above are the evidence; this is the estimator they licensed.
    defl = Mod.fit_deflator(sc, base_year=seasons[0])
    s1 = Mod.fit_stage1(sc, metrics, defl)
    s2 = Mod.fit_stage2(sc, metrics, defl)
    banded = Mod.fit_banded_multipliers(sc, defl)
    board = build_board(rows, eval_doc, metrics, dpw, season=2027,
                        s1=s1, s2=s2, defl=defl, banded=banded)
    history = build_history(recs, sc, A.load_ledger(), dpw)
    if write:
        _write(BOARD_PATH, board, BOARD_CAP_BYTES, log)
        _write(HISTORY_PATH, history, HISTORY_CAP_BYTES, log)
    return {"board": board, "history": history}


if __name__ == "__main__":
    export()
