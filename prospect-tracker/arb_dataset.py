# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""The arbitration label set: one row per MLB player-season, 2008-2026.

THIS IS THE PROGRAM'S HIGHEST-VALUE ASSET. It outlives every gate: even if the
model is a measured null, a panel of arbitration awards carrying an arb-step
provenance, a contamination reason and a coverage census exists nowhere else in
this tree and every downstream lane consumes it.

THE SPINE IS .cache/war_daily/{bat,pit}.parquet, not data/ewar.json. Only the
war_daily frames carry (a) a `salary` column, (b) `player_ID`, the bbref id that
is the join key for MLB Trade Rumors hrefs and the ONLY place bbref ids exist in
this tree, and (c) coverage back to 2005. data/ewar.json (2011-2026 in the
2026-09-03 build) cannot span the window, so it does not replace the spine.

THE WAR COLUMN FOLLOWS THE war_source DEFAULT (eWAR v2 since 2026-09-03).
The parquet frames stay the raw bWAR download (salary, ids and exposure are
read from them unchanged); the WAR column alone is rebased through the
facade's frame transform before the stints collapse, so a covered
player-season's `war` is the artifact's side total (pitching re-priced on
FIP within role, league sum per season preserved; position players equal
bWAR until the SDR defense drop) and every uncovered season (pre-2011, or
no artifact block) stays bWAR. war_daily_spine(provider='bwar') reproduces
the pre-epoch panel exactly.

THE ARB MODEL WAS FIT ON bWAR FEATURES. arb_model's `war` / `war3` /
`career_war` columns and its war_ols coefficients were fit on the bWAR
spine, and data/arb_panel.json predates the flip; the rebuild wave must
re-build the panel and re-fit the model on this spine before the served
arbitration numbers and the spine agree on pitcher WAR.

MEASURED FACTS THIS MODULE IS BUILT AROUND
  * A naive "season 3-7 since debut, salary above the minimum" filter returns
    3,833 player-seasons, and its top 2026 rows are Tarik Skubal (a real award),
    then Crochet / Javier / Tatis Jr (EXTENSIONS), then Jung Hoo Lee and Shota
    Imanaga (POSTED FOREIGN FREE AGENTS with no pre-arb ladder at all). Five of
    six are contaminants. Contamination removal is a deliverable, not a filter.
  * 11.52% of that naive pool violates the CBA maximum-cut rule
    (salary_t / salary_t-1 < 0.80), which a real arbitration award cannot do.
    That share is a direct contamination METER and a gate criterion (G3).
  * war_daily's 2020 salary is the UNPRORATED figure (paired 2019->2020 median
    ratio 1.311), so it is the award, which is the right label. Proration is a
    paid-versus-awarded question and rides a flag, not the label.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import date
from pathlib import Path

import arb_service

_log = logging.getLogger(__name__)

ROOT = Path(__file__).parent
PANEL_PATH = ROOT / "data" / "arb_panel.json"
WAR_DAILY = ROOT / ".cache" / "war_daily"

PANEL_VERSION = "arb_panel_v1"
FIRST_SEASON = 2008          # features start 3 seasons before the label window
FIRST_LABEL_SEASON = 2011
LAST_SEASON = 2026

# League minimum by season, $USD.
#
# value_framework_config.yaml:583 carries 2018-2026 and is the authority for
# those years. 2011-2017 are NOT in the config and are curated here.
# VERIFY_STATUS: curated-unverified for the pre-2018 rows, same convention as
# data/cba_rules.json and arb_service.SUPER_TWO_CUTOFFS. They set the pre-arb
# reference level, so an error shifts the "is this above the minimum" test that
# the debut heuristic and the contamination meters lean on.
_LEAGUE_MIN_CURATED = {
    2008: 390_000, 2009: 400_000, 2010: 400_000, 2011: 414_000, 2012: 480_000,
    2013: 490_000, 2014: 500_000, 2015: 507_500, 2016: 507_500, 2017: 535_000,
}


