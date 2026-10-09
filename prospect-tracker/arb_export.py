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
  data/arb_prospect_rungs.json - the board's fitted chain (stage1 coefficients,
                           banded raise multipliers, deflator) plus a platform
                           profile, for the prospect surplus engine
                           (value_framework.arb_rung_usd). No page fetches it.

CONVENTIONS THAT ARE LOAD-BEARING
  * Dollars are WHOLE INTEGERS rounded to the nearest $1,000. Never 4.2.
  * Service time is a STRING ("5.043"). A float lies about .043 being 43/1000.
  * The six honesty flags are ONE BITFIELD, not six booleans.
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
PROSPECT_RUNGS_PATH = ROOT / "data" / "arb_prospect_rungs.json"

BOARD_CAP_BYTES = 220_000
HISTORY_CAP_BYTES = 320_000

# Flag bits, published in field_key and mirrored in the client.
F_SERVICE_EST = 1     # arbitration step did not come from published service time
F_CLASS_EST = 2       # step came from the weakest source (debut heuristic)
F_NO_SALARY = 4       # no salary on file for that season
F_CARRY_FWD = 8       # season is past the 2026-12-01 CBA expiry
F_PRORATED = 16       # 2020, paid at 60/162 of contract
F_ORDER_FIX = 32      # a Spotrac status ran against service order and was repaired
F_CBA_FLOOR = 64      # an arbitration rung floored at 80% of a signed salary before it

#: CBA Article VI: an arbitration award may not cut the prior salary by more
#: than 20 percent. The projections path applies the same constant.
MAX_CUT = 0.80

CBA_EXPIRES = "2026-12-01"

# --------------------------------------------------------------------------
# Club arbitration process (owner ask 3, 2026-09-30; Part 8 lane
# finance_to_fa_arb, Leg C, plan rows FAA-4 and FAA-9). DESCRIPTIVE: per club,
# over the captured MLB Trade Rumors trackers, how many arbitration cases it
# had, how many went to an exchange of figures, and how many to a hearing,
# credited to the club under whose heading the tracker lists the player on
# exchange day (never arb_history's season-end club). Every chip carries its n
# and its window; no chip takes a colour; a label prints only when the data
# carry it. The point award never reads any of it (docs/ARBITRATION_GATE.md
# sections 4 and 13c; the banned-key test in test_arb_export.py walks
# CLUB_PROCESS_KEYS). Behind this flag: off, arbitration.json is byte-identical
# to the build without it and the block goes to CLUB_PROCESS_PREVIEW only.
# --------------------------------------------------------------------------
ARB_CLUB_PROCESS_CHIPS = False
LAB_LEDGER_PATH = ROOT / "data" / "_labs" / "arb_ledger.json"
CLUB_PROCESS_PREVIEW = ROOT / ".cache" / "arb_club_process" / "preview" / "club_process.json"
#: The two labels and their floors, as docs/ARBITRATION_GATE.md 13b fixes them.
FILE_AND_TRIAL = "File and trial"
SETTLES_BEFORE = "Settles before the exchange"
FILE_AND_TRIAL_MIN_EXCHANGED = 2
SETTLES_BEFORE_MIN_CASES = 10
CLUB_PROCESS_COPY = ("Process record from the MLB Trade Rumors arbitration trackers, credited to the "
                     "club that held the player on exchange day. Descriptive; it changes no projected award.")
#: Tracker classes that count as figures exchanged on exchange day.
EXCHANGED_CLASSES = ("exchanged", "hearing_won", "hearing_lost")
#: A later capture that reads one of these on an exchanged case: it settled.
SETTLED_CLASSES = ("agreed", "extension", "split_deal", "club_option")
#: Every key the club-process block serves, plus the 13e term's name. None of
#: them may reach arb_model.CHAMPION_KEYS or the keys arb_model.features()
#: accepts (test_arb_export.py).
CLUB_PROCESS_KEYS = ("club_process", "cases", "exchanged", "exchanged_share", "settled_after",
                     "unresolved", "hearings", "club_won", "player_won", "label", "chips",
                     "club_file_and_trial", "file_and_trial", "settles_before_exchange")


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


def _signed_salaries() -> dict[int, dict[int, int]]:
    """{mlbam: {season: usd}} for every season a signed Spotrac contract
    prices: arb_dataset.spotrac_salary_by_mlbam, the same team pages and the
    same id map the board's status tokens come from.

    The board's own chain raises off the panel's salary, which knows nothing
    of a contract the club has already signed for the next season, so the
    projections path floored those rungs and the board did not (owner answer
    M11-2). Measured 2026-10-08: on all 880 board players these seasons equal
    the contract seasons the projections payload prices for 2027-2031. The
    board still reads nothing that path writes."""
    import arb_dataset as A
    try:
        return A.spotrac_salary_by_mlbam()
    except Exception as exc:                      # pragma: no cover - defensive
        _log.warning("arb_export: signed salaries unavailable: %s", exc)
        return {}


