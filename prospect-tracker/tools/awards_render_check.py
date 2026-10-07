# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""tools/awards_render_check.py - the /awards/ page against its payload (AWARDS_7;
AWARDS_PLAN 6 'Invariants and tests' row I14). Playwright, outside pytest.

It never sets awards_core.AWARDS_LIVE and never writes the published tree. It builds a
temporary copy of the site: the flag-on shells from build_site.build_awards(live=True) and
build_hof(live=True), the flag-off /hof/ from build_hof(live=False), assets/, and only the
data files the pages fetch; then it writes fixture payloads into that copy's data/ and
serves it with `python -m http.server <port>`. Requests off the loopback are aborted.

Fixtures (from the preview payloads under .cache/awards/preview/, built by awards_export.py
while the flag is False, and the tracked race files under data/_labs/awards/):
  live     2026 before the freeze, with the race blocks of race_2026.json
  frozen   the same after a freeze: frozen_at, drift ("Now", eWAR v3) and writers' results
  stale    the live fixture with generated_at 60 hours old
  2024     a closed season with its race; 2023 a closed season with no race record;
  2022     a closed season whose Manager rule is blocked

Checks (each a failure line in the report): every ladder value, name, lamp count
round(|value| / lamp_unit), lamp fill token (the tier of EephusTiers.tier(value, family)),
the lead line and the rule labels against the payload; the comparison table's numbers and
markers against compare.metrics; race lamp heights 12, 8 and 4 px and every lamp against the
Weeks table; the hero caption and its 1st places; the unmeasured state where a card, a race
or a section has no record; no horizontal page overflow; 44 px targets at a coarse pointer
and 24 px at a fine one; the focus ring colour; text contrast of at least 4.5:1; and no
console error beyond the aborted off-loopback requests. Screenshots land in --out.

    python tools/awards_render_check.py --port 9141 --out <dir>
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PREVIEW = ROOT / ".cache" / "awards" / "preview"
LABS = ROOT / "data" / "_labs" / "awards"
WIDTHS = (390, 768, 1024, 1280, 1440)
THEMES = ("light", "dark")
#: Data files the shells and the shared runtimes fetch (copied into the temporary site).
SHARED_DATA = ("glossary.json", "hof_board.json", "search_index.json", "team.json", "watchlist.json")


# --- fixtures ---------------------------------------------------------------------------------

def _load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def _race(season: int):
    p = LABS / f"race_{season}.json"
    if not p.exists():
        return None
    doc = _load(p)
    return {k: v for k, v in doc.items() if k.count("_") == 1 and k.split("_")[0] in ("MVP", "CY", "ROY", "MOY")}


