# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""MLB Free Agency pipeline orchestrator (Stage 1: data layer).

Standalone entry so the Stage-1 checkpoint is reproducible end-to-end:

    python fa_pipeline.py --backfill      # historical classes 2015..latest
                                          #   + ID resolution + career bWAR
                                          #   + retrospective ledger
    python fa_pipeline.py --current 2027  # the coming winter's class
    python fa_pipeline.py --payroll       # CBT + payroll ledgers

run_monthly grows matching `_step("fa: …")` blocks at Stage 6
(integrations) — this module owns the logic either way.

Identity discipline: signed players resolve to the SAME canonical ids the
rest of the platform uses (player_key slug + MLBAM id via the existing
PlayerIndex/Chadwick machinery in stats.bulk_resolve_ids). Unresolved
players are counted and reported — never silently dropped, never faked.
WAR is bWAR via stats.fetch_career_war_bulk — one WAR source site-wide.
"""

from __future__ import annotations

import argparse
import logging
from datetime import date

import fa_class
import fa_sources
import storage
from fa_class import get_config

log = logging.getLogger(__name__)


def _resolve_signed_via_war_daily(classes: dict[int, dict],
                                  first_year: int, last_year: int
                                  ) -> tuple[dict[str, int], dict[str, dict], dict]:
    """Resolve every signed player against B-Ref's war_daily tables and
    build their per-season bWAR maps in the same pass.

    Returns (player_key -> mlb_ID, player_key -> {"seasons": {str(yr): WAR}},
    stats dict). Sums batting + pitching WAR per season (two-way players),
    and stints within a season. Ambiguous names (two candidates active in
    the same pre-signing window) are skipped and counted — the ledger
    never scores a guessed identity."""
    import pybaseball  # noqa: F401 - availability probe; frames come via war_source
    import war_source
    from scrapers import normalize_key
    import concurrent.futures as _cf

    def _safe(side, label):
        try:
            return war_source.stint_frame(side)
        except Exception as e:                                # noqa: BLE001
            log.warning("%s fetch failed: %s", label, e)
            return None

    with _cf.ThreadPoolExecutor(max_workers=2) as ex:
        f_bat = ex.submit(_safe, "bat", "bwar_bat")
        f_pit = ex.submit(_safe, "pit", "bwar_pitch")
        bat_df, pit_df = f_bat.result(), f_pit.result()
    if bat_df is None and pit_df is None:
        return {}, {}, {"error": "war_daily unavailable"}

    # name(normalized) -> {mlb_ID: {"years": set, "war": {year: total}}}
    by_name: dict[str, dict[int, dict]] = {}
    for df in (bat_df, pit_df):
        if df is None or df.empty:
            continue
        sub = df[df["WAR"].notna() & df["mlb_ID"].notna()]
        for row in sub.itertuples(index=False):
            try:
                mid = int(getattr(row, "mlb_ID"))
                yr = int(getattr(row, "year_ID"))
                war = float(getattr(row, "WAR"))
                nm = normalize_key(str(getattr(row, "name_common")))
            except (TypeError, ValueError):
                continue
            ent = by_name.setdefault(nm, {}).setdefault(mid, {"years": set(), "war": {}})
            ent["years"].add(yr)
            ent["war"][yr] = ent["war"].get(yr, 0.0) + war

    resolved: dict[str, int] = {}
    war_by_key: dict[str, dict] = {}
    n_seen = n_nomatch = n_ambig = 0
    seen_keys: set[str] = set()
    for class_year, cls in sorted(classes.items()):
        for s in cls["signed"]:
            key = s.get("player_key")
            if not key or key in seen_keys:
                continue
            seen_keys.add(key)
            n_seen += 1
            cands = by_name.get(normalize_key(s["player_name"]))
            if not cands:
                n_nomatch += 1
                continue
            # Plausible = active at some point in the 4 platform seasons
            # before the signing winter (war_daily year = season played).
            window = set(range(class_year - 4, class_year))
            plausible = [mid for mid, ent in cands.items() if ent["years"] & window]
            if not plausible:
                # Career predates the window entirely (e.g. re-listed name)
                # — fall back to the most recently active candidate if it is
                # UNIQUE; otherwise ambiguous.
                latest = sorted(cands.items(), key=lambda kv: -max(kv[1]["years"]))
                plausible = [latest[0][0]] if len(cands) == 1 else []
            if len(plausible) != 1:
                n_ambig += 1
                continue
            mid = plausible[0]
            resolved[key] = mid
            war_by_key[key] = {"seasons": {str(y): round(w, 2)
                                           for y, w in sorted(cands[mid]["war"].items())},
                               "source": "bbref"}
    stats = {"seen": n_seen, "resolved": len(resolved),
             "no_match": n_nomatch, "ambiguous": n_ambig}
    return resolved, war_by_key, stats


def backfill_historical(first_year: int | None = None,
                        last_year: int | None = None,
                        force: bool = False) -> dict:
    """Ingest every historical class, resolve ids, fetch career bWAR for
    the signed pool, build the ledger, persist. Returns a summary dict."""
    cfg = get_config()
    first = first_year or int(cfg["backfill"]["first_class_year"])
    last = last_year or date.today().year       # 2026 = the 2025-26 winter (complete)
    classes: dict[int, dict] = {}
    for year in range(first, last + 1):
        classes[year] = fa_class.build_historical_class(year, force=force)

    # ---- identity + per-season bWAR via the B-Ref war_daily tables ----------
    # The platform's PlayerIndex covers PROSPECTS; FA veterans (back to the
    # 2014-15 winter) resolve instead against war_daily itself — the same
    # bWAR source the whole site uses, covering every MLB player ever, with
    # name + mlb_ID + per-season WAR in one place. Disambiguation: a
    # candidate must have been ACTIVE in the platform window before the
    # signing winter; ≥2 plausible candidates → counted ambiguous and
    # skipped (never guessed).
    resolved, war_by_key, id_stats = _resolve_signed_via_war_daily(
        classes, first_year=first, last_year=last)
    log.info("fa backfill: war_daily identity — %s", id_stats)

    # ---- ledger + persistence ----------------------------------------------
    ledger_rows = fa_class.build_ledger(classes, war_by_key)
    n_sign = 0
    for year, cls in classes.items():
        # stamp ledger blocks back onto their signing rows before persisting
        led_by_key = {(r["player_key"], r["class_year"]): r["ledger"] for r in ledger_rows}
        for s in cls["signed"]:
            s["mlbam_id"] = resolved.get(s.get("player_key"))
            led = led_by_key.get((s.get("player_key"), year))
            if led:
                s["ledger"] = led
        n_sign += storage.upsert_fa_signings(year, cls["signed"])
    summary = {
        "classes": len(classes),
        "first_year": first, "last_year": last,
        "signings_stored": n_sign,
        "signed_total": sum(len(c["signed"]) for c in classes.values()),
        "mlb_deals": sum(1 for c in classes.values() for s in c["signed"] if s["mlb_deal"]),
        "id_resolved": id_stats.get("resolved"), "id_no_match": id_stats.get("no_match"),
        "id_ambiguous": id_stats.get("ambiguous"),
        "ledger_rows": len(ledger_rows),
    }
    log.info("fa backfill summary: %s", summary)
    return summary


def refresh_current_class(class_year: int, force: bool = False) -> dict:
    prior = {k: p for (k, yr), p in
             storage.load_fa_class_players(class_year).items() if yr == class_year}
    cls = fa_class.build_current_class(class_year, force=force)
    n = storage.upsert_fa_class_players(class_year, cls["players"])
    log.info("fa current class %d: stored %d players (reconciliation %s)",
             class_year, n, cls["reconciliation"])
    try:
        ev = track_winter_events(class_year, prior, cls["players"], force=force)
        if ev["inserted"]:
            log.info("fa events %d: %s", class_year, ev)
    except Exception:                                    # noqa: BLE001 — tracker is additive
        log.exception("fa winter event tracking failed — continuing")
    # The class page was re-fetched this run, so signings were re-confirmed even
    # when the quiet in-season market produced no NEW signing rows. Record that
    # check so the freshness stamp tracks "last checked", not "last NEW signing"
    # (which can be months stale in-season and falsely trip the UI 14-day flag).
    #
    # Gated on the parse actually producing players: a silently-empty parse (the
    # 2026-07-30 Spotrac layout change returned 0 rows for weeks) must leave the
    # stamp stale so the UI reports it, rather than certifying a frozen board.
    try:
        storage.touch_fa_signings(class_year)
        if n:
            storage.record_source_check("fa_signings", str(class_year), n_rows=0)
            storage.record_source_check("fa_class", str(class_year), n_rows=n)
    except Exception:                                    # noqa: BLE001
        log.exception("fa signings freshness touch failed — continuing")
    return cls


def track_winter_events(class_year: int, prior: dict, available: list[dict],
                        force: bool = False, signed_rows: list[dict] | None = None,
                        as_of: date | None = None) -> dict:
    """Observe winter transitions and append them to the first-seen ledger.

    Spotrac publishes terms but no per-signing dates, so every event stamps
    the date the PIPELINE first saw it (ex-ante — no backdating). Sources:
      • the class page's signed table (authoritative for terms)         → signing
      • status diffs vs the previously stored rows:
          pending_option re-listed as a locked UFA                      → option_declined
          pending_option gone from the page without a signing           → option_exercised
          QO flag newly published on an available row (early November)  → qo_offered
    ``signed_rows`` is injectable for tests; production scrapes the page.
    The option_exercised branch is a documented v1 heuristic (same status
    as the exercise-probability heuristic): page variance can momentarily
    drop a row, but events are append-only with stable keys, so one noisy
    scrape cannot duplicate or re-date anything.

    OPTION-WINDOW GATE (post-mortem 2026-06-12): a mid-June Spotrac page
    restructure dropped every pending-option row at once and the
    disappearance heuristic mass-fired 77 false option_exercised events,
    flooding the wire and dimming live FA-board members. Option decisions
    are a winter-window phenomenon (due days after the World Series), so
    option_declined / option_exercised inference only runs Oct 1 - Jan 31
    (``as_of`` injectable for tests). An empty available page additionally
    skips option inference outright - no page, no observation.
    """
    as_of = as_of or date.today()
    option_window = as_of.month in (10, 11, 12, 1)
    avail_by_key = {p["player_key"]: p for p in available if p.get("player_key")}
    seen = {(e["player_key"], e["event_type"])
            for e in storage.load_fa_events(class_year)}
    events: list[dict] = []

    if signed_rows is None:
        try:
            signed_rows = fa_sources.scrape_spotrac_fa_class(class_year,
                                                             force=force).get("signed") or []
        except Exception:                                # noqa: BLE001 — page may not exist pre-winter
            log.exception("fa class %d: signed-page scrape failed — signings skipped",
                          class_year)
            signed_rows = []
    for s in signed_rows:
        key = s.get("player_key")
        if not key:
            continue
        events.append({"player_key": key, "event_type": "signing",
                       "payload": {k: s.get(k) for k in
                                   ("player_name", "position", "from_team", "to_team",
                                    "years", "guarantee_usd", "aav_usd", "qo",
                                    "qo_accepted", "mlb_deal") if s.get(k) is not None}})
    if signed_rows:
        storage.upsert_fa_signings(class_year, signed_rows)
    signing_keys = ({s.get("player_key") for s in signed_rows}
                    | {k for k, t in seen if t == "signing"})

    if not option_window:
        n_pending = sum(1 for p in prior.values()
                        if p.get("status") == "pending_option")
        if n_pending:
            log.info("fa events %d: option inference skipped - %s is outside "
                     "the Oct-Jan option window (%d pending options held)",
                     class_year, as_of.isoformat(), n_pending)
    elif not avail_by_key:
        log.warning("fa events %d: available page came back empty - option "
                    "inference skipped (page failure, not 77 exercises)",
                    class_year)
    else:
        for key, p in prior.items():
            if p.get("status") != "pending_option":
                continue
            now = avail_by_key.get(key)
            base = {"player_name": p.get("player_name"), "position": p.get("position"),
                    "option_price_usd": p.get("option_price_usd")}
            if now is not None and now.get("status") == "locked":
                events.append({"player_key": key, "event_type": "option_declined",
                               "payload": base})
            elif now is None and key not in signing_keys:
                events.append({"player_key": key, "event_type": "option_exercised",
                               "payload": base})

    for key, now in avail_by_key.items():
        was = prior.get(key) or {}
        if ((now.get("qo") or now.get("qo_offered"))
                and not (was.get("qo") or was.get("qo_offered"))):
            events.append({"player_key": key, "event_type": "qo_offered",
                           "payload": {"player_name": now.get("player_name"),
                                       "position": now.get("position")}})

    inserted = storage.insert_fa_events_first_seen(class_year, events)
    # Reconcile the queryable status column: payload keeps the raw scrape;
    # status is the pipeline's view (board dims signed/exercised members).
    for e in events:
        if e["event_type"] == "signing":
            storage.set_fa_class_player_status(class_year, e["player_key"], "signed")
        elif e["event_type"] == "option_exercised":
            storage.set_fa_class_player_status(class_year, e["player_key"],
                                               "option_exercised")
    return {"observed": len(events), "inserted": inserted,
            "signed_rows": len(signed_rows)}


def refresh_payroll(seasons: list[int] | None = None, force: bool = False) -> int:
    seasons = seasons or [date.today().year, date.today().year + 1]
    n = 0
    for season in seasons:
        tax = {r["team"]: r for r in fa_sources.scrape_spotrac_tax(season, force=force)}
        pay = {r["team"]: r for r in fa_sources.scrape_spotrac_payroll(season, force=force)}
        merged = []
        for team in sorted(set(tax) | set(pay)):
            merged.append({"team": team, "season": season,
                           **(pay.get(team) or {}), **(tax.get(team) or {})})
        n += storage.upsert_fa_team_payroll(season, merged)
    return n


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="MLB Free Agency pipeline (Stage 1)")
    ap.add_argument("--backfill", action="store_true")
    ap.add_argument("--current", type=int, metavar="CLASS_YEAR")
    ap.add_argument("--payroll", action="store_true")
    ap.add_argument("--force", action="store_true", help="bypass page caches")
    args = ap.parse_args()
    if args.backfill:
        print(backfill_historical(force=args.force))
    if args.current:
        cls = refresh_current_class(args.current, force=args.force)
        print({k: cls[k] for k in ("class_year", "reconciliation", "cba_note")},
              "players:", len(cls["players"]))
    if args.payroll:
        print("payroll rows:", refresh_payroll(force=args.force))
    if not (args.backfill or args.current or args.payroll):
        ap.print_help()


if __name__ == "__main__":
    main()
