# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The fWAR label epoch's identity join (precondition E2): resolve, validate, land, report.

    python tools/efv_epoch_id_join.py pre        # the tripwire BEFORE any change (cached)
    python tools/efv_epoch_id_join.py resolve    # StatsAPI: search + bulk validate, writes the label-join file
    python tools/efv_epoch_id_join.py land       # player_photos binding + debuts.json / lite / shards in place
    python tools/efv_epoch_id_join.py fetch      # career_war for the F-VM-window debuts that have no row
    python tools/efv_epoch_id_join.py receipt    # the tripwire AFTER, beside the pre count: data/efv_epoch_id_join.json
    python tools/efv_epoch_id_join.py ledger     # one development row in data/efv_progress.json

docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md part 3 row E2; EFV3_PLAN.md section 3 (G6);
LANE_A.md section 1.5. The fWAR feed (data/fwar_vintage.json) joins on MLBAM, so a label
row whose key resolves to no id, or to the wrong human, loses its label at step C.

WHAT THE IDS FEED. The label join (tools/rebase_career_war.py, the career_war fetch) and
debuts.json's `mlbam_id`, and nothing else: an id landed by debut date is debut-correlated
(bug B4), so efv_identity never reads this file or any id it lands (test_efv_identity.py's
AST pin stands; efv_identity imports only milb_history).

THE RESOLVER PATTERN is tools/efv_oldcohort_id_resolve.py's: StatsAPI /people/search by
name; a candidate is accepted when its birthDate equals the record's and it reached MLB
(unique), else when it is the one candidate whose mlbDebutDate YEAR equals the record's
debut year. Zero ambiguous hits are accepted; every ambiguous hit goes to the manual review
list in the label-join file. A record whose birth date is impossible for its debut (age at
debut outside 16 to 45) has no birth validator, and the entry says so (`void`); a collided
record whose birth date is the photos-bound human's own (read from StatsAPI by that id)
records that evidence and the validator reads `collision`.

THE LABEL-JOIN FILE (data/sources/mlbam_id_label_join.json) carries every binding this tool
lands, with the StatsAPI evidence (fullName, birthDate, mlbDebutDate, fetched_at) beside
each, so test_debuts_ids_validated.py re-checks the landed ids offline. Entries whose
player_photos binding is the wrong human carry `replaces_photos`; step C's rebase reads
this file FIRST, then player_photos, then the override files.