def make_fixtures() -> dict:
    """{name: {relative path under data/: document}}."""
    import awards_core as A

    base = _load(PREVIEW / "awards.json")
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    live = copy.deepcopy(base)
    live["generated_at"] = now.isoformat()
    race = _race(live["season"])
    if race:
        live["race"] = race
        live["seasons"][0]["race"] = True
    shards = {}
    for p in sorted(PREVIEW.glob("awards_20[0-9][0-9].json")):
        doc = _load(p)
        S = doc["season"]
        if S == 2024:
            doc["race"] = _race(S) or doc.get("race")
        elif S == 2023:
            doc["race"] = {k: None for k in (doc.get("race") or {})}
        elif S == 2022:
            doc["awards"].pop("MOY", None)
            doc["rules"]["MOY"]["blocked_on"] = "The inputs for this award are not on file for the season."
        shards[f"awards_{S}.json"] = doc
    for ent in live["seasons"]:
        if ent["season"] == 2022:
            ent["awards"] = [a for a in ent["awards"] if a != "MOY"]
        if ent["season"] == 2024:
            ent["race"] = True

    frozen = copy.deepcopy(live)
    frozen_at = "2026-09-29T14:00:00+00:00"
    frozen["status"] = "frozen"
    frozen["seasons"][0]["status"] = "frozen"
    frozen["stamp"]["frozen_at"] = frozen_at
    frozen["freeze"] = {"frozen_at": frozen_at, "war_provider": frozen["war_provider"], "record_sha256": "0" * 64,
                        "ewar_artifact_generated_at": frozen["stamp"]["ewar_vintage"].get("artifact_generated_at"),
                        "label_build_at": frozen["stamp"]["ewar_vintage"].get("label_build_at"),
                        "finalists_announced": None, "after_finalists": False}
    frozen["selection_caption"] = A.selection_caption(frozen["season"], True)
    for award, by in frozen["awards"].items():
        for lg, blk in by.items():
            drift = []
            for i, r in enumerate(blk["top"][:3]):
                k = r.get("mlbam") if r.get("mlbam") is not None else "c" + str(r.get("club") or "").lower()
                now_v = float(r["score"]) + (0.15 if i == 0 else -0.1)
                drift.append({"id": k, "score_now": now_v, "score_now_display": A.score_display(now_v),
                              "war_provider": "ewar_v3", "unit_label": A.drift_unit_label("ewar_v3"),
                              "tooltip": A.drift_tooltip(frozen_at[:10])})
            blk["drift"] = drift
    top = frozen["awards"]["MVP"]["AL"]["top"]
    frozen["awards"]["MVP"]["AL"]["writers"] = {
        "status": "final", "announce_label": "Writers' vote: not announced yet.",
        "finalists": [{"id": r["mlbam"], "name": r["name"]} for r in top[:3]],
        "winner": {"id": top[1]["mlbam"], "name": top[1]["name"]}, "rule_place_of_winner": 2}
    topn = frozen["awards"]["MVP"]["NL"]["top"]
    frozen["awards"]["MVP"]["NL"]["writers"] = {
        "status": "final", "announce_label": "Writers' vote: not announced yet.",
        "finalists": [{"id": r["mlbam"], "name": r["name"]} for r in topn[:3]],
        "winner": {"id": topn[0]["mlbam"], "name": topn[0]["name"]}, "rule_place_of_winner": 1}
    topc = frozen["awards"]["CY"]["AL"]["top"]
    frozen["awards"]["CY"]["AL"]["writers"] = {
        "status": "finalists", "announce_label": "Writers' vote: not announced yet.",
        "finalists": [{"id": r["mlbam"], "name": r["name"]} for r in topc[:3]], "winner": None,
        "rule_place_of_winner": None}
    frozen["what_this_page_does_not_claim"] = A.does_not_claim_lines(
        "ewar_v2", frozen_at=frozen_at[:10], now_provider="ewar_v3")

    stale = copy.deepcopy(live)
    stale["generated_at"] = (now - dt.timedelta(hours=60)).isoformat()
    return {"live": dict(shards, **{"awards.json": live}),
            "frozen": dict(shards, **{"awards.json": frozen}),
            "stale": dict(shards, **{"awards.json": stale})}


# --- the temporary site -------------------------------------------------------------------------

def build_site_copy(dest: Path) -> None:
    import build_site as B

    shutil.copytree(ROOT / "assets", dest / "assets")
    (dest / "data").mkdir()
    for name in SHARED_DATA:
        if (ROOT / "data" / name).exists():
            shutil.copy2(ROOT / "data" / name, dest / "data" / name)
    for rel, text in (("awards/index.html", B.build_awards(live=True)),
                      ("hof/index.html", B.build_hof(live=True)),
                      ("hof-off/index.html", B.build_hof(live=False))):
        p = dest / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")


def write_fixture(dest: Path, files: dict) -> None:
    for name, doc in files.items():
        (dest / "data" / name).write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")


# --- in-page checks -----------------------------------------------------------------------------