def league_min_by_year() -> dict[int, float]:
    """Config first, curated fallback for the years the config predates."""
    out = dict(_LEAGUE_MIN_CURATED)
    try:
        import value_framework as vf
        for k, v in (vf._config().get("league_min_by_year") or {}).items():
            out[int(k)] = float(v) * 1e6
    except Exception as exc:                    # pragma: no cover - defensive
        _log.warning("arb_dataset: league minimum config unreadable: %s", exc)
    return out


# --------------------------------------------------------------------------- #
# Spine
# --------------------------------------------------------------------------- #

def _collapse(df, pt_col: str, side: str):
    """Stints -> one row per (mlb_ID, year_ID) for one side.

    Counting columns SUM across stints. `salary` takes the MAX of the non-null
    stint values rather than the sum: war_daily repeats the season salary on
    each stint row for a traded player, so summing would double it. Measured on
    2015+: 1,657 multi-stint batting seasons, of which 1,036 carry exactly one
    distinct salary, 620 carry none and 1 carries two.
    """
    import pandas as pd
    keep = ["mlb_ID", "player_ID", "name_common", "year_ID", "team_ID",
            "age", "salary", "WAR", pt_col]
    if side == "pit":
        keep += ["GS", "G"]
    else:
        keep += ["G"]
    d = df[[c for c in keep if c in df.columns]].copy()
    for c in ("mlb_ID", "year_ID", "age", "salary", "WAR", pt_col, "GS", "G"):
        if c in d.columns:
            d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.dropna(subset=["mlb_ID", "year_ID"])
    agg = {
        "player_ID": ("player_ID", "first"),
        "name": ("name_common", "first"),
        "age": ("age", "max"),
        "salary": ("salary", "max"),
        f"war_{side}": ("WAR", "sum"),
        f"pt_{side}": (pt_col, "sum"),
        "n_stints": ("year_ID", "size"),
        "team": ("team_ID", "last"),
    }
    if side == "pit":
        agg["gs"] = ("GS", "sum")
    out = d.groupby(["mlb_ID", "year_ID"]).agg(**agg).reset_index()
    return out


def _war_provider() -> str:
    """The WAR basis the spine's `war` column is served on: the facade default."""
    import war_source
    return war_source.DEFAULT_PROVIDER


def _rebase_war(df, side: str, provider: str | None):
    """Replace the raw parquet frame's WAR column with ``provider``'s series
    (None = the facade default). 'bwar' returns the frame untouched.
    'ewar_v2' runs war_source's stint transform, the same one stint_frame
    serves online: per (mlb_ID, year_ID) the stint WARs sum to the artifact's
    side total, the delta split IPouts / PA proportional, WAR_bwar appended,
    every other column and row untouched. The parquet door is used so the
    panel stays a pure offline read; the last-good parquet always holds raw
    bWAR (war_source._store_last_good), so the transform never stacks."""
    import war_source
    provider = provider or war_source.DEFAULT_PROVIDER
    war_source._require(provider)
    if provider == "bwar":
        return df
    return war_source._ewar_frame(df, side, door="arb_spine")