def _apply_max_cut_after_contract(steps: list, signed: dict, season: int) -> int:
    """Floor arbitration rungs at 80% of a signed salary the season before,
    in place; returns the number of rungs floored.

    The same walk as the projections path's Article VI block, so the board
    and that path print the same figure: a contracted season sets the prior
    and opens the carry, an ARB rung below 0.80 x prior is raised to it and
    the floored figure is the next rung's prior, a PRE-ARB rung closes the
    carry. Later rungs are NOT re-predicted off the floored figure; they are
    only held to the same floor, as on the path. A rung on a season the
    contract itself prices is left as published (the path prices that season
    from the contract)."""
    if not signed:
        return 0
    prior = signed.get(int(season) - 1)
    carry = prior is not None
    by = {int(st[0]): st for st in steps}
    floored = 0
    for y in sorted(set(by) | {s for s in signed if s >= int(season)}):
        if y in signed:
            carry, prior = True, signed[y]
            continue
        st = by[y]
        if st[1] is None:
            continue
        if str(st[4] or "").upper().startswith("ARB"):
            if carry and prior:
                fl = _k(MAX_CUT * float(prior))
                if fl and st[1] < fl:
                    st[1] = fl
                    st[2] = fl if (st[2] or 0) < fl else st[2]
                    st[3] = max(int(st[3] or fl), fl)
                    floored += 1
        else:
            carry = False
        prior = st[1]
    return floored


def _link_targets() -> dict[int, str]:
    """{mlbam: link token} from data/player_links.json, so the page links each
    name without fetching that 1.9 MB map itself (QCLP04, 2026-10-02).

    The token is "p:<key>" for a player with a /projections/ page and
    "x:<slug>" for one with only a PROSPX card, the rule assets/arbitration.js
    applied to the map before: a row's `proj` flag when it carries one, else
    the presence of a key. A player with neither gets no token."""
    p = ROOT / "data" / "player_links.json"
    try:
        by = (json.loads(p.read_text("utf-8")).get("byMlbam") or {})
    except (OSError, ValueError) as exc:
        _log.warning("arb_export: player_links unreadable: %s", exc)
        return {}
    out: dict[int, str] = {}
    for m, e in by.items():
        e = e or {}
        proj = bool(e.get("key")) if e.get("proj") is None else bool(e.get("proj"))
        try:
            mid = int(m)
        except (TypeError, ValueError):
            continue
        if proj and e.get("key"):
            out[mid] = "p:" + str(e["key"])
        elif e.get("prospx"):
            out[mid] = "x:" + str(e["prospx"])
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


def _class_falls(ladder: list) -> bool:
    """True when the arbitration class drops from one rung to a later one.
    Service time only accrues, so a later season can never sit in a lower
    class than an earlier one."""
    top = None
    for _y, tok in ladder:
        st, _ = _token_step(tok)
        if st is None:
            continue
        if top is not None and st < top:
            return True
        top = st if top is None else max(top, st)
    return False


def _repair_status_order(raw: list, ladder: list, base: dict) -> tuple[list, bool]:
    """Repair a ladder whose arbitration class falls (POSTEPOCH_8, 2026-10-07).

    The one case on disk: Blas Castano (680604, COL) after the 2026-10 Spotrac
    refetch. His contract-table row carries a 2027 arbitration estimate pill
    ("$1,000,000", "ARB", no step) and a 2028 PRE-ARB pill, under a header that
    reads 2027 to 2031, so the parser maps both cells to the right season and
    the contradiction is Spotrac's own. _number_bare_arb then numbered the bare
    rung ARB 1, and the board priced an arb-1 award ahead of a league-minimum
    season. The repair the evidence supports: when the latest panel row shows
    no arbitration-eligible service (no arbitration step, no Super Two), the
    later PRE-ARB is believed and every earlier rung Spotrac left as a bare
    "ARB" becomes PRE-ARB. A numbered Spotrac rung is never rewritten. Returns
    (ladder, repaired); a conflict this rule cannot settle is left as served
    and logged, so the ladder-order test names it."""
    if not _class_falls(ladder):
        return ladder, False
    eligible = bool(base.get("arb_year")) or base.get("super_two") is True
    last_pre = max((i for i, (_y, tok) in enumerate(ladder) if tok == "PRE-ARB"),
                   default=None)
    if not eligible and last_pre is not None:
        out = [(y, "PRE-ARB") if i < last_pre and raw[i][1] == "ARB" else (y, tok)
               for i, (y, tok) in enumerate(ladder)]
        if not _class_falls(out):
            return out, True
    _log.warning("arb_export: status order falls for %s and no rule repairs it: %s",
                 base.get("mlbam"), ladder)
    return ladder, False