CHECK_JS = r"""
(doc) => {
  const bad = [], T = window.EephusTiers;
  const AW = ["MVP", "CY", "ROY", "MOY"], LG = ["AL", "NL"], KEY = {MVP: "mvp", CY: "cy", ROY: "roy", MOY: "moy"};
  const fix = (v, d) => {
    if (v === null || v === undefined || v === "") return null;
    return Number(v).toFixed(d == null ? 1 : d);
  };
  const probe = document.createElement("span");
  document.body.appendChild(probe);
  const tok = (name) => { probe.style.color = "var(" + name + ")"; return getComputedStyle(probe).color; };
  const fillOf = (rect) => {
    const m = /url\(#([^)]+)\)/.exec(rect.getAttribute("fill") || "");
    const pr = m && document.getElementById(m[1]);
    return pr ? getComputedStyle(pr.querySelector("rect")).fill : "";
  };
  const name = (r) => r.mlbam != null ? r.name : (r.club_name || r.name);
  const key = (r) => r.mlbam != null ? String(r.mlbam) : "c" + String(r.club || "").toLowerCase();
  let nCards = 0, nRows = 0, nRace = 0, nCmp = 0;
  for (const A of AW) for (const L of LG) {
    const id = KEY[A] + "-" + L.toLowerCase(), card = document.getElementById("aw-c-" + id);
    if (!card) { bad.push("missing card " + id); continue; }
    nCards++;
    const rule = doc.rules[A] || {}, blk = (doc.awards[A] || {})[L];
    if (!blk || rule.blocked_on) {
      if (!card.querySelector(".px-state.is-unmeasured")) bad.push(id + ": blocked card without the unmeasured state");
      const msg = card.querySelector(".px-state-msg");
      if (rule.blocked_on && (!msg || msg.textContent.trim() !== rule.blocked_on)) bad.push(id + ": blocked sentence differs");
      continue;
    }
    const ruleText = (card.querySelector(".aw-rule") || {}).textContent || "";
    for (const f of ["label", "floor_label", "tie_label", "two_way_label", "eligibility_label"]) {
      if (rule[f] && ruleText.indexOf(rule[f]) < 0) bad.push(id + ": rule line lacks " + f);
    }
    const top = blk.top.slice(0, 3), lis = card.querySelectorAll(".aw-ladder > li");
    if (lis.length !== top.length) bad.push(id + ": ladder rows " + lis.length + " != " + top.length);
    const pitch = Number(card.querySelector(".aw-ladder").dataset.pitch);
    top.forEach((r, i) => {
      const li = lis[i]; if (!li) return; nRows++;
      const val = fix(r.score_display, rule.decimals);
      if (li.querySelector(".aw-num").textContent !== val) bad.push(id + " row " + (i + 1) + ": value " + li.querySelector(".aw-num").textContent + " != " + val);
      if (li.querySelector(".aw-name").textContent !== name(r)) bad.push(id + " row " + (i + 1) + ": name");
      if (li.dataset.id !== key(r)) bad.push(id + " row " + (i + 1) + ": id");
      const sd = Number(r.score_display), lit = Math.min(60, Math.round(Math.abs(sd) / rule.lamp_unit));
      if (Number(li.dataset.lit) !== lit) bad.push(id + " row " + (i + 1) + ": lamps " + li.dataset.lit + " != " + lit);
      const rect = li.querySelector("rect.aw-lit");
      if (lit && (!rect || Math.round(Number(rect.getAttribute("width")) / pitch) !== lit)) bad.push(id + " row " + (i + 1) + ": lit rect width");
      const want = sd < 0 ? "down" : (rule.family ? T.tier(sd, rule.family) : "ink");
      if (li.dataset.fill !== want) bad.push(id + " row " + (i + 1) + ": fill " + li.dataset.fill + " != " + want);
      const tokName = want === "ink" ? "--text-primary" : want === "down" ? "--down" : "--vt-" + want;
      if (rect && fillOf(rect) !== tok(tokName)) bad.push(id + " row " + (i + 1) + ": lamp colour " + fillOf(rect) + " != " + tokName);
      if (Number(card.querySelector(".aw-lamps").getAttribute("width")) > (pitch === 5 ? 302 : 482)) bad.push(id + ": lamp svg too wide");
    });
    const leads = Array.from(card.querySelectorAll(".aw-lead")).map((p) => p.textContent);
    if (blk.lead && leads.indexOf(blk.lead) < 0) bad.push(id + ": lead line");
    const cmp = card.querySelector(".aw-cmp-t");
    for (const m of ((blk.compare || {}).metrics || [])) {
      const tr = cmp && cmp.querySelector('tr[data-key="' + m.key + '"]');
      if (!tr) { bad.push(id + ": compare row " + m.key); continue; }
      nCmp++;
      const cells = Array.from(tr.querySelectorAll("td.aw-n")).map((td) => td.dataset.v);
      [0, 1, 2].forEach((i) => {
        const want = fix((m.values || [])[i], m.decimals);
        if ((cells[i] || null) !== (want || null) && !(want === null && cells[i] === "")) bad.push(id + " " + m.key + " value " + i + ": " + cells[i] + " != " + want);
      });
      const marks = tr.querySelectorAll(".aw-mk:not(.w)").length;
      const basis = m.family && T.LADDERS[m.family] && m.p99 > m.p1 ? m.values : m.pct;
      const n = [0, 1, 2].filter((i) => basis && basis[i] != null).length;
      if (marks !== n) bad.push(id + " " + m.key + ": markers " + marks + " != " + n);
      tr.querySelectorAll("rect.aw-seg").forEach((sg) => {
        const t = sg.dataset.tier, f = getComputedStyle(sg).fill;
        if (m.family && T.LADDERS[m.family] && f !== tok("--vt-" + t)) bad.push(id + " " + m.key + ": segment " + t + " colour");
      });
    }
    const race = (doc.race || {})[A + "_" + L], det = card.querySelector('details[data-d="race"]');
    if (!race) {
      if (!det.querySelector(".px-state.is-unmeasured")) bad.push(id + ": race without record lacks the unmeasured state");
    } else {
      nRace++;
      const H = {1: 12, 2: 8, 3: 4};
      const rows = det.querySelectorAll(".aw-wt tbody tr");
      det.querySelectorAll("rect.aw-rl").forEach((rc) => {
        const p = Number(rc.dataset.place);
        if (Number(rc.getAttribute("height")) !== H[p]) bad.push(id + ": race lamp height " + rc.getAttribute("height") + " for place " + p);
        const td = rows[Number(rc.dataset.w)] && rows[Number(rc.dataset.w)].querySelectorAll("td")[Number(rc.dataset.f)];
        if (!td || Number(td.dataset.place) !== p) bad.push(id + ": race lamp and Weeks table differ at week " + rc.dataset.w);
      });
      const fins = race.finalists.slice().sort((a, b) => (a.rule_place || 9) - (b.rule_place || 9));
      let want = 0;
      fins.forEach((f) => (race.places[String(f.id)] || []).forEach((p, j) => {
        if ((p === 1 || p === 2 || p === 3) && (race.missing || []).indexOf(race.weeks[j]) < 0) want++;
      }));
      if (det.querySelectorAll("rect.aw-rl").length !== want) bad.push(id + ": race lamps " + det.querySelectorAll("rect.aw-rl").length + " != " + want);
    }
  }
  const cap = document.querySelector(".aw-hero caption");
  const wantCap = doc.selection_caption || ((doc.status === "live" ? "Current leaders on the rule, " : "The eephus selection, 1st place, ") + doc.season);
  if (!cap || cap.textContent !== wantCap) bad.push("hero caption " + (cap && cap.textContent) + " != " + wantCap);
  probe.remove();
  return {bad, nCards, nRows, nRace, nCmp};
}
"""