def war_daily_spine(first: int = FIRST_SEASON, last: int = LAST_SEASON,
                    *, provider: str | None = None):
    """One row per (mlbam, season) across BOTH sides.

    The bat/pit merge is an OUTER join, not a concat: a two-way player has a row
    in each frame carrying the SAME season salary, so concatenating would enter
    Ohtani's salary twice. WAR sums across sides (it is additive); salary takes
    the max (it is one contract).

    ``provider`` selects the WAR series (module docstring): None = the
    war_source default, 'bwar' = the raw frames. Salary, ids and exposure do
    not depend on it.
    """
    import pandas as pd
    b = _rebase_war(pd.read_parquet(WAR_DAILY / "bat.parquet"), "bat", provider)
    p = _rebase_war(pd.read_parquet(WAR_DAILY / "pit.parquet"), "pit", provider)
    cb = _collapse(b, "PA", "bat")
    cp = _collapse(p, "IPouts", "pit")
    m = cb.merge(cp, on=["mlb_ID", "year_ID"], how="outer",
                 suffixes=("_b", "_p"))
    m["mlbam"] = m["mlb_ID"].astype("Int64")
    m["season"] = m["year_ID"].astype("Int64")
    m["bbref_id"] = m["player_ID_b"].fillna(m["player_ID_p"])
    m["name"] = m["name_b"].fillna(m["name_p"])
    m["age"] = m[["age_b", "age_p"]].max(axis=1)
    m["salary"] = m[["salary_b", "salary_p"]].max(axis=1)
    m["team"] = m["team_b"].fillna(m["team_p"])
    m["war"] = m[["war_bat", "war_pit"]].fillna(0).sum(axis=1)
    m["pa"] = m["pt_bat"].fillna(0)
    m["ipouts"] = m["pt_pit"].fillna(0)
    m["gs"] = m["gs"].fillna(0)
    m["n_stints"] = m[["n_stints_b", "n_stints_p"]].fillna(0).max(axis=1)
    m = m[(m["season"] >= first) & (m["season"] <= last)]
    cols = ["mlbam", "season", "bbref_id", "name", "age", "team", "salary",
            "war", "pa", "ipouts", "gs", "n_stints"]
    return m[cols].sort_values(["mlbam", "season"]).reset_index(drop=True)


# --------------------------------------------------------------------------- #
# External label / contamination sources
# --------------------------------------------------------------------------- #

def _db_path() -> Path:
    import storage
    return Path(storage.DB_PATH)


