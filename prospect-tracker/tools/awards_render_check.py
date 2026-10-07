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

My Ballot (AWARDS_9) against the same fixtures and the candidate files: the chunk and the candidate
file load only on the first My Ballot open; the ballot lengths and point labels equal ballot_rules;
a keyboard-only add, move (button and Alt+Up) and remove with the live region's text and focus; the
sort contract; a reload restores the ballot; a throwing localStorage shows the unavailable note and
edits work in memory; Copy link (the b alphabet), Copy text and Clear's inline confirm; a shared link
in a fresh context (banner focus, nothing written until copied, an unknown id dropped and counted, a
duplicate kept in its first slot, the Replace and Keep mine confirms, Close removing b); the switch
hiding only the "Eephus place" column and the ink numerals, remembered; no comparison word or
percentage; past seasons, the frozen fixture and a failing candidate file; and no request carrying
ballot content across every session (the request log).

Share cards (AWARDS_10, --only gfx): the engine loads only on a Share press; one Share chip per card
with a rule plus the hero's; the podium (an AL MVP and an NL Manager card), the slate, the superlative
seam (one injected chip per picture kind) and My Ballot's Save image each render in Twitter, Wide and
Portrait, light and dark, at 2x, with an untainted toDataURL; the words each card draws (read back
through fillText) carry the payload's names and values and no dash, BAN or verdict word; the ballot
card carries "Choices mine." and no selection, Portrait carries every filled ballot and Twitter only
the active one; a blocked Manager rule has no chip and the slate prints "Not published". The PNGs land
in --out as gfx_*.png.

    python tools/awards_render_check.py --port 9141 --out <dir> [--preview <dir>] [--only ballot|gfx]