THE TRIPWIRE (`tripwire()`): for every label row (a debuts.json record, adjudicated through
efv_dataset.TRAINING_IDENTITY, debut year in DEBUT_YEARS, side known, career_war row
present), every nonzero observed season of its label window has a feed row under its bound
id. Reported per side and debut cohort band. Coverage only, never accuracy (clause (l)).
"""
from __future__ import annotations

import argparse
import collections
import datetime as _dt
import json
import os
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

DATA = ROOT / "data"
DEBUTS = DATA / "debuts.json"
DEBUTS_LITE = DATA / "debuts_lite.json"
DEBUTS_FULL = DATA / "debuts_full"
OVERRIDES = DATA / "sources" / "mlbam_id_overrides.json"
LABEL_JOIN = DATA / "sources" / "mlbam_id_label_join.json"
RECEIPT = DATA / "efv_epoch_id_join.json"
CACHE_DIR = ROOT / ".cache" / "efv_epoch_id_join"
PRE_PATH = CACHE_DIR / "tripwire_pre.json"

SCHEMA = "efv_epoch_id_join/1"
LABEL_JOIN_SCHEMA = "mlbam_id_label_join/1"
MODEL_ID = "efv_identity_epoch_join"
LEDGER_FRAME = "lv_dev"
LEDGER_NOTE = "identity join for the fWAR epoch (E2), coverage counts only, no score"

UA = {"User-Agent": "eephus-io-datasourcing/1.0"}
SEARCH = "https://statsapi.mlb.com/api/v1/people/search?names="
PEOPLE = "https://statsapi.mlb.com/api/v1/people?personIds="
SLEEP = 0.25

#: Debut cohort bands the receipt reports. Label rows sit in the middle three
#: (efv_dataset.DEBUT_YEARS is 2011 through RESOLVED_THROUGH - 1).
BANDS = ("pre-2011", "2011-2016", "2017-2021", "2022-2024", "2025+")
#: The F-VM-window cohorts whose rows without a career_war row are fetched (step 3).
FETCH_COHORTS = (2017, 2021)
#: Birth dates outside this age-at-debut range cannot be the debutant's.
PLAUSIBLE_AGE = (16, 45)


# --------------------------------------------------------------------------- io
def _load(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: Path, obj, indent: int = 1) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, indent=indent, ensure_ascii=False, sort_keys=False) + "\n"
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _git_commit() -> str | None:
    import subprocess
    try:
        out = subprocess.run(["git", "rev-parse", "--short=8", "HEAD"], cwd=ROOT,
                             capture_output=True, text=True, check=False, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None


def band(debut_year: int | None) -> str:
    if debut_year is None:
        return "unknown"
    if debut_year < 2011:
        return BANDS[0]
    if debut_year <= 2016:
        return BANDS[1]
    if debut_year <= 2021:
        return BANDS[2]
    if debut_year <= 2024:
        return BANDS[3]
    return BANDS[4]


def norm(s: str | None) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return " ".join(s.lower().replace(".", "").replace("'", "").split())


# ----------------------------------------------------------------- StatsAPI
def fetch(url: str) -> dict:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read())


def _person(p: dict) -> dict:
    return {"id": p.get("id"), "fullName": p.get("fullName"),
            "mlbDebutDate": p.get("mlbDebutDate"), "birthDate": p.get("birthDate")}


class Api:
    """The two StatsAPI calls, cached on disk per name and per id so a re-run makes no
    second call for anything already answered."""

    def __init__(self, cache_dir: Path = CACHE_DIR, fetcher=fetch, sleep: float = SLEEP):
        self.dir = Path(cache_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.search_path = self.dir / "search_cache.json"
        self.people_path = self.dir / "people_cache.json"
        self.search_cache = _load(self.search_path) if self.search_path.exists() else {}
        self.people_cache = _load(self.people_path) if self.people_path.exists() else {}
        self.fetcher = fetcher
        self.sleep = sleep
        self.calls = 0

    def save(self) -> None:
        _write_json(self.search_path, self.search_cache, indent=0)
        _write_json(self.people_path, self.people_cache, indent=0)

    def search(self, name: str) -> list[dict] | dict:
        key = name.strip()
        if key in self.search_cache:
            return self.search_cache[key]
        try:
            d = self.fetcher(SEARCH + urllib.parse.quote(key))
            res = [_person(p) for p in (d.get("people") or [])]
        except Exception as exc:                       # recorded, never raised
            res = {"error": str(exc)}
        self.calls += 1
        self.search_cache[key] = res
        time.sleep(self.sleep)
        return res

    def people(self, ids: list[int]) -> dict[str, dict]:
        want = [str(i) for i in ids if str(i) not in self.people_cache]
        for i in range(0, len(want), 100):
            chunk = want[i:i + 100]
            try:
                d = self.fetcher(PEOPLE + ",".join(chunk))
                got = {str(p.get("id")): _person(p) for p in (d.get("people") or [])}
            except Exception as exc:
                got = {}
                for c in chunk:
                    self.people_cache[c] = {"error": str(exc)}
            self.calls += 1
            for c in chunk:
                if c in got:
                    self.people_cache[c] = got[c]
                elif c not in self.people_cache:
                    self.people_cache[c] = {"error": "not returned"}
            time.sleep(self.sleep)
        return {str(i): self.people_cache.get(str(i)) for i in ids}


# --------------------------------------------------------------- validation
def birth_plausible(birth_date: str | None, debut_year: int | None) -> bool:
    if not birth_date or not debut_year:
        return False
    try:
        by = int(str(birth_date)[:4])
    except ValueError:
        return False
    return PLAUSIBLE_AGE[0] <= debut_year - by <= PLAUSIBLE_AGE[1]


def pick(cands: list[dict], debut_year: int, birth_date: str | None) -> tuple[str, object]:
    """The old-cohort rule. Returns ("accepted", (person, route)), ("ambiguous", [persons])
    or ("none", reason). A birth date is a validator only when it is plausible for the
    debut year; the route says which validator accepted the candidate."""
    bd = birth_date if birth_plausible(birth_date, debut_year) else None
    yr = [c for c in cands if (c.get("mlbDebutDate") or "")[:4] == str(debut_year)]
    if bd:
        bd_match = [c for c in cands if c.get("birthDate") == bd and c.get("mlbDebutDate")]
        if len(bd_match) == 1:
            route = "birth_date+debut_year" if bd_match[0] in yr else "birth_date"
            return "accepted", (bd_match[0], route)
    if len(yr) == 1:
        return "accepted", (yr[0], "debut_year")
    if yr:
        return "ambiguous", yr
    return "none", f"{len(cands)} candidates, none debuted in {debut_year}"


def check_person(person: dict | None, debut_year: int | None, birth_date: str | None) -> dict:
    """The validation of one id against one record: debut year must match; the birth
    date must match when the record's is plausible."""
    if not person or person.get("error") or not person.get("id"):
        return {"ok": False, "why": "no StatsAPI person", "person": person}
    year_ok = bool(person.get("mlbDebutDate")) and debut_year is not None and \
        person["mlbDebutDate"][:4] == str(debut_year)
    bd_valid = birth_plausible(birth_date, debut_year)
    birth_ok = (person.get("birthDate") == birth_date) if bd_valid else None
    ok = year_ok and birth_ok is not False
    why = None if ok else ("debut year differs" if not year_ok else "birth date differs")
    return {"ok": ok, "why": why, "debut_year_match": year_ok, "birth_date_match": birth_ok,
            "birth_validator": "record" if bd_valid else "void", "person": person}


# ------------------------------------------------------------------- inputs
def load_debuts() -> list[dict]:
    return _load(DEBUTS)


def load_career_war() -> dict[str, dict]:
    import storage
    return storage.load_career_war()


def durable_ids() -> dict[str, int]:
    import rebase_career_war_to_ewar as L1
    return L1.durable_ids_by_key()


def override_ids() -> dict[str, int]:
    import rebase_career_war_to_ewar as L1
    return L1.override_ids()


def label_join_ids(path: Path = LABEL_JOIN) -> dict[str, int]:
    """{player_key: mlbam} from the label-join file (every entry, landed or not)."""
    if not Path(path).exists():
        return {}
    try:
        blob = _load(path)
    except (OSError, ValueError):
        return {}
    out = {}
    for k, e in (blob.get("entries") or {}).items():
        try:
            out[str(k)] = int(e["mlbam"])
        except (KeyError, TypeError, ValueError):
            continue
    return out


def resolve_bound(key: str, label_join: dict, durable: dict, overrides: dict
                  ) -> tuple[int | None, str | None]:
    """STEP C's ORDER: the label-join file, then player_photos, then the overrides."""
    if key in label_join:
        return label_join[key], "label_join"
    if key in durable:
        return durable[key], "photos"
    if key in overrides:
        return overrides[key], "override"
    return None, None