LAYOUT_JS = r"""
() => {
  const bad = [];
  const se = document.scrollingElement;
  if (se.scrollWidth > window.innerWidth) bad.push("horizontal overflow " + se.scrollWidth + " > " + window.innerWidth);
  const coarse = matchMedia("(pointer: coarse)").matches, min = coarse ? 44 : 24;
  const sel = '.aw-tabs [role="tab"], .hof-modstrip a, .aw-app a.aw-chip, .aw-app summary, .aw-season select, .mlbstats-tabs [role="tab"]';
  document.querySelectorAll(sel).forEach((el) => {
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) return;
    if (r.height < min - 0.5) bad.push("target " + (el.textContent || el.tagName).trim().slice(0, 30) + " is " + r.height.toFixed(1) + " px tall, needs " + min);
  });
  const lum = (c) => {
    const m = /rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?/.exec(c);
    if (!m) return null;
    const f = (v) => { v = v / 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return {L: 0.2126 * f(+m[1]) + 0.7152 * f(+m[2]) + 0.0722 * f(+m[3]), a: m[4] == null ? 1 : +m[4]};
  };
  const bgOf = (el) => {
    for (let e = el; e; e = e.parentElement) {
      const c = getComputedStyle(e).backgroundColor, l = lum(c);
      if (l && l.a > 0.99) return c;
    }
    return getComputedStyle(document.body).backgroundColor;
  };
  const ratio = (a, b) => { const x = lum(a).L, y = lum(b).L; return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  let worst = 99, worstWhat = "", n = 0;
  const scope = document.querySelectorAll(".aw-app *, .hof-app .section-head *, .hof-modstrip *");
  scope.forEach((el) => {
    if (el.closest("svg") || el.closest(".visually-hidden") || el.closest("[hidden]")) return;
    const own = Array.from(el.childNodes).some((t) => t.nodeType === 3 && t.textContent.trim());
    if (!own) return;
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) return;
    const cs = getComputedStyle(el);
    if (cs.visibility === "hidden" || cs.opacity === "0") return;
    const k = ratio(cs.color, bgOf(el)); n++;
    if (k < worst) { worst = k; worstWhat = el.tagName + "." + el.className + " '" + el.textContent.trim().slice(0, 30) + "'"; }
    if (k < 4.5) bad.push("contrast " + k.toFixed(2) + " " + el.tagName + "." + el.className + " '" + el.textContent.trim().slice(0, 30) + "'");
  });
  return {bad, worst: Number(worst.toFixed(2)), worstWhat, nText: n};
}
"""

