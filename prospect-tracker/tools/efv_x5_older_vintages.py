# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV X5 older list vintages: fetch, ingest and count (docs/efv-v2/EFV_X5_OLDER_VINTAGES.md).

COUNTS ONLY. Builds the dated board points of every eligible older prospect list and the
census of the (side, list vintage, person) rows the development list-vintage frame gains,
with the minimum detectable effect before and after. No outcome, label, eFV, consensus or
source score is read or computed. Nothing served moves.

Writes (both under data/_labs/efv_x5/, which ships in neither deploy consumer):
  older_vintage_points.json   the ingested lists as universe-shaped records, one dated
                              point per list a printed name appears on
  older_vintage_census.json   per source and list year: coverage, dating, terms, match
                              rate and eligibility; per (side, vintage): augmented rows,
                              gained rows; the floor arithmetic of registration s7

Raw captures live in .cache/EFV_X5_OLDER_VINTAGES/ (gitignored), keyed by the sha1 of the
URL. The default run reads the cache only; --fetch lets a missing page be fetched (one
request per FETCH_GAP_S seconds, identifying user agent).

Run:  python tools/efv_x5_older_vintages.py --write          (cache only)
      python tools/efv_x5_older_vintages.py --fetch --write  (fill the cache first)
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import efv_identity as ID  # noqa: E402
import efv_vintage_frame as F  # noqa: E402
import efv_x5_older_vintages as X  # noqa: E402

CENSUS_REF = ROOT / "data" / "efv_label_pool_census.json"
USER_AGENT = "eephus.io-prospect-tracker/1.0 (research; arkndjl@gmail.com)"
FETCH_GAP_S = 2.5
WAYBACK = "https://web.archive.org"

#: BA all-time Top 100 index, the capture whose lists are parsed (1990 to 2017).
BA_ALLTIME = ("20170706052616",
              "http://www.baseballamerica.com/today/prospects/rankings/top-100-prospects/all-time.php")
BA_ALLTIME_PATTERN = "baseballamerica.com/today/prospects/rankings/top-100-prospects/all-time.php"
#: The dated BA year pages (the list as first published, split in parts from 2008 on):
#: the first page's dateline is the publication date, and every part's text is the
#: cross-check of the all-time index.
_BA_Y = "http://www.baseballamerica.com:80/today/prospects/rankings/top-100-prospects"
BA_YEAR_PAGES: dict[int, list[tuple[str, str]]] = {
    2006: [("20100212124912", f"{_BA_Y}/2006/26660.html")],
    2007: [("20100106115156", "http://www.baseballamerica.com/today/prospects/rankings/"
                              "top-100-prospects/2007/263445.html")],
    2008: [("20080302072338", f"{_BA_Y}/2008/265655.html"),
           ("20080301231024", f"{_BA_Y}/2008/265657.html"),
           ("20080302072353", f"{_BA_Y}/2008/265658.html"),
           ("20080302072359", f"{_BA_Y}/2008/265659.html"),
           ("20080301231422", f"{_BA_Y}/2008/265660.html")],
    2009: [("20090226153045", f"{_BA_Y}/2009/267698.html"),
           ("20090227071651", f"{_BA_Y}/2009/267699.html"),
           ("20090227071703", f"{_BA_Y}/2009/267701.html"),
           ("20090227071658", f"{_BA_Y}/2009/267700.html"),
           ("20090227071708", f"{_BA_Y}/2009/267702.html")],
    2010: [("20100225060038", f"{_BA_Y}/2010/269546.html"),
           ("20100225060043", f"{_BA_Y}/2010/269550.html"),
           ("20100225060103", f"{_BA_Y}/2010/269551.html"),
           ("20100225060108", f"{_BA_Y}/2010/269553.html"),
           ("20100225060123", f"{_BA_Y}/2010/269554.html")],
    2011: [("20110225003405", f"{_BA_Y}/2011/2611316.html"),
           ("20110225003410", f"{_BA_Y}/2011/2611317.html"),
           ("20110225003416", f"{_BA_Y}/2011/2611326.html"),
           ("20110225003400", f"{_BA_Y}/2011/2611313.html"),
           ("20110225003355", f"{_BA_Y}/2011/2611312.html")],
    2012: [("20120222170023", f"{_BA_Y}/2012/2612998.html")],
    2013: [("20130222014253", f"{_BA_Y}/2013/2614739.html")],
}
#: Years whose list is on the all-time index but has no dated page in the archive: the
#: earliest in-window capture of the index that holds the list dates it (upper bound).
BA_CAPTURE_DATED_YEARS = (2014, 2015, 2016, 2017)
BA_ORG_PATTERN = "baseballamerica.com/today/prospects/rankings/organization-top-10-prospects/*"
BP_ARTICLES = {2007: 5892, 2008: 7092, 2009: 8506, 2010: 10142, 2011: 13078}
BP_URL = "https://www.baseballprospectus.com/news/article/{}/"
SICKELS_YEARS = tuple(range(2006, 2012))
SICKELS_MONTHS = (1, 2, 3, 4)