def fa_signings_by_mlbam() -> dict[int, list[dict]]:
    """{mlbam: [signing, ...]} from the fa_signings table, read-only.

    Supplies BOTH the arb-year back-count source (first FA class year minus
    control years) and the multi-year-extension contamination test.
    """
    out: dict[int, list[dict]] = {}
    try:
        con = sqlite3.connect(f"file:{_db_path()}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        _log.warning("arb_dataset: fa_signings unavailable: %s", exc)
        return out
    try:
        for cy, pj in con.execute(
                "select class_year, payload_json from fa_signings"):
            try:
                p = json.loads(pj)
            except (TypeError, ValueError):
                continue
            mlbam = p.get("mlbam_id")
            if not mlbam:
                continue
            out.setdefault(int(mlbam), []).append({
                "class_year": int(cy),
                "years": p.get("years"),
                "guar": p.get("guarantee_usd"),
                "aav": p.get("aav_usd"),
                "qo": bool(p.get("qo")),
            })
    finally:
        con.close()
    for v in out.values():
        v.sort(key=lambda r: r["class_year"])
    return out


def posted_foreign_mlbam() -> set[int]:
    """MLBAM ids of players who entered via an international POSTING (NPB/KBO).

    These are the Jung Hoo Lee / Shota Imanaga class: they signed an MLB free
    agent contract with zero MLB service, so they have no pre-arb ladder and no
    arbitration years at all. A naive service proxy reads their first MLB
    seasons as pre-arb and their salary as an enormous arbitration award.
    """
    out: set[int] = set()
    try:
        con = sqlite3.connect(f"file:{_db_path()}?mode=ro", uri=True)
    except sqlite3.Error:
        return out
    try:
        for (mid,) in con.execute(
                "select mlbam_id from overseas_players where mlbam_id is not null"):
            try:
                out.add(int(mid))
            except (TypeError, ValueError):
                continue
    except sqlite3.Error as exc:
        _log.warning("arb_dataset: overseas_players unreadable: %s", exc)
    finally:
        con.close()
    return out


def spotrac_status_by_mlbam() -> dict[int, dict[int, str]]:
    """{mlbam: {season: status token}} from the cached Spotrac team pages.

    Depends on the 2026-08-08 parser fix: before it, every status cell was
    stored as a $0 salary and the token was discarded entirely.
    """
    import spotrac
    links = {}
    try:
        d = json.loads((ROOT / "data" / "player_links.json").read_text("utf-8"))
        links = {k: (v or {}).get("mlbam") for k, v in (d.get("byKey") or {}).items()}
    except (OSError, ValueError) as exc:
        _log.warning("arb_dataset: player_links unreadable: %s", exc)
    out: dict[int, dict[int, str]] = {}
    unresolved = 0
    for _code, slug in spotrac._SPOTRAC_TEAM_SLUGS.items():
        # Contract tables first, then the club-control tables where OPTIONED
        # players live. Optioned players are exactly the arbitration and pre-arb
        # population, and reading only the contract tables is why 356 veterans
        # on the projection board carry no salary and therefore no surplus:
        # they are absent from the tables the contract scraper consumes.
        # Measured: the extra tables recover 127 of those 356 (35.7%), 124 of
        # them carrying an ARB or PRE-ARB token.
        rows = (spotrac.scrape_spotrac_team_contracts(slug)
                + spotrac.scrape_spotrac_team_statuses(slug))
        for row in rows:
            status = row.get("status_by_year") or {}
            if not status:
                continue
            mlbam = links.get(row.get("player_key"))
            if not mlbam:
                unresolved += 1
                continue
            # A contract-table row wins over a club-control row for the same
            # player: if he has both, the contract row is the current one.
            out.setdefault(int(mlbam), {int(y): s for y, s in status.items()})
    if unresolved:
        _log.info("arb_dataset: %d Spotrac status rows unresolved to an mlbam",
                  unresolved)
    return out


def spotrac_contract_span_by_mlbam() -> dict[int, tuple[int, int]]:
    """{mlbam: (first_priced_year, signed_through)} for the extension test.

    A player whose Spotrac contract prices two or more consecutive future years
    is on a multi-year deal, and a season inside that span is not an
    arbitration outcome.
    """
    import spotrac
    links = {}
    try:
        d = json.loads((ROOT / "data" / "player_links.json").read_text("utf-8"))
        links = {k: (v or {}).get("mlbam") for k, v in (d.get("byKey") or {}).items()}
    except (OSError, ValueError):
        pass
    out: dict[int, tuple[int, int]] = {}
    for _code, slug in spotrac._SPOTRAC_TEAM_SLUGS.items():
        for row in spotrac.scrape_spotrac_team_contracts(slug):
            sby = row.get("salary_by_year") or {}
            if len(sby) < 2:
                continue
            mlbam = links.get(row.get("player_key"))
            if mlbam:
                out[int(mlbam)] = (min(sby), max(sby))
    return out


def career_appearance_seasons():
    """{mlbam: sorted set of EVERY MLB season on file}, unwindowed.

    Deliberately NOT derived from the windowed spine. The panel starts at 2008,
    so a player who debuted in 2005 would read a 2008 "debut" and every
    service-derived step would be three years wrong. Debut year is a career
    fact and has to be read from the whole frame.
    """
    import pandas as pd
    out: dict[int, set[int]] = {}
    for f, pt in (("bat.parquet", "PA"), ("pit.parquet", "IPouts")):
        d = pd.read_parquet(WAR_DAILY / f, columns=["mlb_ID", "year_ID", pt])
        d["mlb_ID"] = pd.to_numeric(d["mlb_ID"], errors="coerce")
        d["year_ID"] = pd.to_numeric(d["year_ID"], errors="coerce")
        d[pt] = pd.to_numeric(d[pt], errors="coerce").fillna(0)
        # A season with zero exposure on this side is still an appearance if
        # the row exists (a pitcher with 0 PA still appeared), so no PT filter.
        d = d.dropna(subset=["mlb_ID", "year_ID"])
        for mid, yr in zip(d["mlb_ID"].astype(int), d["year_ID"].astype(int)):
            out.setdefault(mid, set()).add(yr)
    return out


def load_ledger() -> dict[int, dict[int, dict]]:
    """{mlbam or bbref-keyed: {class_year: entry}} from data/_labs/arb_ledger.json.

    Returns {} when the ledger has not been ingested yet, so the panel builds
    without it and the coverage census reports the absence rather than the
    pipeline failing. Keyed by bbref id, which is what the MLBTR hrefs carry.
    """
    # A lab file: data/_labs/ ships in neither deploy consumer (owner answer
    # M23-3, 2026-09-25, moved it off the public webroot).
    path = ROOT / "data" / "_labs" / "arb_ledger.json"
    if not path.exists():
        return {}
    try:
        doc = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError) as exc:
        _log.warning("arb_dataset: arb_ledger unreadable: %s", exc)
        return {}
    out: dict[str, dict[int, dict]] = {}
    for e in doc.get("entries") or []:
        # Posts before 2023 link no player to Baseball Reference, so those rows
        # carry an mlbam resolved through fa_ident instead. Both key shapes are
        # indexed; the panel looks up bbref first and falls back to mlbam.
        for key in (e.get("bbref_id"), e.get("mlbam")):
            if key:
                out.setdefault(str(key), {})[int(e["class_year"])] = e
    return out