def build_board(panel_rows, model_doc, metrics, dpw, *, season: int,
                s1=None, s2=None, defl=None, banded=None,
                frame: str | None = None, signed=None) -> dict:
    """The projections board: every player with remaining arbitration years,
    with the ladder PRICED by chaining the model forward.

    The chain is the point. arb-1 is a level prediction; arb-2 then takes that
    PREDICTION as its prior and raises off it; arb-3 raises off arb-2. So a
    later rung inherits the earlier rung's error, which is why the interval has
    to widen down the ladder rather than being a per-year residual quantile
    applied independently.

    `frame` is arb_model's feature frame (docs/ARBITRATION_GATE.md section
    15); it must be the frame `s1` was fit on.
    """
    import arb_dataset as A
    import arb_model as Mod

    frame = frame or Mod.FRAME
    status = A.spotrac_status_by_mlbam()
    signed = _signed_salaries() if signed is None else signed
    proj = _projected_war()
    links = _link_targets()
    # Latest observed row per player, for the salary anchor and the features.
    by_player: dict[int, dict] = {}
    # Realized WAR per player-season over the WHOLE panel, not only the scored
    # rows. export() stamps war3/career_war on scored rows alone, and `base`
    # below is usually an unscored pre-arb season, so a forward rung used to
    # read war3 = career_war = 0 through features()' default.
    war_by: dict[int, dict[int, float]] = {}
    # Every observed panel row, for the platform season's PA, outs and starts.
    obs_by: dict[int, dict[int, dict]] = {}
    for r in sorted(panel_rows, key=lambda x: x["season"]):
        by_player[int(r["mlbam"])] = r
        war_by.setdefault(int(r["mlbam"]), {})[int(r["season"])] = float(r.get("war") or 0.0)
        obs_by.setdefault(int(r["mlbam"]), {})[int(r["season"])] = r
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
        raw_ladder = ladder
        ladder = _number_bare_arb(ladder, base)
        # Ladder-order guard: the arbitration class may not fall along the
        # ladder, because service time only accrues.
        ladder, order_fixed = _repair_status_order(raw_ladder, ladder, base)
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
            # The forward row is built the way a training row is, on the
            # model's own frame. Platform frame (section 15): production is
            # season y - 1's, realized where it has been played and projected
            # after it, with the latest observed season's PA, outs and starts
            # as the stated proxy past it. Award frame (the 2026-08-09
            # hindcast): production is season y's. war3 is three seasons
            # ending at that season and career_war runs through it. Age
            # advances with the season on both.
            last = int(y) - 1 if frame == "platform" else int(y)
            if frame == "platform":
                row["war"] = round(_war_at(last), 2)
                src = (obs_by.get(mlbam) or {}).get(last) if last <= last_obs else base
                for fk in ("pa", "ipouts", "gs"):
                    row[fk] = int((src or {}).get(fk) or 0)
            else:
                row["war"] = war if war is not None else base.get("war")
            row["war3"] = round(sum(_war_at(last - k) for k in (0, 1, 2)), 2)
            row["career_war"] = round(
                sum(v for yr, v in hist.items() if yr <= min(last, last_obs))
                + sum(_war_at(yr) for yr in range(last_obs + 1, last + 1)), 2)
            if base.get("age") is not None:
                row["age"] = float(base["age"]) + (int(y) - base_season)
            # hem/sem/rem: the frame's season where it has been observed,
            # else the latest observed season, the stated proxy (keying on an
            # unplayed season found nothing and defaulted every rung to 100).
            met_season = (last if (metrics or {}).get(last, {}).get(mlbam)
                          else base_season)
            row.pop("metrics_season", None)
            rung_metrics = {int(y): (metrics or {}).get(met_season) or {}}
            row["league_min"] = lm.get(int(y))
            pred = None
            if defl is not None:
                try:
                    # WHICH ESTIMATOR SERVES WHICH STEP IS A GATE RESULT, not a
                    # design preference (data/arbitration_eval.json results).
                    # arb-1 PASSED, so the model serves it. arb-2-and-later
                    # serves the banded step multiplier: a NULL on the
                    # 2026-08-09 frame, and docs/ARBITRATION_GATE.md section
                    # 15d keeps it serving after the platform re-run, because
                    # switching the served estimator there is its own change.
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
                # The low end never sits below the league minimum, the same
                # rule as the point (owner answer M12-4): a band that admits
                # an award no club may pay is not a range of awards.
                lo = pred * (1 - spread)
                if floor and lo < floor:
                    lo = float(floor)
                steps.append([int(y), _k(pred), _k(lo),
                              _k(pred * (1 + spread)), tok])
                total += _k(pred) or 0
                prior = pred
            else:
                steps.append([int(y), None, None, None, tok])
        n_floor = _apply_max_cut_after_contract(steps, signed.get(mlbam), season)
        if n_floor:
            total = sum(st[1] or 0 for st in steps)
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
            "e": (_flags(base, season) | (F_ORDER_FIX if order_fixed else 0)
                  | (F_CBA_FLOOR if n_floor else 0)),
            "yl": len(ladder),
            "l": steps,
            "tot": total or None,
            "w": wars,
            "h": links.get(mlbam),
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
                  "8 past the CBA expiry, 16 2020 prorated, "
                  "32 status order repaired (a Spotrac status that put a "
                  "later season in a lower arbitration class was rewritten), "
                  "64 an arbitration rung floored at 80% of the signed salary "
                  "the season before (CBA maximum cut)"),
            "yl": "club-control years remaining",
            "l": "ladder, one tuple per remaining season: [season, proj_usd, lo_usd, hi_usd, token]",
            "tot": ("sum of the ladder, usd: projected arbitration rungs plus "
                    "PRE-ARB rungs at the league minimum"),
            "w": "projected WAR (fWAR basis, the training label since the 2026-10 epoch) per remaining season, aligned to l",
            "h": ("link token for the name: p:<key> opens /projections/#player=<key>, "
                  "x:<slug> opens /prospx/#player=<slug>, null links nothing"),
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