def players_rows(keys: list[str]) -> dict[str, dict]:
    import storage
    out = {}
    if not keys:
        return out
    with storage.connect() as con:
        for i in range(0, len(keys), 500):
            chunk = keys[i:i + 500]
            ph = ",".join("?" for _ in chunk)
            for r in con.execute(
                    f"SELECT player_key, player_name, birth_date, is_pitcher, position "
                    f"FROM players WHERE player_key IN ({ph})", chunk):
                out[r["player_key"]] = dict(r)
    return out


def record_side(rec: dict) -> str | None:
    import efv_dataset as D
    if D._side_match(rec, "pit"):
        return "pit"
    if D._side_match(rec, "hit"):
        return "hit"
    return None


def record_debut_year(rec: dict) -> int | None:
    import efv_dataset as D
    dd, _ph, _frm = D.debut_day_for_cutoff(rec)
    return int(dd[:4]) if dd else None


# ----------------------------------------------------------------- tripwire
def tripwire(debuts: list[dict], cw: dict[str, dict], totals, fwar_years,
             label_join: dict, durable: dict, overrides: dict, *,
             debut_years=None, target_seasons=None, resolved_through=None,
             identity=None) -> dict:
    """Every nonzero observed window season of every label row has a feed row under its
    bound id. Pure: the inputs are passed in, so the test runs it on fixtures.

    `totals` is fwar_vintage.season_totals (keys (mlbam, season)); `fwar_years` the
    seasons the vintage serves as fwar. Returns {"by": {"side|band": counts},
    "rows": [failing rows], "label_rows": n, "binding": {...}}."""
    import efv_dataset as D
    debut_years = tuple(debut_years or D.DEBUT_YEARS)
    target_seasons = int(target_seasons or D.TARGET_SEASONS)
    resolved_through = int(resolved_through or D.RESOLVED_THROUGH)
    identity = D.TRAINING_IDENTITY if identity is None else identity
    fwar_years = set(int(y) for y in fwar_years)
    by: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    bad: list[dict] = []
    binding = collections.Counter()
    label_rows = 0
    for rec in debuts:
        pk = rec.get("player_key")
        if pk in identity:
            adj = identity[pk]
            if adj.get("action") == "exclude":
                by["excluded_by_identity"]["rows"] += 1
                continue
            rec = dict(rec, mlbam_id=adj.get("mlbam_id"), birth_date=adj.get("birth_date"))
        dy = record_debut_year(rec)
        if not (pk and dy):
            continue
        if dy not in debut_years:
            continue
        side = record_side(rec)
        if side is None:
            by[f"unknown|{band(dy)}"]["rows_no_side"] += 1
            continue
        key = f"{side}|{band(dy)}"
        payload = cw.get(pk)
        if not payload:
            by[key]["rows_no_career_war"] += 1
            continue
        label_rows += 1
        seasons, _fell = D._label_seasons(payload)
        observed = [dy + i for i in range(target_seasons) if dy + i <= resolved_through]
        nonzero = [y for y in observed
                   if float(seasons.get(str(y), seasons.get(y, 0.0)) or 0.0) != 0.0]
        mid, how = resolve_bound(pk, label_join, durable, overrides)
        binding[how or "unbound"] += 1
        c = by[key]
        c["label_rows"] += 1
        c["nonzero_window_seasons"] += len(nonzero)
        if not nonzero:
            c["rows_no_nonzero_season"] += 1
            c["rows_kept"] += 1
            continue
        if mid is None:
            c["rows_unbound"] += 1
            c["seasons_unbound"] += len(nonzero)
            bad.append({"player_key": pk, "side": side, "debut_year": dy, "band": band(dy),
                        "bound": None, "how": None, "seasons": nonzero, "why": "unbound"})
            continue
        missing = [y for y in nonzero if y not in fwar_years or (int(mid), y) not in totals]
        if missing:
            c["rows_bound_no_feed"] += 1
            c["seasons_bound_no_feed"] += len(missing)
            bad.append({"player_key": pk, "side": side, "debut_year": dy, "band": band(dy),
                        "bound": int(mid), "how": how, "seasons": missing,
                        "why": "bound id has no feed row"})
        else:
            c["rows_kept"] += 1
    for k in list(by):
        by[k] = dict(sorted(by[k].items()))
    return {"label_rows": label_rows, "rows_failing": len(bad),
            "by": dict(sorted(by.items())), "rows": bad, "binding": dict(binding)}


def live_inputs():
    import fwar_vintage
    blob = fwar_vintage.load()
    return {"debuts": load_debuts(), "cw": load_career_war(),
            "totals": fwar_vintage.season_totals(blob),
            "fwar_years": fwar_vintage.fwar_seasons(blob),
            "vintage_id": blob.get("vintage_id"),
            "label_join": label_join_ids(), "durable": durable_ids(),
            "overrides": override_ids()}


def run_tripwire_live() -> dict:
    inp = live_inputs()
    out = tripwire(inp["debuts"], inp["cw"], inp["totals"], inp["fwar_years"],
                   inp["label_join"], inp["durable"], inp["overrides"])
    out["vintage_id"] = inp["vintage_id"]
    out["career_war_rows"] = len(inp["cw"])
    out["generated_at"] = _now()
    return out


# ------------------------------------------------------------------ resolve
LANDED_PATH = CACHE_DIR / "landed.json"