"""
from __future__ import annotations

import argparse
import copy
import re
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
ONLY = "all"


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
    # My Ballot's candidate files (AWARDS_9); the 2022 fixture's Manager rule is blocked, so its
    # Manager pools are dropped too.
    for p in sorted(PREVIEW.glob("awards_candidates_20[0-9][0-9].json")):
        doc = _load(p)
        if doc["season"] == 2022:
            for k in ("al-moy", "nl-moy"):
                doc["pools"].pop(k, None)
        shards[p.name] = doc
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
  const sel = '.aw-tabs [role="tab"], .hof-modstrip a, .aw-app a.aw-chip, .aw-app .aw-share, .aw-app summary, .aw-season select, .mlbstats-tabs [role="tab"]';
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
                if ONLY in ("all", "selections"):
                    _run_all(browser, base, site, fixtures, out, report)
                if ONLY in ("all", "ballot"):
                    _run_ballot(browser, base, site, fixtures, out, report)
                if ONLY in ("all", "gfx"):
                    _run_gfx(browser, base, site, fixtures, out, report)
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
    # a loopback request that never got a response (a reset connection) is a failure too
    page.on("requestfailed", lambda r: log.append(("http", "failed", r.url))
            if urlparse(r.url).hostname in ("127.0.0.1", "localhost") else None)
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


# --- My Ballot (AWARDS_9; AWARDS_PLAN 5.8, 6 row I14's ballot items) ------------------------------

BALLOT_URL = "/awards/#section=ballot"
LS_KEY = "eephus.awards.ballot.v1"
B_ALPHABET = re.compile(r"^[a-z0-9._:,-]+$")
UNAVAILABLE = ("This browser is not saving your ballot (private window or blocked storage). It lasts until you "
               "leave the page; copy the link to keep it.")
BALLOT_TARGETS_JS = r"""
() => {
  const bad = [], coarse = matchMedia("(pointer: coarse)").matches, min = coarse ? 44 : 24;
  document.querySelectorAll(".aw-b button, .aw-b-chk, .aw-b-qw input, .aw-b [role=option]").forEach((el) => {
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height || el.closest("[hidden]")) return;
    if (r.height < min - 0.5) bad.push("ballot target " + (el.textContent || el.tagName).trim().slice(0, 30) + " is " + r.height.toFixed(1) + " px tall");
  });
  document.querySelectorAll(".aw-b-tbl th[scope=row]").forEach((th, i) => {
    if (i > 3) return;
    const bg = getComputedStyle(th).backgroundColor;
    if (!/^rgb\(/.test(bg)) bad.push("sticky name column is not opaque: " + bg);
  });
  return bad;
}
"""
# The switch hides only the "Eephus place" column and the ink numerals (and their legend).
SWITCH_JS = r"""
() => {
  const p = document.getElementById("aw-panel-ballot").cloneNode(true);
  const n = {sel: p.querySelectorAll(".aw-b-sel").length, ink: p.querySelectorAll(".aw-mk:not(.me)").length,
             mine: p.querySelectorAll(".aw-mk.me").length,
             place: Array.from(p.querySelectorAll(".aw-b-tbl thead th")).filter((t) => t.textContent.trim() === "Eephus place").length};
  p.querySelectorAll(".aw-b-sel, .aw-mk:not(.me), .aw-b-sw").forEach((e) => e.remove());
  return {n, text: p.textContent.replace(/\s+/g, " ").trim()};
}
"""


def _ord(n: int) -> str:
    return f"{n}{'th' if 11 <= n % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _b36(n) -> str:
    n, out = int(n), ""
    while True:
        n, r = divmod(n, 36)
        out = "0123456789abcdefghijklmnopqrstuvwxyz"[r] + out
        if not n:
            return out


def _ballot_rows_check(page, rules: dict) -> list:
    bad = []
    keys = page.eval_on_selector_all('#aw-b-chooser [role="tab"]', "(els) => els.map((e) => e.dataset.key)")
    if len(keys) != 8:
        bad.append(f"chooser tabs {len(keys)}")
    for key in keys:
        page.click(f"#aw-b-t{key}")
        page.wait_for_selector(f'#aw-b-t{key}[aria-selected="true"]')
        if page.eval_on_selector_all('#aw-b-chooser [aria-selected="true"]', "(e) => e.length") != 1:
            bad.append(f"{key}: more than one selected tab")
        r = rules[key.split("-")[1].upper()]
        cnt = page.text_content(f"#aw-b-t{key} span") or ""
        if not cnt.endswith(f"/{r['n']}"):
            bad.append(f"{key}: chooser count {cnt!r}")
        if page.get_attribute("#aw-b-panel", "aria-labelledby") != f"aw-b-t{key}":
            bad.append(f"{key}: tabpanel aria-labelledby")
        labels = page.eval_on_selector_all("#aw-b-panel .aw-b-slot .aw-b-sl", "(els) => els.map((e) => e.textContent)")
        want = [f"{_ord(i + 1)} · {pts} pts" for i, pts in enumerate(r["points"])]
        if labels != want:
            bad.append(f"{key}: slot labels {labels} != {want}")
    page.click("#aw-b-tal-mvp")
    return bad


def _open_ballot(page, base: str, path: str = BALLOT_URL):
    page.goto(base + path, wait_until="networkidle")
    page.wait_for_selector("#aw-b-panel .aw-slots, #aw-b-panel .px-state, .aw-b-banner", timeout=15000)


def _storage(page):
    return page.evaluate(f"() => {{ try {{ return localStorage.getItem({LS_KEY!r}); }} catch (e) {{ return 'THROWS'; }} }}")


def _slot_ids(page, n=3):
    return page.eval_on_selector_all("#aw-b-panel .aw-b-slot", f"(els) => els.slice(0, {n}).map((e) => e.dataset.id || null)")


def _fill_three(page) -> list:
    ids = page.eval_on_selector_all('#aw-b-table [data-act="add"]', "(els) => els.slice(0, 3).map((e) => e.dataset.id)")
    for i in ids:
        page.click(f'#aw-b-table [data-act="add"][data-id="{i}"]')
    return ids


def _copied(page, act: str) -> str:
    page.click(f'[data-act="{act}"]')
    page.wait_for_timeout(300)
    ta = page.query_selector("#aw-b-out textarea")
    return ta.input_value() if ta else page.evaluate("() => navigator.clipboard.readText()")


def _run_ballot(browser, base, site, fixtures, out, report):
    live = fixtures["live"]["awards.json"]
    rules = live["ballot_rules"]
    S = live["season"]
    net: list = []

    def watch(page):
        page.on("request", lambda r: net.append((r.method, r.url, r.post_data)))

    def live_txt(page):
        return (page.text_content("#aw-b-live") or "").replace(" ", "").strip()

    # 0. Selections alone never loads the ballot chunk or a candidate file.
    write_fixture(site, fixtures["live"])
    ctx = _context(browser, 1280, "light")
    log: list = []
    page = _page(ctx, log)
    watch(page)
    page.goto(f"{base}/awards/", wait_until="networkidle")
    _wait_app(page)
    res = {"bad": [f"cold paint requested {u}" for _m, u, _p in net if "awards-ballot" in u or "awards_candidates" in u]}
    _record(report, "ballot_lazy_load", res, _errors(log, page._aw_aborted))
    ctx.close()

    # 1. Every width and theme on the live fixture: lengths, points, layout, targets, contrast.
    for w in WIDTHS:
        for theme in THEMES:
            ctx = _context(browser, w, theme)
            log = []
            page = _page(ctx, log)
            watch(page)
            _open_ballot(page, base)
            name = f"ballot_live_{w}_{theme}"
            res = {"bad": []}
            if theme == "light" and w in (390, 1280):
                res["bad"] += _ballot_rows_check(page, rules)
            ids = _fill_three(page)
            page.click(f'#aw-b-table [data-act="drawer"][data-id="{ids[0]}"]')
            page.wait_for_selector("#aw-b-dw")
            lay = page.evaluate(LAYOUT_JS)
            res["bad"] += lay["bad"] + page.evaluate(BALLOT_TARGETS_JS)
            res.update({"contrast_worst": lay["worst"], "contrast_worst_at": lay["worstWhat"]})
            txt = page.text_content("#aw-panel-ballot") or ""
            if "%" in txt or re.search(r"\b(match(es|ed)?|agree\w*|overlap\w*|same as)\b", txt, re.I):
                res["bad"].append("the ballot panel prints a comparison word or a percentage")
            page.evaluate("() => document.querySelector('.aw-b').scrollIntoView()")
            shot = out / f"{name}.png"
            page.screenshot(path=str(shot))
            report["screens"].append(shot.name)
            if w in (390, 1280):
                rs = out / f"{name}_right.png"
                page.query_selector(".aw-b-right").screenshot(path=str(rs))
                report["screens"].append(rs.name)
            _record(report, name, res, _errors(log, page._aw_aborted))
            ctx.close()

    # 2. Keyboard only: add, move and remove with the live region's text; the sort contract;
    #    reload restores; the switch hides only its two things and is remembered.
    ctx = _context(browser, 390, "light")
    log = []
    page = _page(ctx, log)
    watch(page)
    _open_ballot(page, base)
    res = {"bad": []}
    first = live["awards"]["MVP"]["AL"]["top"][0]
    who, mid = first["name"], str(first["mlbam"])
    page.focus('[data-act="choose"][data-slot="0"]')
    page.keyboard.press("Enter")
    if page.evaluate("() => document.activeElement.id") != "aw-b-q":
        res["bad"].append("Choose 1st place did not move focus to the search")
    page.keyboard.type(who.split()[-1][:3])
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")
    if live_txt(page) != f"{who} added to 1st on your AL MVP ballot.":
        res["bad"].append(f"add announced {live_txt(page)!r}")
    if _slot_ids(page, 1) != [mid]:
        res["bad"].append("the keyboard add did not land in 1st")
    page.focus('.aw-b-slot[data-slot="0"] [data-act="down"]')
    page.keyboard.press("Enter")
    if live_txt(page) != f"{who} moved to 2nd." or _slot_ids(page, 2) != [None, mid]:
        res["bad"].append(f"Move down announced {live_txt(page)!r}")
    act = page.evaluate("() => [document.activeElement.dataset.act, document.activeElement.dataset.slot]")
    if act != ["up", "1"]:
        res["bad"].append(f"focus after Move down is {act}")
    page.keyboard.press("Alt+ArrowUp")
    if live_txt(page) != f"{who} moved to 1st." or _slot_ids(page, 1) != [mid]:
        res["bad"].append(f"Alt+Up announced {live_txt(page)!r}")
    page.focus('.aw-b-slot[data-slot="0"] [data-act="rm"]')
    page.keyboard.press("Enter")
    if live_txt(page) != f"{who} removed.":
        res["bad"].append(f"Remove announced {live_txt(page)!r}")
    act = page.evaluate("() => [document.activeElement.dataset.act, document.activeElement.dataset.slot]")
    if act != ["choose", "0"]:
        res["bad"].append(f"focus after Remove is {act}")
    page.focus('#aw-b-table [data-act="sort"][data-k="name"]')
    page.keyboard.press("Enter")
    if page.evaluate("() => document.activeElement.dataset.k") != "name":
        res["bad"].append("focus left the pressed sort button")
    if page.get_attribute('#aw-b-table th:has([data-k="name"])', "aria-sort") != "ascending":
        res["bad"].append("aria-sort on the sorted th")
    if page.evaluate("() => document.querySelectorAll('[aria-sort]:not(th)').length"):
        res["bad"].append("aria-sort outside a th")
    if (page.text_content("#aw-b-sortst") or "").strip() != "Sorted by Name, A to Z.":
        res["bad"].append(f"the sort status line reads {page.text_content('#aw-b-sortst')!r}")
    if page.get_attribute("#aw-b-count", "role") != "status":
        res["bad"].append("the count line is not role=status")
    ids = _fill_three(page)
    page.wait_for_timeout(450)
    page.reload(wait_until="networkidle")
    page.wait_for_selector("#aw-b-panel .aw-slots")
    if _slot_ids(page) != ids:
        res["bad"].append(f"reload restored {_slot_ids(page)}, wanted {ids}")
    stored = json.loads(_storage(page) or "{}")
    if stored.get("v") != 1 or stored.get("seasons", {}).get(str(S), {}).get("al-mvp", [])[:3] != ids:
        res["bad"].append("the stored value is not the v1 shape")
    before = page.evaluate(SWITCH_JS)
    page.click('[data-act="sel"]')
    after = page.evaluate(SWITCH_JS)
    if not (before["n"]["sel"] and before["n"]["ink"] and before["n"]["place"] == 1 and before["n"]["mine"]):
        res["bad"].append(f"switch on draws no selection elements {before['n']}")
    if after["n"]["sel"] or after["n"]["ink"] or after["n"]["place"] or after["n"]["mine"] != before["n"]["mine"]:
        res["bad"].append(f"switch off left {after['n']}")
    if before["text"] != after["text"]:
        res["bad"].append("the switch changed something besides the Eephus place column and the ink numerals")
    page.wait_for_timeout(450)
    page.reload(wait_until="networkidle")
    page.wait_for_selector("#aw-b-panel .aw-slots")
    if page.get_attribute('[data-act="sel"]', "aria-checked") != "false":
        res["bad"].append("the switch is not remembered")
    page.evaluate("() => document.querySelector('.aw-b-right').scrollIntoView()")
    page.screenshot(path=str(out / "ballot_switch_off_390_light.png"))
    report["screens"].append("ballot_switch_off_390_light.png")
    page.click('[data-act="sel"]')
    page.wait_for_timeout(450)
    _record(report, "ballot_keyboard_sort_reload_switch", res, _errors(log, page._aw_aborted))
    ctx.close()

    # 3. Storage that throws: the unavailable note, and edits work in memory.
    ctx = _context(browser, 390, "dark")
    ctx.add_init_script("Object.defineProperty(window, 'localStorage', {get() { throw new Error('blocked'); }});")
    log = []
    page = _page(ctx, log)
    watch(page)
    _open_ballot(page, base)
    res = {"bad": []}
    if (page.text_content("#aw-b-save") or "").strip() != UNAVAILABLE:
        res["bad"].append("the unavailable note is not shown")
    ids3 = _fill_three(page)
    page.wait_for_timeout(450)
    if _slot_ids(page) != ids3:
        res["bad"].append("edits do not work in memory without storage")
    page.evaluate("() => document.querySelector('.aw-b').scrollIntoView()")
    page.screenshot(path=str(out / "ballot_storage_unavailable_390_dark.png"))
    report["screens"].append("ballot_storage_unavailable_390_dark.png")
    _record(report, "ballot_storage_unavailable", res, _errors(log, page._aw_aborted))
    ctx.close()

    # 4. Copy link, Copy text and Clear's inline confirm.
    ctx = _context(browser, 1280, "light")
    ctx.grant_permissions(["clipboard-read", "clipboard-write"], origin=base)
    log = []
    page = _page(ctx, log)
    watch(page)
    _open_ballot(page, base)
    res = {"bad": []}
    ids = _fill_three(page)
    page.click("#aw-b-tnl-cy")
    cy = _fill_three(page)
    link = _copied(page, "link")
    b = link.split("&b=", 1)[1] if "&b=" in link else ""
    if not b or not B_ALPHABET.match(b) or not link.startswith(f"{base}/awards/#section=ballot&season={S}&b="):
        res["bad"].append(f"the copied link reads {link!r}")
    text = _copied(page, "text").replace("\r\n", "\n")
    if not text.startswith(f"My {S} NL Cy Young ballot\n1. ") or "&b=nl-cy:" not in text:
        res["bad"].append(f"the copied text reads {text[:80]!r}")
    page.click('[data-act="clear"]')
    if "Clear your NL Cy Young ballot?" not in (page.text_content("#aw-b-confirm") or ""):
        res["bad"].append("Clear shows no inline confirm")
    page.click('[data-act="clear-no"]')
    if _slot_ids(page) != cy:
        res["bad"].append("Keep cleared the ballot")
    page.click('[data-act="clear"]')
    page.click('[data-act="clear-yes"]')
    if _slot_ids(page) != [None, None, None]:
        res["bad"].append("Clear did not empty the ballot")
    _record(report, "ballot_exports_clear", res, _errors(log, page._aw_aborted))
    ctx.close()

    # 5. A shared link in a fresh context: banner with focus, nothing written until copied, the
    #    unknown id dropped and counted, the duplicate kept in its first slot; then the confirms.
    crafted = f"al-mvp:{_b36(ids[0])}.{_b36(ids[0])}.zzzzzz,nl-cy:{_b36(cy[0])}"
    path = f"/awards/#section=ballot&season={S}&b={crafted}"
    ctx = _context(browser, 390, "light")
    log = []
    page = _page(ctx, log)
    watch(page)
    _open_ballot(page, base, path)
    res = {"bad": []}
    page.wait_for_timeout(450)
    if not page.query_selector(".aw-b-banner"):
        res["bad"].append("the shared link shows no banner")
    if page.evaluate("() => document.activeElement.id") != "aw-b-shared":
        res["bad"].append("the banner did not take focus")
    if _storage(page) is not None:
        res["bad"].append("opening a shared link wrote to storage")
    btxt = page.text_content(".aw-b-banner") or ""
    if f"1 name in this link is not on the {S} candidate list and was left out." not in btxt:
        res["bad"].append(f"the dropped count reads {btxt!r}")
    if page.eval_on_selector_all(".aw-b-sb li", "(els) => els.map((e) => e.value)") != [1, 1]:
        res["bad"].append("the duplicate did not keep its first slot only")
    page.screenshot(path=str(out / "ballot_shared_banner_390_light.png"))
    report["screens"].append("ballot_shared_banner_390_light.png")
    page.click('[data-act="sh-copy"]')
    page.wait_for_timeout(450)
    st = json.loads(_storage(page) or "{}").get("seasons", {}).get(str(S), {})
    if (st.get("al-mvp") or [None, 1])[:2] != [str(ids[0]), None] or (st.get("nl-cy") or [None])[0] != str(cy[0]):
        res["bad"].append(f"Copy to my ballot wrote {st}")
    if "b=" in page.evaluate("() => location.hash") or page.query_selector(".aw-b-banner"):
        res["bad"].append("the banner or b stayed after the copy")
    page.goto(base + path, wait_until="networkidle")
    page.wait_for_selector(".aw-b-banner")
    page.click('[data-act="sh-copy"]')
    q1 = page.text_content(".aw-b-ask") or ""
    page.screenshot(path=str(out / "ballot_shared_confirm_390_light.png"))
    report["screens"].append("ballot_shared_confirm_390_light.png")
    page.click('[data-act="sh-yes"]')
    q2 = page.text_content(".aw-b-ask") or ""
    page.click('[data-act="sh-no"]')
    if "Replace your AL MVP ballot?" not in q1 or "Replace your NL Cy Young ballot?" not in q2:
        res["bad"].append(f"the inline confirms read {q1!r} then {q2!r}")
    page.goto(base + path, wait_until="networkidle")
    page.wait_for_selector(".aw-b-banner")
    page.click('[data-act="sh-close"]')
    if "b=" in page.evaluate("() => location.hash") or page.query_selector(".aw-b-banner"):
        res["bad"].append("Close left b in the hash or the banner on the page")
    _record(report, "ballot_shared_link", res, _errors(log, page._aw_aborted))
    ctx.close()

    # 6. Past seasons (no race record; a blocked Manager rule) and the frozen fixture.
    for season, key in ((2023, "al-mvp"), (2022, "al-moy")):
        for theme in THEMES:
            ctx = _context(browser, 390, theme)
            log = []
            page = _page(ctx, log)
            watch(page)
            _open_ballot(page, base, f"/awards/#section=ballot&season={season}&award={key[3:]}&lg={key[:2]}")
            res = {"bad": []}
            if season == 2022 and not page.query_selector("#aw-b-panel .px-state.is-unmeasured"):
                res["bad"].append("the blocked Manager season shows no unmeasured state")
            if season == 2023:
                _fill_three(page)
            res["bad"] += page.evaluate(LAYOUT_JS)["bad"]
            shot = out / f"ballot_season{season}_390_{theme}.png"
            page.evaluate("() => document.querySelector('.aw-b').scrollIntoView()")
            page.screenshot(path=str(shot))
            report["screens"].append(shot.name)
            _record(report, f"ballot_season{season}_{theme}", res, _errors(log, page._aw_aborted))
            ctx.close()
    write_fixture(site, fixtures["frozen"])
    for w in (390, 1280):
        ctx = _context(browser, w, "dark")
        log = []
        page = _page(ctx, log)
        watch(page)
        _open_ballot(page, base)
        _fill_three(page)
        res = {"bad": [] if "Ink box: the eephus selection" in (page.text_content(".aw-b-keys") or "")
               else ["the frozen fixture's legend does not name the eephus selection"]}
        res["bad"] += page.evaluate(LAYOUT_JS)["bad"]
        shot = out / f"ballot_frozen_{w}_dark.png"
        page.evaluate("() => document.querySelector('.aw-b').scrollIntoView()")
        page.screenshot(path=str(shot))
        report["screens"].append(shot.name)
        _record(report, f"ballot_frozen_{w}", res, _errors(log, page._aw_aborted))
        ctx.close()
    write_fixture(site, fixtures["live"])

    # 7. The candidate file fails (500), then Retry.
    ctx = _context(browser, 390, "dark")
    log = []
    page = _page(ctx, log)
    fail = {"on": True}
    page.route("**/data/awards_candidates_*.json", lambda r: r.fulfill(status=500, body="no") if fail["on"] else r.continue_())
    page.goto(f"{base}{BALLOT_URL}", wait_until="networkidle")
    page.wait_for_selector("#aw-panel-ballot .px-state.is-failed")
    res = {"bad": []}
    if "The candidates could not load." not in (page.text_content("#aw-panel-ballot .px-state.is-failed") or ""):
        res["bad"].append("the candidate failure sentence")
    if page.get_attribute("#aw-panel-ballot .px-state.is-failed", "role") != "alert":
        res["bad"].append("the failed state is not role=alert")
    page.screenshot(path=str(out / "ballot_failed_390_dark.png"))
    report["screens"].append("ballot_failed_390_dark.png")
    fail["on"] = False
    page.click('[data-act="retry"]')
    page.wait_for_selector("#aw-b-panel .aw-slots")
    _record(report, "ballot_failed_retry", res, [e for e in _errors(log, page._aw_aborted) if "awards_candidates" not in e])
    ctx.close()

    # 8. No request carried ballot content in any session above (route interception log).
    res = {"bad": []}
    marks = [str(i) for i in ids + cy] + [_b36(i) for i in ids + cy]
    for method, u, post in net:
        if method != "GET" or post:
            res["bad"].append(f"{method} {u} carried a body")
        q = u.split("#")[0]
        qs = q.split("?", 1)[1] if "?" in q else ""
        seg = q.split("?")[0].rstrip("/").rsplit("/", 1)[-1]
        if "b=" in qs or "-mvp" in q or "-cy:" in q or seg in marks or any(m in qs.split("&") for m in marks):
            res["bad"].append(f"a request carries ballot content: {u}")
    report["n_requests_logged"] = len(net)
    _record(report, "ballot_no_request_carries_content", res, [])


# --- Share cards (AWARDS_10; AWARDS_PLAN 5.16) ----------------------------------------------------

#: Every canvas text call is logged so a card's words can be read back (fillText wraps once).
FILLTEXT_INIT = r"""
(() => {
  const f = CanvasRenderingContext2D.prototype.fillText;
  window.__ft = [];
  CanvasRenderingContext2D.prototype.fillText = function (t, x, y, m) {
    window.__ft.push(String(t));
    return f.call(this, t, x, y, m);
  };
})();
"""
GFX_FORMATS = {"twitter": (1200, 675), "wide": (1600, 900), "portrait": (1080, 1350)}
#: Draw one mode in the open modal at a format and theme; return its size, text and PNG.
GFX_RENDER_JS = r"""
async ([fmt, theme]) => {
  const prev = document.getElementById("egfx-preview");
  const old = prev.querySelector("canvas");
  window.__ft = [];
  const sf = document.getElementById("egfx-format"), st = document.getElementById("egfx-theme");
  sf.value = fmt; sf.dispatchEvent(new Event("change"));
  st.value = theme; st.dispatchEvent(new Event("change"));
  for (let i = 0; i < 200; i++) {
    const c = prev.querySelector("canvas");
    if (c && c !== old && !prev.classList.contains("is-busy")) break;
    await new Promise((r) => setTimeout(r, 25));
  }
  const c = prev.querySelector("canvas");
  if (!c) return {err: (prev.textContent || "no canvas").trim()};
  let url = null, err = null;
  try { url = c.toDataURL("image/png"); } catch (e) { err = String(e); }
  return {w: c.width, h: c.height, url, err, text: window.__ft.slice(),
          fmtShown: getComputedStyle(document.querySelector(".egfx-ctrl-format")).display !== "none",
          countShown: getComputedStyle(document.querySelector(".egfx-ctrl-count")).display !== "none"};
}
"""
GFX_CLOSE_JS = "() => { const x = document.querySelector('#egfx-overlay .egfx-x'); if (x) x.click(); }"


def _gfx_words(texts: list) -> list:
    """Copy rule hits in a card's text: dashes, copy_lint's BAN words, the plan's verdict words."""
    sys.path.insert(0, str(ROOT / "tools"))
    import awards_core as A
    import copy_lint
    bad = []
    for t in texts:
        if chr(0x2014) in t or chr(0x2013) in t:
            bad.append(f"dash in {t!r}")
        if copy_lint.BAN_RE.search(t):
            bad.append(f"banned word in {t!r}")
        if A.verdict_hits(t):
            bad.append(f"verdict word in {t!r}")
    return bad


