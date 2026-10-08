/* =============================================================================
   eephus.io - /awards/, the Awards section of Awards / HoF (AWARDS_7)
   -----------------------------------------------------------------------------
   Reads data/awards.json (awards_export.py) and, for a closed season picked in
   the Season select, data/awards_<S>.json. Selections is built here: the stamp
   line, the scoreboard hero, the award jump strip and eight award cards (four
   awards by two leagues), each with its lamp ladder, lead line, writers' line,
   drift ("Now") after a freeze, the Rookie list outside the rookie test, the
   Manager card's two parts and two management facts, and three disclosures
   (the finalist comparison strip, the race strip and the rule's full ballot).
   My Ballot is assets/awards-ballot.js (AWARDS_9), loaded on its first open.
   Share (each card, the hero, and the superlatives' seam) and My Ballot's Save
   image open the shared GFX modal's awards cards (AWARDS_10), rendered only
   when the shell names the engine, which loads on the first press.
   Superlatives, Rule and vote and Method (AWARDS_8) are assets/awards-tabs.js,
   loaded on the first open of any of the three.

   Every number is printed from the payload as served (score_display, lead,
   compare values) and every label from its payload field; the client builds no
   ids and computes no score. The selection is a published rule over the site's
   numbers and never a forecast of the vote (AWARDS_PLAN 5.15).

   Pictures are aria-hidden SVG with a text or table twin, or role=img with a
   field-built label and a table twin. Lamps are whole pixels: 4 x 10 with a
   1 px gap below 768 px, 6 x 12 with a 2 px gap from 768 px, one rect per run
   filled with a lamp pattern (the PX-14 technique). No animation: the loading
   lamp is EephusState's. Colours are site.css tokens only.
   ========================================================================== */