def _landed_before(path: Path = LABEL_JOIN, sidecar: Path = LANDED_PATH) -> dict[str, int]:
    """{player_key: mlbam} this tool landed into debuts.json on an earlier run (the
    label-join file's landed entries, united with the land step's own sidecar), so a
    re-run keeps treating those records as the id-less records they were (idempotent
    after `land`)."""
    out: dict[str, int] = {}
    if Path(sidecar).exists():
        try:
            out.update({k: int(v) for k, v in (_load(sidecar).get("landed") or {}).items()})
        except (OSError, ValueError, TypeError):
            pass
    if Path(path).exists():
        try:
            blob = _load(path)
        except (OSError, ValueError):
            return out
        for k, e in (blob.get("entries") or {}).items():
            if e.get("landed_in_debuts") and e.get("mlbam") is not None:
                out[k] = int(e["mlbam"])
    return out


def _record_no_id(rec: dict, landed: dict[str, int]) -> bool:
    mid = rec.get("mlbam_id")
    if not mid:
        return True
    pk = rec.get("player_key")
    return pk in landed and int(mid) == landed[pk]


def resolve_targets(debuts: list[dict], cw: dict[str, dict], pre: dict,
                    durable: dict, overrides: dict, landed: dict | None = None
                    ) -> dict[str, list[dict]]:
    """The three target sets of step (2): the no-id debuts.json records no route covers,
    the bbref-only career_war keys outside debuts.json, and the label rows whose
    player_photos binding has no feed row (the collided slugs). `landed` names the ids an
    earlier run of this tool put on the records (and into player_photos), so they still
    count as id-less here and the run is idempotent."""
    landed = landed or {}
    # a key the override asset covers is validated by validate_overrides, never
    # searched; a key this tool landed FROM a search is searched again (cached)
    index = (set(durable) | set(overrides)) - {k for k in landed if k not in overrides}
    no_id = []
    for rec in debuts:
        pk = rec.get("player_key")
        if not pk or not _record_no_id(rec, landed) or pk in index:
            continue
        no_id.append({"player_key": pk, "name": rec.get("player_name"),
                      "debut_year": record_debut_year(rec), "birth_date": rec.get("birth_date"),
                      "set": "no_id_debut", "record_mlbam": None})
    deb_keys = {r.get("player_key") for r in debuts}
    outside_keys = sorted(k for k, p in cw.items()
                          if (p or {}).get("source") == "bbref" and k not in deb_keys
                          and k not in index)
    prow = players_rows(outside_keys)
    outside = []
    for k in outside_keys:
        p = cw[k]
        seasons = [int(y) for y in (p.get("seasons") or {})]
        pr = prow.get(k) or {}
        outside.append({"player_key": k, "name": pr.get("player_name"),
                        "debut_year": min(seasons) if seasons else None,
                        "birth_date": pr.get("birth_date"), "set": "bbref_outside_debuts",
                        "record_mlbam": None,
                        "debut_year_source": "first career_war season"})
    rec_by = {r.get("player_key"): r for r in debuts}
    collided = []
    for row in pre.get("rows") or []:
        if row.get("why") != "bound id has no feed row":
            continue
        rec = rec_by.get(row["player_key"]) or {}
        collided.append({"player_key": row["player_key"], "name": rec.get("player_name"),
                         "debut_year": row["debut_year"], "birth_date": rec.get("birth_date"),
                         "set": "photos_no_feed_row", "record_mlbam": rec.get("mlbam_id"),
                         "photos_mlbam": row.get("bound")})
    record_id = []
    for row in pre.get("rows") or []:
        if row.get("why") != "unbound" or row["player_key"] in landed:
            continue
        rec = rec_by.get(row["player_key"]) or {}
        if rec.get("mlbam_id"):
            record_id.append({"player_key": row["player_key"], "name": rec.get("player_name"),
                              "debut_year": row["debut_year"], "birth_date": rec.get("birth_date"),
                              "set": "record_id_not_durable", "record_mlbam": rec.get("mlbam_id")})
    return {"no_id_debut": no_id, "bbref_outside_debuts": outside,
            "photos_no_feed_row": collided, "record_id_not_durable": record_id}