def _gfx_matrix(page, name: str, out: Path, report: dict, want: list, forbid: list = ()) -> list:
    """Every format (Twitter, Wide, Portrait) in both themes: size, an untainted toDataURL, the words."""
    import base64
    bad = []
    for fmt, (W, H) in GFX_FORMATS.items():
        for theme in THEMES:
            r = page.evaluate(GFX_RENDER_JS, [fmt, theme])
            tag = f"{name} {fmt} {theme}"
            if r.get("err") or not r.get("url"):
                bad.append(f"{tag}: no image ({r.get('err')})")
                continue
            if (r["w"], r["h"]) != (2 * W, 2 * H):
                bad.append(f"{tag}: canvas {r['w']} x {r['h']} != {2 * W} x {2 * H}")
            if not r["fmtShown"] or r["countShown"]:
                bad.append(f"{tag}: the Format control must show and Show must hide")
            text = " | ".join(r["text"])
            for w in want:
                if w not in text:
                    bad.append(f"{tag}: card lacks {w!r}")
            for w in forbid:
                if w.lower() in text.lower():
                    bad.append(f"{tag}: card carries {w!r}")
            bad += [f"{tag}: {b}" for b in _gfx_words(r["text"])]
            png = out / f"gfx_{name}_{fmt}_{theme}.png"
            png.write_bytes(base64.b64decode(r["url"].split(",", 1)[1]))
            report["screens"].append(png.name)
    return bad