_last = [0.0]


# ---------------------------------------------------------------------------
# the polite cache

class Missing(RuntimeError):
    """A page that is not in the cache on a cache-only run."""


def _cache_path(url: str) -> Path:
    return X.CACHE_DIR / f"{hashlib.sha1(url.encode()).hexdigest()[:20]}.html"


def get(url: str, *, fetch: bool) -> str:
    p = _cache_path(url)
    if p.exists():
        return p.read_bytes().decode("utf-8", "replace")
    if not fetch:
        raise Missing(url)
    X.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    err: Exception | None = None
    for attempt in range(4):
        gap = time.time() - _last[0]
        if gap < FETCH_GAP_S:
            time.sleep(FETCH_GAP_S - gap)
        _last[0] = time.time()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            body = urllib.request.urlopen(req, timeout=60).read()
        except Exception as ex:  # noqa: BLE001 - network, retried then raised
            err = ex
            time.sleep(5 * (attempt + 1))
            continue
        p.write_bytes(body)
        with (X.CACHE_DIR / "index.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"key": p.stem, "url": url, "fetched": datetime.now(
                timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}) + "\n")
        return body.decode("utf-8", "replace")
    raise err if err else Missing(url)


def cdx(pattern: str, extra: str, *, fetch: bool) -> list[list[str]]:
    url = (f"{WAYBACK}/cdx/search/cdx?url=" + urllib.parse.quote(pattern, safe="/*:")
           + "&output=json&filter=statuscode:200" + extra)
    t = get(url, fetch=fetch)
    rows = json.loads(t) if t.strip() else []
    return rows[1:] if rows else []


def snap(ts: str, url: str, *, fetch: bool) -> str:
    return get(f"{WAYBACK}/web/{ts}id_/{url}", fetch=fetch)


# ---------------------------------------------------------------------------
# the lists

def _list(source, year, published_on, basis, capture_ts, url, rows, **extra) -> dict:
    d = {"source": source, "list_year": int(year), "published_on": published_on,
         "date_basis": basis, "capture_ts": capture_ts, "url": url, "rows": rows}
    d.update(extra)
    return d


def ba_top100(fetch: bool) -> tuple[list[dict], list[dict]]:
    """(lists, notes) for Baseball America's Top 100, 2006 to 2017."""
    lists, notes = [], []
    alltime = X.parse_ba_alltime(snap(*BA_ALLTIME, fetch=fetch))
    for year, pages in sorted(BA_YEAR_PAGES.items()):
        texts = [X.html_text(snap(ts, u, fetch=fetch)) for ts, u in pages]
        first = texts[0]
        k = first.find("Sitemap")
        pub = X.parse_dateline(first[k:] if k >= 0 else first)
        rows = alltime.get(year) or []
        # the dated pages print names in capitals: compare letters only
        joined = ID.norm_name(" ".join(texts))
        seen = sum(1 for r in rows if ID.norm_name(r["name"]) in joined)
        lists.append(_list("ba_top100_hist", year, pub, "page_dateline", BA_ALLTIME[0],
                           BA_ALLTIME[1], rows, dated_page=pages[0][1],
                           dated_page_capture=pages[0][0],
                           alltime_names_on_dated_pages=[seen, len(rows)]))
    caps = cdx(BA_ALLTIME_PATTERN, "&collapse=digest", fetch=fetch)
    for year in BA_CAPTURE_DATED_YEARS:
        lo, hi = X.window(year)
        found = None
        for row in sorted(caps, key=lambda r: r[1]):
            day = X.capture_day(row[1])
            if not (lo <= day < hi):
                continue
            page = X.parse_ba_alltime(snap(row[1], row[2], fetch=fetch))
            if page.get(year):
                found = (row[1], row[2], page[year])
                break
        if found is None:
            rows = alltime.get(year) or []
            notes.append({"source": "ba_top100_hist", "list_year": year,
                          "rows": len(rows), "ingested": False,
                          "reason": "no page dateline in the archive and no capture "
                                    "inside the preseason window holds the list"})
            continue
        ts, url, rows = found
        lists.append(_list("ba_top100_hist", year, X.capture_day(ts),
                           "capture_upper_bound", ts, url, rows))
    return lists, notes


