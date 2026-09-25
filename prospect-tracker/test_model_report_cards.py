"""Guards for the two accountability surfaces built on data/model_registry.json.

Part 1, Model Report Cards v0. The card blocks put proof numbers on the
Models & Proofs view, so the load-bearing risk is a card number drifting from
its eval artifact. These tests are the anti-drift fence: every champion/baseline
must trace to a value in the row's committed artifact (within display rounding),
the card schema must validate, and the number must survive refresh_stamps().

Part 2, the /models/ accountability hub (build_site.build_models). The risk
there is different and worse: the page's whole claim is that its verdicts are
read rather than written and that its receipts resolve. A link to an artifact
the deploy does not ship is a 404 on a page about honesty, and a verdict string
the page invented would be the exact failure the ledger exists to prevent. Both
are pinned here against the registry, the artifacts and the deploy manifests.

build_models() only reads, so these tests dirty nothing.
"""
import functools
import json
import re
from pathlib import Path

import model_registry as mr

HERE = Path(__file__).parent


def _cards():
    reg = mr.load()
    return [m for m in reg["models"] if m.get("card")]


def _flatten_numbers(obj):
    out = []
    if isinstance(obj, dict):
        for v in obj.values():
            out += _flatten_numbers(v)
    elif isinstance(obj, list):
        for v in obj:
            out += _flatten_numbers(v)
    elif isinstance(obj, bool):
        pass
    elif isinstance(obj, (int, float)):
        out.append(float(obj))
    return out


def test_at_least_the_flagship_cards_exist():
    ids = {m["model_id"] for m in _cards()}
    assert {"fa_projection_marcel", "eta", "consensus_fv", "sem_plus"} <= ids


def test_registry_validates_with_cards():
    assert mr.validate() == []


def test_card_numbers_trace_to_artifact():
    """Each headline champion/baseline is a display-rounding of some value in
    the row's eval artifact (abs tol max(0.02, 2% of value))."""
    problems = []
    for m in _cards():
        art = HERE / m["eval_artifact"]
        nums = _flatten_numbers(json.loads(art.read_text(encoding="utf-8")))
        for h in m["card"]["headline"]:
            for role in ("champion", "baseline"):
                target = float(h[role])
                tol = max(0.02, abs(target) * 0.02)
                if not any(abs(target - x) <= tol for x in nums):
                    problems.append(
                        f"{m['model_id']} card {role}={target} not found in {m['eval_artifact']}")
    assert not problems, "\n".join(problems)


def test_refresh_stamps_preserves_card(tmp_path, monkeypatch):
    """refresh_stamps() rewrites the registry monthly; the card field must
    round-trip. A literal card comes back unchanged. A derived card comes back
    as its artifact reading with its spec intact (and
    test_derived_cards_equal_their_artifact_exactly holds that reading equal
    to the committed card). Run it against a temp copy so the committed file
    is untouched."""
    reg = mr.load()
    before = {m["model_id"]: m for m in reg["models"] if m.get("card")}
    want = {mid: (mr.derive_card(m) if m["card"].get("derived_from") else m["card"])
            for mid, m in before.items()}
    tmp = tmp_path / "reg.json"
    tmp.write_text(json.dumps(reg, ensure_ascii=False, indent=1), encoding="utf-8")
    monkeypatch.setattr(mr, "REGISTRY_PATH", tmp)
    mr.refresh_stamps()
    after = json.loads(tmp.read_text(encoding="utf-8"))
    got = {m["model_id"]: m.get("card") for m in after["models"]}
    for mid, card in want.items():
        assert got.get(mid) == card, f"{mid} card lost or altered by refresh_stamps"