# --------------------------------------------------------------------------- #
# The prospect rung model (owner answer 2026-09-25 'more' batch 11, OD-4
# 2026-09-30; docs/ARBITRATION_GATE.md section 20)
# --------------------------------------------------------------------------- #
#: Platform-WAR bin edges for the prospect profile, and the fewest arb-1
#: training rows a bin may hold before it merges into the bin below it.
PROFILE_WAR_EDGES = (0.5, 1.5, 2.5, 3.5)
PROFILE_MIN_ROWS = 8


def _row_role(row: dict) -> str:
    """The role arb_model.features reads off a row: a pitcher has outs and
    under 50 PA, a reliever is a pitcher with fewer than 5 starts."""
    pa = _f0(row.get("pa"))
    ipouts = _f0(row.get("ipouts"))
    gs = _f0(row.get("gs"))
    if ipouts > 0 and pa < 50:
        return "rp" if gs < 5 else "sp"
    return "hit"


def _median(vals: list[float]) -> float:
    s = sorted(vals)
    n = len(s)
    return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])


def build_prospect_rungs(fr, metrics, defl, s1, banded, *, frame: str) -> dict:
    """The coefficients the board priced its rungs with, for the prospect
    engine (value_framework.arb_rung_usd), plus the one input a prospect lacks:
    a platform season's playing time and skill indices. That `profile` is the
    median arb-1 training row of each role in each platform-WAR bin, with a
    bin of fewer than PROFILE_MIN_ROWS rows merged into the bin below it, and
    metrics imputed at 100 where the panel has none, as features() does."""
    import arb_model as Mod

    a1 = [r for r in fr if int(r.get("arb_year") or 0) == 1 and r.get("salary")]
    profile = {}
    for role in ("hit", "sp", "rp"):
        rows = [r for r in a1 if _row_role(r) == role]
        edges = (float("-inf"),) + PROFILE_WAR_EDGES + (float("inf"),)
        bins = [[r for r in rows if edges[i] <= _f0(r.get("war")) < edges[i + 1]]
                for i in range(len(edges) - 1)]
        merged: list[list] = []
        for b in bins:
            if merged and len(b) < PROFILE_MIN_ROWS:
                merged[-1] = merged[-1] + b
            elif b or not merged:
                merged.append(list(b))
        # A thin FIRST bin merges upward instead.
        while len(merged) > 1 and len(merged[0]) < PROFILE_MIN_ROWS:
            merged[1] = merged[0] + merged[1]
            merged.pop(0)
        merged = [b for b in merged if b]
        prof = {"war": [], "n": [], "pa": [], "ipouts": [], "gs": [],
                "hem": [], "sem": [], "rem": []}
        for b in merged:
            mx = [Mod._mx(metrics, r) or {} for r in b]
            prof["war"].append(round(_median([_f0(r.get("war")) for r in b]), 4))
            prof["n"].append(len(b))
            for k in ("pa", "ipouts", "gs"):
                prof[k].append(_median([_f0(r.get(k)) for r in b]))
            for k in ("hem", "sem", "rem"):
                prof[k].append(_median([Mod._f(m.get(k), 100.0) for m in mx]))
        profile[role] = prof
    mu, sd, ww, b = s1["m"]
    return {
        "model": "arb_award_v1",
        "generated_at": date.today().isoformat(),
        "produced_by": "arb_export.build_prospect_rungs",
        "frame": frame,
        "purpose": ("The /arbitration/ board's own fitted chain, for the prospect "
                    "surplus engine (value_framework.arb_rung_usd): ARB 1 through "
                    "stage1 from a league-minimum prior, ARB 2+ through the banded "
                    "raise multiplier, every rung at the deflator's last level."),
        "stage1": {"keys": list(s1["keys"]),
                   "mu": [float(v) for v in mu], "sd": [float(v) for v in sd],
                   "w": [float(v) for v in ww], "b": float(b),
                   "smear": float(s1["smear"])},
        "banded": {"bands_usd": [[lo, None if hi == float("inf") else hi]
                                 for lo, hi in Mod.SALARY_BANDS],
                   "cells": [[int(k[0]), int(k[1]), float(v)]
                             for k, v in sorted(banded["cells"].items())],
                   "by_band": [[int(k), float(v)] for k, v in sorted(banded["by_band"].items())],
                   "fallback": 1.4, "max_cut": MAX_CUT},
        "deflator": {str(k): float(v) for k, v in sorted(defl.items())},
        "profile": profile,
        "profile_rule": {"war_edges": list(PROFILE_WAR_EDGES), "min_rows": PROFILE_MIN_ROWS,
                         "statistic": "median of the arb-1 training rows (platform frame)",
                         "interpolation": "linear in platform WAR between bin medians, clamped"},
        "age_arb1_median": _median([_f0(r.get("age")) for r in a1 if r.get("age") is not None]),
        "n_train_arb1": len(a1),
    }