def ba_org10(fetch: bool) -> list[dict]:
    """Every Baseball America organization Top 10 page in the archive, one list each
    (the earliest capture of a repeated (year, first player) list is kept)."""
    seen: dict[tuple, dict] = {}
    for row in sorted(cdx(BA_ORG_PATTERN, "&collapse=urlkey&limit=3000", fetch=fetch),
                      key=lambda r: r[1]):
        url = row[2]
        if not url.endswith(".html"):
            continue
        folder = url.split("organization-top-10-prospects/")[1].split("/")[0]
        if not folder.isdigit():
            continue
        p = X.parse_ba_org10(snap(row[1], url, fetch=fetch))
        if not p["rows"]:
            continue
        key = (int(folder), ID.norm_name(p["rows"][0]["name"]))
        if key in seen:
            continue
        seen[key] = _list("ba_org10_hist", int(folder), p["published_on"],
                          "page_dateline", row[1], url, p["rows"])
    return list(seen.values())


def bp_top100(fetch: bool) -> list[dict]:
    out = []
    for year, aid in sorted(BP_ARTICLES.items()):
        url = BP_URL.format(aid)
        p = X.parse_bp_top100(get(url, fetch=fetch))
        out.append(_list("bp_top100_hist", year, p["published_on"], "page_dateline",
                         None, url, p["rows"]))
    return out


def sickels(fetch: bool) -> tuple[list[dict], list[dict]]:
    """John Sickels's organization Top 20 posts dated January to April of each year."""
    urls: dict[str, tuple[str, str]] = {}
    for y in SICKELS_YEARS:
        for mo in SICKELS_MONTHS:
            for pat in (f"minorleagueball.com/{y}/{mo}/", f"minorleagueball.com/{y}/{mo:02d}/"):
                for row in cdx(pat + "*", "&collapse=urlkey&limit=5000", fetch=fetch):
                    u = row[2].split("?")[0]
                    if "top-20" not in u and "top20" not in u:
                        continue
                    key = u.split("minorleagueball.com", 1)[1].replace(":80", "")
                    parts = key.split("/")
                    if len(parts) < 4 or not (parts[1].isdigit() and parts[2].isdigit()):
                        continue
                    if int(parts[2]) not in SICKELS_MONTHS:
                        continue
                    urls.setdefault(key, (row[1], row[2]))
    lists, skipped = [], []
    for key, (ts, url) in sorted(urls.items()):
        p = X.parse_sickels(snap(ts, url, fetch=fetch))
        if p["author"] != "John Sickels" or not X.sickels_is_org_list(p["title"]):
            skipped.append({"url": key, "author": p["author"], "title": p["title"]})
            continue
        year = int(p["published_on"][:4])
        lists.append(_list("sickels_hist", year, p["published_on"], "page_dateline", ts,
                           url, p["rows"], title=p["title"]))
    return lists, skipped


# ---------------------------------------------------------------------------
# eligibility, ingest, census

def eligibility(lists: list[dict]) -> list[dict]:
    """Registration s4 per list: dated inside its window and resolved at or above
    ELIGIBLE_MATCH_RATE. Mutates each list with its verdict and returns the rows."""
    out = []
    for lst in lists:
        V = int(lst["list_year"])
        reasons = []
        if not (X.FIRST_VINTAGE <= V <= X.LAST_VINTAGE):
            reasons.append(f"vintage {V} outside {X.FIRST_VINTAGE}..{X.LAST_VINTAGE}")
        if not X.in_window(lst["published_on"], V):
            reasons.append(f"published {lst['published_on']} outside the {V} window")
        rate, how = None, {}
        if not reasons:
            res = X.resolve_list_rows(lst)
            rate = X.match_rate(res)
            how = dict(collections.Counter(r["how"] for r in res))
            if rate is None or rate < X.ELIGIBLE_MATCH_RATE:
                reasons.append(f"match rate {rate} below {X.ELIGIBLE_MATCH_RATE}")
        lst["eligible"] = not reasons
        lst["reasons"] = reasons
        lst["match_rate"] = None if rate is None else round(rate, 4)
        lst["id_how"] = how
        out.append(lst)
    return out