def _gfx_open(page, selector: str) -> list:
    page.click(selector)
    page.wait_for_selector("#egfx-overlay.is-open #egfx-preview canvas", timeout=20000)
    return []


def _run_gfx(browser, base, site, fixtures, out, report):
    # 1. Share chips and the four modes on the live and frozen fixtures, at 390 and 1280.
    for fx in ("live", "frozen"):
        write_fixture(site, fixtures[fx])
        doc = fixtures[fx]["awards.json"]
        for w in (390, 1280):
            ctx = _context(browser, w, "light")
            ctx.add_init_script(FILLTEXT_INIT)
            log: list = []
            page = _page(ctx, log)
            net: list = []
            page.on("request", lambda r: net.append(r.url))
            page.goto(f"{base}/awards/", wait_until="networkidle")
            _wait_app(page)
            name = f"gfx_{fx}_{w}"
            res = {"bad": []}
            if any("eephus-gfx.js" in u for u in net):
                res["bad"].append("the GFX engine loaded before a Share press")
            chips = page.eval_on_selector_all("[data-aw-share]", "(els) => els.map((e) => e.dataset.awShare + ':' + "
                                              "(e.dataset.award || '') + ':' + (e.dataset.lg || ''))")
            want_chips = 1 + sum(1 for A in doc["awards"] for L in doc["awards"][A]
                                 if not doc["rules"][A].get("blocked_on") and doc["awards"][A][L].get("top"))
            if len(chips) != want_chips:
                res["bad"].append(f"share chips {len(chips)} != {want_chips}")
            lay = page.evaluate(LAYOUT_JS)
            res["bad"] += lay["bad"]
            # podium: AL MVP
            res["bad"] += _gfx_open(page, '[data-aw-share="podium"][data-award="mvp"][data-lg="al"]')
            if not any("eephus-gfx.js" in u for u in net):
                res["bad"].append("Share did not load the GFX engine")
            ov = page.evaluate("() => document.scrollingElement.scrollWidth - window.innerWidth")
            if ov > 0:
                res["bad"].append(f"modal open: horizontal overflow {ov} px")
            blk, rule = doc["awards"]["MVP"]["AL"], doc["rules"]["MVP"]
            want = [r["name"] for r in blk["top"][:3]] + [f"{float(r['score_display']):.{rule['decimals']}f} {rule['unit']}"
                                                          for r in blk["top"][:3]]
            if w == 1280:
                res["bad"] += _gfx_matrix(page, f"{fx}_podium_mvp_al", out, report, want)
            else:
                r0 = page.evaluate(GFX_RENDER_JS, ["twitter", "light"])
                if r0.get("err") or not r0.get("url"):
                    res["bad"].append(f"podium at 390: {r0.get('err')}")
                page.screenshot(path=str(out / f"{name}_modal.png"))
                report["screens"].append(f"{name}_modal.png")
            page.evaluate(GFX_CLOSE_JS)
            # podium: a Manager card (club rows) and the slate
            if w == 1280:
                res["bad"] += _gfx_open(page, '[data-aw-share="podium"][data-award="moy"][data-lg="nl"]')
                res["bad"] += _gfx_matrix(page, f"{fx}_podium_moy_nl", out, report,
                                          [doc["awards"]["MOY"]["NL"]["top"][0]["club_code"]])
                page.evaluate(GFX_CLOSE_JS)
                res["bad"] += _gfx_open(page, '[data-aw-share="slate"]')
                cap = doc.get("selection_caption") or ""
                res["bad"] += _gfx_matrix(page, f"{fx}_slate", out, report, [cap] if cap else [])
                page.evaluate(GFX_CLOSE_JS)
                # superlatives: the seam AWARDS_8's cards will carry, one chip per picture kind
                for sl in ("prospect_above", "next_drop", "glove", "contact_ahead", "pitching_changes"):
                    s = next((x for x in doc.get("superlatives") or [] if x["id"] == sl), None)
                    if not s or s.get("blocked_on") or not s.get("rows"):
                        continue
                    page.evaluate("(sl) => document.getElementById('awards-app-root').insertAdjacentHTML('beforeend', "
                                  "'<button type=\"button\" class=\"aw-share\" id=\"aw-test-sl\" data-aw-share=\"superlative\" "
                                  "data-sl=\"' + sl + '\">Share</button>')", sl)
                    res["bad"] += _gfx_open(page, "#aw-test-sl")
                    want_s = [s["title"]] + [str(r["value_display"]) for r in s["rows"][:5]] + [s["rows"][0]["name"]]
                    if fx == "live" or sl in ("glove", "pitching_changes"):
                        res["bad"] += _gfx_matrix(page, f"{fx}_superlative_{sl}", out, report, want_s)
                    page.evaluate(GFX_CLOSE_JS)
                    page.evaluate("() => document.getElementById('aw-test-sl').remove()")
            _record(report, name, res, _errors(log, page._aw_aborted))
            ctx.close()

    # 2. Past seasons: 2023 (no race) and 2022 (Manager blocked: no Manager chip, "Not published").
    write_fixture(site, fixtures["live"])
    for S in (2023, 2022):
        doc = fixtures["live"][f"awards_{S}.json"]
        ctx = _context(browser, 1280, "dark")
        ctx.add_init_script(FILLTEXT_INIT)
        log = []
        page = _page(ctx, log)
        page.goto(f"{base}/awards/#season={S}", wait_until="networkidle")
        page.wait_for_selector(".aw-hero", timeout=15000)
        res = {"bad": []}
        moy = page.query_selector_all('[data-aw-share="podium"][data-award="moy"]')
        if S == 2022 and moy:
            res["bad"].append("a blocked Manager rule still carries a Share chip")
        res["bad"] += _gfx_open(page, '[data-aw-share="slate"]')
        r = page.evaluate(GFX_RENDER_JS, ["wide", "dark"])
        if r.get("err") or not r.get("url"):
            res["bad"].append(f"slate {S}: {r.get('err')}")
        elif S == 2022 and "Not published" not in r["text"]:
            res["bad"].append("2022 slate lacks Not published for the blocked Manager rule")
        if r.get("text") and not any(f"/awards/#season={S}" in t for t in r["text"]):
            res["bad"].append(f"{S} slate link lacks the season")
        res["bad"] += _gfx_matrix(page, f"season{S}_slate", out, report, [])
        page.evaluate(GFX_CLOSE_JS)
        _record(report, f"gfx_season{S}", res, _errors(log, page._aw_aborted))
        ctx.close()

    # 3. My Ballot's Save image: the viewer's card, never the selection.
    for w in (390, 1280):
        ctx = _context(browser, w, "light")
        ctx.add_init_script(FILLTEXT_INIT)
        log = []
        page = _page(ctx, log)
        _open_ballot(page, base)
        res = {"bad": []}
        note = (page.text_content("#aw-b-save") or "").strip()
        if not note.endswith("To keep it, copy the link or save the image."):
            res["bad"].append(f"save note reads {note!r}")
        page.click('[data-act="img"]')
        page.wait_for_timeout(400)
        if page.query_selector("#egfx-overlay.is-open"):
            res["bad"].append("Save image opened on an empty ballot")
        if "ballot is empty" not in (page.text_content("#aw-b-live") or ""):
            res["bad"].append("an empty Save image does not say so")
        ids = _fill_three(page)
        names = page.eval_on_selector_all("#aw-b-panel .aw-b-slot .aw-b-who", "(els) => els.map((e) => e.textContent)")
        res["bad"] += _gfx_open(page, '[data-act="img"]')
        forbid = ["eephus selection", "Current leaders", "Eephus place", "the rule"]
        want = ["Choices mine. Numbers from eephus.io.", "1st · 14 pts"] + names
        if w == 1280:
            res["bad"] += _gfx_matrix(page, "ballot_al_mvp", out, report, want, forbid)
            page.evaluate(GFX_CLOSE_JS)
            # a second filled ballot: Portrait draws both, Twitter only the active one
            page.click("#aw-b-tnl-cy")
            page.wait_for_selector('#aw-b-tnl-cy[aria-selected="true"]')
            _fill_three(page)
            res["bad"] += _gfx_open(page, '[data-act="img"]')
            rp = page.evaluate(GFX_RENDER_JS, ["portrait", "light"])
            if not any("AL MVP" in t for t in rp.get("text", [])) or not any("NL Cy Young" in t for t in rp.get("text", [])):
                res["bad"].append("the Portrait ballot card does not carry every filled ballot")
            rt = page.evaluate(GFX_RENDER_JS, ["twitter", "light"])
            if any("AL MVP" in t for t in rt.get("text", [])):
                res["bad"].append("the Twitter ballot card carries a second ballot")
            res["bad"] += _gfx_matrix(page, "ballot_two", out, report, ["Choices mine. Numbers from eephus.io."], forbid)
        else:
            r0 = page.evaluate(GFX_RENDER_JS, ["twitter", "dark"])
            if r0.get("err") or "Choices mine. Numbers from eephus.io." not in " ".join(r0.get("text", [])):
                res["bad"].append("ballot card at 390")
            page.screenshot(path=str(out / f"gfx_ballot_{w}_modal.png"))
            report["screens"].append(f"gfx_ballot_{w}_modal.png")
        _record(report, f"gfx_ballot_{w}", res, _errors(log, page._aw_aborted))
        ctx.close()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--port", type=int, default=9141)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--preview", type=Path, default=None,
                    help="read the fixture payloads from this copy of .cache/awards/preview/")
    ap.add_argument("--only", choices=("all", "selections", "ballot", "gfx"), default="all")
    a = ap.parse_args(argv)
    global PREVIEW, ONLY
    if a.preview:
        PREVIEW = a.preview
    ONLY = a.only
    if not (PREVIEW / "awards.json").exists():
        print(f"no preview payload at {PREVIEW}: run awards_export.py first (flag False writes there)")
        return 2
    rep = run(a.port, a.out)
    for c in rep["checks"]:
        extra = f" contrast min {c['contrast_worst']}" if "contrast_worst" in c else ""
        print(f"  {'FAIL' if c['bad'] else 'ok  '} {c['name']}{extra}")
    print(f"{len(rep['screens'])} screenshots in {a.out}; {len(rep['failures'])} failures")
    for f in rep["failures"][:80]:
        print("   ", f.encode("ascii", "replace").decode())
    return 1 if rep["failures"] else 0


if __name__ == "__main__":
    sys.exit(main())