(function () {
  "use strict";
  var root = document.getElementById("awards-app-root");
  if (!root) return;
  var T = window.EephusTiers || null;
  var ST = window.EephusState || null;
  var SRC = "/data/awards.json";
  var AWARDS = ["MVP", "CY", "ROY", "MOY"];
  var LGS = ["AL", "NL"];
  var KEY = { MVP: "mvp", CY: "cy", ROY: "roy", MOY: "moy" };
  var BY_KEY = { mvp: "MVP", cy: "CY", roy: "ROY", moy: "MOY" };
  var SHORT = { MVP: "MVP", CY: "Cy Young", ROY: "Rookie", MOY: "Manager" };
  var TITLE = { MVP: "MVP", CY: "Cy Young", ROY: "Rookie of the Year", MOY: "Manager of the Year" };
  var LEAGUE = { AL: "American League", NL: "National League" };
  var SECTIONS = [["selections", "Selections"], ["superlatives", "Superlatives"], ["ballot", "My Ballot"],
                  ["vote", "Rule and vote"], ["method", "Method"]];
  var POS = { C: "catcher", "1B": "first base", "2B": "second base", "3B": "third base", SS: "shortstop",
              LF: "left field", CF: "center field", RF: "right field", OF: "outfield", IF: "infield",
              DH: "designated hitter", P: "pitcher", SP: "starting pitcher", RP: "relief pitcher",
              TWP: "two-way player" };
  var MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
                "October", "November", "December"];
  var SUFFIX = /^(jr\.?|sr\.?|ii|iii|iv|v)$/i;
  var LAMP = { s: { w: 4, h: 10, p: 5 }, l: { w: 6, h: 12, p: 8 } };
  var FILLS = ["elite", "great", "good", "above", "avg", "below", "poor", "ink", "down", "up", "off"];
  var MAX_LAMPS = 60;
  var STALE_MS = 48 * 3600 * 1000;

  var main = null;
  var shards = {};
  var state = null;
  var lastHash = null;
  var layoutKey = "";
  var sprite = (function () {
    var u = document.querySelector('use[href*="/assets/eephus-icons.svg"]');
    return u ? String(u.getAttribute("href")).split("#")[0] : "/assets/eephus-icons.svg";
  })();

  // ---- small helpers --------------------------------------------------------
  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function num(v) { var n = Number(v); return (v == null || v === "" || !isFinite(n)) ? null : n; }
  function fmt(v, d) { var n = num(v); return n == null ? null : n.toFixed(d == null ? 1 : d); }
  function signed(v, d) { var s = fmt(v, d); return s == null ? "" : (Number(v) > 0 ? "+" + s : s); }
  function ord(n) {
    var m = n % 100, t = n % 10;
    return n + ((m >= 11 && m <= 13) ? "th" : t === 1 ? "st" : t === 2 ? "nd" : t === 3 ? "rd" : "th");
  }
  function ymd(iso) {
    var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || ""));
    return m ? { y: +m[1], m: +m[2], d: +m[3] } : null;
  }
  function dateLong(iso) { var t = ymd(iso); return t ? MONTHS[t.m - 1] + " " + t.d + ", " + t.y : ""; }
  function dateShort(iso) { var t = ymd(iso); return t ? MONTHS[t.m - 1].slice(0, 3) + " " + t.d : ""; }
  function ico(key, size) {
    var href = esc(sprite + "#i-" + key);
    return size === 12
      ? '<svg class="ico" width="12" height="12" viewBox="2 2 12 12" aria-hidden="true" focusable="false"><use href="' + href + '" width="16" height="16"/></svg>'
      : '<svg class="ico" width="16" height="16" viewBox="0 0 16 16" aria-hidden="true" focusable="false"><use href="' + href + '"/></svg>';
  }
  function stateBox(kind, msg, cls) {
    if (ST) return ST.html(kind, msg, cls);
    return '<div class="px-state is-' + kind + '"' + (kind === "failed" ? ' role="alert"' : "") +
      '><div class="px-state-msg">' + msg + "</div></div>";
  }
  function surname(name) {
    var p = String(name || "").trim().split(/\s+/);
    if (p.length < 2) return p[0] || "";
    return SUFFIX.test(p[p.length - 1]) && p.length > 2 ? p.slice(-2).join(" ") : p[p.length - 1];
  }
  function tierOf(v, fam) { return (T && fam) ? T.tier(v, fam) : ""; }
  function ink(v, fam) { return (T && fam) ? T.clsInk(v, fam) : ""; }
  function wide() { return window.matchMedia && window.matchMedia("(min-width: 768px)").matches; }
  function twoCol() { return window.matchMedia && window.matchMedia("(min-width: 1024px)").matches; }
  function rowKey(r) { return r.mlbam != null ? String(r.mlbam) : "c" + String(r.club || "").toLowerCase(); }
  function rowName(r) { return r.mlbam != null ? r.name : (r.club_name || r.name); }

  // ---- the hash (AWARDS_PLAN 5.1): every value checked against the payload ----
  function parseHash() {
    var q = {};
    String(location.hash || "").replace(/^#/, "").split("&").forEach(function (kv) {
      var i = kv.indexOf("=");
      if (i > 0) {
        try { q[decodeURIComponent(kv.slice(0, i))] = decodeURIComponent(kv.slice(i + 1)); } catch (e) { /* dropped */ }
      }
    });
    var s = { section: "selections", season: main.default_season, award: null, lg: null, sl: null, b: null };
    if (SECTIONS.some(function (x) { return x[0] === q.section; })) s.section = q.section;
    (main.seasons || []).forEach(function (x) { if (String(x.season) === q.season) s.season = x.season; });
    if (BY_KEY[q.award]) s.award = q.award;
    if (q.lg === "al" || q.lg === "nl") s.lg = q.lg;
    if ((main.superlatives || []).some(function (x) { return x.id === q.sl; })) s.sl = q.sl;
    if (q.b && /^[a-z0-9._:,-]+$/.test(q.b)) {
      s.b = q.b;
      if (!q.section) s.section = "ballot";
    }
    return s;
  }
  function hashOf(s) {
    var p = [];
    if (s.section !== "selections") p.push("section=" + s.section);
    if (s.season !== main.default_season) p.push("season=" + s.season);
    if (s.award) p.push("award=" + s.award);
    if (s.lg) p.push("lg=" + s.lg);
    if (s.sl) p.push("sl=" + s.sl);
    if (s.b) p.push("b=" + s.b);
    return p.join("&");
  }
  function linkTo(award, lg) {
    var h = hashOf({ section: "selections", season: state.season, award: award, lg: lg, sl: null, b: null });
    return "#" + h;
  }
  function go(s) {
    var h = hashOf(s), cur = String(location.hash || "").replace(/^#/, "");
    if (h !== cur) {
      try { history.pushState(null, "", h ? "#" + h : location.pathname + location.search); } catch (e) { /* stays */ }
    }
    apply(s, true);
  }
  function onHash() {
    if (!main) return;
    if (location.hash === lastHash) return;
    apply(parseHash(), true);
  }

  // ---- the shell: tabs and panels --------------------------------------------
  function shell() {
    var defs = "";
    ["s", "l"].forEach(function (z) {
      var L = LAMP[z];
      FILLS.forEach(function (f) {
        defs += '<pattern id="aw-lp-' + z + "-" + f + '" width="' + L.p + '" height="' + L.h +
          '" patternUnits="userSpaceOnUse"><rect class="aw-f-' + f + '" width="' + L.w + '" height="' + L.h + '"/></pattern>';
      });
    });
    var tabs = SECTIONS.map(function (x) {
      return '<button type="button" class="mlbstats-tab" role="tab" id="aw-tab-' + x[0] + '" aria-controls="aw-panel-' +
        x[0] + '" aria-selected="false" tabindex="-1" data-section="' + x[0] + '">' +
        (x[0] === "ballot" ? ico("aw-ballot", 12) : "") + x[1] + "</button>";
    }).join("");
    var panels = SECTIONS.map(function (x) {
      return '<div class="aw-panel" id="aw-panel-' + x[0] + '" role="tabpanel" aria-labelledby="aw-tab-' + x[0] +
        '" tabindex="0" hidden></div>';
    }).join("");
    root.innerHTML = '<svg class="aw-defs" width="0" height="0" aria-hidden="true" focusable="false"><defs>' + defs +
      "</defs></svg>" + '<div class="mlbstats-tabs aw-tabs" role="tablist" aria-label="Awards sections">' + tabs +
      "</div>" + panels;
    var list = root.querySelector(".aw-tabs");
    var keyMove = false;
    list.addEventListener("keydown", function (e) {
      keyMove = /^(ArrowLeft|ArrowRight|Home|End)$/.test(e.key) && !e.altKey && !e.ctrlKey && !e.metaKey;
    });
    list.addEventListener("focusin", function (e) {
      var t = e.target.closest && e.target.closest('[role="tab"]');
      if (keyMove && t && t.getAttribute("aria-selected") !== "true") {
        keyMove = false;
        go(merge({ section: t.getAttribute("data-section"), award: null, lg: null, sl: null }));
      }
      keyMove = false;
    });
    list.addEventListener("click", function (e) {
      var t = e.target.closest && e.target.closest('[role="tab"]');
      if (t) go(merge({ section: t.getAttribute("data-section"), award: null, lg: null, sl: null }));
    });
    if (window.EephusUI && window.EephusUI.wireTablist) window.EephusUI.wireTablist(list);
    root.addEventListener("change", function (e) {
      if (e.target && e.target.classList.contains("aw-season-sel")) {
        go(merge({ season: Number(e.target.value), sl: null }));
      }
    });
    root.addEventListener("click", function (e) {
      var r = e.target.closest && e.target.closest(".aw-retry");
      if (r) { delete shards[state.season]; apply(state, false); }
      var sh = e.target.closest && e.target.closest("[data-aw-share]");
      if (sh) share(sh);
      var cv = e.target.closest && e.target.closest("[data-aw-csv]");
      if (cv && window.EephusAwardsTabs) window.EephusAwardsTabs.csv(tabsCtx(), cv.getAttribute("data-aw-csv"));
      var mo = e.target.closest && e.target.closest(".aw-more");
      if (mo) {
        var ol = document.getElementById(mo.getAttribute("aria-controls")), on = mo.getAttribute("aria-expanded") !== "true";
        ol.classList.toggle("open", on);
        mo.setAttribute("aria-expanded", on ? "true" : "false");
        mo.textContent = "Show " + (on ? 3 : ol.children.length);
      }
    });
  }
  function merge(o) {
    var s = {};
    for (var k in state) s[k] = state[k];
    for (var j in o) s[j] = o[j];
    return s;
  }

  function apply(s, scroll) {
    state = s;
    lastHash = location.hash;
    var list = root.querySelector(".aw-tabs");
    SECTIONS.forEach(function (x) {
      var on = x[0] === s.section;
      var tab = document.getElementById("aw-tab-" + x[0]);
      tab.setAttribute("aria-selected", on ? "true" : "false");
      tab.setAttribute("tabindex", on ? "0" : "-1");
      tab.classList.toggle("active", on);
      document.getElementById("aw-panel-" + x[0]).hidden = !on;
      if (on && list.scrollWidth > list.clientWidth) {
        list.scrollLeft = Math.max(0, tab.offsetLeft - list.offsetLeft - 16);
      }
    });
    var panel = document.getElementById("aw-panel-" + s.section);
    var el = null;
    if (s.section === "ballot") { ballot(panel, s); return; }
    if (!window.EephusAwardsTabs && s.section !== "selections") {
      panel.innerHTML = controls(s.section) + stateBox("loading", "Loading the awards.");
      tabsLoad().then(function () { if (state === s) apply(s, scroll); }, function () {
        if (state === s) panel.innerHTML = controls(s.section) + stateBox("failed", 'The awards could not load. <button type="button" class="aw-retry">Retry</button>');
      });
      return;
    }
    var X = window.EephusAwardsTabs;
    if (s.section === "vote") {
      panel.innerHTML = X.vote(tabsCtx());
      el = scroll && s.season !== main.default_season && document.getElementById("aw-v-" + s.season);
      if (el && el.scrollIntoView) el.scrollIntoView({ block: "start" });
      return;
    }
    var doc = docFor(s.season);
    if (doc && doc.then) {
      panel.innerHTML = controls(s.section) + stateBox("loading", "Loading the awards.");
      doc.then(function () { if (state === s) apply(s, scroll); }, function () {
        if (state !== s) return;
        panel.innerHTML = controls(s.section) + stateBox("failed",
          'The awards could not load. <button type="button" class="aw-retry">Retry</button>');
      });
      return;
    }
    layoutKey = layout();
    panel.innerHTML = s.section === "selections" ? selections(doc) : X[s.section](tabsCtx(), doc);
    if (window.EEPHUS_GL && window.EEPHUS_GL.wire) window.EEPHUS_GL.wire(panel);
    if (scroll && s.section === "selections" && s.award) {
      el = document.getElementById(s.lg ? "aw-c-" + s.award + "-" + s.lg : "aw-g-" + s.award);
    } else if (scroll && s.sl) {
      el = document.getElementById((s.section === "method" ? "aw-m-" : "aw-sl-") + s.sl);
    }
    if (el && el.scrollIntoView) el.scrollIntoView({ block: "start" });
  }

  function docFor(season) {
    if (season === main.season) return main;
    var d = shards[season];
    if (d && !d.then) return d;
    if (d) return d;
    var p = fetch("/data/awards_" + season + ".json", { credentials: "same-origin" })
      .then(function (r) { if (!r.ok) throw new Error("http " + r.status); return r.json(); })
      .then(function (j) { if (!valid(j)) throw new Error("schema"); shards[season] = j; return j; },
        function (e) { delete shards[season]; throw e; });
    p.catch(function () { delete shards[season]; });
    shards[season] = p;
    return p;
  }
  function valid(d) {
    return !!(d && d.schema === 1 && d.awards && d.rules && typeof d.season === "number");
  }

  // ---- controls, stamp ------------------------------------------------------
  function controls(section) {
    var opts = (main.seasons || []).slice().sort(function (a, b) { return b.season - a.season; })
      .map(function (x) {
        return '<option value="' + x.season + '"' + (x.season === state.season ? " selected" : "") + ">" + x.season + "</option>";
      }).join("");
    return '<div class="aw-controls"><label class="aw-season">Season <select class="aw-season-sel" id="aw-season-' +
      section + '">' + opts + "</select></label></div>";
  }
  function seasonEntry(S) {
    return (main.seasons || []).filter(function (x) { return x.season === S; })[0] || null;
  }
  function warUnit(doc) {
    var r = doc.rules && doc.rules.MVP;
    return r && r.unit ? r.unit : "";
  }
  function stampLine(doc) {
    return '<p class="aw-stamp" role="status">' + esc(stampText(doc)) + "</p>";
  }
  function stampText(doc) {
    var st = doc.stamp || {}, status = doc.status, out = "";
    var through = dateLong(st.through);
    if (status === "closed") {
      out = "Season through " + through + ". Computed after the fact by the same rule from the same files; " +
        "the site did not publish a selection that season.";
    } else if (st.frozen_at) {
      var v = st.ewar_vintage && st.ewar_vintage.as_of;
      out = "Regular season through " + through + "." + (v ? " " + warUnit(doc) + " as of " + dateLong(v) + "." : "") +
        " Selection frozen " + dateLong(st.frozen_at) + ".";
    } else {
      out = "Current leaders on the rule through " + through + ". Selection freezes before the writers' results.";
    }
    var g = Date.parse(doc.generated_at || "");
    if (status === "live" && isFinite(g) && Date.now() - g > STALE_MS) {
      out += " Last updated " + dateLong(doc.generated_at) + "; numbers may be out of date.";
    }
    return out;
  }
  function kicker(doc) { return doc.status === "live" ? "Current leaders on the rule" : "The eephus selection"; }
  function caption(doc) {
    if (doc === main && main.selection_caption) return main.selection_caption;
    return (doc.status === "live" ? "Current leaders on the rule, " : "The eephus selection, 1st place, ") + doc.season;
  }

  // ---- Selections -------------------------------------------------------------
  function layout() {
    return (wide() ? "l" : "s") + (twoCol() ? "2" : "1") + ":" + Math.round(root.clientWidth / 40);
  }
  function selections(doc) {
    var ent = seasonEntry(doc.season);
    var h = controls("selections") + stampLine(doc);
    if (ent && ent.note) h += '<p class="aw-note">' + esc(ent.note) + "</p>";
    h += hero(doc) + jump();
    AWARDS.forEach(function (A) {
      var rule = doc.rules[A] || {};
      h += '<section class="aw-group" id="aw-g-' + KEY[A] + '" aria-labelledby="aw-gh-' + KEY[A] + '">' +
        '<h2 class="aw-gh" id="aw-gh-' + KEY[A] + '">' + esc(rule.name || TITLE[A]) + '</h2><div class="aw-pair">';
      LGS.forEach(function (LG) { h += card(doc, A, LG); });
      h += "</div></section>";
    });
    return h;
  }
  function block(doc, A, LG) {
    var r = doc.rules[A];
    if (!r || r.blocked_on) return null;
    var b = doc.awards[A] && doc.awards[A][LG];
    return b && b.top && b.top.length ? b : null;
  }
  function firsts(b) {
    var top = b.top, s0 = top[0].score;
    return top.filter(function (r, i) { return i === 0 || (r.score === s0 && (r.flags || []).indexOf("tie") >= 0); });
  }
  function hero(doc) {
    var h = '<table class="aw-hero"><caption>' + esc(caption(doc)) + '</caption><thead><tr><td></td>' +
      '<th scope="col">AL</th><th scope="col">NL</th></tr></thead><tbody>';
    AWARDS.forEach(function (A) {
      h += '<tr><th scope="row">' + SHORT[A] + "</th>";
      LGS.forEach(function (LG) {
        var b = block(doc, A, LG);
        if (!b) {
          h += '<td class="aw-hero-off">' + boardGlyph() + "<span>Not published</span></td>";
          return;
        }
        var f = firsts(b), tie = f.length > 1;
        var label = LG + " " + SHORT[A] + ", 1st: " + f.map(function (r) {
          return rowName(r) + ", " + r.club_code;
        }).join("; ") + (tie ? ", tied" : "");
        h += '<td><a href="' + esc(linkTo(KEY[A], LG.toLowerCase())) + '" aria-label="' + esc(label) + '">' +
          f.map(function (r) {
            var n = A === "MOY" ? rowName(r) : surname(r.name);
            return '<span class="aw-hero-n">' + (tie ? "T " : "") + esc(n) + '</span><span class="aw-hero-c">' +
              esc(r.club_code) + "</span>";
          }).join("") + "</a></td>";
      });
      h += "</tr>";
    });
    return h + "</tbody></table>";
  }
  function boardGlyph() {
    var m = /<svg[\s\S]*?<\/svg>/.exec(stateBox("unmeasured", ""));
    return m ? m[0].replace(/width="64" height="32"/, 'width="24" height="12"').replace('class="px-art"', 'class="px-art aw-glyph"') : "";
  }
  function jump() {
    return '<nav class="aw-jump" aria-label="Awards on this page">' + AWARDS.map(function (A) {
      return '<a class="aw-chip" href="' + esc(linkTo(KEY[A], null)) + '">' + SHORT[A] + "</a>";
    }).join("") + shareChip("slate", "", "Share the eight 1st places as an image") + "</nav>";
  }

  function card(doc, A, LG) {
    var id = KEY[A] + "-" + LG.toLowerCase();
    var rule = doc.rules[A] || {};
    var full = LEAGUE[LG] + " " + (rule.name || TITLE[A]);
    var b = block(doc, A, LG);
    var h = '<article class="aw-card" id="aw-c-' + id + '" aria-labelledby="aw-cn-' + id + '">' +
      '<header class="aw-card-h"><h3 title="' + esc(full) + '">' + ico("aw-podium", 16) + LG + " " + TITLE[A] + "</h3>" +
      '<span id="aw-cn-' + id + '" hidden>' + esc(full) + "</span>" +
      regChip(doc, rule.registry) +
      (b ? shareChip("podium", ' data-award="' + KEY[A] + '" data-lg="' + LG.toLowerCase() + '"',
        "Share " + LG + " " + TITLE[A] + " as an image") : "") + "</header>";
    if (!b) {
      var why = rule.blocked_on || ("No rule is published for " + (rule.name || TITLE[A]) + " in " + doc.season + ".");
      return h + stateBox("unmeasured", esc(why)) + "</article>";
    }
    h += '<p class="aw-kicker">' + kicker(doc) + "</p>";
    h += '<p class="aw-rule">' + [rule.label, rule.floor_label, rule.tie_label, rule.two_way_label, rule.eligibility_label]
      .filter(Boolean).map(esc).join(" ") + "</p>";
    h += ladder(doc, A, LG, b, rule);
    if (b.lead) h += '<p class="aw-lead">' + esc(b.lead) + "</p>";
    if (b.tiebreak_sentence) h += '<p class="aw-lead">' + esc(b.tiebreak_sentence) + "</p>";
    if (A === "MOY") {
      h += '<p class="aw-fact">The site&#39;s decision values are realized value, not skill, and are never summed ' +
        'across families. <a href="/management/#section=decisions">Decisions by club on In-Game Management</a></p>';
    }
    if (b.excluded && b.excluded.length) {
      h += '<details class="aw-excl"' + (b.excluded.length <= 3 ? " open" : "") + "><summary>Outside the rookie test (" +
        b.excluded.length + ")</summary><ul>" + b.excluded.map(function (e) {
          return "<li>" + esc(e.label || e.name) + "</li>";
        }).join("") + "</ul></details>";
    }
    h += writers(doc, b, A, LG);
    var n = ((doc.ballot_rules || main.ballot_rules || {})[A] || {}).n || b.top.length;
    h += '<details class="aw-d" data-d="cmp"' + (twoCol() ? " open" : "") + "><summary>Compare the three</summary>" +
      compare(doc, A, LG, b) + "</details>";
    h += '<details class="aw-d" data-d="race"><summary>The race</summary>' + race(doc, A, LG) + "</details>";
    h += '<details class="aw-d" data-d="ballot"><summary>The rule&#39;s full ballot (' + n + " places)</summary>" +
      fullBallot(b, rule, n) + "</details>";
    return h + "</article>";
  }

  function places(top) {
    var out = [], i = 0;
    while (i < top.length) {
      var j = i;
      while (j + 1 < top.length && top[j + 1].score === top[i].score) j++;
      for (var k = i; k <= j; k++) out.push({ n: i + 1, tie: j > i });
      i = j + 1;
    }
    return out;
  }
  function lampSize() { return wide() ? LAMP.l : LAMP.s; }
  function lampGeom(rows, unit) {
    var lit = rows.map(function (r) {
      var v = num(r.score_display);
      return v == null ? 0 : Math.min(MAX_LAMPS, Math.round(Math.abs(v) / unit));
    });
    var neg = 0, lead = 0;
    rows.forEach(function (r, i) {
      if (num(r.score_display) < 0) neg = Math.max(neg, lit[i]); else lead = Math.max(lead, lit[i]);
    });
    if (num(rows[0].score_display) >= 0) lead = Math.max(lead, lit[0]);
    return { lit: lit, neg: neg, lead: lead };
  }
  function ladder(doc, A, LG, b, rule) {
    var top = b.top.slice(0, 3), pl = places(b.top);
    var unit = num(rule.lamp_unit) || 1, d = rule.decimals == null ? 1 : rule.decimals;
    var L = lampSize(), g = lampGeom(top, unit);
    var z = wide() ? "l" : "s", zero = g.neg ? (g.neg + 1) * L.p : 0;
    var width = zero + Math.max(g.lead, 1) * L.p;
    var drift = {};
    (b.drift || []).forEach(function (e) { drift[String(e.id)] = e; });
    var h = '<ol class="aw-ladder" data-unit="' + unit + '" data-pitch="' + L.p + '">';
    top.forEach(function (r, i) {
      var v = num(r.score_display), place = pl[i], pnum = (place.tie ? "T" : "") + place.n;
      var fam = rule.family || null, tier = fam ? tierOf(v, fam) : "";
      var fill = v != null && v < 0 ? "down" : (tier || "ink");
      var name = rowName(r), lit = g.lit[i];
      var sub = A === "MOY" ? [r.club_code, (r.w != null ? fmt(r.w, 0) + "-" + fmt(r.l, 0) : "")] : [r.club_code, r.pos];
      var spoken = [r.club_code, A === "MOY" ? null : (POS[r.pos] || r.pos)].filter(Boolean).join(", ");
      var val = fmt(v, d);
      var links = r.links || {};
      var href = links.overview || links.management || links.franchise || null;
      h += '<li class="aw-row" data-id="' + esc(rowKey(r)) + '" data-value="' + esc(val) + '" data-lit="' + lit +
        '" data-fill="' + fill + '"><span class="visually-hidden">' + ord(place.n) + (place.tie ? ", tied" : "") +
        ", </span>" + '<span class="aw-place' + (place.n === 1 ? " p1" : "") + '" aria-hidden="true">' + pnum + "</span>" +
        '<div class="aw-who">' + (href ? '<a class="aw-name" href="' + esc(href) + '">' + esc(name) + "</a>" :
          '<span class="aw-name">' + esc(name) + "</span>") +
        (links.prospx ? ' <a class="aw-px" href="' + esc(links.prospx) + '" aria-label="' + esc(name + " on PROSPX") + '">PROSPX</a>' : "") +
        '<span class="visually-hidden">, ' + esc(spoken) + ", " + esc(val) + " " + esc(rule.unit) + "</span>" +
        '<span class="aw-sub" aria-hidden="true">' + esc(sub.filter(Boolean).join(" \u00b7 ")) + "</span>";
      if (r.split_label) h += '<span class="aw-sub">' + esc(r.split_label) + "</span>";
      if (A === "MOY" && r.parts) h += partsLine(b, r);
      var dr = drift[rowKey(r)];
      if (dr && dr.score_now_display != null) {
        h += '<span class="aw-drift" title="' + esc(dr.tooltip || "") + '">' + esc(dr.unit_label) + " " +
          esc(fmt(dr.score_now_display, d)) + "</span>";
      }
      h += '</div><span class="aw-val" aria-hidden="true"><span class="aw-num ' + ink(v, fam) + '">' + esc(val) +
        '</span> <span class="aw-unit">' + esc(rule.unit) + "</span></span>" + lamps(z, L, g, i, v, fill, zero, width) + "</li>";
    });
    h += "</ol>" + ticks(L, g, zero, width, unit, rule);
    return h;
  }
  function lamps(z, L, g, i, v, fill, zero, width) {
    var lit = g.lit[i], s = "";
    if (v != null && v < 0) {
      s += '<rect class="aw-lit" fill="url(#aw-lp-' + z + "-down)" + '" x="' + (zero - lit * L.p) + '" y="0" width="' + (lit * L.p) +
        '" height="' + L.h + '"/>';
    } else if (lit) {
      s += '<rect class="aw-lit" fill="url(#aw-lp-' + z + "-" + fill + ')" x="' + zero + '" y="0" width="' + (lit * L.p) +
        '" height="' + L.h + '"/>';
    }
    var unlit = g.lead - (v != null && v >= 0 ? lit : 0);
    if (unlit > 0) {
      s += '<rect class="aw-unlit" fill="url(#aw-lp-' + z + '-off)" x="' + (zero + (v != null && v >= 0 ? lit : 0) * L.p) +
        '" y="0" width="' + (unlit * L.p) + '" height="' + L.h + '"/>';
    }
    if (g.neg) s += '<rect class="aw-zero" x="' + (zero - 1) + '" y="0" width="1" height="' + L.h + '"/>';
    return '<svg class="aw-lamps" aria-hidden="true" focusable="false" width="' + width + '" height="' + L.h +
      '" viewBox="0 0 ' + width + " " + L.h + '" shape-rendering="crispEdges">' + s + "</svg>";
  }
  function ticks(L, g, zero, width, unit, rule) {
    var every = num(rule.tick_every) || 1, step = every / unit, s = "", k = 0;
    if (!(step >= 1)) return "";
    for (var x = zero; x <= width; x = zero + Math.round(++k * step) * L.p) {
      s += '<rect x="' + x + '" y="0" width="1" height="4"/>' +
        '<text x="' + x + '" y="14">' + (k * every) + "</text>";
    }
    return '<div class="aw-ticks" title="' + esc("One lamp is " + unit + " " + (rule.unit || "") + ". The number beside the row is exact.") +
      '"><svg aria-hidden="true" focusable="false" width="' + (width + 16) + '" height="16" viewBox="0 0 ' + (width + 16) +
      ' 16" shape-rendering="crispEdges">' + s + "</svg></div>";
  }
  function partsLine(b, r) {
    var lab = {};
    ((b.compare || {}).metrics || []).forEach(function (m) { lab[m.key] = m.label; });
    var p = r.parts;
    return '<span class="aw-sub aw-parts">' + esc((lab.sequencing || "sequencing") + " " + signed(p.sequencing_display, 1) +
      "; " + (lab.runs_vs_player_value || "runs against player value") + " " + signed(p.runs_vs_player_value_display, 1)) + "</span>";
  }
  // The writers' line (AWARDS_PLAN 5.6): the vote's state, the rule's place of the
  // writers' 1st, the rule's 1st's finish where the source has finishes, and
  // before the vote the freeze date from the payload.
  function writers(doc, b, A, LG) {
    var w = b.writers || {}, t = "", fz = doc.status !== "closed" && doc.stamp && doc.stamp.frozen_at;
    if (w.status === "final" && w.winner) {
      var p = w.rule_place_of_winner, who = A === "MOY" ? "his club" : "him";
      var v = (main.vote_table || []).filter(function (r) { return r.season === doc.season && r.award === A && r.league === LG; })[0];
      t = "Writers' 1st: " + w.winner.name + ". " + (p === 1 ? "The rule placed " + who + " 1st too."
        : p ? "The rule placed " + who + " " + ord(p) + "." : "Outside the rule's ballot.") +
        (p !== 1 && v && v.writers_finish_of_rule_first ? " The rule's 1st finished " + ord(v.writers_finish_of_rule_first) + " in the vote." : "");
      fz = null;
    } else if (w.status === "finalists" && w.finalists && w.finalists.length) {
      t = "Writers' finalists: " + w.finalists.map(function (f) { return f.name; }).join(", ") + ".";
    } else {
      t = w.announce_label || "";
    }
    if (t && fz) {
      t += " The selection was frozen on " + dateLong(fz) + ((doc.freeze || {}).after_finalists ? ", after the writers' finalists were named."
        : ", before the writers' results.");
    }
    return t ? '<p class="aw-writers">' + esc(t) + "</p>" : "";
  }
  function fullBallot(b, rule, n) {
    var d = rule.decimals == null ? 1 : rule.decimals, pl = places(b.top);
    return '<ol class="aw-full">' + b.top.slice(0, n).map(function (r, i) {
      return '<li value="' + pl[i].n + '"><span class="aw-fp">' + (pl[i].tie ? "T" : "") + pl[i].n + "</span> " +
        esc(rowName(r)) + ", " + esc(r.club_code) + ", " + esc(fmt(r.score_display, d)) + " " + esc(rule.unit) + "</li>";
    }).join("") + "</ol>";
  }

  // ---- the finalist comparison strip (AWARDS_PLAN 5.3) ---------------------
  function cmpGeom() {
    var w = root.clientWidth || 358, two = twoCol();
    var card = two ? (w - 32) / 2 : w;
    var inner = card - 26, lab = wide() ? 110 : 56, numW = wide() ? 64 : 46;
    return { lab: lab, num: numW, trk: Math.max(96, Math.min(300, Math.floor(inner - lab - 3 * numW - 8))) };
  }
  function segs(fam, p1, p99, W) {
    var Lf = T && T.LADDERS && T.LADDERS[fam];
    if (!Lf || !(p99 > p1)) return null;
    var b = Lf.cuts.slice(), tiers = T.TIERS, out = [], lo = p1, edges = [];
    if (Lf.dir === "hi") {
      var steps = [[-Infinity, Lf.neg ? 0 : -Infinity, "poor"], [Lf.neg ? 0 : -Infinity, b[4], "below"]];
      for (var i = 4; i >= 0; i--) steps.push([b[i], i ? b[i - 1] : Infinity, tiers[i]]);
      edges = steps;
    } else {
      edges = [[-Infinity, b[0], "elite"]];
      for (var j = 0; j < 4; j++) edges.push([b[j], b[j + 1], tiers[j + 1]]);
      edges.push([b[4], Infinity, "below"]);
    }
    edges.forEach(function (e) {
      var a = Math.max(e[0], lo), z = Math.min(e[1], p99);
      if (z > a) out.push({ x: Math.round((a - p1) / (p99 - p1) * W), x2: Math.round((z - p1) / (p99 - p1) * W), t: e[2] });
    });
    return out;
  }
  // `o` (My Ballot, AWARDS_9): {id, cap, keys, G, heads, cell(m, i) -> [value, text], pts(m), noRule}
  // draws the viewer's 1st to 3rd in the columns; the Selections cards pass none.
  function compare(doc, A, LG, b, o) {
    var c = b.compare || {}, ms = c.metrics || [], top = b.top.slice(0, 3);
    if (!ms.length) return stateBox("unmeasured", "No comparison metrics are on file for this card.");
    var G = (o && o.G) || cmpGeom(), W = G.trk, id = o ? o.id : "aw-cc-" + KEY[A] + "-" + LG.toLowerCase();
    var w = (b.writers || {}), wp = !o && w.status === "final" ? w.rule_place_of_winner : null;
    var cap = o ? o.cap : "Compare the three: " + LG + " " + TITLE[A] + ", " + doc.season;
    var heads = o ? o.heads : top.map(function (r, i) { return (i + 1) + " " + (A === "MOY" ? r.club_code : surname(r.name)); });
    var h = '<figure class="aw-cmp" role="group" aria-labelledby="' + id + '">' + (o ? o.keys : "") +
      '<div class="aw-cmp-key" title="The metric&#39;s own value ruler, from the pool&#39;s 1st to 99th percentile.">' +
      (T ? T.keyHTML() : "") + "</div>" +
      '<div class="aw-scroll"><table class="aw-cmp-t" style="width:' + (G.lab + W + 8 + 3 * G.num) + 'px"><caption id="' +
      id + '">' + esc(cap) + '</caption><colgroup><col style="width:' + G.lab + 'px"><col style="width:' + (W + 8) +
      'px"><col style="width:' + G.num + 'px"><col style="width:' + G.num + 'px"><col style="width:' + G.num + 'px"></colgroup><thead><tr><th scope="col">Metric</th><th scope="col"><span class="visually-hidden">Value ruler</span></th>' +
      heads.map(function (t) { return '<th scope="col" class="aw-n">' + esc(t) + "</th>"; }).join("") + "</tr></thead><tbody>";
    ms.forEach(function (m) {
      var d = m.decimals == null ? 1 : m.decimals, vals = m.values || [], pct = m.pct || [];
      h += '<tr data-key="' + esc(m.key) + '"><th scope="row" title="' + esc(m.producer || "") + '">' + esc(m.label) + "</th>" +
        '<td class="aw-trk">' + track(m, W, wp, o && o.pts(m), o && o.noRule) + "</td>" + [0, 1, 2].map(function (i) {
          var cv = o ? o.cell(m, i) : [vals[i], fmt(vals[i], d)], s = cv[1];
          return s == null ? '<td class="aw-n aw-null" data-v="">-</td>'
            : '<td class="aw-n ' + ink(cv[0], m.family) + '" data-v="' + esc(s) + '">' + esc(s) + "</td>";
        }).join("") + "</tr>" + (o ? "" :
        '<tr class="aw-pct"><th scope="row" colspan="2">Pool percentile</th>' + [0, 1, 2].map(function (i) {
          var s = fmt(pct[i], 1);
          return '<td class="aw-n" data-v="' + esc(s || "") + '">' + esc(s == null ? "-" : s) + "</td>";
        }).join("") + "</tr>");
    });
    return h + "</tbody></table></div></figure>";
  }
  // `mine` (My Ballot, AWARDS_9): the viewer's slots 1 to 3 as {n, v, pc}, drawn as
  // lilac squares; `noRule` leaves out the rule's ink numerals (the ballot's switch).
  function track(m, W, wp, mine, noRule) {
    var p1 = num(m.p1), p99 = num(m.p99), fam = m.family, s = "", seg = fam ? segs(fam, p1, p99, W) : null;
    var byPct = !seg;
    if (seg) {
      seg.forEach(function (q) {
        s += '<rect class="aw-seg" data-tier="' + q.t + '" x="' + q.x + '" y="Y" width="' + Math.max(0, q.x2 - q.x) +
          '" height="4" style="fill:var(--vt-' + q.t + ')"/>';
      });
    } else {
      var stops = (T && T.PCT_STOPS) || [];
      for (var i = 0; i < 7; i++) {
        var x0 = Math.round(i * W / 7), x1 = Math.round((i + 1) * W / 7), t = stops[i] ? stops[i][1] : "avg";
        s += '<rect class="aw-seg" data-tier="' + t + '" x="' + x0 + '" y="Y" width="' + (x1 - x0) +
          '" height="4" style="fill:' + ((T && stops[i]) ? T.pctColor(stops[i][0]) : "var(--vt-avg)") + '"/>';
      }
    }
    var marks = [];
    if (!noRule) [0, 1, 2].forEach(function (i) {
      var x = null;
      if (byPct) { var pc = num((m.pct || [])[i]); if (pc != null) x = pc / 100 * W; }
      else { var v = num((m.values || [])[i]); if (v != null) x = (Math.min(p99, Math.max(p1, v)) - p1) / (p99 - p1) * W; }
      if (x != null) marks.push({ x: Math.round(x), n: i + 1, w: false });
      if (x != null && wp === i + 1) marks.push({ x: Math.round(x), n: "W", w: true });
    });
    (mine || []).forEach(function (e) {
      var x = byPct ? (e.pc == null ? null : e.pc / 100 * W)
        : (e.v == null ? null : (Math.min(p99, Math.max(p1, e.v)) - p1) / (p99 - p1) * W);
      if (x != null) marks.push({ x: Math.round(x), n: e.n, w: false, me: true });
    });
    var levels = [];
    marks.forEach(function (mk) {
      var lv = 0;
      while ((levels[lv] || []).some(function (x) { return Math.abs(x - mk.x) < 12; })) lv++;
      (levels[lv] = levels[lv] || []).push(mk.x);
      mk.lv = lv;
    });
    var H = 4 + 2 + 12 + Math.max(0, levels.length - 1) * 13, y = H - 4;
    s = s.replace(/y="Y"/g, 'y="' + y + '"');
    marks.forEach(function (mk) {
      var bx = Math.max(0, Math.min(W - 12, mk.x - 6)), by = y - 2 - 12 - mk.lv * 13;
      s += '<g class="aw-mk' + (mk.w ? " w" : "") + (mk.me ? " me" : "") + '" data-place="' + mk.n + '"><rect x="' + (bx + (mk.w ? 0.5 : 0)) + '" y="' +
        (by + (mk.w ? 0.5 : 0)) + '" width="' + (mk.w ? 11 : 12) + '" height="' + (mk.w ? 11 : 12) + '"/><text x="' + (bx + 6) +
        '" y="' + (by + 10) + '">' + mk.n + "</text></g>";
    });
    return '<svg aria-hidden="true" focusable="false" width="' + W + '" height="' + H + '" viewBox="0 0 ' + W + " " + H +
      '" shape-rendering="crispEdges">' + s + "</svg>";
  }

  // ---- the race strip (AWARDS_PLAN 5.4) --------------------------------------
  function race(doc, A, LG) {
    var r = doc.race && doc.race[A + "_" + LG];
    if (!r || !r.weeks || !r.weeks.length || !r.finalists || !r.finalists.length) {
      return stateBox("unmeasured", "Weekly standings are not on file for " + doc.season +
        ". The card shows the season-end order only.");
    }
    var big = wide(), P = big ? 8 : 5, LW = big ? 6 : 4, X0 = big ? 128 : 96, Y0 = 16, RH = 16;
    var weeks = r.weeks, miss = {}, fins = r.finalists.slice().sort(function (a, b) { return (a.rule_place || 9) - (b.rule_place || 9); });
    (r.missing || []).forEach(function (w) { miss[w] = 1; });
    var W = X0 + weeks.length * P + 2, H = Y0 + fins.length * RH + 14, s = "";
    var first = -1;
    weeks.forEach(function (w, j) { if (first < 0 && !miss[w]) first = j; });
    fins.forEach(function (f, i) {
      var pl = (r.places || {})[String(f.id)] || [], top = Y0 + i * RH, bot = top + 12;
      s += '<text class="aw-rlab" x="0" y="' + (bot - 1) + '">' + (f.rule_place || i + 1) + " " + esc(surname(f.name)) + "</text>";
      weeks.forEach(function (w, j) {
        var x = X0 + j * P, p = pl[j];
        if (miss[w]) {
          s += '<rect class="aw-rm" x="' + x + '" y="' + (bot - 1) + '" width="1" height="1"/>' +
            (LW > 2 ? '<rect class="aw-rm" x="' + (x + 2) + '" y="' + (bot - 1) + '" width="1" height="1"/>' : "");
        } else if (p === 1 || p === 2 || p === 3) {
          var hh = p === 1 ? 12 : p === 2 ? 8 : 4;
          s += '<rect class="aw-rl" data-place="' + p + '" data-w="' + j + '" data-f="' + i + '" x="' + x + '" y="' + (bot - hh) +
            '" width="' + LW + '" height="' + hh + '"/>';
        } else {
          s += '<rect class="aw-ro" x="' + x + '" y="' + (bot - 1) + '" width="' + LW + '" height="1"/>';
        }
      });
    });
    var lastM = -1;
    weeks.forEach(function (w, j) {
      var t = ymd(w);
      if (t && t.m !== lastM) {
        s += '<text class="aw-rmo" x="' + (X0 + j * P) + '" y="' + (H - 2) + '">' + MONTHS[t.m - 1].charAt(0) + "</text>";
        lastM = t.m;
      }
    });
    if (first >= 0 && r.record_starts) {
      var lx = X0 + first * P - 1;
      s += '<line class="aw-rs" x1="' + (lx + 0.5) + '" y1="' + (Y0 - 2) + '" x2="' + (lx + 0.5) + '" y2="' + (Y0 + fins.length * RH) + '"/>' +
        '<text class="aw-rmo" x="' + Math.max(0, lx - 2) + '" y="10">Record starts ' + esc(dateShort(r.record_starts)) + "</text>";
    }
    var label = LG + " " + TITLE[A] + " race, places by week from " + dateShort(weeks[0]) + ": " + fins.map(function (f, i) {
      var n = ((r.places || {})[String(f.id)] || []).filter(function (p) { return p === 1; }).length;
      return n ? f.name + (i === 0 ? " held 1st in " + n + " of " + weeks.length + " weeks" : " 1st in " + n) : f.name + " never held 1st";
    }).join(", ") + ".";
    var h = '<div class="aw-scroll"><svg class="aw-race" role="img" aria-label="' + esc(label) + '" width="' + W + '" height="' + H +
      '" viewBox="0 0 ' + W + " " + H + '" shape-rendering="crispEdges">' + s + "</svg></div>";
    h += '<p class="aw-note" title="Tall lamp: held 1st that week. Middle: 2nd. Short: 3rd. A line: outside the top 3. Dots: no record that week.">' +
      esc(r.metric_label || "") + "</p>";
    h += '<details class="aw-weeks"><summary>Weeks</summary><div class="aw-scroll"><table class="aw-wt"><caption>' +
      esc("Weeks: " + LG + " " + TITLE[A] + " race, " + doc.season) + '</caption><thead><tr><th scope="col">Week</th>' +
      fins.map(function (f) { return '<th scope="col">' + esc(f.name) + "</th>"; }).join("") + "</tr></thead><tbody>" +
      weeks.map(function (w, j) {
        return '<tr><th scope="row">' + esc(dateShort(w)) + "</th>" + fins.map(function (f) {
          var p = ((r.places || {})[String(f.id)] || [])[j], v = ((r.values || {})[String(f.id)] || [])[j];
          var t = miss[w] ? "no record" : (p == null ? "-" : p + (v == null ? "" : " (" + v + ")"));
          return '<td data-place="' + (miss[w] ? "" : (p == null ? "" : p)) + '">' + esc(t) + "</td>";
        }).join("") + "</tr>";
      }).join("") + "</tbody></table></div></details>";
    return h;
  }

  // ---- Superlatives, Rule and vote, Method (AWARDS_8) -------------------------
  // assets/awards-tabs.js renders the three; it loads on the first open of any
  // of them from the stamped URL on the mount (data-tabs-js), so the Selections
  // cold paint stays awards.js and awards.json. regChip is shared with the cards.
  function regChip(doc, id) {
    if (!id) return "";
    var g = (doc.registry || main.registry || {})[id] || {}, v = g.verdict || "not yet registered";
    return '<a class="aw-reg' + (g.stale ? " is-stale" : "") + '" href="/models/#' + esc(id) + '" title="' +
      esc("Registry row " + id + ": " + v + "." + (g.stale ? " Its eval is " + g.age_days + " days old; stale until it is refreshed." : "")) +
      '">' + esc(v + (g.stale ? ", stale" : "")) + "</a>";
  }
  var tabsChunk = null;
  function tabsLoad() {
    if (!tabsChunk) {
      tabsChunk = new Promise(function (ok, no) {
        var t = document.createElement("script");
        t.onload = ok; t.onerror = no; t.src = root.getAttribute("data-tabs-js"); document.head.appendChild(t);
      }).then(function () { if (!window.EephusAwardsTabs) throw new Error("chunk"); });
      tabsChunk.catch(function () { tabsChunk = null; });
    }
    return tabsChunk;
  }
  function tabsCtx() {
    return { main: main, root: root, state: function () { return state; }, esc: esc, num: num, fmt: fmt, ord: ord, ico: ico,
      stateBox: stateBox, controls: controls, stampLine: stampLine, shareChip: shareChip, hashOf: hashOf, block: block,
      tierOf: tierOf, dateLong: dateLong, docFor: docFor, regChip: regChip, wide: wide, twoCol: twoCol, LAMP: LAMP,
      MAX_LAMPS: MAX_LAMPS, TITLE: TITLE, AWARDS: AWARDS, KEY: KEY };
  }

  // ---- My Ballot (AWARDS_9; AWARDS_PLAN 5.8) ----------------------------------
  // assets/awards-ballot.js and its stylesheet load on the first My Ballot open
  // (their stamped URLs ride the mount's data attributes); the chunk fetches the
  // season's candidate file itself. The hash keeps b only for a shared link.
  var ballotChunk = null;
  function ballotLoad() {
    if (window.EephusAwardsBallot) return null;
    if (ballotChunk) return ballotChunk;
    function tag(el, attr, url) {
      return new Promise(function (ok, no) { el.onload = ok; el.onerror = no; el[attr] = url; document.head.appendChild(el); });
    }
    var css = root.getAttribute("data-ballot-css"), js = root.getAttribute("data-ballot-js"), l = document.createElement("link");
    l.rel = "stylesheet";
    ballotChunk = Promise.all([css ? tag(l, "href", css).catch(function () { return null; }) : null,
      js ? tag(document.createElement("script"), "src", js) : Promise.reject(new Error("chunk"))])
      .then(function () { if (!window.EephusAwardsBallot) throw new Error("chunk"); });
    ballotChunk.catch(function () { ballotChunk = null; });
    return ballotChunk;
  }
  function ballot(panel, s) {
    var ctx = { main: main, state: s, docFor: docFor, stateBox: stateBox, controls: controls, compare: compare,
      esc: esc, ord: ord, surname: surname, live: function () { return state === s; }, gfx: !!GFX, share: shareBallot,
      setHash: function (o) {
        for (var k in o) s[k] = o[k];
        try { history.replaceState(null, "", "#" + hashOf(s)); } catch (e) { /* stays */ }
        lastHash = location.hash;
      } };
    var p = ballotLoad();
    if (!p) { window.EephusAwardsBallot.mount(panel, ctx); return; }
    panel.innerHTML = controls("ballot") + stateBox("loading", "Loading the candidates.");
    p.then(function () { if (state === s) window.EephusAwardsBallot.mount(panel, ctx); }, function () {
      if (state === s) {
        panel.innerHTML = controls("ballot") + stateBox("failed",
          'The candidates could not load. <button type="button" class="aw-retry">Retry</button>');
      }
    });
  }

  // ---- share cards (AWARDS_10; AWARDS_PLAN 5.16) -----------------------------
  // Each card is built from the numbers this page prints; the ballot card from
  // the viewer's own slots only, never the selection. A superlative card
  // (AWARDS_8) carries shareChip("superlative", ' data-sl="<id>"', label).
  var GFX = root.getAttribute("data-gfx-js"), gfxChunk = null;
  var CREDIT = "Data: MLB, FanGraphs, Baseball-Reference via eephus.io";
  function shareChip(mode, attrs, label) {
    return GFX ? '<button type="button" class="aw-share" data-aw-share="' + mode + '"' + attrs + ' aria-label="' +
      esc(label) + '">Share</button>' : "";
  }
  function gfxLoad() {
    if (window.EEPHUS_GFX && window.EEPHUS_GFX.drawAwards) return Promise.resolve();
    if (!gfxChunk) {
      gfxChunk = new Promise(function (ok, no) {
        var t = document.createElement("script");
        t.onload = ok; t.onerror = no; t.src = GFX; document.head.appendChild(t);
      }).then(function () { if (!window.EEPHUS_GFX || !window.EEPHUS_GFX.drawAwards) throw new Error("gfx"); });
      gfxChunk.catch(function () { gfxChunk = null; });
    }
    return gfxChunk;
  }
  function bare(u) { return String(u).replace(/^https?:\/\//, "").replace(/#$/, ""); }
  function shareOpen(mode, title, url, aw, btn) {
    aw.mode = mode;
    gfxLoad().then(function () {
      window.EEPHUS_GFX.open({ kind: "awards", module: "Awards", accentToken: "--accent-lilac", aw: aw,
        format: mode === "slate" ? "wide" : "twitter", icon: mode === "ballot" ? "aw-ballot" : "aw-podium",
        title: title, url: bare(url), filenameBase: "eephus-awards-" + mode });
    }, function () { if (btn) btn.textContent = "Could not load"; });
  }
  function cardUrl(doc, o) {
    var s = { section: "selections", season: doc.season, award: null, lg: null, sl: null, b: null };
    for (var k in o) s[k] = o[k];
    return "eephus.io/awards/#" + hashOf(s);
  }
  function share(el) {
    var m = el.getAttribute("data-aw-share"), doc = docFor(state.season), A = BY_KEY[el.getAttribute("data-award")];
    var LG = String(el.getAttribute("data-lg") || "").toUpperCase(), b, s;
    if (!doc || doc.then) return;
    var st = { stamp: stampText(doc), credit: CREDIT };
    if (m === "podium" && (b = block(doc, A, LG))) {
      var rule = doc.rules[A], pl = places(b.top), d = rule.decimals == null ? 1 : rule.decimals, k = kicker(doc);
      st.sub = rule.label; st.unit = rule.unit;
      st.rows = b.top.slice(0, 3).map(function (r, i) {
        var v = num(r.score_display), t = tierOf(v, rule.family);
        return { p: (pl[i].tie ? "T" : "") + pl[i].n, n: rowName(r), c: r.club_code, t: fmt(v, d), v: v,
          ink: t ? "--vt-" + t : "--text-primary" };
      });
      shareOpen(m, LG + " " + TITLE[A] + ": " + k.charAt(0).toLowerCase() + k.slice(1) + ", " + doc.season,
        cardUrl(doc, { award: KEY[A], lg: LG.toLowerCase() }), st, el);
    } else if (m === "slate") {
      st.rows = AWARDS.map(function (A2) {
        return { a: SHORT[A2], cells: LGS.map(function (L2) {
          var b2 = block(doc, A2, L2), f = b2 ? firsts(b2) : [], tie = f.length > 1;
          return b2 ? { n: f.map(function (r) { return (tie ? "T " : "") + (A2 === "MOY" ? rowName(r) : surname(r.name)); })
            .join(" / "), c: f.map(function (r) { return r.club_code; }).join(" / ") } : { n: "Not published", off: 1 };
        }) };
      });
      shareOpen(m, caption(doc), cardUrl(doc, {}), st, el);
    } else if (m === "superlative") {
      s = (doc.superlatives || []).filter(function (x) { return x.id === el.getAttribute("data-sl"); })[0];
      if (!s || s.blocked_on || !(s.rows || []).length) return;
      st.sub = s.definition; st.stamp = s.frame_label || st.stamp;
      st.pic = s.kind === "index" || s.kind === "signed" ? s.kind : "dumbbell";
      st.dec = (String(s.rows[0].value_display).split(".")[1] || "").length;
      st.rows = s.rows.slice(0, 5).map(function (r) {
        var t = s.kind === "index" ? tierOf(r.value_display, s.ruler || s.family) : "";
        return { r: r.rank, n: r.name, c: r.club_code, t: r.value_display, v: r.value, f: r.from, to: r.to,
          ink: t ? "--vt-" + t : null };
      });
      shareOpen(m, s.title, cardUrl(doc, { section: "superlatives", sl: s.id }), st, el);
    }
  }
  // My Ballot's Save image (the chunk passes [key, [label or null per slot]]
  // for the eight ballots): the active ballot leads, then every other filled one.
  function shareBallot(S, k, list, url1, urlAll, btn) {
    var bs = [];
    list.forEach(function (x) {
      var pts = ((main.ballot_rules || {})[BY_KEY[x[0].slice(3)]] || {}).points || [];
      if (x[0] !== k && !x[1].some(Boolean)) return;
      var b = { h: "My " + S + " " + x[0].slice(0, 2).toUpperCase() + " " + TITLE[BY_KEY[x[0].slice(3)]] + " ballot",
        rows: x[1].map(function (n, i) {
          return { l: ord(i + 1) + " \u00b7 " + pts[i] + " pts", n: n };
        }) };
      if (x[0] === k) bs.unshift(b); else bs.push(b);
    });
    shareOpen("ballot", bs[0].h, url1, { ballots: bs, allTitle: "My " + S + " ballots", allUrl: bare(urlAll) }, btn);
  }

  // ---- boot -----------------------------------------------------------------
  function boot() {
    root.innerHTML = stateBox("loading", "Loading the awards.");
    fetch(SRC, { credentials: "same-origin" })
      .then(function (r) { if (!r.ok) throw new Error("http " + r.status); return r.json(); })
      .then(function (j) {
        if (!valid(j) || !Array.isArray(j.seasons)) throw new Error("schema");
        main = j;
        shell();
        var s = parseHash();
        apply(s, !!(s.award || s.sl));
      })
      .catch(function () {
        root.innerHTML = stateBox("failed", 'The awards could not load. <button type="button" class="aw-boot-retry">Retry</button>');
        var b = root.querySelector(".aw-boot-retry");
        if (b) b.addEventListener("click", boot);
      });
  }
  window.addEventListener("hashchange", onHash);
  window.addEventListener("popstate", onHash);
  var resizeTimer = null;
  window.addEventListener("resize", function () {
    if (!main || !state || state.section === "ballot" || state.section === "vote") return;
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () { if (layout() !== layoutKey) apply(state, false); }, 150);
  });
  boot();
})();