def _floor_ref() -> dict:
    doc = json.loads(CENSUS_REF.read_text(encoding="utf-8"))
    fc = doc["floor_curve"]
    ref = next(r for r in fc["references"] if r["id"] == X.FLOOR_REF_ID)
    return {"z95": fc["z95"], "sd_ref": ref["sd_ref"], "n_ref": ref["n_ref"],
            "n_clusters_ref": ref["n_clusters_ref"], "path": "data/efv_label_pool_census.json",
            "key": f"floor_curve.references[{X.FLOOR_REF_ID}]",
            "source_key": ref["key"], "source_path": ref["path"],
            "census_generated_at": doc.get("generated_at")}


def census(records: list[dict]) -> dict:
    universe = F.load_universe()
    by_sv: list[dict] = []
    gained_persons: set[int] = set()
    cur_persons: set[int] = set()
    n_cur = 0
    for V in range(X.FIRST_VINTAGE, X.LAST_VINTAGE + 1):
        index = ID.build_index(V - 1)
        aug = X.augmented_rows(records, V, index=index)
        cur = X.current_frame_ids(V, universe)
        for side in X.SIDES:
            n_cur += len(cur[side])
            cur_persons |= cur[side]
            a = [r for r in aug if r["side"] == side]
            gained = [r for r in a if r["person_id"] not in cur[side]]
            gained_persons |= {r["person_id"] for r in gained}
            by_sv.append({
                "side": side, "vintage": V,
                "current_rows_resolved": len(cur[side]),
                "augmented_new_source_rows": len(a),
                "already_in_frame": len(a) - len(gained),
                "gained": len(gained),
                "gained_by_source_set": dict(collections.Counter(
                    "+".join(r["sources"]) for r in gained)),
                "gained_id_how": dict(collections.Counter(r["id_how"] for r in gained)),
            })
    G = sum(r["gained"] for r in by_sv)
    P = len(gained_persons - cur_persons)
    ref = _floor_ref()
    r_ret = ref["n_ref"] / n_cur if n_cur else None
    n_after = ref["n_ref"] + (r_ret or 0) * G
    n_after_ub = ref["n_ref"] + G
    c_after = ref["n_clusters_ref"] + (r_ret or 0) * P
    m = lambda n: X.mde95(n, ref["sd_ref"], ref["n_ref"], ref["z95"])  # noqa: E731
    mc = lambda c: X.mde95(c, ref["sd_ref"], ref["n_clusters_ref"], ref["z95"])  # noqa: E731
    floors = {
        "reference": ref,
        "formula": "mde95(n) = z95 * sd_ref * sqrt(n_ref / n)",
        "n_current_resolved_2011_2019": n_cur,
        "retention": None if r_ret is None else round(r_ret, 4),
        "gained_rows": G,
        "gained_distinct_new_persons": P,
        "primary": {"n_before": ref["n_ref"], "n_after": round(n_after, 1),
                    "mde95_before": round(m(ref["n_ref"]), 5),
                    "mde95_after": round(m(n_after), 5),
                    "change": round(m(n_after) - m(ref["n_ref"]), 5)},
        "upper_bound": {"n_after": n_after_ub, "mde95_after": round(m(n_after_ub), 5),
                        "change": round(m(n_after_ub) - m(ref["n_ref"]), 5)},
        "cluster_read": {"clusters_before": ref["n_clusters_ref"],
                         "clusters_after": round(c_after, 1),
                         "mde95_before": round(mc(ref["n_clusters_ref"]), 5),
                         "mde95_after": round(mc(c_after), 5),
                         "change": round(mc(c_after) - mc(ref["n_clusters_ref"]), 5)},
        "caveat": "scaling by n ignores that a pre-2011 row's comparator would be the "
                  "archived source's own rank (no PROSPX consensus exists before 2011) "
                  "and that era shifts the label; the measured floor of an augmented "
                  "frame is owed by the task that scores it",
    }
    return {"by_side_vintage": by_sv, "floors": floors}