# --------------------------------------------------------------------------- #
# Contamination
# --------------------------------------------------------------------------- #

# Reason codes. Every excluded row leaves with one and the counts are published
# in the coverage audit, so an exclusion is never silent.
EXCL_EXTENSION = "multiyear_extension"
EXCL_POSTED_FA = "posted_foreign_fa"
EXCL_SEASON_2020 = "season_2020_not_a_label_year"
EXCL_SUB_MAX_CUT = "sub_max_cut_not_an_award"

# CBA Article VI: a club may not cut an arbitration-eligible player's salary by
# more than 20% from the prior season. So a year-over-year ratio below 0.80 is
# not an arbitration award AT ALL - it is a new contract signed after a
# non-tender or a release, and the prior figure was the last arbitration salary
# rather than this one's basis.
#
# This is a DEFINITIONAL exclusion, not a fit convenience, and the distinction
# matters because excluding rows that fail your own meter is how a meter gets
# laundered into passing. Two consequences are stated rather than hidden:
#   1. After the rule, the post-filter violation rate is 0% BY CONSTRUCTION and
#      is not evidence of anything.
#   2. The reported contamination quantity is therefore the REMOVAL RATE - how
#      many candidate rows the rule deletes - which is also the non-tender /
#      broken-chain meter this panel otherwise had no way to see.
#
# Measured before the rule existed: 5.16% of rows carrying MLBTR service-time
# GROUND TRUTH still violated it, and the worst offenders are Ty France 2025
# ($6,775,000 -> $1,000,000), Nicky Lopez and Luis Urias - all non-tendered and
# re-signed. That proved the residual violations were a missing exclusion, not a
# step-reconstruction error.
MAX_CUT_RATIO = 0.80


def contamination(row: dict, *, fa_rows, spotrac_span, posted: set[int]) -> dict:
    """Flags plus the exclusion decision for one player-season.

    KEPT deliberately: a one-year deal signed to avoid a hearing IS an
    arbitration outcome - the settlement is the award - so a single priced year
    is not an extension.

    NOT dropped: non-tenders. They are the truncation at the bottom of the
    label distribution. They are counted, because deleting them is exactly what
    makes a forward projection overstate payroll.

    2020 is never a label year: the paid figure is 60/162 = 37.04% of contract
    and the sources disagree on which basis they report.
    """
    season = int(row["season"])
    mlbam = int(row["mlbam"])
    flags: dict = {
        "prorated_2020": season == 2020,
        "pandemic_platform": season == 2021,
        "posted_foreign_fa": mlbam in posted,
        "multiyear_extension": False,
        "traded_midseason": int(row.get("n_stints") or 0) > 1,
    }
    for s in fa_rows or []:
        try:
            yrs = int(s.get("years"))
        except (TypeError, ValueError):
            continue
        if yrs > 1 and s["class_year"] <= season <= s["class_year"] + yrs - 1:
            flags["multiyear_extension"] = True
            flags["extension_class_year"] = s["class_year"]
            break
    span = spotrac_span.get(mlbam)
    if span and not flags["multiyear_extension"]:
        lo, hi = span
        if hi > lo and lo <= season <= hi:
            flags["multiyear_extension"] = True
            flags["extension_class_year"] = lo

    reason = None
    if flags["posted_foreign_fa"]:
        reason = EXCL_POSTED_FA
    elif flags["multiyear_extension"]:
        reason = EXCL_EXTENSION
    elif season == 2020:
        reason = EXCL_SEASON_2020
    flags["exclude_reason"] = reason
    return flags