def build_history(recs, panel_rows, ledger, dpw, projections=None) -> dict:
    """Per-season actual vs ours vs the MLBTR/Swartz projection.

    The MLBTR column reads the REPAIRED pool (docs/ARBITRATION_GATE.md
    section 16): every projection entry, joined on its MLBAM id or the
    panel's Baseball Reference id. Through load_ledger the arbitration
    tracker post overwrote the projection for nearly every settled 2024-2026
    player, and the column was filled on 18, 16 and 17 rows for those years
    against 236 for 2023. `ledger` is no longer read; `projections` lets a
    test pass entries in."""
    import arb_dataset as A
    by = {(r["mlbam"], r["season"]): r for r in recs}
    swartz, _census = A.swartz_by_mlbam(panel_rows, pool="repaired",
                                        projections=projections)

    links = _link_targets()
    out = []
    for r in panel_rows:
        rec = by.get((r["mlbam"], r["season"]))
        if not rec or not r.get("salary"):
            continue
        act = _k(r["salary"])
        # NOMINAL DOLLARS, like Actual and MLBTR (owner answer M11-4). The
        # fold scores in deflated dollars; each prediction is re-inflated by
        # its own fold's deflator level for that season, salary / actual,
        # the same factor that deflated the actual it is compared with.
        # Printing the deflated figure put every 2024-2026 Ours on a 2022
        # dollar basis beside a nominal Actual, and vs Market inherited it.
        served = rec.get("served")
        if served and rec.get("actual") and rec.get("salary"):
            served = served * float(rec["salary"]) / float(rec["actual"])
        pred = _k(served)
        swz = _k(swartz.get((int(r["mlbam"]), int(r["season"]))))
        war = r.get("war") or 0.0
        d = dpw.get(str(r["season"])) or dpw.get(r["season"])
        ou_mkt = (act - pred) if (act and pred) else None
        ou_war = (act - int(war * d)) if (act and d) else None
        out.append([
            int(r["season"]), int(r["mlbam"]), r.get("name"), r.get("team"),
            int(r["arb_year"]), act, pred, swz, ou_mkt, ou_war,
            round(float(war), 2), _flags(r, int(r["season"])),
            links.get(int(r["mlbam"])),
        ])
    out.sort(key=lambda x: (-x[0], -(x[5] or 0)))
    return {
        "model": "arb_award_v1",
        "generated_at": date.today().isoformat(),
        "field_key": {
            "rows": "[season, mlbam, name, team, arb_year, actual_usd, "
                    "ours_usd, swartz_usd, ou_mkt_usd, ou_war_usd, war, flags, "
                    "link]",
            "ours": ("this model's forward-chained prediction in NOMINAL "
                     "dollars, re-inflated by the deflator its own fold "
                     "fitted on earlier seasons"),
            "link": ("the name's link token, as the board's h: p:<key> opens "
                     "/projections/#player=<key>, x:<slug> opens "
                     "/prospx/#player=<slug>, null links nothing"),
            "ou_mkt": ("vs market: actual minus this model; what arbitration paid "
                       "against comparables. Sums to roughly zero by "
                       "construction."),
            "ou_war": ("actual minus WAR (fWAR basis) priced at that season's dollars per "
                       "win. Does not sum to zero, because arbitration "
                       "systematically pays below the open market."),
            "never_combine": ("The two residuals measure different things and are "
                              "never averaged or summed."),
        },
        "dpw": dpw,
        "seasons": sorted({r[0] for r in out}),
        "rows": out,
    }


