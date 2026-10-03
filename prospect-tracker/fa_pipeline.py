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
            # DISPLAY DOOR (fWAR label epoch step D + U, 2026-10-03): the Archive's
            # realized WAR is a displayed number, so it names eWAR v2 explicitly
            # (owner answer EPOCH-Q4; orchestrator ruling EPOCH-Q4-IMPL R1a).
            # Owner answer M14-3 wants the realized ledger rebuilt on fWAR at the
            # epoch and yearly: queue 7 M14 owns that rebuild and chooses its
            # provider explicitly when it runs after step Z; this run never
            # executes backfill_historical.
            return war_source.stint_frame(side, provider="ewar_v2")
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
            # M04-04: the basis the facade served these frames on, not a
            # hardcoded "bbref". Since the fWAR label epoch (2026-10-03) the
            # frames above are read on the displayed series by name, so the
            # stamp names it the same way, and build_ledger carries it onto
            # every ledger row so the Archive can say which WAR it realized.
            war_by_key[key] = {"seasons": {str(y): round(w, 2)
                                           for y, w in sorted(cands[mid]["war"].items())},
                               "source": "ewar_v2"}
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
    # HOME_1 (2026-10-02): hold every option or QO stamp first seen before
    # this class's window opened. Idempotent; a no-op on a clean ledger.
    try:
        q = quarantine_premature_winter_events(class_year)
        if q["marked"]:
            log.info("fa events %d: premature winter stamps held %s", class_year, q)
    except Exception:                                    # noqa: BLE001
        log.exception("fa premature-event quarantine failed - continuing")
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
          QO flag newly published on an available row (early November,
          window gated like the option branches)                        → qo_offered
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
    option_declined / option_exercised inference only runs inside the
    class's window (``as_of`` injectable for tests). An empty available page
    additionally skips option inference outright - no page, no observation.

    WINDOW START (HOME_1, 2026-10-02): the window used to open on October 1
    by calendar month, while decisions come after the World Series. On
    2026-10-02, with the postseason still in its first round, Spotrac
    re-listed 25 mutual and conditional options as plain UFAs and dropped 7
    pending rows, and the heuristic stamped 25 option_declined and 7
    option_exercised events that no club had made (plus 10 declines on the
    2028 class, a winter a year away). The window for class Y now opens the
    day after the last final World Series game of season Y - 1, read from
    the postseason schedule cache (winter_window_opens; November 1 when the
    cache cannot answer), and closes January 31 of Y. Stamps first seen
    before it are held by quarantine_premature_winter_events; a row whose
    option event is held re-enters the decision set, so a genuine in-window
    observation re-stamps it to that date.

    QO-WINDOW GATE (post-mortem 2026-08-12): qo_offered stamping had NO
    such guard, so 16 prior-QO-recipient flags surfacing on the August
    available page fired as fresh offers (Verlander, Scherzer, Springer -
    players who by rule cannot receive another QO). QOs are offerable ~5
    days after the World Series and expire mid-November, inside the same
    window, so qo_offered stamping rides the identical gate (and the same
    day-after-the-World-Series start).
    A genuine in-window observation for a key whose stored qo_offered row
    was quarantined (see quarantine_out_of_window_qo_events) re-stamps
    that row to the valid first-seen date and clears the invalidation.
    """
    as_of = as_of or date.today()
    option_window, window_opens, window_basis = winter_window_open(class_year, as_of)
    avail_by_key = {p["player_key"]: p for p in available if p.get("player_key")}
    stored = storage.load_fa_events(class_year)
    seen = {(e["player_key"], e["event_type"]) for e in stored}
    # Option stamps held by quarantine_premature_winter_events. Their rows
    # re-enter the decision set in window: the 2026-10-02 declines were
    # re-listed as UFAs the same night, so the stored class row no longer
    # reads pending_option and the diff alone would never see them again.
    held_options = {e["player_key"]: e for e in stored
                    if e.get("invalidated") and e["event_type"] in OPTION_EVENT_TYPES}
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
                     "the option window (opens %s, %s; %d pending options held)",
                     class_year, as_of.isoformat(),
                     window_opens.isoformat() if window_opens else "after the World Series",
                     window_basis, n_pending)
    elif not avail_by_key:
        log.warning("fa events %d: available page came back empty - option "
                    "inference skipped (page failure, not 77 exercises)",
                    class_year)
    else:
        # MASS-DROP HOLD (M04-05, 2026-09-25). The daily scrape now runs
        # through October too, so the disappearance heuristic gets ~30 more
        # looks a winter. The 2026-06-12 failure dropped EVERY pending row
        # at once with nothing re-listed; a real decision day always
        # re-lists some declined options as locked free agents. When at
        # least MASS_DROP_MIN_PENDING rows are pending, none is re-listed,
        # and MASS_DROP_SHARE of them vanished in one scrape, the vanished
        # rows stamp nothing and the night logs a warning; the next scrape
        # decides them. Declines (re-listed rows) are never held.
        pend = {k: p for k, p in prior.items() if p.get("status") == "pending_option"}
        for k, e in held_options.items():
            if k not in pend and k not in signing_keys:
                pend[k] = {"player_name": e.get("player_name"),
                           "position": e.get("position"),
                           "option_price_usd": e.get("option_price_usd"),
                           "status": "pending_option"}
        vanished =[k for k in pend if k not in avail_by_key and k not in signing_keys]
        relisted = [k for k in pend
                    if (avail_by_key.get(k) or {}).get("status") == "locked"]
        mass_drop = (len(pend) >= MASS_DROP_MIN_PENDING and not relisted
                     and len(vanished) >= MASS_DROP_SHARE * len(pend))
        if mass_drop:
            log.warning("fa events %d: %d of %d pending options vanished in one "
                        "scrape with none re-listed - option_exercised held for "
                        "this scrape (page restructure signature, 2026-06-12)",
                        class_year, len(vanished), len(pend))
        for key, p in pend.items():
            now = avail_by_key.get(key)
            base = {"player_name": p.get("player_name"), "position": p.get("position"),
                    "option_price_usd": p.get("option_price_usd")}
            if now is not None and now.get("status") == "locked":
                events.append({"player_key": key, "event_type": "option_declined",
                               "payload": base})
            elif now is None and key not in signing_keys and not mass_drop:
                events.append({"player_key": key, "event_type": "option_exercised",
                               "payload": base})

    qo_flips = []
    for key, now in avail_by_key.items():
        was = prior.get(key) or {}
        if ((now.get("qo") or now.get("qo_offered"))
                and not (was.get("qo") or was.get("qo_offered"))):
            qo_flips.append((key, now))
    if option_window:
        for key, now in qo_flips:
            events.append({"player_key": key, "event_type": "qo_offered",
                           "payload": {"player_name": now.get("player_name"),
                                       "position": now.get("position")}})
    elif qo_flips:
        log.info("fa events %d: %d qo flag flip(s) ignored - %s is outside "
                 "the QO window (offers open ~5 days post-World Series; "
                 "the window opens %s, %s; the 2026-08-12 defect stamped 16 "
                 "prior-winter flags as fresh offers)",
                 class_year, len(qo_flips), as_of.isoformat(),
                 window_opens.isoformat() if window_opens else "after the World Series",
                 window_basis)

    inserted = storage.insert_fa_events_first_seen(class_year, events)
    revalidated = 0
    if option_window:
        held_pairs = [(e["player_key"], e["event_type"]) for e in events
                      if e["event_type"] in WINTER_EVENT_TYPES]
        if held_pairs:
            revalidated = _revalidate_quarantined_events(
                class_year, held_pairs, as_of)
    # Reconcile the queryable status column: payload keeps the raw scrape;
    # status is the pipeline's view (board dims signed/exercised members).
    for e in events:
        if e["event_type"] == "signing":
            storage.set_fa_class_player_status(class_year, e["player_key"], "signed")
        elif e["event_type"] == "option_exercised":
            storage.set_fa_class_player_status(class_year, e["player_key"],
                                               "option_exercised")
    return {"observed": len(events), "inserted": inserted,
            "revalidated": revalidated, "signed_rows": len(signed_rows)}


# --------------------------------------------------------------------------- #
# Event quarantine (post-mortem 2026-08-12: 16 out-of-window qo_offered rows)
# --------------------------------------------------------------------------- #

QO_WINDOW_MONTHS = (10, 11, 12, 1)
# Months the daily job re-scrapes the class (run_monthly d10). It is the
# option / QO inference window plus the signing tail through March, derived
# here so the scrape window and the inference window cannot drift apart
# again: d10 used to run Nov-Mar while inference opened Oct 1, so an October
# decision was first seen on Nov 1 (M04-05, 2026-09-25).
DAILY_SCRAPE_MONTHS = tuple(sorted(set(QO_WINDOW_MONTHS) | {2, 3}))
MASS_DROP_MIN_PENDING = 10
MASS_DROP_SHARE = 0.9
QO_INVALID_REASON = ("qo_offered stamped outside the Oct-Jan QO window "
                     "(no window guard at stamp time; guard shipped "
                     "2026-08-19). Prior-winter QO flag misread as a fresh "
                     "offer.")


def quarantine_out_of_window_qo_events(class_year: int | None = None) -> dict:
    """Mark qo_offered events first-seen OUTSIDE the Oct-Jan window as
    invalidated. Rows are UPDATED in place (payload gains invalidated /
    invalid_reason / invalidated_at), never deleted - the ledger stays
    append-only and auditable. Idempotent; safe to re-run any day.

    One-off target: the 16 events of 2026-08-12 (class 2027), all
    prior-QO recipients whose historical flag the detector misread.
    Serving surfaces must read served_fa_events (or equivalently skip
    e["invalidated"]) so the nightly fa_class.json events block stops
    carrying quarantined rows."""
    import json as _json
    where = "WHERE event_type='qo_offered'"
    args: tuple = ()
    if class_year:
        where += " AND class_year=?"
        args = (class_year,)
    marked = already = 0
    with storage.connect() as con:
        rows = con.execute(
            f"SELECT class_year, player_key, event_date, payload_json "
            f"FROM fa_events {where}", args).fetchall()
        for yr, key, ev_date, pj in rows:
            try:
                month = int(str(ev_date)[5:7])
            except ValueError:
                month = 0
            if month in QO_WINDOW_MONTHS:
                continue
            payload = _json.loads(pj or "{}")
            if payload.get("invalidated"):
                already += 1
                continue
            payload["invalidated"] = True
            payload["invalid_reason"] = QO_INVALID_REASON
            payload["invalidated_at"] = date.today().isoformat()
            con.execute(
                "UPDATE fa_events SET payload_json=? "
                "WHERE class_year=? AND player_key=? AND event_type='qo_offered'",
                (_json.dumps(payload), yr, key))
            marked += 1
    if marked:
        log.info("fa events: quarantined %d out-of-window qo_offered row(s)"
                 " (%d already marked)", marked, already)
    return {"marked": marked, "already_marked": already}


def served_fa_events(class_year: int | None = None) -> list[dict]:
    """The event ledger AS IT SHOULD BE SERVED: load_fa_events minus
    invalidated rows. Quarantined rows stay in the DB (append-only) but
    never reach the wire, the Signing Tracker, or fa_class.json."""
    return [e for e in storage.load_fa_events(class_year)
            if not e.get("invalidated")]


def _revalidate_quarantined_events(class_year: int, pairs: list[tuple[str, str]],
                                   as_of: date) -> int:
    """A genuine IN-WINDOW observation supersedes a quarantined stamp of the
    same (player, event type): qo_offered, option_declined or
    option_exercised. The held first-seen date never became a valid
    observation, so the row re-dates to the first VALID one and the
    invalidation clears; the superseded date is kept in the payload for
    audit. Without this, INSERT OR IGNORE would silently pin the winter's
    real event to the quarantined date forever."""
    import json as _json
    n = 0
    with storage.connect() as con:
        for key, etype in pairs:
            row = con.execute(
                "SELECT event_date, payload_json FROM fa_events "
                "WHERE class_year=? AND player_key=? AND event_type=?",
                (class_year, key, etype)).fetchone()
            if not row:
                continue
            payload = _json.loads(row[1] or "{}")
            if not payload.get("invalidated"):
                continue
            for k in ("invalidated", "invalid_reason", "invalidated_at", "window_basis"):
                payload.pop(k, None)
            payload["superseded_invalid_first_seen"] = row[0]
            con.execute(
                "UPDATE fa_events SET event_date=?, payload_json=? "
                "WHERE class_year=? AND player_key=? AND event_type=?",
                (as_of.isoformat(), _json.dumps(payload), class_year, key, etype))
            n += 1
    if n:
        log.info("fa events %d: %d quarantined winter row(s) re-stamped "
                 "on genuine in-window observation", class_year, n)
    return n


# --------------------------------------------------------------------------- #
# The option and QO window (HOME_1, 2026-10-02)
# --------------------------------------------------------------------------- #

OPTION_EVENT_TYPES = ("option_declined", "option_exercised")
WINTER_EVENT_TYPES = OPTION_EVENT_TYPES + ("qo_offered",)
#: (month, day) the window opens when the postseason schedule cannot answer.
WINDOW_FALLBACK_OPEN = (11, 1)
#: An unfinished World Series read from a cache older than this many days
#: is a failed read (the nightly refetch stopped), so the fallback applies.
POSTSEASON_STALE_DAYS = 3
#: Where the postseason schedule cache lives (None: postseason.CACHE, the
#: file run_daily d8p refreshes). Tests point it at an empty directory.
POSTSEASON_CACHE_DIR = None
PREMATURE_REASON = ("{etype} first seen {seen}, before the class {year} option "
                    "and QO window opened ({opens}; {basis}). A Spotrac status "
                    "change seen before the day after the last World Series "
                    "game is not a decision; held until an in-window observation.")


def winter_window_opens(class_year: int, as_of: date | None = None,
                        cache_dir=None) -> tuple[date | None, str]:
    """(the day class ``class_year``'s option and QO window opens, basis).

    The window opens the day after the last final World Series game of
    season class_year - 1 (gameType W, codedGameState F or O, the latest
    officialDate), read from the StatsAPI postseason schedule cache that
    postseason.py writes nightly. A decided World Series gives that day.
    An unfinished one on a fresh cache gives None (not open yet). No file,
    no body, no game dates, or an unfinished series on a cache older than
    POSTSEASON_STALE_DAYS is a failed read: November 1 of season
    class_year - 1."""
    import json as _json
    from collections import Counter as _Counter
    from datetime import timedelta as _td
    import postseason
    season = int(class_year) - 1
    as_of = as_of or date.today()
    fallback = date(season, *WINDOW_FALLBACK_OPEN)
    path = postseason.cache_path(season, cache_dir or POSTSEASON_CACHE_DIR)
    try:
        doc = _json.loads(path.read_text(encoding="utf-8"))
        series = doc["body"]["series"]
        if not isinstance(series, list):
            raise TypeError("series is not a list")
    except (OSError, ValueError, KeyError, TypeError):
        return fallback, "fallback, no postseason schedule on disk"
    finals: dict = {}
    best_of = 0
    for s in series:
        meta = (s or {}).get("series") or {}
        for g in (s or {}).get("games") or []:
            if (g.get("gameType") or meta.get("gameType")) != "W":
                continue
            best_of = max(best_of, int(g.get("gamesInSeries") or 0))
            if ((g.get("status") or {}).get("codedGameState") or "") not in postseason.FINAL_CODES:
                continue
            winner = None
            for side in ("home", "away"):
                t = (g.get("teams") or {}).get(side) or {}
                if t.get("isWinner") is True:
                    winner = (t.get("team") or {}).get("id")
            finals[g.get("gamePk")] = (str(g.get("officialDate") or "")[:10], winner)
    wins = _Counter(w for _, w in finals.values() if w is not None)
    if best_of and wins and max(wins.values()) >= best_of // 2 + 1:
        days = [d for d, _ in finals.values() if d]
        if not days:
            return fallback, "fallback, the World Series games carry no dates"
        last = max(days)
        return (date.fromisoformat(last) + _td(days=1),
                f"StatsAPI schedule, last World Series game {last}")
    fetched = str(doc.get("fetched_at") or "")[:10]
    try:
        stale = (as_of - date.fromisoformat(fetched)).days > POSTSEASON_STALE_DAYS
    except ValueError:
        stale = True
    if stale:
        return fallback, f"fallback, postseason schedule last read {fetched or 'never'}"
    return None, f"StatsAPI schedule read {fetched}, {season} World Series not finished"


def winter_window_open(class_year: int, as_of: date | None = None,
                       cache_dir=None) -> tuple[bool, date | None, str]:
    """(is the window open on as_of, the day it opens, basis). It closes
    January 31 of class_year, so a future class (whose winter follows a
    later World Series) is never in window."""
    as_of = as_of or date.today()
    opens, basis = winter_window_opens(class_year, as_of, cache_dir)
    is_open = opens is not None and opens <= as_of <= date(int(class_year), 1, 31)
    return is_open, opens, basis


def quarantine_premature_winter_events(class_year: int | None = None,
                                       as_of: date | None = None,
                                       cache_dir=None) -> dict:
    """Hold every option_declined, option_exercised and qo_offered row first
    seen before its class's window opened (winter_window_opens), the way
    quarantine_out_of_window_qo_events holds the August QOs: the row is
    UPDATED in place (payload gains invalidated, invalid_reason,
    invalidated_at, window_basis), never deleted, so served_fa_events drops
    it and fa_class.json, the wire, the Club Ledger and /fa/ statuses stop
    carrying it. A held option_exercised row also returns its class row's
    status column to the as-scraped payload status. Idempotent. Returns
    {marked, already_marked, by_type, status_restored}."""
    import json as _json
    as_of = as_of or date.today()
    marks = ",".join("?" * len(WINTER_EVENT_TYPES))
    where, args = f"WHERE event_type IN ({marks})", tuple(WINTER_EVENT_TYPES)
    if class_year:
        where += " AND class_year=?"
        args += (int(class_year),)
    opens_by_year: dict = {}
    marked = already = 0
    by_type: dict = {}
    restored: list = []
    with storage.connect() as con:
        rows = con.execute(
            "SELECT class_year, player_key, event_type, event_date, payload_json "
            f"FROM fa_events {where} ORDER BY class_year, event_type, player_key",
            args).fetchall()
        for yr, key, etype, seen, pj in rows:
            payload = _json.loads(pj or "{}")
            if payload.get("invalidated"):
                already += 1
                continue
            if yr not in opens_by_year:
                opens_by_year[yr] = winter_window_opens(yr, as_of, cache_dir)
            opens, basis = opens_by_year[yr]
            if opens is not None and str(seen) >= opens.isoformat():
                continue
            payload["invalidated"] = True
            payload["invalid_reason"] = PREMATURE_REASON.format(
                etype=etype, seen=seen, year=yr, basis=basis,
                opens=opens.isoformat() if opens else "not yet open")
            payload["invalidated_at"] = as_of.isoformat()
            payload["window_basis"] = basis
            con.execute(
                "UPDATE fa_events SET payload_json=? "
                "WHERE class_year=? AND player_key=? AND event_type=?",
                (_json.dumps(payload), yr, key, etype))
            marked += 1
            by_type[f"{yr}:{etype}"] = by_type.get(f"{yr}:{etype}", 0) + 1
            if etype == "option_exercised":
                row = con.execute(
                    "SELECT status, payload_json FROM fa_class_players "
                    "WHERE class_year=? AND player_key=?", (yr, key)).fetchone()
                if row and row[0] == "option_exercised":
                    was = _json.loads(row[1] or "{}").get("status") or "pending_option"
                    con.execute(
                        "UPDATE fa_class_players SET status=? "
                        "WHERE class_year=? AND player_key=?", (was, yr, key))
                    restored.append(f"{yr}:{key}")
    if marked:
        log.info("fa events: held %d premature winter row(s) %s (%d already "
                 "held); status restored on %d", marked, by_type, already,
                 len(restored))
    return {"marked": marked, "already_marked": already, "by_type": by_type,
            "status_restored": restored}


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
    ap.add_argument("--quarantine", action="store_true",
                    help="hold option and QO stamps first seen before their window opened")
    args = ap.parse_args()
    if args.quarantine:
        print(quarantine_premature_winter_events())
    if args.backfill:
        print(backfill_historical(force=args.force))
    if args.current:
        cls = refresh_current_class(args.current, force=args.force)
        print({k: cls[k] for k in ("class_year", "reconciliation", "cba_note")},
              "players:", len(cls["players"]))
    if args.payroll:
        print("payroll rows:", refresh_payroll(force=args.force))
    if not (args.backfill or args.current or args.payroll or args.quarantine):
        ap.print_help()


if __name__ == "__main__":
    main()