# --------------------------------------------------------------------------- #
# Panel
# --------------------------------------------------------------------------- #

def build_panel(*, first: int = FIRST_SEASON, last: int = LAST_SEASON,
                log=None) -> dict:
    """Assemble the full labelled panel. Pure read; writes nothing."""
    say = log or (lambda *_a, **_k: None)
    say("  arb_panel: spine...")
    spine = war_daily_spine(first, last)
    lm = league_min_by_year()
    say("  arb_panel: careers...")
    careers = career_appearance_seasons()
    say("  arb_panel: fa_signings / overseas / spotrac...")
    fa = fa_signings_by_mlbam()
    posted = posted_foreign_mlbam()
    status = spotrac_status_by_mlbam()
    span = spotrac_contract_span_by_mlbam()
    ledger = load_ledger()

    sal_path: dict[int, dict[int, float]] = {}
    for r in spine.itertuples(index=False):
        if r.salary == r.salary and r.salary is not None:
            sal_path.setdefault(int(r.mlbam), {})[int(r.season)] = float(r.salary)

    back: dict[int, dict[int, dict]] = {}
    for mlbam, sby in status.items():
        back[mlbam] = arb_service.backpropagate(
            sby, appearance_seasons=careers.get(mlbam, set()))

    faback: dict[int, dict[int, dict]] = {}
    for mlbam, rows_ in fa.items():
        if rows_:
            seasons_ = careers.get(mlbam, set())
            faback[mlbam] = arb_service.from_fa_class(
                rows_[0]["class_year"], seasons_,
                debut_year=min(seasons_) if seasons_ else None)

    out: list[dict] = []
    for r in spine.itertuples(index=False):
        mlbam = int(r.mlbam)
        season = int(r.season)
        seasons = careers.get(mlbam) or set()
        debut = min(seasons) if seasons else season

        votes: dict[str, dict] = {}
        led = None
        for key in (r.bbref_id, str(mlbam)):
            if key and key in ledger:
                led = ledger[key].get(season)
                if led:
                    break
        if led and led.get("service_years") is not None:
            v = arb_service.arb_year_from_service(
                int(led["service_years"]), int(led.get("service_days") or 0), season)
            if v.get("arb_year"):
                votes["mlbtr_service"] = v
        if season in (back.get(mlbam) or {}):
            votes["spotrac_backprop"] = back[mlbam][season]
        if season in (faback.get(mlbam) or {}):
            votes["fa_class_backcount"] = faback[mlbam][season]
        heur = arb_service.from_debut(debut, seasons, sal_path.get(mlbam, {}),
                                      lm, season=season)
        if heur:
            votes["debut_heuristic"] = heur

        lab = arb_service.reconcile(votes, season=season)
        flags = contamination(
            {"season": season, "mlbam": mlbam, "n_stints": r.n_stints},
            fa_rows=fa.get(mlbam), spotrac_span=span, posted=posted)

        salary = (float(r.salary)
                  if r.salary == r.salary and r.salary is not None else None)
        prior = sal_path.get(mlbam, {}).get(season - 1)
        # The maximum-cut rule, applied as a definition. Only meaningful when
        # the player was labelled arb-eligible and both figures exist.
        if (flags["exclude_reason"] is None and lab["arb_year"] and salary
                and prior and salary / prior < MAX_CUT_RATIO):
            flags["exclude_reason"] = EXCL_SUB_MAX_CUT
            flags["cut_ratio"] = round(salary / prior, 3)
        out.append({
            "mlbam": mlbam, "bbref": r.bbref_id, "name": r.name,
            "season": season,
            "age": None if r.age != r.age else float(r.age),
            "team": r.team, "debut": debut,
            # PUBLISHED SERVICE TIME, carried from the MLBTR ledger entry this
            # loop already resolved (`led`). arb_export emits it as the board's
            # `sv` field, which asked for `service_time` and got None on all 852
            # rows because nothing here ever emitted it - a dead field since the
            # board shipped. Nothing reads `sv` today, so populating it moves no
            # served number; what it unblocks is the only EXTERNAL check on the
            # control horizon (GATE C2 clause C9', docs/ARBITRATION_GATE.md
            # section 11d), which scores class closure's implied last controlled
            # season against a published service-time string. The string is a
            # STRING on purpose: 5.043 as a float lies about .043 being 43/1000.
            "service_time": (led or {}).get("service_time"),
            "service_years": (led or {}).get("service_years"),
            "salary": salary,
            "prior_salary": prior,
            "league_min": lm.get(season),
            "war": round(float(r.war), 2),
            "pa": int(r.pa), "ipouts": int(r.ipouts), "gs": int(r.gs),
            "n_stints": int(r.n_stints),
            "arb_year": lab["arb_year"], "super_two": lab["super_two"],
            "arb_year_source": lab["arb_year_source"],
            "votes": lab["votes"], "n_sources": lab["n_sources"],
            "source_agree": lab["agree"],
            **flags,
        })
    say(f"  arb_panel: {len(out)} player-seasons")
    return {
        "version": PANEL_VERSION,
        "generated_at": date.today().isoformat(),
        "window": [first, last],
        "label_window": [FIRST_LABEL_SEASON, last],
        "ledger_present": bool(ledger),
        "super_two_verified": arb_service.SUPER_TWO_VERIFIED,
        "rows": out,
    }