# --------------------------------------------------------------------------- #
# Club arbitration process (FAA-4) and the cases that changed clubs (FAA-9)
# --------------------------------------------------------------------------- #

def _lab_ledger(path: Path | None = None) -> dict:
    """data/_labs/arb_ledger.json (tools/ingest_arbitration_ledger.py), or {}."""
    try:
        return json.loads(Path(path or LAB_LEDGER_PATH).read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def _tracker_rows(ledger: dict) -> list:
    return [e for e in ledger.get("entries") or []
            if e.get("kind") == "tracker" and e.get("club") and e.get("class_year")]


def case_state(e: dict) -> str | None:
    """What one tracker row says about its exchange. None: no figures were
    exchanged on exchange day. Otherwise 'club_won' or 'player_won' when a
    hearing line fires on any capture, 'settled_after' when a later capture
    reads a settlement, and 'unresolved' when no capture says how it ended
    (MLB Trade Rumors does not write hearing results into the trackers)."""
    if e.get("outcome") not in EXCHANGED_CLASSES:
        return None
    result = (e.get("hearing") or {}).get("result")
    if result in ("club_won", "player_won"):
        return result
    if (e.get("recaptured") or {}).get("outcome") in SETTLED_CLASSES:
        return "settled_after"
    return "unresolved"


def club_process_label(cases: int, exchanged: int, settled_after: int, unresolved: int) -> str | None:
    """The label rule docs/ARBITRATION_GATE.md 13b fixes, one function for the
    chips and for any later 13b or 13e count. File and trial needs every
    exchanged case's ending on file, because an unresolved case may have
    settled after the exchange; with none on file the label is withheld."""
    if exchanged >= FILE_AND_TRIAL_MIN_EXCHANGED and unresolved == 0 and settled_after == 0:
        return FILE_AND_TRIAL
    if exchanged == 0 and cases >= SETTLES_BEFORE_MIN_CASES:
        return SETTLES_BEFORE
    return None


def club_chips(t: dict, window: str) -> list:
    """[key, n, text] per chip. Every text states its n and the window; the
    label chip exists only when club_process_label returns one."""
    n, x, u = t["cases"], t["exchanged"], t["unresolved"]
    cw, pw = t["club_won"], t["player_won"]
    h = cw + pw
    share = f", {round(100 * x / n)}%" if n else ""
    out = [["cases", n, f"Cases {n} ({window})"],
           ["exchanged", x, f"Exchanged {x} of {n}{share} ({window})"]]
    if x == 0:
        out.append(["hearings", 0, f"Hearings 0 ({window})"])
    elif u == 0:
        out.append(["hearings", h, f"Hearings {h}, club won {cw}, lost {pw} ({window})"])
    elif h:
        out.append(["hearings", h, f"Hearings {h} on file, club won {cw}, lost {pw}; "
                                   f"no result captured for {u} of {x} exchanged ({window})"])
    else:
        out.append(["hearings", u, f"Hearings: no result captured for {u} of {x} exchanged ({window})"])
    label = club_process_label(n, x, t["settled_after"], u)
    if label == FILE_AND_TRIAL:
        out.append(["label", x, f"{label}: {x} exchanged, {h} to a hearing ({window})"])
    elif label == SETTLES_BEFORE:
        out.append(["label", n, f"{label}: 0 of {n} exchanged ({window})"])
    return out


def build_club_process(ledger: dict | None = None, *, before: int | None = None) -> dict | None:
    """The per-club process block over the captured tracker winters (strictly
    before `before` when given, the 13b form). None when no tracker row exists.
    Credited to the tracker heading's club, canonicalized."""
    from trades import canonical_org

    led = _lab_ledger() if ledger is None else ledger
    rows = [e for e in _tracker_rows(led) if before is None or int(e["class_year"]) < int(before)]
    if not rows:
        return None
    years = sorted({int(e["class_year"]) for e in rows})
    window = f"{years[0]}-{years[-1]}" if len(years) > 1 else str(years[0])
    by: dict = {}
    for e in rows:
        c = canonical_org(e["club"]) or e["club"]
        t = by.setdefault(c, {"cases": 0, "exchanged": 0, "settled_after": 0, "unresolved": 0,
                              "club_won": 0, "player_won": 0})
        t["cases"] += 1
        st = case_state(e)
        if st is not None:
            t["exchanged"] += 1
            t[st] += 1
    clubs = {}
    for c in sorted(by):
        t = by[c]
        clubs[c] = {
            "cases": t["cases"], "exchanged": t["exchanged"],
            "exchanged_share": round(t["exchanged"] / t["cases"], 3) if t["cases"] else None,
            "settled_after": t["settled_after"], "unresolved": t["unresolved"],
            "hearings": t["club_won"] + t["player_won"],
            "club_won": t["club_won"], "player_won": t["player_won"],
            "label": club_process_label(t["cases"], t["exchanged"], t["settled_after"], t["unresolved"]),
            "chips": club_chips(t, window),
        }
    tot = {k: sum(v[k] for v in clubs.values())
           for k in ("cases", "exchanged", "settled_after", "unresolved", "hearings")}
    return {
        "source": "MLB Trade Rumors arbitration trackers",
        "window": window, "seasons": years,
        "attribution": "the club heading the tracker lists the player under on exchange day",
        "recaptures": sorted((led.get("recaptures") or {}).keys()),
        "copy": CLUB_PROCESS_COPY,
        "labels": {
            FILE_AND_TRIAL: (f"exchanged >= {FILE_AND_TRIAL_MIN_EXCHANGED} and settled after the exchange "
                             "= 0, with every exchanged case's ending on file"),
            SETTLES_BEFORE: f"exchanged = 0 on at least {SETTLES_BEFORE_MIN_CASES} cases",
        },
        "totals": tot,
        "field_key": {
            "cases": "tracker rows listed under the club, every class",
            "exchanged": "rows whose exchange-day class is an exchange of figures",
            "settled_after": "exchanged rows a later capture reads as settled",
            "unresolved": "exchanged rows no capture says the ending of",
            "hearings": "exchanged rows a hearing line reads, club_won + player_won",
            "chips": "[key, n, text]; every text states its n and the window",
            "label": "File and trial, Settles before the exchange, or null",
        },
        "clubs": clubs,
    }


def _name_key(s) -> str:
    import re
    import unicodedata
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b\.?", "", s)
    return re.sub(r"[^a-z]", "", s)


def _amount_agrees(e: dict, actual) -> bool | None:
    """Does the tracker row's figure agree with the season's salary? None when
    the row carries neither a settled figure nor both filed figures."""
    if not actual:
        return None
    a = float(actual)
    s = e.get("settled_usd")
    if s:
        return abs(float(s) - a) <= max(50_000.0, 0.02 * a)
    f = e.get("filing") or {}
    if f.get("player_usd") and f.get("club_usd"):
        lo, hi = sorted((float(f["club_usd"]), float(f["player_usd"])))
        return lo - 50_000 <= a <= hi + 50_000
    return None


def traded_cases(history_rows, ledger: dict | None = None) -> dict:
    """FAA-9: arb_history credits an award to the club of the award season's
    last stint; the tracker credits the case to the club that held the player
    on exchange day. A row is named here when the two differ. The join is
    (season, MLBAM id) where the tracker row carries one, else (season, name)
    with exactly one candidate; a name join must also agree on the figure
    (settled within 2% or $50K, or inside the filed pair), so a namesake on
    another club is never named. `history_rows` are arb_history tuples."""
    from trades import canonical_org

    led = _lab_ledger() if ledger is None else ledger
    rows = _tracker_rows(led)
    years = sorted({int(e["class_year"]) for e in rows})
    by_id: dict = {}
    by_name: dict = {}
    for e in rows:
        y = int(e["class_year"])
        if e.get("mlbam"):
            by_id.setdefault((y, int(e["mlbam"])), []).append(e)
        by_name.setdefault((y, _name_key(e.get("player_name"))), []).append(e)
    out = []
    census = {"in_window": 0, "joined": 0, "not_joined": 0, "moved": 0, "moved_unconfirmed": 0}
    for r in history_rows or []:
        season, mlbam, name, team, actual = int(r[0]), r[1], r[2], r[3], r[5]
        if season not in years:
            continue
        census["in_window"] += 1
        ids = by_id.get((season, int(mlbam))) if mlbam is not None else None
        if ids and len(ids) == 1:
            e, confirmed = ids[0], True
        else:
            cands = [c for c in by_name.get((season, _name_key(name))) or []
                     if _amount_agrees(c, actual) is not False]
            if len(cands) != 1:
                census["not_joined"] += 1
                continue
            e = cands[0]
            confirmed = _amount_agrees(e, actual) is True
        census["joined"] += 1
        ex, end = canonical_org(e["club"]) or e["club"], canonical_org(team) or team
        if ex == end:
            continue
        if not confirmed:
            census["moved_unconfirmed"] += 1
            continue
        census["moved"] += 1
        out.append([season, int(mlbam) if mlbam is not None else None, name, ex, end, actual])
    out.sort(key=lambda x: (-x[0], -(x[5] or 0), x[2] or ""))
    return {"window": f"{years[0]}-{years[-1]}" if years else None, "seasons": years,
            "field_key": "[season, mlbam, name, exchange_day_club, season_end_club, actual_usd]",
            "rows": out, "census": census}


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


def export(*, write: bool = True, log=print, frame: str | None = None) -> dict:
    """Build both payloads. Offline: reads the committed panel inputs only.

    `frame` defaults to arb_model.FRAME (the platform season since the
    docs/ARBITRATION_GATE.md section 15 amendment); "award" rebuilds the
    2026-08-09 frame for comparison and is never written by the pipeline."""
    import arb_dataset as A
    import arb_metrics as M
    import arb_model as Mod

    panel = A.build_panel(log=None)
    rows = panel["rows"]
    frame = frame or Mod.FRAME
    # `sc` keeps each row's own season WAR for the History's WAR and vs Value
    # columns; the model reads the framed copies.
    sc = A.scored_rows(rows)
    fr = Mod.attach_frame(sc, rows, frame)
    metrics = M.metric_panel(2018, 2026)
    seasons = sorted({r["season"] for r in sc})
    recs = Mod.forward_chain(fr, metrics, seasons=seasons)

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
    defl = Mod.fit_deflator(fr, base_year=seasons[0])
    s1 = Mod.fit_stage1(fr, metrics, defl)
    s2 = Mod.fit_stage2(fr, metrics, defl)
    banded = Mod.fit_banded_multipliers(fr, defl)
    board = build_board(rows, eval_doc, metrics, dpw, season=2027,
                        s1=s1, s2=s2, defl=defl, banded=banded, frame=frame)
    history = build_history(recs, sc, None, dpw)
    process = attach_club_process(board)
    rungs = build_prospect_rungs(fr, metrics, defl, s1, banded, frame=frame)
    if write:
        _write(BOARD_PATH, board, BOARD_CAP_BYTES, log)
        _write(HISTORY_PATH, history, HISTORY_CAP_BYTES, log)
        _write_rungs(rungs, log)
        if process is not None and not ARB_CLUB_PROCESS_CHIPS:
            write_club_process_preview(process, log)
    return {"board": board, "history": history, "prospect_rungs": rungs}


def _write_rungs(doc: dict, log) -> None:
    """The prospect rung model, indented so a coefficient change reads as a
    line diff. Resolved at call time through PROSPECT_RUNGS_PATH."""
    path = Path(PROSPECT_RUNGS_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=1) + chr(10), encoding="utf-8")
    tmp.replace(path)
    log(f"  arb_export: wrote {path.name} ({doc['n_train_arb1']} arb-1 training rows)")


def attach_club_process(board: dict, ledger: dict | None = None, *, live: bool | None = None) -> dict | None:
    """Build the club-process block; with the flag on it rides the board as
    `club_process` (and a field_key line), with it off the board is untouched.
    Returns the block either way."""
    live = ARB_CLUB_PROCESS_CHIPS if live is None else live
    process = build_club_process(ledger)
    if live and process is not None:
        board["club_process"] = process
        board["field_key"]["club_process"] = (
            "per club over the captured MLB Trade Rumors trackers, credited to the exchange-day club: "
            "cases, exchanged, hearings, a label only when the data carry it; descriptive, read by no award")
    return process


def write_club_process_preview(process: dict, log=print, path: Path | None = None) -> Path:
    """The flag-off home of the block: under .cache, never data/."""
    p = Path(path or CLUB_PROCESS_PREVIEW)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(process, separators=(",", ":")), encoding="utf-8")
    log(f"  arb_export: club process preview {p.name} ({p.stat().st_size} bytes, flag off)")
    return p


if __name__ == "__main__":
    export()