def resolve(api: Api, debuts: list[dict], cw: dict[str, dict], pre: dict,
            durable: dict, overrides: dict, now: str, landed: dict | None = None) -> dict:
    targets = resolve_targets(debuts, cw, pre, durable, overrides, landed)
    entries: dict[str, dict] = {}
    review: list[dict] = []
    counts: dict[str, collections.Counter] = {s: collections.Counter() for s in targets}
    for set_name, rows in targets.items():
        for t in rows:
            pk, name, dy, bd = t["player_key"], t["name"], t["debut_year"], t["birth_date"]
            if not name or not dy:
                counts[set_name]["no_name_or_year"] += 1
                review.append({**t, "status": "no name or debut year to search on"})
                continue
            if t.get("record_mlbam") and set_name == "record_id_not_durable":
                # the record already carries an id: validate that id, no search
                person = api.people([int(t["record_mlbam"])]).get(str(t["record_mlbam"]))
                chk = check_person(person, dy, bd)
                if chk["ok"]:
                    counts[set_name]["accepted"] += 1
                    entries[pk] = _entry(pk, person, "record_id_validated", t, chk, now)
                else:
                    counts[set_name]["rejected"] += 1
                    review.append({**t, "status": f"record id fails validation: {chk['why']}",
                                   "person": person})
                continue
            collision = None
            if set_name == "photos_no_feed_row" and t.get("photos_mlbam") and bd:
                # the record is a fusion: when the photos-bound human carries the
                # record's birth date, that date is the other human's and is no
                # validator for this row (recorded as evidence on the entry)
                other = api.people([int(t["photos_mlbam"])]).get(str(t["photos_mlbam"]))
                if other and not other.get("error") and other.get("birthDate") == bd:
                    collision = {"photos_mlbam": int(t["photos_mlbam"]),
                                 "fullName": other.get("fullName"),
                                 "birthDate": other.get("birthDate"),
                                 "mlbDebutDate": other.get("mlbDebutDate")}
                    bd = None
            res = api.search(name)
            if isinstance(res, dict):
                counts[set_name]["search_error"] += 1
                review.append({**t, "status": f"search error: {res.get('error')}"})
                continue
            searched = name
            if not res and len(name.split()) > 1:
                # the full name returned nobody: one more search on the surname, the
                # same validators decide (a surname hit without a unique debut-year or
                # birth-date match is still ambiguous or none)
                surname = name.split()[-1]
                res2 = api.search(surname)
                if isinstance(res2, list) and res2:
                    res, searched = res2, surname
                    counts[set_name]["surname_search"] += 1
            verdict, payload = pick(res, dy, bd)
            if verdict == "accepted":
                person, route = payload
                chk = check_person(person, dy, bd)
                e = _entry(pk, person, route, t, chk, now)
                if searched != name:
                    e["searched_as"] = searched
                if collision:
                    e["record"]["birth_validator"] = "collision"
                    e["record"]["collision"] = collision
                if set_name == "photos_no_feed_row":
                    e["replaces_photos"] = t.get("photos_mlbam")
                    if int(person["id"]) == int(t.get("photos_mlbam") or -1):
                        counts[set_name]["same_as_photos"] += 1
                        review.append({**t, "status": "search returns the photos id itself; "
                                       "the feed has no row for it", "person": person})
                        continue
                counts[set_name]["accepted"] += 1
                entries[pk] = e
            elif verdict == "ambiguous":
                counts[set_name]["ambiguous"] += 1
                review.append({**t, "status": "ambiguous: more than one candidate debuted "
                               "that year and no birth date settles it",
                               "candidates": payload})
            else:
                counts[set_name]["none"] += 1
                review.append({**t, "status": payload,
                               "candidates": res[:6] if isinstance(res, list) else None})
    return {"entries": entries, "manual_review": review,
            "counts": {k: dict(v) for k, v in counts.items()},
            "targets": {k: len(v) for k, v in targets.items()}}


def _entry(pk: str, person: dict, route: str, t: dict, chk: dict, now: str) -> dict:
    return {"mlbam": int(person["id"]), "set": t["set"], "route": route,
            "record": {"name": t.get("name"), "debut_year": t.get("debut_year"),
                       "debut_year_source": t.get("debut_year_source", "record debut_date"),
                       "birth_date": t.get("birth_date"),
                       "birth_validator": chk.get("birth_validator")},
            "statsapi": {"fullName": person.get("fullName"), "birthDate": person.get("birthDate"),
                         "mlbDebutDate": person.get("mlbDebutDate"), "fetched_at": now},
            "landed_in_debuts": False}


def validate_overrides(api: Api, debuts: list[dict], overrides: dict, now: str,
                       landed: dict | None = None) -> dict:
    """The override asset's ids that cover a no-id debuts.json record (or one this tool
    landed on an earlier run), each re-read from StatsAPI and checked against the
    record's debut year and birth date."""
    landed = landed or {}
    rec_by = {r.get("player_key"): r for r in debuts}
    keys = sorted(k for k in overrides if k in rec_by and _record_no_id(rec_by[k], landed))
    people = api.people([overrides[k] for k in keys])
    ok, rejected = {}, []
    for k in keys:
        rec = rec_by[k]
        dy = record_debut_year(rec)
        person = people.get(str(overrides[k]))
        chk = check_person(person, dy, rec.get("birth_date"))
        if chk["ok"]:
            ok[k] = {"mlbam": int(overrides[k]), "set": "override_asset", "route": "override_revalidated",
                     "record": {"name": rec.get("player_name"), "debut_year": dy,
                                "debut_year_source": "record debut_date",
                                "birth_date": rec.get("birth_date"),
                                "birth_validator": chk.get("birth_validator")},
                     "statsapi": {"fullName": (person or {}).get("fullName"),
                                  "birthDate": (person or {}).get("birthDate"),
                                  "mlbDebutDate": (person or {}).get("mlbDebutDate"),
                                  "fetched_at": now},
                     "landed_in_debuts": False}
        else:
            rejected.append({"player_key": k, "mlbam": overrides[k], "set": "override_asset",
                             "name": rec.get("player_name"), "debut_year": dy,
                             "birth_date": rec.get("birth_date"),
                             "status": f"override id fails validation: {chk['why']}",
                             "person": person})
    return {"covering": len(keys), "validated": ok, "rejected": rejected}


def write_label_join(entries: dict, review: list, meta: dict, path: Path = LABEL_JOIN) -> None:
    """Writes the file; a re-run after `land` keeps the landed state (the `landed` block
    and each entry's landed_in_debuts) for every entry whose id did not change."""
    prev = _load(path) if Path(path).exists() else {}
    landed = _landed_before(path)
    for k, e in entries.items():
        if k in landed and int(landed[k]) == int(e["mlbam"]):
            e["landed_in_debuts"] = True
    doc = {"schema": LABEL_JOIN_SCHEMA, "generated_at": meta["generated_at"],
           "commit": meta.get("commit"),
           "rule": ("every entry was read from StatsAPI (/people/search by name, or /people by "
                    "id) and accepted only when its mlbDebutDate year equals the record's debut "
                    "year and, where the record's birth date is plausible for that debut, its "
                    "birthDate equals it; zero ambiguous hits accepted, each listed under "
                    "manual_review. Consumers: the label join (tools/rebase_career_war.py reads "
                    "entries FIRST, then player_photos, then the override files; the career_war "
                    "fetch) and debuts.json's mlbam_id. efv_identity never reads this file."),
           "counts": meta.get("counts"),
           "entries": {k: entries[k] for k in sorted(entries)},
           "manual_review": review}
    if prev.get("landed"):
        doc["landed"] = prev["landed"]
    _write_json(path, doc)