FOCUS_JS = r"""
() => {
  const el = document.activeElement, cs = getComputedStyle(el);
  const p = document.createElement("span"); document.body.appendChild(p);
  p.style.color = "var(--accent-cyan)"; const cyan = getComputedStyle(p).color; p.remove();
  return {tag: el.tagName, id: el.id, color: cs.outlineColor, width: cs.outlineWidth, style: cs.outlineStyle, cyan,
          selected: el.getAttribute("aria-selected")};
}
"""


# --- the run ------------------------------------------------------------------------------------

def run(port: int, out: Path) -> dict:
    from playwright.sync_api import sync_playwright

    out.mkdir(parents=True, exist_ok=True)
    fixtures = make_fixtures()
    report = {"checks": [], "screens": [], "failures": []}
    tmp = Path(tempfile.mkdtemp(prefix="awards_render_"))
    site = tmp / "site"
    site.mkdir()
    build_site_copy(site)
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1",
                               "--directory", str(site)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    try:
        time.sleep(1.0)
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            try:
                _run_all(browser, base, site, fixtures, out, report)
            finally:
                browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
        shutil.rmtree(tmp, ignore_errors=True)
    (out / "render_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report


def _context(browser, width: int, theme: str):
    coarse = width <= 768
    ctx = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=theme,
                              has_touch=coarse, is_mobile=coarse, device_scale_factor=1)
    return ctx


def _page(ctx, log: list):
    page = ctx.new_page()
    aborted = []

    def route(r):
        host = urlparse(r.request.url).hostname
        if host not in ("127.0.0.1", "localhost"):
            aborted.append(r.request.url)
            r.abort()
        else:
            r.continue_()
    page.route("**/*", route)
    page.on("console", lambda m: log.append(("console", m.type, m.text)) if m.type == "error" else None)
    page.on("pageerror", lambda e: log.append(("pageerror", "error", str(e))))
    page.on("response", lambda r: log.append(("http", str(r.status), r.url)) if r.status >= 400 else None)
    page._aw_aborted = aborted
    return page


def _errors(log: list, aborted: list) -> list:
    out = []
    for kind, typ, text in log:
        if kind == "http":
            out.append(f"HTTP {typ} {text}")
        elif kind == "pageerror":
            out.append(f"page error: {text}")
        elif "ERR_FAILED" in text and aborted:
            continue
        elif "Failed to load resource" in text:
            continue        # the HTTP line above names it
        else:
            out.append(f"console: {text}")
    return out