def clean_arb_rows(rows: list[dict]) -> list[dict]:
    """The fit pool: labelled arbitration seasons with a salary, no
    contaminant, inside the label window."""
    return [r for r in rows
            if r.get("arb_year") and r.get("salary")
            and not r.get("exclude_reason")
            and FIRST_LABEL_SEASON <= r["season"] <= LAST_SEASON]


# Seasons whose arb-step labels rest on MLBTR-published service time. Measured
# agreement of the substitute sources against that ground truth is 0.6067
# (fa_class_backcount) and 0.6861 (debut_heuristic) - roughly a third of their
# labels are wrong - against a G2 criterion of 0.95. Spotrac reaches 0.8588 but
# only exists from 2024 and is survivor-only before that.
#
# So seasons outside this window are REPORTED AND NOT SCORED. That is the
# pre-registered consequence in docs/ARBITRATION_GATE.md section 2, and it
# withdraws the plan's "2011-2026 backtest" description.
SCORED_SEASONS = (2022, 2023, 2024, 2025, 2026)


def scored_rows(rows: list[dict]) -> list[dict]:
    """Clean rows whose arb step came from MLBTR service time, in the scored
    window. This is the pool any gate may adjudicate on."""
    return [r for r in clean_arb_rows(rows)
            if r["season"] in SCORED_SEASONS
            and r.get("arb_year_source") == "mlbtr_service"]