# --------------------------------------------------------------------- land
#: debuts_lite.json's scalar order (storage._LITE_SCALARS): a null scalar is omitted from
#: a lite record, so a landed id is inserted at its place in this order.
LITE_SCALARS = (
    "player_key", "player_name", "position", "org", "age", "status",
    "debut_date", "current_level", "mlbam_id", "fv_close", "fv_close_raw",
    "fv_label", "fv_close_plus", "fv_total_instances", "overall_rank",
    "prev_overall_rank", "org_rank", "org_rank_total", "statcast_plus",
    "dollar_dvm_plus", "breakout_flag",
)


def _dump_bytes(obj) -> bytes:
    """storage._dump's serializer: orjson compact with OPT_NON_STR_KEYS, else the stdlib
    compact form with ensure_ascii off (byte-equivalent on these payloads)."""
    try:
        import orjson
        return orjson.dumps(obj, option=orjson.OPT_NON_STR_KEYS)
    except ImportError:
        return json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _with_id(rec: dict, mid: int, lite: bool) -> dict:
    if "mlbam_id" in rec or not lite:
        out = dict(rec)
        out["mlbam_id"] = int(mid)
        return out
    out = {}
    placed = False
    for k, v in rec.items():
        if not placed and k in LITE_SCALARS and LITE_SCALARS.index(k) > LITE_SCALARS.index("mlbam_id"):
            out["mlbam_id"] = int(mid)
            placed = True
        out[k] = v
    if not placed:
        out["mlbam_id"] = int(mid)
    return out


class RoundTripError(RuntimeError):
    pass


def patch_ids_in_file(path: Path, ids: dict[str, int], *, lite: bool = False) -> dict:
    """Set `mlbam_id` on the named records (a list of records, or one record for a
    debuts_full shard) and re-dump the file exactly as storage._dump would. The parse and
    re-dump of the UNCHANGED payload must reproduce the file byte for byte first, or
    nothing is written (RoundTripError). A record that already carries a different id is
    left alone and listed. Returns {patched, missing, kept_other_id}."""
    path = Path(path)
    raw = path.read_bytes()
    obj = json.loads(raw)
    if _dump_bytes(obj) != raw:
        raise RoundTripError(f"{path.name}: re-dump is not byte-identical; not patched")
    patched, missing, other = [], [], []
    if isinstance(obj, list):
        pos = {r.get("player_key"): i for i, r in enumerate(obj) if isinstance(r, dict)}
        for key, mid in ids.items():
            i = pos.get(key)
            if i is None:
                missing.append(key)
                continue
            cur = obj[i].get("mlbam_id")
            if cur and int(cur) != int(mid):
                other.append(key)
                continue
            obj[i] = _with_id(obj[i], mid, lite)
            patched.append(key)
    else:
        key = obj.get("player_key")
        if key not in ids:
            missing.extend(ids)
        else:
            cur = obj.get("mlbam_id")
            if cur and int(cur) != int(ids[key]):
                other.append(key)
            else:
                obj = _with_id(obj, ids[key], lite)
                patched.append(key)
    if patched:
        tmp = path.with_name(path.name + f".tmp{os.getpid()}")
        tmp.write_bytes(_dump_bytes(obj))
        os.replace(tmp, path)
    return {"patched": len(patched), "missing": missing, "kept_other_id": other}


def land(entries: dict, debuts: list[dict]) -> dict:
    """Bind the validated ids of no-id debuts.json records into player_photos (the
    export's durable id source), then set them on debuts.json, debuts_lite.json and the
    debuts_full shards in place. Only entries whose record carries no id are landed; a
    key player_photos already binds to another id, or an id another key owns, is skipped
    and listed."""
    import storage
    rec_by = {r.get("player_key"): r for r in debuts}
    cand = {k: int(e["mlbam"]) for k, e in entries.items()
            if k in rec_by and not rec_by[k].get("mlbam_id")}
    with storage.connect() as con:
        rows = con.execute("SELECT player_key, mlbam_id FROM player_photos "
                           "WHERE player_key IS NOT NULL").fetchall()
    existing = {r[0]: int(r[1]) for r in rows if r[1] is not None}
    owner_of = {int(r[1]): r[0] for r in rows if r[1] is not None}
    to_bind, skipped = {}, []
    for k, mid in sorted(cand.items()):
        prior = existing.get(k)
        if prior is not None and prior != mid:
            skipped.append({"player_key": k, "mlbam": mid, "why": f"key already bound to {prior}"})
            continue
        owner = owner_of.get(mid)
        if owner is not None and owner != k:
            skipped.append({"player_key": k, "mlbam": mid, "why": f"id owned by {owner}"})
            continue
        to_bind[k] = mid
    bound_new = storage.bind_player_ids({k: v for k, v in to_bind.items() if k not in existing})
    files = {"debuts.json": patch_ids_in_file(DEBUTS, to_bind)}
    if DEBUTS_LITE.exists():
        files["debuts_lite.json"] = patch_ids_in_file(DEBUTS_LITE, to_bind, lite=True)
    shards = {"patched": 0, "missing": [], "kept_other_id": [], "absent": 0}
    for k, mid in to_bind.items():
        p = DEBUTS_FULL / f"{k}.json"
        if not p.exists():
            shards["absent"] += 1
            continue
        r = patch_ids_in_file(p, {k: mid})
        shards["patched"] += r["patched"]
        shards["missing"] += r["missing"]
        shards["kept_other_id"] += r["kept_other_id"]
    files["debuts_full"] = shards
    for k in to_bind:
        entries[k]["landed_in_debuts"] = True
    # the land step's own durable record of what it landed (union across runs)
    prev = _landed_before(sidecar=LANDED_PATH)
    prev.update(to_bind)
    _write_json(LANDED_PATH, {"landed": {k: prev[k] for k in sorted(prev)}, "at": _now()}, indent=0)
    for k, mid in prev.items():
        if k in entries and int(entries[k].get("mlbam", -1)) == int(mid):
            entries[k]["landed_in_debuts"] = True
    return {"candidates": len(cand), "bound_in_player_photos": bound_new,
            "already_bound_same_id": sum(1 for k in to_bind if k in existing),
            "landed": len(to_bind), "skipped": skipped, "files": files}


