# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Served-payload equivalence for the port (PORT_SPEC.md Gate C, PORT_RUNBOOK.md).

Three commands:

    python tools/port_equivalence.py snapshot --root . --out ref.json
        Record every published payload (the nightly rsync's data set) with its
        sha256 and three canonical digests. Pages and assets are recorded by
        sha256 only; Gate C covers payloads, Gate B covers pages.

    python tools/port_equivalence.py compare --ref ref.json --root /target/tree
        Sort every payload into one category and exit 1 on any DIFFERENT,
        MISSING or EXTRA file:
          IDENTICAL   same bytes
          LINE_ENDINGS same bytes once CRLF reads as LF (a Windows checkout of
                      a tracked file against the Linux box's LF checkout)
          TIMESTAMP   equal once the stamp keys below are dropped
          FLOAT_REPR  equal once numbers compare as decimals (1.0 == 1)
          ORDERING    equal once every list is sorted
          DIFFERENT   anything else (run `diff` on the pair for the leaves)

    python tools/port_equivalence.py diff REF_FILE TARGET_FILE
        Every differing leaf path with both values, numbers compared as
        decimals at full precision, no tolerance.

    python tools/port_equivalence.py selftest FILE
        Positive control: perturbs one numeric leaf of a copy of FILE in its
        last serialized place and asserts `diff` reports exactly that leaf.

    python tools/port_equivalence.py compare-http --bundle BUNDLE_DIR
            --origin https://eephus.io [--pace 0.5] [--only data/] [--every N]
            [--explained explained.tsv] [--out report.json]
    python tools/port_equivalence.py compare-http --ref ref.json --origin URL
        The HTTP fetch mode: reads every file of the frozen snapshot from the
        PUBLISHED webroot (browser UA through curl, one request at a time,
        --pace seconds apart) and names each difference. With --bundle (a
        served bundle from tools/port_bundle.py --served-bundle) the reference
        is the bundle's MANIFEST.tsv and its site/ bytes, so a DIFFERENT JSON
        file lists its differing leaves and any other file its first differing
        line. With --ref (a snapshot) payloads take the category ladder above
        and pages compare by sha256_lf. Extra categories over HTTP:
          CDN_INJECTED an HTML page equal once the scripts Cloudflare adds
                      (/cdn-cgi/ beacons and challenge or email helpers) are
                      removed
          EXPLAINED   differs, and --explained names the difference (a TSV of
                      glob<TAB>reason lines: the headshot proxy, the forums
                      layer); the reason is printed with the file
          BLOCKED     Cloudflare answered with a challenge, not the origin;
                      rerun from a browser session or with a skip rule
          MISSING     any status but 200 (the status is recorded)
        Exit 1 on any DIFFERENT, MISSING or BLOCKED file.

    python tools/port_equivalence.py compare-bundles --ref FULL_BUNDLE
            --new SLIM_BUNDLE [--fetched crawl.json ...]
            [--crawl-ref crawl_full.json --crawl-new crawl_slim.json] [--out report.json]
        Two served bundles from the same tree (port_bundle.py --served-bundle
        with and without --no-slim): every page and asset row identical, no
        row changed or added, and every file a crawl fetched (a crawl JSON of
        {path: [status, sha256]}) present in the new bundle with the same
        bytes; with --crawl-ref/--crawl-new, the two crawls of the two
        bundles' sites answered every request with the same status and bytes.
        Lists what the new bundle dropped. Exit 1 on any page difference,
        change, addition, dropped fetched file or crawl difference.

The published set is computed the way deploy/nightly-build.sh's rsync computes
it: data/*.json and data/*.js at depth one minus deploy/data_exclude.txt, plus
the per-player directories in PER_PLAYER_DIRS (pinned to the script's include
lines by test_port_equivalence.py). The served bundle adds the live store in
LIVE_DIRS (data/scores/, as of the build); compare-bundles reports its rows
apart, because the scores job rewrites them between two builds.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# The per-player directories deploy/nightly-build.sh's rsync includes.
PER_PLAYER_DIRS: tuple[str, ...] = (
    "pitch_plots", "player_detail", "debuts_full", "mgmt_decisions",
    "ledger_clubs", "franchise_clubs", "mlb_events", "mlbstats_player",
    "mlb_player_detail",
)
# The live store the served bundle carries as of its build and the nightly
# rsync never ships (port task PORT_SCORES_PR11, 2026-10-27): data/scores/,
# written by tools/scores_job.py between builds for /scores/ and /standings/.
# On the box it is published from the bundle like every other payload, so
# the site's copy is the store as of the build; two bundles from the same
# tree minutes apart may differ here, and compare_bundles reports those rows
# apart. Never a nightly rsync include (test_scores_fence, test_publish_manifest).
LIVE_DIRS: tuple[str, ...] = ("data/scores",)
# Leaf keys that carry a write time, not a value (the TIMESTAMP category).
STAMP_KEYS: frozenset[str] = frozenset({
    "generated_at", "built_at", "checked_at", "written_at", "stamped_at",
    "updated_at", "last_updated", "run_at", "exported_at", "refreshed_at",
    "built", "generated",
})


def _lines(path: Path) -> list[str]:
    return [x.strip() for x in path.read_text(encoding="utf-8").splitlines()
            if x.strip() and not x.strip().startswith("#")]


def payload_files(root: Path) -> list[str]:
    """Module-relative posix paths of every published payload under data/."""
    excl = set(_lines(root / "deploy" / "data_exclude.txt"))
    data = root / "data"
    out = [p.relative_to(root).as_posix() for p in sorted(data.iterdir())
           if p.is_file() and p.suffix in (".json", ".js") and p.name not in excl]
    for d in PER_PLAYER_DIRS:
        base = data / d
        if base.is_dir():
            out += sorted(p.relative_to(root).as_posix()
                          for p in base.rglob("*") if p.is_file())
    return out


def live_files(root: Path) -> list[str]:
    """Module-relative posix paths of every file of the live stores in
    LIVE_DIRS: the served bundle's extra set, never the nightly rsync's."""
    out: list[str] = []
    for d in LIVE_DIRS:
        base = root / d
        if base.is_dir():
            out += sorted(p.relative_to(root).as_posix()
                          for p in base.rglob("*") if p.is_file())
    return out


def is_live(rel: str) -> bool:
    """True for a file inside one of LIVE_DIRS."""
    return rel.startswith(tuple(d + "/" for d in LIVE_DIRS))


def page_files(root: Path) -> list[str]:
    out: list[str] = []
    for e in _lines(root / "deploy" / "publish_paths.txt"):
        p = root / e
        if p.is_dir():
            out += sorted(f.relative_to(root).as_posix() for f in p.rglob("*")
                          if f.is_file() and "__pycache__" not in f.parts)
        elif p.is_file():
            out.append(e)
    return out


def _strip(obj, *, numbers: bool, unordered: bool):
    if isinstance(obj, dict):
        return {k: _strip(v, numbers=numbers, unordered=unordered)
                for k, v in obj.items() if k not in STAMP_KEYS}
    if isinstance(obj, list):
        items = [_strip(v, numbers=numbers, unordered=unordered) for v in obj]
        if unordered:
            items.sort(key=lambda v: json.dumps(v, sort_keys=True, default=str))
        return items
    if numbers and isinstance(obj, Decimal):
        n = obj.normalize()
        return format(n, "f") if n == n.to_integral_value() else str(n)
    if isinstance(obj, Decimal):
        return "D:" + str(obj)
    return obj


def _digest(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False,
                                     default=str).encode("utf-8")).hexdigest()


def _load(raw: bytes):
    return json.loads(raw.decode("utf-8"), parse_float=Decimal, parse_int=Decimal)


def fingerprint(path: Path) -> dict:
    return fingerprint_bytes(path.read_bytes(), path.suffix)


def fingerprint_bytes(raw: bytes, suffix: str) -> dict:
    rec = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
           "sha256_lf": hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()}
    if suffix == ".json":
        try:
            obj = _load(raw)
        except ValueError:
            rec["parse_error"] = True
            return rec
        rec["canon_stamp"] = _digest(_strip(obj, numbers=False, unordered=False))
        rec["canon_num"] = _digest(_strip(obj, numbers=True, unordered=False))
        rec["canon_unordered"] = _digest(_strip(obj, numbers=True, unordered=True))
    return rec


def _sha_lf(path: Path) -> str:
    """sha256 with CRLF read as LF: a page is the same page on either checkout."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def snapshot(root: Path) -> dict:
    return {
        "root": str(root),
        "payloads": {rel: fingerprint(root / rel) for rel in payload_files(root)},
        "pages": {rel: {"sha256_lf": _sha_lf(root / rel)} for rel in page_files(root)},
    }


def categorize(ref: dict, new: dict) -> str:
    if ref["sha256"] == new["sha256"]:
        return "IDENTICAL"
    if "sha256_lf" in ref and ref["sha256_lf"] == new.get("sha256_lf"):
        return "LINE_ENDINGS"
    for key, cat in (("canon_stamp", "TIMESTAMP"), ("canon_num", "FLOAT_REPR"),
                     ("canon_unordered", "ORDERING")):
        if key in ref and ref.get(key) == new.get(key):
            return cat
    return "DIFFERENT"


def compare(ref_doc: dict, root: Path) -> dict:
    ref = ref_doc["payloads"]
    now = set(payload_files(root))
    cats: dict[str, list[str]] = {}
    for rel in sorted(ref):
        if rel not in now:
            cats.setdefault("MISSING", []).append(rel)
            continue
        cats.setdefault(categorize(ref[rel], fingerprint(root / rel)), []).append(rel)
    for rel in sorted(now - set(ref)):
        cats.setdefault("EXTRA", []).append(rel)
    pages_ref = ref_doc.get("pages", {})
    page_diff = sorted(rel for rel, r in pages_ref.items()
                       if not (root / rel).is_file()
                       or _sha_lf(root / rel) != r.get("sha256_lf"))
    return {"counts": {k: len(v) for k, v in sorted(cats.items())},
            "files": cats, "pages_differing": page_diff,
            "ok": not any(k in cats for k in ("DIFFERENT", "MISSING", "EXTRA"))}


def leaf_diff(a, b, path: str = "$", out: list | None = None, cap: int = 500) -> list:
    out = [] if out is None else out
    if len(out) >= cap:
        return out
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                out.append((f"{path}.{k}", a.get(k, "<absent>"), b.get(k, "<absent>")))
            else:
                leaf_diff(a[k], b[k], f"{path}.{k}", out, cap)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append((f"{path}.length", len(a), len(b)))
        for i, (x, y) in enumerate(zip(a, b)):
            leaf_diff(x, y, f"{path}[{i}]", out, cap)
    elif a != b:
        out.append((path, a, b))
    return out


def diff_files(a: Path, b: Path) -> list:
    return leaf_diff(_load(a.read_bytes()), _load(b.read_bytes()))


def _first_numeric_leaf(obj, path="$", keys=()):
    """(printed path, key list, value) of the first numeric leaf, depth first."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            hit = _first_numeric_leaf(v, f"{path}.{k}", keys + (k,))
            if hit:
                return hit
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            hit = _first_numeric_leaf(v, f"{path}[{i}]", keys + (i,))
            if hit:
                return hit
    elif isinstance(obj, Decimal):
        return path, keys, obj
    return None


def _set_leaf(obj, keys: tuple, value):
    cur = obj
    for k in keys[:-1]:
        cur = cur[k]
    cur[keys[-1]] = value


def selftest(path: Path) -> dict:
    """Positive control: one unit in the last serialized place of one leaf."""
    obj = _load(path.read_bytes())
    hit = _first_numeric_leaf(obj)
    if hit is None:
        return {"ok": False, "reason": "no numeric leaf"}
    leaf, keys, val = hit
    exp = val.as_tuple().exponent
    bumped = val + Decimal(1).scaleb(exp if isinstance(exp, int) else 0)
    obj2 = copy.deepcopy(obj)
    _set_leaf(obj2, keys, bumped)
    found = leaf_diff(obj, obj2)
    return {"leaf": leaf, "before": str(val), "after": str(bumped),
            "reported": [(p_, str(x), str(y)) for p_, x, y in found],
            "ok": len(found) == 1 and found[0][0] == leaf}


# --------------------------------------------------------------------------- #
# HTTP fetch mode: the published webroot against the frozen snapshot
# --------------------------------------------------------------------------- #
_SCRIPT_BLOCK = re.compile(rb"<script\b[^>]*>.*?</script>[ \t]*\r?\n?", re.S | re.I)
_CDN_MARKS = (b"/cdn-cgi/", b"cloudflareinsights", b"data-cf-beacon")
BAD_HTTP = ("DIFFERENT", "MISSING", "BLOCKED")


def strip_cdn(raw: bytes) -> bytes:
    """Drop the script blocks Cloudflare injects into an HTML response."""
    return _SCRIPT_BLOCK.sub(
        lambda m: b"" if any(k in m.group(0) for k in _CDN_MARKS) else m.group(0), raw)


def _lf(raw: bytes) -> bytes:
    return raw.replace(b"\r\n", b"\n")


def _first_line_diff(a: bytes, b: bytes) -> dict:
    la, lb = _lf(a).split(b"\n"), _lf(b).split(b"\n")
    for i, (x, y) in enumerate(zip(la, lb)):
        if x != y:
            return {"line": i + 1, "ref": x[:200].decode("utf-8", "replace"),
                    "live": y[:200].decode("utf-8", "replace")}
    return {"line": min(len(la), len(lb)) + 1, "ref_lines": len(la), "live_lines": len(lb)}


def read_bundle_manifest(bundle: Path) -> list[str]:
    """Webroot-relative paths of a served bundle's MANIFEST.tsv."""
    with open(bundle / "MANIFEST.tsv", encoding="utf-8") as f:
        next(f)
        return [line.split("\t", 1)[0] for line in f if line.strip()]


def _manifest_rows(bundle: Path) -> dict[str, tuple[int, str]]:
    rows: dict[str, tuple[int, str]] = {}
    with open(bundle / "MANIFEST.tsv", encoding="utf-8") as f:
        next(f)
        for line in f:
            if line.strip():
                rel, size, digest = line.rstrip("\n").split("\t")
                rows[rel] = (int(size), digest)
    return rows


def _crawl_rel(path: str) -> str:
    rel = path.lstrip("/")
    return rel + "index.html" if rel == "" or rel.endswith("/") else rel


def compare_bundles(ref: Path, new: Path, fetched: tuple[dict, ...] = (),
                    crawl_ref: dict | None = None, crawl_new: dict | None = None) -> dict:
    """A slimmed bundle against the full one built from the same tree.

    Rows inside LIVE_DIRS (the scores store) are reported under "live" and
    never fail the comparison on their bytes: the scores job rewrites them
    between the two builds. A live file a crawl fetched must still be
    present in the new bundle, and a crawl of each bundle's site must have
    answered it with the same status."""
    a, b = _manifest_rows(ref), _manifest_rows(new)
    skip = {"data/bundle_info.json"}         # names its own bundle id: differs by design
    both = (a.keys() & b.keys()) - skip
    changed = sorted(r for r in both if a[r] != b[r] and not is_live(r))
    dropped = sorted(r for r in a.keys() - b.keys() - skip if not is_live(r))
    added = sorted(r for r in b.keys() - a.keys() - skip if not is_live(r))
    live = {
        "dirs": list(LIVE_DIRS),
        "ref": sum(1 for r in a if is_live(r)), "new": sum(1 for r in b if is_live(r)),
        "changed": sorted(r for r in both if is_live(r) and a[r] != b[r]),
        "added": sorted(r for r in b.keys() - a.keys() if is_live(r)),
        "dropped": sorted(r for r in a.keys() - b.keys() if is_live(r)),
    }
    pages_ref = sorted(r for r in a if not r.startswith("data/"))
    pages_new = sorted(r for r in b if not r.startswith("data/"))
    page_diff = sorted(set(pages_ref) ^ set(pages_new)) + [
        r for r in pages_ref if r in b and a[r] != b[r]]
    fetched_paths: set[str] = set()
    for crawl in fetched:
        for path, (status, _sha) in crawl.get("requests", {}).items():
            if status == 200:
                fetched_paths.add(_crawl_rel(path))
    fetched_in_ref = sorted(r for r in fetched_paths if r in a and r not in skip)
    fetched_dropped = sorted(r for r in fetched_in_ref if r not in b)
    fetched_changed = sorted(r for r in fetched_in_ref
                             if r in b and a[r] != b[r] and not is_live(r))
    crawl_diff: list[str] = []
    if crawl_ref is not None and crawl_new is not None:
        ra, rb = crawl_ref.get("requests", {}), crawl_new.get("requests", {})
        for path in sorted(set(ra) | set(rb)):
            if path == "/data/bundle_info.json":
                continue
            if is_live(_crawl_rel(path)):          # the status, not the bytes
                if (ra.get(path) or [None])[0] != (rb.get(path) or [None])[0]:
                    crawl_diff.append(f"{path}: {ra.get(path)} -> {rb.get(path)}")
                continue
            if ra.get(path) != rb.get(path):
                crawl_diff.append(f"{path}: {ra.get(path)} -> {rb.get(path)}")
    res = {
        "ref": str(ref), "new": str(new),
        "rows": {"ref": len(a), "new": len(b)},
        "pages": {"ref": len(pages_ref), "new": len(pages_new), "differing": page_diff},
        "changed": changed, "added": added,
        "dropped": dropped, "dropped_bytes": sum(a[r][0] for r in dropped),
        "live": live,
        "fetched": {"files": len(fetched_paths), "in_ref": len(fetched_in_ref),
                    "dropped": fetched_dropped, "changed": fetched_changed},
        "crawl_diff": crawl_diff,
    }
    res["ok"] = not (page_diff or changed or added or fetched_dropped or fetched_changed
                     or crawl_diff)
    return res


def read_explained(path: Path | None) -> list[tuple[str, str]]:
    if path is None:
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "\t" in line:
            pat, reason = line.split("\t", 1)
            rows.append((pat.strip(), reason.strip()))
    return rows


def _categorize_bytes(rel: str, ref_raw: bytes, live: bytes) -> tuple[str, object]:
    if ref_raw == live:
        return "IDENTICAL", None
    if _lf(ref_raw) == _lf(live):
        return "LINE_ENDINGS", None
    suffix = Path(rel).suffix
    if suffix in (".html", ".htm") and _lf(strip_cdn(ref_raw)) == _lf(strip_cdn(live)):
        return "CDN_INJECTED", None
    if suffix == ".json":
        cat = categorize(fingerprint_bytes(ref_raw, suffix), fingerprint_bytes(live, suffix))
        if cat != "DIFFERENT":
            return cat, None
        try:
            leaves = leaf_diff(_load(ref_raw), _load(live), cap=20)
        except ValueError:
            return "DIFFERENT", {"parse_error": True}
        return "DIFFERENT", [{"leaf": p, "ref": str(x), "live": str(y)} for p, x, y in leaves]
    return "DIFFERENT", _first_line_diff(ref_raw, live)


def compare_http(origin: str, *, bundle: Path | None = None, ref_doc: dict | None = None,
                 fetch_raw=None, pace: float = 0.5, only: tuple[str, ...] = (),
                 every: int = 1, explained: list[tuple[str, str]] = (),
                 pacer=None) -> dict:
    """Fetch every snapshot file from the origin and sort it into a category."""
    import fnmatch
    sys.path.insert(0, str(ROOT / "tools"))
    import port_live_check as plc
    fetch_raw = fetch_raw or plc.curl_fetch_raw
    pacer = pacer or plc.Pacer(pace)
    origin = origin.rstrip("/")
    if bundle is not None:
        rels = read_bundle_manifest(bundle)
        reference = {"bundle": str(bundle)}
        info = bundle / "BUNDLE.json"
        if info.is_file():
            reference["bundle_id"] = json.loads(info.read_text(encoding="utf-8")).get("bundle_id")
    elif ref_doc is not None:
        rels = sorted(set(ref_doc.get("payloads", {})) | set(ref_doc.get("pages", {})))
        reference = {"ref_root": ref_doc.get("root")}
    else:
        raise ValueError("compare_http needs a bundle or a snapshot")
    if only:
        rels = [r for r in rels if r.startswith(only)]
    rels = rels[::max(1, int(every))]
    files: dict[str, list[str]] = {}
    details: dict[str, object] = {}
    codes: dict[str, object] = {}
    reasons: dict[str, str] = {}
    for rel in rels:
        pacer.wait()
        code, body, headers = fetch_raw(f"{origin}/{rel}")
        if plc.is_challenge(code, headers, body):
            cat, det = "BLOCKED", None
            codes[rel] = code
        elif code != 200 or body is None:
            cat, det = "MISSING", None
            codes[rel] = code
        elif bundle is not None:
            cat, det = _categorize_bytes(rel, (bundle / "site" / rel).read_bytes(), body)
        elif rel in ref_doc.get("payloads", {}):
            cat = categorize(ref_doc["payloads"][rel], fingerprint_bytes(body, Path(rel).suffix))
            det = None
        else:
            same = hashlib.sha256(_lf(body)).hexdigest() == ref_doc["pages"][rel].get("sha256_lf")
            cat = "IDENTICAL" if same else "DIFFERENT"
            det = None if same else "a snapshot keeps no page bytes: rerun with --bundle"
        if cat == "DIFFERENT":
            hit = next((reason for pat, reason in explained if fnmatch.fnmatch(rel, pat)), None)
            if hit is not None:
                cat = "EXPLAINED"
                reasons[rel] = hit
        files.setdefault(cat, []).append(rel)
        if det is not None:
            details[rel] = det
    return {"origin": origin, "reference": reference, "checked": len(rels),
            "counts": {k: len(v) for k, v in sorted(files.items())}, "files": files,
            "details": details, "codes": codes, "explained": reasons,
            "ok": not any(k in files for k in BAD_HTTP)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("snapshot")
    s.add_argument("--root", type=Path, default=ROOT)
    s.add_argument("--out", type=Path, required=True)
    c = sub.add_parser("compare")
    c.add_argument("--ref", type=Path, required=True)
    c.add_argument("--root", type=Path, default=ROOT)
    c.add_argument("--out", type=Path, help="write the full report here")
    d = sub.add_parser("diff")
    d.add_argument("ref_file", type=Path)
    d.add_argument("target_file", type=Path)
    t = sub.add_parser("selftest")
    t.add_argument("file", type=Path)
    h = sub.add_parser("compare-http")
    src = h.add_mutually_exclusive_group(required=True)
    src.add_argument("--bundle", type=Path, help="a served bundle directory")
    src.add_argument("--ref", type=Path, help="a snapshot written by `snapshot`")
    h.add_argument("--origin", default="https://eephus.io")
    h.add_argument("--pace", type=float, default=0.5, metavar="SECONDS",
                   help="seconds between two requests (one at a time)")
    h.add_argument("--only", action="append", default=[], metavar="PREFIX",
                   help="only paths starting with PREFIX (repeatable)")
    h.add_argument("--every", type=int, default=1, metavar="N",
                   help="every Nth path of the sorted list (a fixed sample)")
    h.add_argument("--explained", type=Path, help="TSV of glob<TAB>reason lines")
    h.add_argument("--out", type=Path, help="write the full report here")
    cb = sub.add_parser("compare-bundles")
    cb.add_argument("--ref", type=Path, required=True, help="the full served bundle")
    cb.add_argument("--new", type=Path, required=True, help="the slimmed served bundle")
    cb.add_argument("--fetched", type=Path, action="append", default=[],
                    help="a crawl JSON whose fetched files must survive (repeatable)")
    cb.add_argument("--crawl-ref", type=Path, help="a crawl of the full bundle's site/")
    cb.add_argument("--crawl-new", type=Path, help="a crawl of the slimmed bundle's site/")
    cb.add_argument("--out", type=Path, help="write the full report here")
    a = ap.parse_args(argv)
    if a.cmd == "compare-bundles":
        def _j(path):
            return json.loads(path.read_text(encoding="utf-8")) if path else None
        res = compare_bundles(a.ref.resolve(), a.new.resolve(),
                              tuple(_j(x) for x in a.fetched),
                              _j(a.crawl_ref), _j(a.crawl_new))
        if a.out:
            a.out.write_text(json.dumps(res, indent=1), encoding="utf-8")
        print(json.dumps({"rows": res["rows"], "pages": {k: (len(v) if isinstance(v, list) else v)
                                                         for k, v in res["pages"].items()},
                          "changed": len(res["changed"]), "added": len(res["added"]),
                          "dropped": len(res["dropped"]), "dropped_bytes": res["dropped_bytes"],
                          "live": {k: (len(v) if isinstance(v, list) else v)
                                   for k, v in res["live"].items() if k != "dirs"},
                          "fetched": {k: (len(v) if isinstance(v, list) else v)
                                      for k, v in res["fetched"].items()},
                          "crawl_diff": len(res["crawl_diff"]), "ok": res["ok"]}, indent=1))
        for rel in res["dropped"]:
            print("DROPPED", rel)
        for key in ("changed", "added", "dropped"):
            for rel in res["live"][key][:20]:
                print("LIVE", key.upper(), rel)
        for line in res["crawl_diff"][:50]:
            print("CRAWL", line)
        return 0 if res["ok"] else 1
    if a.cmd == "compare-http":
        res = compare_http(
            a.origin, bundle=a.bundle.resolve() if a.bundle else None,
            ref_doc=json.loads(a.ref.read_text(encoding="utf-8")) if a.ref else None,
            pace=a.pace, only=tuple(a.only), every=a.every,
            explained=read_explained(a.explained))
        if a.out:
            a.out.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
        print(json.dumps({"origin": res["origin"], "reference": res["reference"],
                          "checked": res["checked"], "counts": res["counts"],
                          "ok": res["ok"]}, indent=1))
        shown = 0
        for cat in ("DIFFERENT", "MISSING", "BLOCKED", "EXPLAINED"):
            for rel in res["files"].get(cat, []):
                if shown >= 200:
                    break
                note = res["explained"].get(rel) or res["codes"].get(rel) or ""
                det = res["details"].get(rel)
                print(cat, rel, note, json.dumps(det, default=str)[:400] if det else "")
                shown += 1
        return 0 if res["ok"] else 1
    if a.cmd == "snapshot":
        snap = snapshot(a.root.resolve())
        a.out.write_text(json.dumps(snap, indent=0, sort_keys=True), encoding="utf-8")
        print(json.dumps({"payloads": len(snap["payloads"]), "pages": len(snap["pages"])}))
        return 0
    if a.cmd == "compare":
        res = compare(json.loads(a.ref.read_text(encoding="utf-8")), a.root.resolve())
        if a.out:
            a.out.write_text(json.dumps(res, indent=1), encoding="utf-8")
        print(json.dumps({"counts": res["counts"], "pages_differing": len(res["pages_differing"]),
                          "ok": res["ok"]}, indent=1))
        for cat in ("DIFFERENT", "MISSING", "EXTRA"):
            for rel in res["files"].get(cat, [])[:50]:
                print(cat, rel)
        return 0 if res["ok"] else 1
    if a.cmd == "diff":
        rows = diff_files(a.ref_file, a.target_file)
        for path, x, y in rows:
            print(f"{path}\t{x}\t{y}")
        print(f"{len(rows)} differing leaves (capped at 500)")
        return 0 if not rows else 1
    res = selftest(a.file)
    print(json.dumps(res, indent=1, default=str))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