def write_panel(doc: dict, audit: dict) -> Path:
    """Commit the panel audit. The panel ROWS are not committed - 25,892 rows
    would be a large artifact nothing serves - but the census, the meters and
    the source mix are, because they are the evidence the label set is what it
    claims to be."""
    out = {
        "generated_at": doc["generated_at"],
        "version": doc["version"],
        "produced_by": "arb_dataset.build_panel",
        "window": doc["window"],
        "label_window": doc["label_window"],
        "scored_seasons": list(SCORED_SEASONS),
        "ledger_present": doc["ledger_present"],
        "super_two_verified": doc["super_two_verified"],
        "conventions": {
            "spine": "war_daily bat+pit parquet, stints collapsed, salary MAX not SUM, two-way merge OUTER",
            "war": (f"WAR column on war_source provider {_war_provider()} "
                    "(eWAR v2: FIP-repriced pitching within role, position players equal bWAR "
                    "until the SDR defense drop, uncovered seasons bWAR); salary/ids/exposure raw; "
                    "arb_model coefficients were fit on bWAR until the rebuild wave re-fits"),
            "label": "Baseball Reference season salary, fused with the MLBTR settled figure where present",
            "arb_step": "fused from mlbtr_service > spotrac_backprop(>=2024) > fa_class_backcount > debut_heuristic",
            "max_cut": "CBA Article VI: a ratio below 0.80 is not an award, so those rows are EXCLUDED by definition",
            "2020": "never a label year; war_daily's 2020 salary is the UNPRORATED award",
        },
        "audit": audit,
    }
    PANEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = PANEL_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(out, indent=1), encoding="utf-8")
    tmp.replace(PANEL_PATH)
    return PANEL_PATH


def _count(rows, key: str) -> dict:
    out: dict[str, int] = {}
    for r in rows:
        v = r.get(key)
        if v:
            out[str(v)] = out.get(str(v), 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def coverage_audit(rows: list[dict]) -> dict:
    """Per-season census plus the label-quality meters.

    G3 RESTATED. The maximum-cut rule is now applied as a DEFINITION (see
    EXCL_SUB_MAX_CUT), so the post-filter violation rate is 0% by construction
    and proves nothing. The reported quantity is the REMOVAL RATE - the share of
    otherwise-clean candidate rows the rule deletes - which is simultaneously
    the non-tender / broken-salary-chain meter this panel had no other way to
    see. A rising removal rate means more of the population is leaving
    arbitration by non-tender, not that the model got worse.

    G5 (coverage): a season below 70% label coverage is REPORTED AND NOT
    SCORED, never quietly dropped.
    """
    by_season: dict[str, dict] = {}
    for y in range(FIRST_LABEL_SEASON, LAST_SEASON + 1):
        ys = [r for r in rows if r["season"] == y]
        labelled = [r for r in ys if r.get("arb_year")]
        clean = clean_arb_rows(ys)
        withsal = [r for r in labelled if r.get("salary")]
        removed = [r for r in ys if r.get("exclude_reason") == EXCL_SUB_MAX_CUT]
        denom = len(clean) + len(removed)
        by_season[str(y)] = {
            "rows": len(ys), "labelled": len(labelled),
            "labelled_with_salary": len(withsal), "clean": len(clean),
            "salary_coverage": (round(len(withsal) / len(labelled), 4)
                                if labelled else None),
            "max_cut_removed": len(removed),
            "max_cut_removal_rate": (round(len(removed) / denom, 4)
                                     if denom else None),
            "excluded": _count(ys, "exclude_reason"),
            "source_mix": _count(labelled, "arb_year_source"),
        }
    clean_all = clean_arb_rows(rows)
    removed_all = [r for r in rows if r.get("exclude_reason") == EXCL_SUB_MAX_CUT]
    denom_all = len(clean_all) + len(removed_all)
    return {
        "by_season": by_season,
        "totals": {
            "rows": len(rows),
            "labelled": sum(1 for r in rows if r.get("arb_year")),
            "clean": len(clean_all),
            "max_cut_removed": len(removed_all),
            "max_cut_removal_rate": (round(len(removed_all) / denom_all, 4)
                                     if denom_all else None),
            "post_filter_violation_rate": 0.0,
            "post_filter_note": ("0 by construction: the maximum-cut rule is a "
                                 "definitional exclusion, so this number is not "
                                 "evidence. Read max_cut_removal_rate instead."),
        },
        "disagreement": arb_service.disagreement_report(rows),
    }