# -------------------------------------------------------------------- fetch
def fetch_targets(debuts: list[dict], cw: dict, label_join: dict, durable: dict,
                  overrides: dict, cohorts=FETCH_COHORTS) -> tuple[list, list]:
    """(targets, no_id): debuts of the F-VM-window cohorts with no career_war row."""
    targets, no_id = [], []
    for rec in debuts:
        pk = rec.get("player_key")
        dy = record_debut_year(rec)
        if not pk or not dy or not (cohorts[0] <= dy <= cohorts[1]) or pk in cw:
            continue
        side = record_side(rec)
        mid = rec.get("mlbam_id")
        if not mid:
            mid, _how = resolve_bound(pk, label_join, durable, overrides)
        if not mid or side is None:
            no_id.append({"player_key": pk, "debut_year": dy, "side": side, "mlbam": mid})
            continue
        targets.append((pk, int(mid), side == "pit"))
    return targets, no_id


def fetch_career_war(targets: list, end_year: int) -> dict:
    """The nightly's own door: war_source.career_war_bulk on the DEFAULT provider, the
    window floored at 2011 (run_monthly step 3d), stored through storage.upsert_career_war."""
    import storage
    import war_source
    if not targets:
        return {"requested": 0, "fetched": 0, "written": 0, "provider": war_source.DEFAULT_PROVIDER}
    data = war_source.career_war_bulk(targets, start_year=2011, end_year=end_year)
    n = storage.upsert_career_war(data) if data else 0
    return {"requested": len(targets), "fetched": len(data or {}), "written": n,
            "provider": war_source.DEFAULT_PROVIDER,
            "missing": sorted(k for k, _m, _p in targets if k not in (data or {}))}


# ------------------------------------------------------------------ receipt
def kept_table(tw: dict) -> dict:
    """{side|band: rows_kept} from a tripwire run (coverage only)."""
    return {k: int((v or {}).get("rows_kept", 0)) for k, v in (tw.get("by") or {}).items()
            if "|" in k and not k.startswith("unknown")}


def build_receipt(pre: dict, post: dict, meta: dict) -> dict:
    kept_pre, kept_post = kept_table(pre), kept_table(post)
    keys = sorted(set(kept_pre) | set(kept_post))
    return {
        "schema": SCHEMA, "generated_at": meta["generated_at"], "commit": meta.get("commit"),
        "vintage_id": post.get("vintage_id"),
        "rule": ("coverage only, never accuracy (FWAR_LABEL_EPOCH_GATE.md clause (l)): a label "
                 "row is kept when every nonzero observed season of its label window has a "
                 "feed row under its bound id; bound = the label-join file, then "
                 "player_photos, then the override files, which is step C's order"),
        "label_window": {"target_seasons": meta.get("target_seasons"),
                         "resolved_through": meta.get("resolved_through"),
                         "debut_years": [meta.get("debut_years")[0], meta.get("debut_years")[-1]]},
        "kept": {"by_side_and_band": {k: {"before": kept_pre.get(k, 0), "after": kept_post.get(k, 0)}
                                      for k in keys},
                 "total": {"before": sum(kept_pre.values()), "after": sum(kept_post.values())}},
        "label_rows": {"before": pre.get("label_rows"), "after": post.get("label_rows")},
        "rows_failing": {"before": pre.get("rows_failing"), "after": post.get("rows_failing")},
        "career_war_rows": {"before": pre.get("career_war_rows"), "after": post.get("career_war_rows")},
        "binding": {"before": pre.get("binding"), "after": post.get("binding")},
        "by_side_and_band": {"before": pre.get("by"), "after": post.get("by")},
        "failing_rows_after": post.get("rows"),
        "steps": meta.get("steps"),
        "manual_review_keys": meta.get("manual_review_keys"),
    }


def ledger_row(receipt: dict, path: Path, *, now_iso: str) -> dict:
    import efv_progress as P
    import efv_dataset as D
    by = receipt["by_side_and_band"]["after"] or {}
    n_by_side = {s: sum(int((v or {}).get("rows_kept", 0)) for k, v in by.items()
                        if k.startswith(f"{s}|")) for s in P.STRATA}
    sha = P._sha256(path)
    row = {"run_id": None, "date": receipt["generated_at"][:10], "trigger": "data_correction",
           "model_id": MODEL_ID,
           "model_version": {"fingerprint": None, "commit": receipt.get("commit"),
                             "label": D._label_provider() if hasattr(D, "_label_provider") else None,
                             "resolved_through": D.RESOLVED_THROUGH,
                             "provider": None},
           "frame": LEDGER_FRAME, "frame_version": None,
           "role": P.FRAMES[LEDGER_FRAME]["role"], "tilted": bool(P.FRAMES[LEDGER_FRAME]["tilted"]),
           "window": [D.DEBUT_YEARS[0], D.DEBUT_YEARS[-1]],
           "n": receipt["kept"]["total"]["after"], "n_by_side": n_by_side,
           "raters": {}, "deltas": {}, "resolvable": None,
           "verdict": "coverage only, no score", "share": None,
           "sources": [{"path": P._rel(Path(path)), "generated_at": receipt["generated_at"],
                        "sha256": sha}],
           "note": (f"{LEDGER_NOTE}; label rows kept {receipt['kept']['total']['before']} -> "
                    f"{receipt['kept']['total']['after']}; failing rows "
                    f"{receipt['rows_failing']['before']} -> {receipt['rows_failing']['after']}"),
           "last_verified_at": now_iso}
    row["content_hash"] = P.content_hash(row)
    row["run_id"] = f"{receipt['generated_at']}|{LEDGER_FRAME}|{row['content_hash'][:8]}"
    return row