# --------------------------------------------------------------------------- #
# Derived cards (audit L18-01, 2026-09-11)
# --------------------------------------------------------------------------- #
# consensus_fv served a weighted-vs-equal pair its own notes said had been
# removed, with a star on a Spearman lead its own artifact calls not
# resolvable, and every test above stayed green: the tolerance trace accepts a
# number within max(0.02, 2 percent) of ANY leaf of a file with thousands of
# leaves. A card over an artifact the pipeline regenerates now names the path
# of each number (card.derived_from) and refresh_stamps() re-reads it.
#
# Artifacts run_monthly regenerates on every run, whose cards therefore cannot
# hold typed numbers. data/eta_eval.json is regenerated too and its card is
# still a literal that has drifted slightly from it; converting that card is an
# open follow-up (which of its two champion blocks the card quotes is a
# judgement call), so it is not listed here yet.
REGENERATED_CARD_ARTIFACTS = {"data/source_backtest.json"}


def _derived_cards():
    return [m for m in _cards() if m["card"].get("derived_from")]


def _champ_beats(h) -> bool:
    return (h["champion"] < h["baseline"] if h["better"] == "lower"
            else h["champion"] > h["baseline"])


def test_derived_cards_equal_their_artifact_exactly():
    """Provenance, not proximity: a derived card is held to the value at the
    path it names, exactly. A failure means the artifact was regenerated and
    refresh_stamps() has not run since (`python model_registry.py`)."""
    cards = _derived_cards()
    assert cards, "no derived cards; consensus_fv's card must be derived"
    problems = []
    for m in cards:
        reading = mr.derive_card(m)
        if reading != m["card"]:
            problems.append(f"{m['model_id']}: committed card {m['card']} "
                            f"!= artifact reading {reading}")
    assert not problems, "\n".join(problems)


def test_cards_on_regenerated_artifacts_are_derived():
    literal = [m["model_id"] for m in _cards()
               if m["eval_artifact"] in REGENERATED_CARD_ARTIFACTS
               and not m["card"].get("derived_from")]
    assert not literal, (
        f"typed card numbers over an artifact run_monthly regenerates: {literal}. "
        "They go stale on the next run; give the card a derived_from spec.")


def test_consensus_fv_card_carries_only_the_leg_its_artifact_resolves():
    """The row's own reading: blending buys discrimination, not ordering. The
    ordering (Spearman) leg of accuracy.consensus_vs_inputs is not resolvable
    at this power, so this row's card is the AUC leg alone, read from that
    block, with n read from the common set it was measured on."""
    row = next(m for m in mr.load()["models"] if m["model_id"] == "consensus_fv")
    card = row["card"]
    spec = card.get("derived_from")
    assert spec, "consensus_fv's card is typed again; it must be derived"
    assert spec.get("n") == "accuracy.common_n"
    paths = [p for hs in spec["headline"] for p in hs.values()]
    assert paths and all(p.startswith("accuracy.consensus_vs_inputs.auc.")
                         for p in paths), paths
    assert not any("spearman" in h["label"].lower() for h in card["headline"]), (
        "a Spearman headline is back on consensus_fv; the row does not claim to "
        "order realized WAR better than its best input")


def test_fa_projection_marcel_card_reads_gate1_pooled_war():
    """The literal 0.63 vs 0.73 card outlived two Gate 1 re-measures (0.574 on
    2026-08-03, 0.5157 on 2026-09-23). It is read from pooled.war now, rounded
    to three places for display, with the star gated on the artifact's own WAR
    gate."""
    row = next(m for m in mr.load()["models"] if m["model_id"] == "fa_projection_marcel")
    spec = row["card"].get("derived_from")
    assert spec, "fa_projection_marcel's card is typed again; it must be derived"
    assert spec["headline"] == [{"champion": "pooled.war.mae_model",
                                 "baseline": "pooled.war.mae_base",
                                 "resolvable": "gates.war"}]
    art = json.loads((HERE / "data" / "fa_gate1_eval.json").read_text(encoding="utf-8"))
    h = row["card"]["headline"][0]
    assert h["champion"] == round(art["pooled"]["war"]["mae_model"], spec["digits"])
    assert h["baseline"] == round(art["pooled"]["war"]["mae_base"], spec["digits"])
    assert row["card"]["n"] == art["pooled"]["war"]["n"]


