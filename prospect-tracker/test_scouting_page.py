# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""/scouting/, built dark (TL_22_SCOUTING_PAGE_BUILD_DARK).

The twelve tests of docs/scouting-2026-10/SCOUTING_PAGE.md section 9, plus the
transcription pin (every cell of data/reference/fv_framework_tables.json equals
the framework document's table cell) and the dormant glossary receipt.

The payload is built in process from the committed inputs; the page is built
from that payload. Nothing here writes the served tree: the exporter's two
outputs are redirected to tmp paths (and by conftest's sidecar mirror for every
other test), and the page goes to a tmp preview root.
"""
from __future__ import annotations

import ast
import html
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

import build_site as B  # noqa: E402
import tools.scouting_export as SX  # noqa: E402
import value_framework as VF  # noqa: E402

EXPORTER = ROOT / "tools" / "scouting_export.py"
SPEC = ROOT / "docs" / "scouting-2026-10" / "SCOUTING_PAGE.md"
FIT_FILE = ROOT / "data" / "value_framework_fitted.json"
YAML = ROOT / "value_framework_config.yaml"
REGISTRY = ROOT / "data" / "model_registry.json"
TOOL_EVAL = ROOT / "data" / "tool_tables_rederived_eval.json"
FRAMEWORK_DOC = ROOT / "docs" / "reference" / "FANGRAPHS_FV_FRAMEWORK.md"

# The post-step-J markers, copied at TL_22's build (2026-10-14) from the fit
# file's empirical_anchors.anchors_provenance: its opening amendment line and
# the clause naming the label the 35 and 40 knots were re-measured on.
PROV_MARK_A = "SUB-45 KNOTS RE-AMENDED"
PROV_MARK_B = "RE-MEASURED ON THE fWAR LABEL (published FanGraphs WAR"
PROV_LABEL = "FanGraphs WAR"   # owner answer EPOCH-Q4
PIN_FAIL = "the fit file no longer matches the provenance sentence: change the copy"


@pytest.fixture(scope="module")
def payload() -> dict:
    return SX.build_payload()


@pytest.fixture(scope="module")
def page_html(payload) -> str:
    return B.build_scouting_page(payload)


def _soup(text: str):
    from bs4 import BeautifulSoup
    return BeautifulSoup(text, "html.parser")


def _registry_ids() -> set:
    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
    return {m.get("model_id") for m in reg["models"]}


# ---- 1. flag off: nothing served moves ---------------------------------------

def test_flag_off_served_tree_byte_identical(tmp_path, monkeypatch):
    assert B.SCOUTING_PAGE_LIVE is False
    assert SX.page_live() is False
    # No nav leaf, no sitemap row, no published page, no data/ payload.
    assert "scouting" not in {k for k, _l, _h in B.nav_leaves()}
    assert "/scouting/" not in {p for p, _f, _w in B.sitemap_pages()}
    assert not (ROOT / "scouting" / "index.html").exists()
    assert not (ROOT / "data" / "scouting_reference.json").exists()
    # The exporter writes only its preview path.
    out, prev = tmp_path / "data" / "scouting_reference.json", tmp_path / "preview" / "s.json"
    monkeypatch.setattr(SX, "OUT_PATH", out)
    monkeypatch.setattr(SX, "PREVIEW_PATH", prev)
    assert SX.main([]) == 0
    assert prev.is_file() and not out.exists()
    assert {p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file()} == {
        "preview/s.json"}
    # The page lands only in the preview root; _write (the served tree) is never called.
    calls = []
    monkeypatch.setattr(B, "_write", lambda rel, content: calls.append(rel))
    monkeypatch.setattr(B, "SCOUTING_PREVIEW_SITE", tmp_path / "site")
    written = Path(B.write_scouting_page())
    assert calls == []
    assert written == tmp_path / "site" / "scouting" / "index.html" and written.is_file()
    # main() reaches the page only through write_scouting_page (no literal route).
    src = Path(B.__file__).read_text(encoding="utf-8")
    assert '_write("scouting/index.html"' not in src
    assert "    write_scouting_page()\n" in src.replace("\r\n", "\n")


def test_flag_on_emits_nav_and_sitemap_only_then(tmp_path, monkeypatch):
    """The sitemap row is read at call time; the nav entry is the one
    conditional element of NAV_ITEMS; the exporter follows the flag literal."""
    monkeypatch.setattr(B, "SCOUTING_PAGE_LIVE", True)
    assert ("/scouting/", "monthly", "0.6") in B.sitemap_pages()
    src = Path(B.__file__).read_text(encoding="utf-8")
    assert ('*((("scouting", "Scouting", "/scouting/"),) if SCOUTING_PAGE_LIVE else ()),'
            in src)
    fake = tmp_path / "build_site.py"
    fake.write_text("SCOUTING_PAGE_LIVE = True\n", encoding="utf-8")
    monkeypatch.setattr(SX, "BUILD_SITE_PATH", fake)
    assert SX.page_live() is True and SX.output_path() == SX.OUT_PATH


# ---- 2. every number has a registered source -----------------------------------

_LABEL_KEYS = {"schema", "grade", "fv", "year"}


def _walk_numbers(node, path, cells, loose):
    if isinstance(node, dict):
        if "v" in node and "ref" in node:
            cells.append((path, node))
            return
        for k, v in node.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                if k not in _LABEL_KEYS:
                    loose.append(f"{path}.{k}")
            else:
                _walk_numbers(v, f"{path}.{k}", cells, loose)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                loose.append(f"{path}[{i}]")
            else:
                _walk_numbers(v, f"{path}[{i}]", cells, loose)


def test_every_number_has_registered_source(payload):
    cells, loose = [], []
    _walk_numbers({k: v for k, v in payload.items() if k != "sources"}, "", cells, loose)
    assert not loose, f"numbers outside a sourced cell: {loose[:10]}"
    srcs = {s["id"]: s for s in payload["sources"]}
    assert set(srcs) == SX.SOURCE_IDS
    numeric = [c for _p, c in cells if isinstance(c["v"], (int, float)) and not isinstance(c["v"], bool)]
    assert numeric, "the payload carries served numbers"
    for path, c in cells:
        assert c["ref"] in srcs, f"{path}: {c['ref']}"
    ids = _registry_ids()
    spec = SPEC.read_text(encoding="utf-8")
    for s in srcs.values():
        row = s["registry_row"]
        if row == "scouting_reference" and row not in ids:
            # TL_23 adds the row; until then only the id registered in the spec passes.
            assert "| `scouting_reference` (new, TL_23) |" in spec
        else:
            assert row in ids, f"{s['id']}: registry row {row} does not resolve"
        for named in s.get("named_rows", ()):
            assert named in ids


# ---- 3. the FV-cell guard ---------------------------------------------------------

def _tree():
    return ast.parse(EXPORTER.read_text(encoding="utf-8"))


def _vf_aliases(tree) -> set:
    names = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                if a.name == "value_framework":
                    names.add(a.asname or a.name)
    return names


ALLOWED_VF = {"fv_to_prime_war", "fv_to_6yr_avg_war", "p_bucket_given_fv"}


def test_fv_cell_guard_imports():
    std = set(sys.stdlib_module_names) | {"__future__"}
    for n in ast.walk(_tree()):
        if isinstance(n, ast.Import):
            for a in n.names:
                top = a.name.split(".")[0]
                assert top in std or a.name == "value_framework", f"import {a.name}"
        elif isinstance(n, ast.ImportFrom):
            mod = n.module or ""
            if mod == "value_framework":
                assert {a.name for a in n.names} <= ALLOWED_VF, mod
            else:
                assert mod.split(".")[0] in std and n.level == 0, f"from {mod} import"


def test_fv_cell_guard_attributes():
    tree = _tree()
    aliases = _vf_aliases(tree)
    assert aliases == {"vf"}
    attr_parents = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id in aliases:
            assert n.attr in ALLOWED_VF, f"value_framework.{n.attr}"
            attr_parents.add(id(n.value))
    # The module object is never passed around or read dynamically (getattr).
    for n in ast.walk(tree):
        if isinstance(n, ast.Name) and n.id in aliases:
            assert id(n) in attr_parents, f"bare use of {n.id} at line {n.lineno}"


FORBIDDEN_LITERALS = (r"debuts", r"prospects\.db", r"value_framework_fitted", r"empirical_anchors",
                      r"cohort", r"outcome", r"\befv", r"[ex]fv[a-z0-9_]*\.(json|js|csv|parquet)",
                      r"fit_and_write", r"_fitted\b")


def test_fv_cell_guard_literals():
    tree = _tree()
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            for pat in FORBIDDEN_LITERALS:
                assert not re.search(pat, n.value, re.I), f"literal {n.value[:60]!r} matches {pat}"
        # No group-by on FV, or on anything: the exporter aggregates nothing.
        if isinstance(n, (ast.Name, ast.Attribute)):
            name = n.id if isinstance(n, ast.Name) else n.attr
            assert name not in {"groupby", "defaultdict", "Counter", "pandas", "sqlite3"}, name


def test_fv_cell_guard_fit_path_untouched(tmp_path, monkeypatch):
    import empirical_anchors
    before = json.dumps(SX.build_payload(), sort_keys=True)

    def _boom(*_a, **_k):
        raise AssertionError("the scouting exporter reached the fit path")
    monkeypatch.setattr(VF, "fit_and_write", _boom)
    monkeypatch.setattr(empirical_anchors, "derive_empirical_war_anchors", _boom)
    after = json.dumps(SX.build_payload(), sort_keys=True)
    assert after == before
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    SX.write_payload(SX.build_payload(), a)
    SX.write_payload(SX.build_payload(), b)
    assert a.read_bytes() == b.read_bytes(), "the output is deterministic"


# ---- 4. the FV tier block --------------------------------------------------------

def test_fv_tier_block_keys_registered(payload):
    fv = payload["fv_tiers"]
    assert tuple(fv) == SX.FV_TIER_KEYS == (
        "headline", "published_arrives", "low_end_roles", "published_expected",
        "bucket_odds", "published_shares")
    for r in fv["headline"]["rows"]:
        assert set(r) == {"fv", "role", "prime_war", "six_yr_avg_war"}
    assert [r["fv"] for r in fv["headline"]["rows"]] == list(range(20, 81, 5))
    cells, loose = [], []
    _walk_numbers(fv, "fv_tiers", cells, loose)
    assert cells and not loose
    assert {c["source"] for _p, c in cells} <= set(SX.FV_TIER_SOURCES)
    # The served cells are exactly the three served functions at g.
    for r in fv["headline"]["rows"]:
        g = r["fv"]
        assert r["six_yr_avg_war"]["v"] == round(VF.fv_to_6yr_avg_war(g), 4)
        if g >= SX.PRIME_TABLE_MIN_FV:
            assert r["prime_war"]["v"] == round(VF.fv_to_prime_war(g), 4)
        else:
            assert r["prime_war"]["v"] is None and r["prime_war"]["status"] == "no_table"


# ---- 5. the provenance pin ---------------------------------------------------------

def _fit_reads() -> dict:
    """ONLY cohort_window, n_cohort, policy_digest.blend_weight_public and
    anchors_provenance of empirical_anchors; never anchors or diagnostics."""
    ea = json.loads(FIT_FILE.read_text(encoding="utf-8"))["empirical_anchors"]
    return {"cohort_window": ea["cohort_window"], "n_cohort": ea["n_cohort"],
            "blend_weight_public": ea["policy_digest"]["blend_weight_public"],
            "anchors_provenance": ea["anchors_provenance"]}


def test_provenance_sentence_matches_fit_file(page_html):
    import yaml
    cfg = yaml.safe_load(YAML.read_text(encoding="utf-8"))
    use_empirical = bool((cfg.get("anchor_calibration") or {}).get("use_empirical"))
    f = _fit_reads()
    prov = f["anchors_provenance"]
    label = PROV_LABEL if PROV_MARK_B in prov else None
    y0, y1 = f["cohort_window"]
    filled = B.SCOUTING_PROV_TEMPLATE.format(Y0=y0, Y1=y1, N=f"{int(f['n_cohort']):,}", LABEL=label)
    ok = (use_empirical  # if false, the sentence must describe the yaml seed instead
          and PROV_MARK_A in prov and PROV_MARK_B in prov and label is not None
          and f["blend_weight_public"] == 0.5 and "half and half" in B.SCOUTING_PROV
          and B.SCOUTING_PROV == filled
          and B.SCOUTING_COPY["B-PROV"] == B.SCOUTING_PROV
          and B.SCOUTING_PROV in html.unescape(page_html))
    assert ok, PIN_FAIL
    assert B.SCOUTING_PROV_TEMPLATE == (
        "45 and up: the {Y0}-{Y1} average ({N} players), blended half and half with the public "
        "Edwards scale, more public weight where a tier is thin, the top tier the public scale "
        "alone; 35 and 40: re-measured on {LABEL} without a blend; below 35: a floor, not a "
        "measurement."), "the TL_20 template, verbatim"


# ---- 6. the calibration line and the reconciliation note ------------------------------

B_CAL = ("This column is the table our valuations use today. It is under a registered "
         "calibration test, the Prospect Anchor gate, and it is not a measured result until that "
         "test reads.")
B_REC = ("The glossary's methodology table prints the configuration's starting values for this "
         "table until the Prospect Anchor gate moves that table to what serves; this page prints "
         "what serves.")


def test_calibration_line_and_reconciliation_note_verbatim(page_html):
    soup = _soup(page_html)
    box = soup.select_one('#fv-tiers .sc-expected-notes[data-quantity="B"]')
    assert box is not None
    texts = [p.get_text() for p in box.find_all("p")]
    assert B_CAL in texts and B_REC in texts
    # Beside the expected column: right after the headline table.
    head_fig = soup.select_one("#fv-tiers figure")
    assert box in head_fig.find_next_siblings()
    text = soup.get_text(" ").lower()
    assert "accurate" not in text and "validated" not in text


# ---- 7. Quantity A and B never share a column ------------------------------------------

def test_quantity_a_and_b_never_share_a_column(payload, page_html):
    fv = payload["fv_tiers"]
    tables = [fv["headline"], fv["published_arrives"], fv["published_expected"],
              fv["low_end_roles"]["hitters"], fv["low_end_roles"]["relievers"],
              fv["bucket_odds"]["hitter"], fv["bucket_odds"]["pitcher"],
              fv["published_shares"]["hitter"], fv["published_shares"]["pitcher"]]
    for t in tables:
        qs = [c["quantity"] for c in t["columns"]]
        assert set(qs) <= {"A", "B", None}
        a = [i for i, q in enumerate(qs) if q == "A"]
        b = [i for i, q in enumerate(qs) if q == "B"]
        assert not (a and b) or max(a) < min(b), "the A group precedes the B group"
    assert [c["quantity"] for c in fv["headline"]["columns"]] == [None, "A", "A", "B"]
    soup = _soup(page_html)
    for table in soup.select("#fv-tiers table"):
        heads = [th.get("data-quantity") for th in table.select("thead th")]
        for row in table.select("tbody tr"):
            cells = row.find_all(["th", "td"])
            assert [c.get("data-quantity") for c in cells] == heads


# ---- 8. measured tool cells only on PASS ------------------------------------------------

def test_tool_cells_measured_only_on_pass(payload, page_html):
    rec = json.loads(TOOL_EVAL.read_text(encoding="utf-8"))
    primary = rec["result"]["primary"]
    secondary = set(rec["result"].get("secondary") or {})
    n_measured = 0
    for t in payload["tool_tiers"]["tables"]:
        has = any(c["kind"] == "measured" for c in t["columns"])
        cell = t["cell"]
        assert cell is None or cell in primary, cell
        assert cell not in secondary
        passed = bool(cell) and primary[cell]["verdict"] == "PASS"
        assert has == passed, t["key"]
        n_measured += has
        if has:
            for r in t["rows"]:
                m = r["measured"]
                if m["v"] is not None:
                    b = [x for x in primary[cell]["candidate_bins"] if x["bin"] == r["grade"]][0]
                    assert not b["thin"] and m["v"] == round(b["smoothed"], 6)
        if cell in SX.NO_ESTIMATE_CELLS:
            assert not any(c["kind"] == "estimate" for c in t["columns"])
    assert n_measured == sum(1 for c in primary.values() if c["verdict"] == "PASS"
                             and c["cell"] not in SX.NO_ESTIMATE_CELLS)
    assert page_html.count("measured on debuted players</th>") == n_measured
    k = primary["hit__k_pct"]["verdict"]
    if k != "PASS":
        assert B.SCOUTING_COPY["C-K-NONE"] in html.unescape(page_html)


# ---- 9. the ISO column ----------------------------------------------------------------

def test_iso_column_labelled_estimate(payload, page_html):
    iso = [t for t in payload["tool_tiers"]["tables"] if t["key"] == "game_pwr_iso"][0]
    row20 = [r for r in iso["rows"] if r["grade"] == 20][0]["smith_power.iso"]
    assert row20["v"] == ".000" and row20["source_value"] == "-.013" and row20["status"] == "floored"
    soup = _soup(page_html)
    cap = [t for t in soup.select("#tools table") if t.caption.get_text() == "ISO by game power grade"]
    assert cap, "the ISO table"
    heads = [th.get_text() for th in cap[0].select("thead th")]
    assert "ISO: FanGraphs framework estimate (Smith, 2013)" in heads
    rows = {tr.th.get_text(): [td.get_text() for td in tr.find_all("td")] for tr in cap[0].select("tbody tr")}
    assert rows["20"][0] == ".000"
    assert B.SCOUTING_COPY["C-GP-NOTE-2"] in html.unescape(page_html)


# ---- 10. grades integer, WAR one decimal ------------------------------------------------

def test_grades_integer_war_one_decimal(payload, page_html):
    soup = _soup(page_html)
    tables = soup.select("table")
    head = [t for t in tables if t.caption.get_text() == B.SCOUTING_COPY["B-TBL-CAP"]][0]
    for tr in head.select("tbody tr"):
        g = tr.th.get_text()
        assert re.fullmatch(r"\d{2}", g), g
        tds = [td.get_text() for td in tr.find_all("td")]
        assert re.fullmatch(r"\d+\.\d", tds[1]) or (tds[1] == "no table" and int(g) < 35), tds
        assert re.fullmatch(r"\d+\.\d", tds[2]), tds
    for cap in (B.SCOUTING_COPY["B-PO-CAP-H"], B.SCOUTING_COPY["B-PO-CAP-P"]):
        t = [t for t in tables if t.caption.get_text() == cap][0]
        for tr in t.select("tbody tr"):
            assert re.fullmatch(r"\d{2}", tr.th.get_text())
            for td in tr.find_all("td"):
                assert re.fullmatch(r"\d{1,3}%", td.get_text()), td.get_text()
    # Every grade cell in every tool table is an integer.
    for t in soup.select("#tools table"):
        for tr in t.select("tbody tr"):
            assert re.fullmatch(r"\d{2}", tr.th.get_text())
    # Transcribed values print exactly as the transcription carries them.
    tr_tables = json.loads((ROOT / "data" / "reference" / "fv_framework_tables.json")
                           .read_text(encoding="utf-8"))["tables"]
    pb = [t for t in tables if t.caption.get_text() == B.SCOUTING_COPY["B-PB-CAP"]][0]
    first = pb.select("tbody tr")[0]
    src = [r for r in tr_tables["expected_value_2026"]["rows"] if r["row"] == "70"]
    assert [td.get_text() for td in first.find_all("td")] == [
        src[0]["cells"]["expected_war"]["v"], src[0]["cells"]["star_odds"]["v"],
        src[1]["cells"]["expected_war"]["v"], src[1]["cells"]["star_odds"]["v"]]
    assert B._sc_grade(62.1) == "63", "grades round up"
    assert B._sc_war(0.0703) == "0.1" and B._sc_pct(0.505) == "51%"


# ---- 11. the exporter's copy constants match the yaml --------------------------------------

def test_static_constants_match_config():
    import yaml
    cfg = yaml.safe_load(YAML.read_text(encoding="utf-8"))
    b = cfg["buckets"]
    assert [k for k, *_ in SX.BUCKETS] == list(b["order"])
    assert [band for _k, band, *_ in SX.BUCKETS] == [b[k]["band"] for k in b["order"]]
    assert SX.PRIME_TABLE_MIN_FV == min(int(k) for k in cfg["fv_to_prime_war"])


# ---- 12. copy ----------------------------------------------------------------------------

def test_scouting_copy_lint(page_html):
    import copy_lint as L
    recs = L.extract_page("scouting/index.html", page_html)
    res = L.lint_records(recs)
    hard = {r: [v["text"] for v in h.values()] for r, h in res["rules"].items() if h}
    assert not hard, hard
    assert not res["L4"] and not res["L5_density"]
    text = html.unescape(page_html)
    assert chr(0x2014) not in text and chr(0x2013) not in text
    for s in B.SCOUTING_COPY.values():
        for line in (s if isinstance(s, tuple) else (s,)):
            assert not L.BAN_RE.search(line), line
    src = EXPORTER.read_text(encoding="utf-8") + Path(__file__).read_text(encoding="utf-8")
    assert chr(0x2014) not in src and chr(0x2013) not in src


def test_copy_matches_the_registered_document():
    """Every copy item the page prints is the section 8 text, verbatim."""
    spec = SPEC.read_text(encoding="utf-8").replace("\r\n", "\n")
    for k, v in B.SCOUTING_COPY.items():
        if k in ("B-PROV", "B-NO-TABLE", "B-NOT-PUBLISHED", "C-BLANK", "B-PO-CAP-H", "B-PO-CAP-P",
                 "H1", "LEDE", "A-11") or isinstance(v, tuple):
            continue
        flat = re.sub(r"\s+", " ", spec)
        assert v in flat, k


# ---- the transcription and the receipt ---------------------------------------------------

def _md_table_after(lines: list, heading_path: list) -> list:
    i = 0
    for h in heading_path:
        i = next(j for j in range(i, len(lines)) if lines[j].strip() == h)
    j = i + 1
    while not lines[j].startswith("|"):
        j += 1
    rows = []
    while j < len(lines) and lines[j].startswith("|"):
        rows.append([c.strip() for c in lines[j].strip().strip("|").split("|")])
        j += 1
    return rows[2:]


def test_transcription_matches_the_framework_document():
    doc = json.loads((ROOT / "data" / "reference" / "fv_framework_tables.json").read_text(encoding="utf-8"))
    lines = FRAMEWORK_DOC.read_text(encoding="utf-8").splitlines()
    assert len(doc["tables"]) == 20
    for key, t in doc["tables"].items():
        sec = next(ln.strip() for ln in lines if re.match(rf"## {re.escape(t['section'])} ", ln))
        path = [sec] if t["heading"] == sec.lstrip("# ") else [sec, "### " + t["heading"]]
        body = _md_table_after(lines, path)
        assert [r[0] for r in body] == [r["row"] for r in t["rows"]], key
        for md_row, row in zip(body, t["rows"]):
            vals = ["" if v in ("(no term)", "(blank)") else v for v in md_row[1:]]
            assert [c["v"] for c in row["cells"].values()] == vals, (key, row["row"])
            for c in row["cells"].values():
                assert c["section"] == t["section"] and c["source"] == t["source"]
                assert c["source"] in doc["sources"]


def test_glossary_receipt_is_registered():
    js = (ROOT / "assets" / "glossary.js").read_text(encoding="utf-8")
    m = re.search(r"\n      scouting_reference: \{\n        art: \"/data/scouting_reference\.json\",", js)
    assert m, "the scouting_reference receipt in _receiptSpecs"