def append_ledger(receipt: dict, path: Path = RECEIPT, *, ledger_path=None) -> dict:
    import efv_progress as P
    now_iso = P._now_iso()
    sb_path = P.DATA_DIR / P.SB_NAME
    sb = P._load_json(sb_path) if sb_path.exists() else None
    row = ledger_row(receipt, path, now_iso=now_iso)
    return P.commit_rows([row], ledger_path=ledger_path, sb=sb, now_iso=now_iso)


# --------------------------------------------------------------------- main
def _meta_now() -> dict:
    import efv_dataset as D
    return {"generated_at": _now(), "commit": _git_commit(),
            "target_seasons": D.TARGET_SEASONS, "resolved_through": D.RESOLVED_THROUGH,
            "debut_years": list(D.DEBUT_YEARS)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("step", choices=("pre", "resolve", "land", "fetch", "receipt", "ledger", "tripwire"))
    ap.add_argument("--ledger-path", default=None)
    ap.add_argument("--end-year", type=int, default=_dt.date.today().year)
    args = ap.parse_args(argv)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    steps_path = CACHE_DIR / "steps.json"
    steps = _load(steps_path) if steps_path.exists() else {}

    if args.step in ("pre", "tripwire"):
        tw = run_tripwire_live()
        if args.step == "pre":
            _write_json(PRE_PATH, tw)
            print(f"wrote {PRE_PATH}")
        print(json.dumps({"label_rows": tw["label_rows"], "rows_failing": tw["rows_failing"],
                          "binding": tw["binding"], "by": tw["by"]}, indent=1))
        return 0

    if args.step == "resolve":
        if not PRE_PATH.exists():
            print("run `pre` first")
            return 2
        pre = _load(PRE_PATH)
        api = Api()
        debuts, cw = load_debuts(), load_career_war()
        durable, overrides = durable_ids(), override_ids()
        now = _now()
        landed_before = _landed_before()
        res = resolve(api, debuts, cw, pre, durable, overrides, now, landed_before)
        api.save()
        val = validate_overrides(api, debuts, overrides, now, landed_before)
        api.save()
        entries = dict(val["validated"])
        entries.update(res["entries"])
        review = res["manual_review"] + val["rejected"]
        counts = {"targets": res["targets"], "by_set": res["counts"],
                  "override_asset": {"covering_no_id_records": val["covering"],
                                     "validated": len(val["validated"]),
                                     "rejected": len(val["rejected"])},
                  "entries": len(entries), "manual_review": len(review),
                  "statsapi_calls": api.calls}
        write_label_join(entries, review, {"generated_at": now, "commit": _git_commit(),
                                           "counts": counts})
        steps["resolve"] = {"at": now, **counts}
        _write_json(steps_path, steps)
        print(json.dumps(counts, indent=1))
        print(f"wrote {LABEL_JOIN}")
        return 0

    if args.step == "land":
        blob = _load(LABEL_JOIN)
        entries = blob["entries"]
        r = land(entries, load_debuts())
        blob["entries"] = entries
        blob["landed"] = {"at": _now(), **{k: v for k, v in r.items() if k != "skipped"},
                          "skipped": r["skipped"]}
        _write_json(LABEL_JOIN, blob)
        steps["land"] = {"at": blob["landed"]["at"], "landed": r["landed"],
                         "bound_in_player_photos": r["bound_in_player_photos"],
                         "skipped": len(r["skipped"]), "files": r["files"]}
        _write_json(steps_path, steps)
        print(json.dumps(steps["land"], indent=1, default=str))
        return 0

    if args.step == "fetch":
        debuts, cw = load_debuts(), load_career_war()
        targets, no_id = fetch_targets(debuts, cw, label_join_ids(), durable_ids(), override_ids())
        r = fetch_career_war(targets, args.end_year)
        r["no_id"] = no_id
        r["cohorts"] = list(FETCH_COHORTS)
        steps["fetch"] = {"at": _now(), **r}
        _write_json(steps_path, steps)
        print(json.dumps(steps["fetch"], indent=1, default=str))
        return 0

    if args.step == "receipt":
        if not PRE_PATH.exists():
            print("run `pre` first")
            return 2
        pre = _load(PRE_PATH)
        post = run_tripwire_live()
        meta = _meta_now()
        meta["steps"] = steps
        lj = _load(LABEL_JOIN) if LABEL_JOIN.exists() else {}
        meta["manual_review_keys"] = sorted({r.get("player_key") for r in lj.get("manual_review") or []
                                             if r.get("player_key")})
        rec = build_receipt(pre, post, meta)
        _write_json(RECEIPT, rec)
        print(json.dumps({"kept": rec["kept"], "rows_failing": rec["rows_failing"],
                          "label_rows": rec["label_rows"], "binding": rec["binding"]}, indent=1))
        print(f"wrote {RECEIPT}")
        return 0

    if args.step == "ledger":
        rec = _load(RECEIPT)
        res = append_ledger(rec, RECEIPT, ledger_path=args.ledger_path)
        print(json.dumps(res, indent=1))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