def test_derived_card_digits_must_be_a_small_integer():
    import pytest
    art = {"a": 0.123456, "b": 0.2}
    card = {"headline": [{"label": "x", "champion": 0, "baseline": 0, "better": "lower"}],
            "derived_from": {"headline": [{"champion": "a", "baseline": "b"}]}}
    got = mr.derive_card({"card": dict(card, derived_from=dict(card["derived_from"], digits=2))}, art)
    assert got["headline"][0]["champion"] == 0.12
    assert mr.derive_card({"card": card}, art)["headline"][0]["champion"] == 0.123456
    for bad in (True, -1, 7, 2.0, "3"):
        with pytest.raises(ValueError):
            mr.derive_card({"card": dict(card, derived_from=dict(card["derived_from"], digits=bad))}, art)


def test_a_validated_derived_card_shows_a_resolved_win():
    """`validated` means the champion beats its stated baseline. When a
    derived card is the proof, at least one headline must be a strict win on a
    leg the artifact resolves. If a regeneration moves every leg inside its
    floor the verdict needs an owner look, and this is where that surfaces."""
    problems = []
    for m in _derived_cards():
        if m["verdict"] != "validated":
            continue
        if not any(h.get("resolvable") is True and _champ_beats(h)
                   for h in m["card"]["headline"]):
            problems.append(f"{m['model_id']}: validated, but its derived card "
                            "shows no resolved win")
    assert not problems, "\n".join(problems)


def _card_js():
    """assets/glossary.js::_cardHeadline, run in a real JS engine. The function
    is pure (card in, markup out) and needs only escapeHtml beside it."""
    import pytest
    MiniRacer = pytest.importorskip("py_mini_racer").MiniRacer
    js = (HERE / "assets" / "glossary.js").read_text(encoding="utf-8").replace("\r\n", "\n")
    i = js.index("function _cardHeadline(card) {")
    j = js.index("\n}\n", i) + 2
    ctx = MiniRacer()
    ctx.eval('function escapeHtml(s) { return String(s == null ? "" : s)'
             '.replace(/&/g, "&amp;").replace(/</g, "&lt;")'
             '.replace(/>/g, "&gt;").replace(/"/g, "&quot;"); }')
    ctx.eval(js[i:j])
    return ctx


def _render(ctx, card) -> str:
    return ctx.eval(f"_cardHeadline({json.dumps(card)})")


STAR = "★"


def test_the_card_star_needs_a_strict_resolved_win():
    ctx = _card_js()
    base = {"label": "x", "champion": 0.75, "baseline": 0.70, "better": "higher"}
    literal = _render(ctx, {"headline": [base]})
    assert literal.count(STAR) == 1, "a literal card lost its star"
    unresolved = _render(ctx, {"headline": [dict(
        base, resolvable=False, verdict="not resolvable at this power")]})
    assert unresolved.count(STAR) == 0, (
        "the star went to a lead its artifact calls not resolvable")
    assert "not resolvable at this power" in unresolved, (
        "the artifact's verdict is not shown beside an unresolved bar pair")
    resolved = _render(ctx, {"headline": [dict(base, resolvable=True,
                                               verdict="the blend wins")]})
    assert resolved.count(STAR) == 1 and "the blend wins" in resolved
    tie = _render(ctx, {"headline": [dict(base, champion=0.70)]})
    assert tie.count(STAR) == 0, "a tie was starred as a win"
    lower = _render(ctx, {"headline": [dict(base, better="lower", champion=0.60)]})
    assert lower.count(STAR) == 1


def test_no_served_card_stars_a_leg_its_artifact_does_not_resolve():
    """Over the live registry: render each headline alone and count stars. A
    star appears exactly where the champion strictly wins and the artifact has
    not marked the leg unresolvable."""
    ctx = _card_js()
    problems = []
    for m in _cards():
        for h in m["card"]["headline"]:
            got = _render(ctx, {"headline": [h]}).count(STAR)
            want = int(_champ_beats(h) and h.get("resolvable") is not False)
            if got != want:
                problems.append(f"{m['model_id']} {h['label']!r}: {got} stars, "
                                f"expected {want}")
    assert not problems, "\n".join(problems)


# --------------------------------------------------------------------------- #
# Part 2: the /models/ accountability hub
# --------------------------------------------------------------------------- #
@functools.lru_cache(maxsize=1)
def _models_page() -> str:
    import build_site
    return build_site.build_models()