def _git_commit() -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                             capture_output=True, text=True, check=False, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build(fetch: bool) -> tuple[dict, dict]:
    t0 = time.time()
    ba, ba_notes = ba_top100(fetch)
    org = ba_org10(fetch)
    bp = bp_top100(fetch)
    sk, sk_skipped = sickels(fetch)
    lists = eligibility(ba + org + bp + sk)
    ok = [lst for lst in lists if lst["eligible"]]
    records = X.build_records(ok)
    bad = X.point_violations(records)
    if bad:
        raise SystemExit("dating rule violated:\n" + "\n".join(bad[:20]))
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    stamp = {"generated_at": now, "produced_by": "tools/efv_x5_older_vintages.py",
             "registration": X.REGISTRATION, "commit": _git_commit(),
             "module_sha256": _sha(ROOT / "efv_x5_older_vintages.py"),
             "role": "development", "adjudicates": "nothing; counts only, no score",
             "served": False}
    points = dict(stamp, sources=sorted({lst["source"] for lst in ok}),
                  n_records=len(records), n_points=sum(len(r["points"]) for r in records),
                  records=records)
    per_list = [{k: lst.get(k) for k in ("source", "list_year", "published_on",
                                          "date_basis", "capture_ts", "url", "eligible",
                                          "reasons", "match_rate", "id_how",
                                          "alltime_names_on_dated_pages", "title")}
                | {"rows": len(lst["rows"])} for lst in lists]
    summary = collections.defaultdict(lambda: {"lists": 0, "eligible_lists": 0,
                                               "rows": 0, "eligible_rows": 0,
                                               "depth_max": 0, "routed_rows_read": 0,
                                               "resolved_rows_read": 0,
                                               "years": set(), "eligible_years": set()})
    for lst in lists:
        s = summary[lst["source"]]
        s["lists"] += 1
        s["rows"] += len(lst["rows"])
        s["depth_max"] = max(s["depth_max"], len(lst["rows"]))
        how = lst.get("id_how") or {}
        s["routed_rows_read"] += sum(v for k, v in how.items() if k != "no_side")
        s["resolved_rows_read"] += sum(v for k, v in how.items() if k in ID.HOW_WITH_ID)
        s["years"].add(lst["list_year"])
        if lst["eligible"]:
            s["eligible_lists"] += 1
            s["eligible_rows"] += len(lst["rows"])
            s["eligible_years"].add(lst["list_year"])
    sources = {}
    for key, meta in X.SOURCES.items():
        s = summary.get(key)
        sources[key] = dict(meta, **({k: (sorted(v) if isinstance(v, set) else v)
                                      for k, v in s.items()} if s else
                                     {"lists": 0, "rows": 0, "eligible_lists": 0}))
        sources[key]["passes"] = bool(s and s["eligible_lists"])
        routed = sources[key].get("routed_rows_read") or 0
        sources[key]["match_rate_pooled"] = (
            round(sources[key]["resolved_rows_read"] / routed, 4) if routed else None)
    sources["mlbcom_top50_hist"]["not_ingested"] = (
        "2009 list announced on mlb.mlb.com/mlb/minorleagues/prospects/y2009/ with "
        "'Prospects 1 to 10 coming December 5th' (capture 2008-12-05): published in "
        "December 2008, outside the 2009 window. 2010 list (50 rows on the GraphQL host) "
        "has no publisher-dated page reachable without a block (mlb.com returned 406) and "
        "no archive capture; a third-party report dates it 2010-01-28, which the "
        "registration does not admit. 2004 to 2008 lists sit on an all-time page first "
        "captured 2008-12-05, outside every window.")
    sources["fg_hulet_hist"]["not_ingested"] = (
        "not probed inside the time box: WebFetch-only access, and the organization "
        "lists were published October to February, so most fall before their window")
    cen = census(records)
    census_doc = dict(stamp, sources=sources, lists=per_list, ba_top100_notes=ba_notes,
                      sickels_skipped=sk_skipped, frame=cen["by_side_vintage"],
                      floors=cen["floors"], seconds=round(time.time() - t0, 1),
                      strata=["source", "list_year", "vintage", "side", "id_how"])
    return points, census_doc


def write(points: dict, census_doc: dict) -> None:
    X.LAB_DIR.mkdir(parents=True, exist_ok=True)
    for path, doc in ((X.POINTS_PATH, points), (X.CENSUS_PATH, census_doc)):
        path.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n",
                        encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--fetch", action="store_true", help="fetch pages missing from the cache")
    ap.add_argument("--write", action="store_true", help="write the two artifacts")
    a = ap.parse_args(argv)
    points, census_doc = build(a.fetch)
    print(json.dumps({"sources": {k: {kk: v.get(kk) for kk in ("lists", "eligible_lists",
                                                              "rows", "eligible_rows",
                                                              "passes")}
                                  for k, v in census_doc["sources"].items()},
                      "floors": census_doc["floors"]}, indent=1, default=str))
    if a.write:
        write(points, census_doc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