def _wait_app(page):
    page.wait_for_selector(".aw-hero, .aw-panel:not([hidden]) .px-state", timeout=15000)


def _record(report, name, res, errs):
    bad = list(res.get("bad", [])) + errs
    report["checks"].append({"name": name, **{k: v for k, v in res.items() if k != "bad"}, "bad": bad})
    report["failures"].extend(f"{name}: {b}" for b in bad)


def _run_all(browser, base, site, fixtures, out, report):
    # 1. Selections against each fixture, every width and theme for the live one.
    plan = [("live", w, t) for w in WIDTHS for t in THEMES]
    plan += [("frozen", w, t) for w in (390, 1280) for t in THEMES]
    plan += [("stale", 390, "light")]
    current = None
    for fx, w, theme in plan:
        if fx != current:
            write_fixture(site, fixtures[fx])
            current = fx
        doc = fixtures[fx]["awards.json"]
        ctx = _context(browser, w, theme)
        log: list = []
        page = _page(ctx, log)
        page.goto(f"{base}/awards/", wait_until="networkidle")
        _wait_app(page)
        name = f"{fx}_selections_{w}_{theme}"
        res = page.evaluate(CHECK_JS, doc)
        lay = page.evaluate(LAYOUT_JS)
        res["bad"] += lay["bad"]
        res.update({"contrast_worst": lay["worst"], "contrast_worst_at": lay["worstWhat"], "n_text": lay["nText"]})
        stamp = page.text_content(".aw-stamp") or ""
        if fx == "stale" and "numbers may be out of date" not in stamp:
            res["bad"].append("stale fixture without the stale sentence")
        if fx != "stale" and "numbers may be out of date" in stamp:
            res["bad"].append("fresh fixture with the stale sentence")
        if fx == "frozen":
            if not page.query_selector(".aw-drift"):
                res["bad"].append("frozen fixture draws no Now value")
            wl = page.text_content("#aw-c-mvp-al .aw-writers") or ""
            if "The rule placed him 2nd." not in wl:
                res["bad"].append(f"writers' line after the vote reads {wl!r}")
        if w in (390, 1280) or fx != "live":
            for d in page.query_selector_all("details.aw-d"):
                d.evaluate("(e) => { e.open = true; }")
            for d in page.query_selector_all("details.aw-weeks, details.aw-excl"):
                d.evaluate("(e) => { e.open = true; }")
            lay2 = page.evaluate(LAYOUT_JS)
            res["bad"] += [f"(disclosures open) {b}" for b in lay2["bad"]]
            shot = out / f"{name}.png"
            page.screenshot(path=str(shot), full_page=True)
            report["screens"].append(shot.name)
            card = page.query_selector("#aw-c-mvp-nl")
            if card:
                cshot = out / f"{name}_card_mvp_nl.png"
                card.screenshot(path=str(cshot))
                report["screens"].append(cshot.name)
        else:
            page.evaluate("() => { const c = document.getElementById('aw-c-mvp-al'); if (c) c.scrollIntoView(); }")
            shot = out / f"{name}_view.png"
            page.screenshot(path=str(shot))
            report["screens"].append(shot.name)
        if w == 390 and theme == "light" and fx == "live":
            page.focus("#aw-tab-selections")
            page.keyboard.press("ArrowRight")
            f = page.evaluate(FOCUS_JS)
            if f["color"] != f["cyan"] or f["width"] != "2px":
                res["bad"].append(f"focus ring {f}")
            if f["id"] != "aw-tab-superlatives" or f["selected"] != "true":
                res["bad"].append(f"arrow key did not move and select the next tab: {f}")
            msg = page.text_content("#aw-panel-superlatives .px-state-msg") or ""
            if msg.strip() != "This section is being built.":
                res["bad"].append(f"superlatives panel reads {msg!r}")
            page.keyboard.press("End")
            f2 = page.evaluate(FOCUS_JS)
            if f2["id"] != "aw-tab-method":
                res["bad"].append(f"End did not reach Method: {f2}")
            page.screenshot(path=str(out / f"{name}_tab_method.png"))
            report["screens"].append(f"{name}_tab_method.png")
            res["focus"] = f
        _record(report, name, res, _errors(log, page._aw_aborted))
        ctx.close()

    # 2. Past seasons: a race on file, none on file, a blocked Manager rule.
    write_fixture(site, fixtures["live"])
    for S in (2024, 2023, 2022):
        doc = fixtures["live"][f"awards_{S}.json"]
        for w in (390, 1280):
            for theme in THEMES:
                ctx = _context(browser, w, theme)
                log = []
                page = _page(ctx, log)
                page.goto(f"{base}/awards/#season={S}", wait_until="networkidle")
                page.wait_for_selector(".aw-hero", timeout=15000)
                name = f"season{S}_selections_{w}_{theme}"
                res = page.evaluate(CHECK_JS, doc)
                lay = page.evaluate(LAYOUT_JS)
                res["bad"] += lay["bad"]
                res.update({"contrast_worst": lay["worst"], "contrast_worst_at": lay["worstWhat"]})
                stamp = page.text_content(".aw-stamp") or ""
                if "Computed after the fact" not in stamp:
                    res["bad"].append(f"closed season stamp reads {stamp!r}")
                for d in page.query_selector_all("details.aw-d"):
                    d.evaluate("(e) => { e.open = true; }")
                shot = out / f"{name}.png"
                page.screenshot(path=str(shot), full_page=True)
                report["screens"].append(shot.name)
                _record(report, name, res, _errors(log, page._aw_aborted))
                ctx.close()

    # 3. The states: loading held 1.5 s, failed (500) with Retry, a shard that fails.
    ctx = _context(browser, 390, "light")
    log = []
    page = _page(ctx, log)
    held = []
    page.route("**/data/awards.json", lambda r: held.append(r))
    page.goto(f"{base}/awards/", wait_until="domcontentloaded")
    page.wait_for_selector(".px-state.is-loading", timeout=10000)
    res = {"bad": []}
    if (page.get_attribute(".px-state.is-loading", "role") or "") != "status":
        res["bad"].append("loading state is not role=status")
    if (page.text_content(".px-state.is-loading .px-state-msg") or "").strip() != "Loading the awards.":
        res["bad"].append("loading sentence")
    page.wait_for_timeout(1500)
    page.screenshot(path=str(out / "state_loading_390_light.png"))
    report["screens"].append("state_loading_390_light.png")
    for r in held:
        r.continue_()
    page.wait_for_selector(".aw-hero", timeout=15000)
    _record(report, "state_loading", res, [])
    ctx.close()

    ctx = _context(browser, 390, "dark")
    log = []
    page = _page(ctx, log)
    fail = {"on": True}
    page.route("**/data/awards.json", lambda r: r.fulfill(status=500, body="no") if fail["on"] else r.continue_())
    page.goto(f"{base}/awards/", wait_until="networkidle")
    page.wait_for_selector(".px-state.is-failed", timeout=10000)
    res = {"bad": []}
    if (page.get_attribute(".px-state.is-failed", "role") or "") != "alert":
        res["bad"].append("failed state is not role=alert")
    if "The awards could not load." not in (page.text_content(".px-state.is-failed") or ""):
        res["bad"].append("failed sentence")
    page.screenshot(path=str(out / "state_failed_390_dark.png"))
    report["screens"].append("state_failed_390_dark.png")
    fail["on"] = False
    page.click(".aw-boot-retry")
    page.wait_for_selector(".aw-hero", timeout=15000)
    page.route("**/data/awards_2023.json", lambda r: r.fulfill(status=500, body="no"))
    page.select_option("#aw-season-selections", "2023")
    page.wait_for_selector("#aw-panel-selections .px-state.is-failed", timeout=10000)
    if not page.query_selector("#aw-panel-selections .aw-retry"):
        res["bad"].append("shard failure has no Retry")
    page.screenshot(path=str(out / "state_shard_failed_390_dark.png"))
    report["screens"].append("state_shard_failed_390_dark.png")
    errs = [e for e in _errors(log, page._aw_aborted) if "awards.json" not in e and "awards_2023.json" not in e]
    _record(report, "state_failed", res, errs)
    ctx.close()

    # 4. The deep link and the hash grammar.
    ctx = _context(browser, 1280, "light")
    log = []
    page = _page(ctx, log)
    page.goto(f"{base}/awards/#award=cy&lg=nl&season=1999&section=nope&b=BAD!", wait_until="networkidle")
    page.wait_for_selector(".aw-hero", timeout=15000)
    res = {"bad": []}
    top = page.evaluate("() => document.getElementById('aw-c-cy-nl').getBoundingClientRect().top")
    if not (-2 <= top <= 60):
        res["bad"].append(f"deep link to the NL Cy Young card left it at y={top}")
    if page.get_attribute("#aw-tab-selections", "aria-selected") != "true":
        res["bad"].append("an unknown section did not fall back to Selections")
    if (page.input_value("#aw-season-selections") or "") != str(fixtures["live"]["awards.json"]["default_season"]):
        res["bad"].append("an unknown season was not dropped")
    _record(report, "hash", res, _errors(log, page._aw_aborted))
    ctx.close()

    # 5. /hof/ with the flag on and off.
    for rel, label in (("hof", "hof_flag_on"), ("hof-off", "hof_flag_off")):
        for w in (390, 1280):
            for theme in THEMES:
                ctx = _context(browser, w, theme)
                log = []
                page = _page(ctx, log)
                page.goto(f"{base}/{rel}/", wait_until="networkidle")
                page.wait_for_timeout(300)
                res = page.evaluate(LAYOUT_JS)
                strip = page.query_selector(".hof-modstrip")
                if rel == "hof":
                    cur = page.query_selector('.hof-modstrip a[aria-current="page"]')
                    if not strip or not cur or (cur.text_content() or "").strip() != "Hall of Fame":
                        res["bad"].append("flag on: the strip's current link is not Hall of Fame")
                    if not page.query_selector('.mlbstats-tabs[role="tablist"] .mlbstats-tab[role="tab"][data-hofsection]'):
                        res["bad"].append("flag on: the section row is not the underline tab row")
                    if "Awards / HoF" not in (page.text_content("h1") or ""):
                        res["bad"].append("flag on: h1")
                else:
                    if strip:
                        res["bad"].append("flag off: a module strip is drawn")
                    if "Hall of Fame" not in (page.text_content("h1") or ""):
                        res["bad"].append("flag off: h1")
                shot = out / f"{label}_{w}_{theme}.png"
                page.screenshot(path=str(shot))
                report["screens"].append(shot.name)
                _record(report, f"{label}_{w}_{theme}", res, _errors(log, page._aw_aborted))
                ctx.close()
    # the /awards/ head with the flag on: aria-current on Awards
    ctx = _context(browser, 390, "light")
    log = []
    page = _page(ctx, log)
    page.goto(f"{base}/awards/", wait_until="networkidle")
    cur = page.query_selector('.hof-modstrip a[aria-current="page"]')
    res = {"bad": [] if cur and (cur.text_content() or "").strip() == "Awards" else ["/awards/ strip current link"]}
    _record(report, "awards_strip", res, _errors(log, page._aw_aborted))
    ctx.close()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--port", type=int, default=9141)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    if not (PREVIEW / "awards.json").exists():
        print(f"no preview payload at {PREVIEW}: run awards_export.py first (flag False writes there)")
        return 2
    rep = run(a.port, a.out)
    for c in rep["checks"]:
        extra = f" contrast min {c['contrast_worst']}" if "contrast_worst" in c else ""
        print(f"  {'FAIL' if c['bad'] else 'ok  '} {c['name']}{extra}")
    print(f"{len(rep['screens'])} screenshots in {a.out}; {len(rep['failures'])} failures")
    for f in rep["failures"][:80]:
        print("   ", f)
    return 1 if rep["failures"] else 0


if __name__ == "__main__":
    sys.exit(main())