def _excluded_data_files() -> set:
    out = set()
    for line in (HERE / "deploy" / "data_exclude.txt").read_text(
            encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.add(line)
    return out


def _page_data_links() -> list:
    return sorted(set(re.findall(r'href="(/data/[^"]+)"', _models_page())))


def test_models_page_links_only_files_the_deploy_actually_ships():
    """Both deploy consumers ship data/ at depth one only. A link to
    /data/<subdir>/<file> or to an excluded file renders as a working link
    locally and a 404 in production, which on a receipts page is worse than
    publishing no link at all."""
    excluded = _excluded_data_files()
    problems = []
    for url in _page_data_links():
        rel = url.lstrip("/")
        if rel.count("/") != 1:
            problems.append(f"{url} is not at data/ depth one")
        elif not (HERE / rel).exists():
            problems.append(f"{url} has no file in the tree")
        elif rel.split("/", 1)[1] in excluded:
            problems.append(f"{url} is held back by deploy/data_exclude.txt")
    assert not problems, "\n".join(problems)


def test_models_page_names_unshippable_artifacts_without_linking_them():
    """Some registry rows point at gate records under docs/ or at lab output
    under tools/. Those paths exist here and do not exist on the webroot, so
    the page must name them and say why they are not linked."""
    page = _models_page()
    unshippable = sorted({
        (m.get("eval_artifact") or "").strip().replace("\\", "/")
        for m in mr.load()["models"]
        if (m.get("eval_artifact") or "").strip()
        and not (m["eval_artifact"].replace("\\", "/").startswith("data/")
                 and m["eval_artifact"].replace("\\", "/").count("/") == 1)})
    for rel in unshippable:
        assert f'href="/{rel}"' not in page, (
            f"the ledger links {rel}, which the deploy does not publish")
        assert rel in page, (
            f"the ledger drops {rel} entirely; it must be named with the "
            "reason it carries no link")
    if unshippable:
        assert "not published:" in page


def test_models_page_verdict_counts_match_the_registry():
    """The tiles and the filter chips are counted off the registry at build
    time. A count that drifts from the rows underneath it would be the page
    making its own claim about the ledger."""
    page = _models_page()
    reg = mr.load()
    counts: dict = {}
    for m in reg["models"]:
        counts[m["verdict"]] = counts.get(m["verdict"], 0) + 1
    for verdict in mr.VERDICTS:
        n = counts.get(verdict, 0)
        # The count is asserted on the verdict's OWN tile, not anywhere on the
        # page: two verdicts can legitimately share a count.
        assert (f'acct-tile--{verdict}"><div class="acct-tilen">{n}</div>'
                in page), f"the {verdict} tile does not show {n}"
        assert (f'data-acct-filter="{verdict}">' in page), f"no {verdict} filter chip"
    assert f'data-acct-filter="all">All <span class="acct-count">{len(reg["models"])}</span>' in page


def test_every_registry_row_is_on_the_page():
    """The ledger's value is that nothing can hide in it, so a row that fails
    to render is the one bug worth a test of its own."""
    page = _models_page()
    missing = [m["model_id"] for m in mr.load()["models"]
               if f"<code>{m['model_id']}</code>" not in page]
    assert not missing, f"registry rows missing from /models/: {missing}"


def test_deprecated_is_rendered_as_a_first_class_group():
    """A loss ledger that files its losses somewhere quieter than its wins is
    not a loss ledger."""
    page = _models_page()
    assert 'data-acct-group="deprecated"' in page
    assert "failed its gate" in page


def test_unvalidated_is_defined_as_ungated_not_as_broken():
    """Owner copy rule for this page: `unvalidated` is a model whose gate has
    not been run. A reader who assumes it means defective has been misled by
    the page, not by the registry."""
    page = _models_page()
    assert "Registered and serving, with no measurement yet" in page
    assert "not the same thing as a model that is wrong" in page


def test_no_verdict_string_on_the_page_is_hand_written():
    """Every quoted artifact verdict must be a byte-for-byte top-level
    `verdict` field of the artifact the same row links. This is the test that
    makes the page's central promise checkable."""
    page = _models_page()
    quoted = re.findall(
        r"<dt>The artifact&#x27;s own words</dt><dd>(.*?)</dd>", page, re.S)
    assert quoted, "no artifact verdicts rendered; has the field label changed?"
    import html as _html
    known = set()
    for path in sorted((HERE / "data").glob("*.json")):
        if path.stat().st_size > 4_000_000:
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(doc, dict) and isinstance(doc.get("verdict"), str):
            known.add(doc["verdict"].strip())
    unknown = [q for q in quoted if _html.unescape(q) not in known]
    assert not unknown, (
        "verdict text on /models/ that is in no artifact: "
        f"{unknown[:3]}")


def test_the_deploy_rule_the_page_encodes_still_matches_the_deploy_scripts():
    """build_site._acct_artifact_url re-derives 'data/ at depth one, minus the
    exclude list' to decide what it may link. If a deploy consumer changes that
    rule, the page starts publishing 404s and every other test here still
    passes, so the rule itself is pinned."""
    nightly = (HERE / "deploy" / "nightly-build.sh").read_text(encoding="utf-8")
    assert "--include='/data/*.json'" in nightly
    workflow = (HERE.parent / ".github" / "workflows"
                / "deploy-prospect-tracker.yml").read_text(encoding="utf-8")
    assert "find data -maxdepth 1" in workflow


# assets/accountability.js drives the one thing on /models/ that is not
# server-rendered: the artifact age, recomputed against the READER's clock so a
# cached page stops advertising the freshness it had on build day. It is run in
# a real JS engine over a DOM shim shaped like the markup build_models() emits
# (the test_betting.py / test_collegesavant_smoke.py pattern), because a filter
# that silently stops filtering on a receipts page hides rows without ever
# failing anything else.
_JS_SHIM = r"""
var __styles = [];
var __url = null;
function __el(tag, attrs, kids) {
  attrs = attrs || {};
  var e = {tag: tag, attrs: attrs, kids: kids || [], textContent: "", title: "",
           style: {}, classes: (attrs["class"] || "").split(" ").filter(Boolean)};
  e.getAttribute = function (k) { return this.attrs[k] === undefined ? null : this.attrs[k]; };
  e.setAttribute = function (k, v) { this.attrs[k] = v; };
  e.classList = {toggle: function (c, on) {
    var i = e.classes.indexOf(c);
    if (on && i === -1) e.classes.push(c);
    if (!on && i !== -1) e.classes.splice(i, 1);
  }};
  e.addEventListener = function (t, fn) { this.__click = fn; };
  e.querySelectorAll = function (sel) { return __find(this, sel); };
  e.querySelector = function (sel) { var r = __find(this, sel); return r.length ? r[0] : null; };
  return e;
}
function __walk(n, out) {
  for (var i = 0; i < n.kids.length; i++) { out.push(n.kids[i]); __walk(n.kids[i], out); }
  return out;
}
function __find(root, sel) {
  return __walk(root, []).filter(function (n) {
    if (sel === ".acct-group") return n.classes.indexOf("acct-group") !== -1;
    if (sel === ".acct-row") return n.classes.indexOf("acct-row") !== -1;
    if (sel === "[data-acct-filter]") return n.attrs["data-acct-filter"] !== undefined;
    if (sel === ".acct-sum>time[datetime]") return n.tag === "time" && n.attrs.datetime !== undefined;
    if (sel.indexOf('[data-acct-filter="') === 0)
      return n.attrs["data-acct-filter"] === sel.slice(19, -2);
    return false;
  });
}
var __app = null;
var document = {
  querySelector: function (s) { return s === ".acct-app" ? __app : null; },
  createElement: function (t) { return {tag: t, textContent: ""}; },
  head: {appendChild: function (n) { __styles.push(n.textContent); }}
};
var history = {replaceState: function (a, b, u) { __url = u; }};
var location = {hash: "", pathname: "/models/"};

function __row(flags, iso) {
  var t = iso ? __el("time", {datetime: iso}) : __el("time", {});
  var attrs = {"class": "acct-row"};
  if (flags) attrs["data-acct-flags"] = flags;
  return __el("details", attrs, [__el("summary", {"class": "acct-sum"}, [t])]);
}
var __groups = [
  __el("div", {"class": "acct-group", "data-acct-group": "validated"},
       [__row("undated", null), __row("", "2026-08-01")]),
  __el("div", {"class": "acct-group", "data-acct-group": "deprecated"},
       [__row("", "2026-08-01"), __row("", "2000-01-01")])
];
var __chips = ["all", "validated", "deprecated", "undated"].map(function (k) {
  return __el("button", {"data-acct-filter": k, "class": "chip"});
});
__app = __el("div", {"class": "acct-app", "data-acct-stale-days": "90"},
             __chips.concat(__groups));
function __click(k) { __find(__app, '[data-acct-filter="' + k + '"]')[0].__click(); }
function __vis() {
  var out = {groups: {}, rows: [], styles: __styles.length, url: __url, times: []};
  __find(__app, ".acct-group").forEach(function (g) {
    out.groups[g.getAttribute("data-acct-group")] = g.style.display || "";
    __find(g, ".acct-row").forEach(function (r) {
      out.rows.push([r.getAttribute("data-acct-flags") || "", r.style.display || ""]);
    });
  });
  __find(__app, ".acct-sum>time[datetime]").forEach(function (t) {
    out.times.push([t.getAttribute("datetime"), t.textContent,
                    t.classes.indexOf("is-stale") !== -1]);
  });
  return JSON.stringify(out);
}
"""


def _js_ctx():
    import pytest
    MiniRacer = pytest.importorskip("py_mini_racer").MiniRacer
    ctx = MiniRacer()
    ctx.eval(_JS_SHIM)
    ctx.eval((HERE / "assets" / "accountability.js").read_text(encoding="utf-8"))
    return ctx


def test_client_recomputes_artifact_age_against_the_readers_clock():
    ctx = _js_ctx()
    st = json.loads(ctx.eval("__vis()"))
    assert st["styles"] == 1, "the client must inject exactly one stylesheet"
    ages = {t[0]: t for t in st["times"]}
    assert ages["2026-08-01"][1].endswith("d"), "a dated artifact got no age"
    assert ages["2026-08-01"][2] is False, "a recent artifact was flagged stale"
    assert ages["2000-01-01"][2] is True, "a decades-old artifact did not read stale"


def test_client_filters_by_verdict_and_by_audit_flag():
    """A verdict chip selects a group. An audit chip cuts across groups, which
    is a different code path and the one that can silently show nothing."""
    ctx = _js_ctx()
    ctx.eval('__click("deprecated")')
    st = json.loads(ctx.eval("__vis()"))
    assert st["groups"] == {"validated": "none", "deprecated": ""}
    assert all(r[1] == "" for r in st["rows"]), "a verdict filter hid single rows"
    assert st["url"] == "#verdict=deprecated"

    ctx.eval('__click("undated")')
    st = json.loads(ctx.eval("__vis()"))
    shown = [r for r in st["rows"] if r[1] == ""]
    assert shown == [["undated", ""]], f"the audit filter selected {shown}"
    assert st["groups"]["validated"] == "" and st["groups"]["deprecated"] == "none"
    assert st["url"] == "#show=undated"

    ctx.eval('__click("all")')
    st = json.loads(ctx.eval("__vis()"))
    assert all(r[1] == "" for r in st["rows"])
    assert set(st["groups"].values()) == {""}
    assert st["url"] == "/models/"


def test_the_hub_ships_and_is_crawlable():
    import build_site
    manifest = [ln.strip() for ln in
                (HERE / "deploy" / "publish_paths.txt").read_text(encoding="utf-8").splitlines()
                if ln.strip() and not ln.strip().startswith("#")]
    assert "models" in manifest, (
        "models/ is not in deploy/publish_paths.txt and would 404 in production")
    assert "/models/</loc>" in build_site.build_sitemap([])
    assert 'href="/models/"' in build_site._footer()
