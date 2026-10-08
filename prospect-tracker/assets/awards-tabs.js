/* =============================================================================
   eephus.io - /awards/ Superlatives, Rule and vote and Method (AWARDS_8;
   AWARDS_PLAN 5.5 to 5.7 and 5.15), the chunk assets/awards.js loads on the
   first open of any of the three (its stamped URL rides the mount's
   data-tabs-js). Every number and label is the payload's; the client computes
   no score. Pictures are whole-pixel rect runs in site.css tokens; no motion.
   ========================================================================== */
(function () {
  "use strict";
  var cx, main, root, T, esc, num, fmt, ord, ico, stateBox, controls, stampLine, shareChip, hashOf, block, tierOf,
    dateLong, docFor, regChip, wide, twoCol, LAMP, MAX_LAMPS, TITLE, AWARDS, KEY;
  function use(c) {
    cx = c; main = c.main; root = c.root; T = window.EephusTiers || null; esc = c.esc; num = c.num; fmt = c.fmt; ord = c.ord;
    ico = c.ico; stateBox = c.stateBox; controls = c.controls; stampLine = c.stampLine; shareChip = c.shareChip; hashOf = c.hashOf;
    block = c.block; tierOf = c.tierOf; dateLong = c.dateLong; docFor = c.docFor; regChip = c.regChip; wide = c.wide;
    twoCol = c.twoCol; LAMP = c.LAMP; MAX_LAMPS = c.MAX_LAMPS; TITLE = c.TITLE; AWARDS = c.AWARDS; KEY = c.KEY;
  }

  // ---- Superlatives (AWARDS_8; AWARDS_PLAN 5.5) -------------------------------
  // The required six, then "More from the site's numbers". A row's picture is an
  // aria-hidden SVG of whole-pixel rects; the row's own text is its twin.
  var SL_REQ = ["prospect_above", "prospect_below", "proj_above", "proj_below", "next_rise", "next_drop"];
  function svgOf(w, h, s) {
    return '<svg class="aw-lamps" aria-hidden="true" focusable="false" width="' + w + '" height="' + h + '" viewBox="0 0 ' + w +
      " " + h + '" shape-rendering="crispEdges">' + s + "</svg>";
  }
  function nice(lo, hi) {
    if (!(hi > lo)) { lo -= 1; hi += 1; }
    var raw = (hi - lo) / 5, p = Math.pow(10, Math.floor(Math.log(raw) / Math.LN10)), f = raw / p;
    var st = (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * p;
    return { lo: +(Math.floor(lo / st) * st).toFixed(6), hi: +(Math.ceil(hi / st) * st).toFixed(6), st: st };
  }
  function slW() {
    var c = twoCol() ? 3 : wide() ? 2 : 1, w = root.clientWidth || 358;
    return Math.max(120, Math.min(300, Math.floor((w - (c - 1) * 16) / c) - 58));
  }
  // {attrs, svg: [per row], axis, tip}: the dumbbell on a shared 1-2-5 axis, or a
  // lamp bar from the anchor (0 signed, 100 index) whose unit widens 1-2-5 past 60 lamps.
  function slPics(s, rows, W) {
    var P = LAMP.s.p, H = LAMP.s.h, o = { attrs: "", svg: [], axis: "", tip: "" };
    if (s.kind === "dumbbell") {
      var lo = Infinity, hi = -Infinity;
      rows.forEach(function (r) {
        [num(r.from), num(r.to)].forEach(function (v) { if (v != null) { lo = Math.min(lo, v); hi = Math.max(hi, v); } });
      });
      var n = nice(lo, hi), x = function (v) { return Math.round((v - n.lo) / (n.hi - n.lo) * (W - 8)); };
      var dec = n.st >= 1 ? 0 : Math.ceil(-Math.log(n.st) / Math.LN10 - 1e-9), ax = "", t;
      o.attrs = ' data-lo="' + n.lo + '" data-hi="' + n.hi + '" data-w="' + W + '"';
      o.svg = rows.map(function (r) {
        var a = num(r.from), b = num(r.to);
        if (a == null || b == null) return "";
        var xa = x(a), xb = x(b);
        return svgOf(W, 12, '<rect class="aw-f-' + (b >= a ? "up" : "down") + '" x="' + (Math.min(xa, xb) + 4) + '" y="5" width="' +
          Math.abs(xb - xa) + '" height="2"/><rect class="aw-db-a" data-x="' + xa + '" x="' + (xa + 0.5) +
          '" y="2.5" width="7" height="7"/><rect class="aw-f-ink aw-db-b" data-x="' + xb + '" x="' + xb + '" y="2" width="8" height="8"/>');
      });
      for (t = n.lo; t <= n.hi + 1e-9; t = +(t + n.st).toFixed(6)) ax += '<rect x="' + (x(t) + 4) + '" y="0" width="1" height="4"/>';
      [[n.lo, "start"], [n.hi, "end"]].concat(x(0) - x(n.lo) > 24 && x(n.hi) - x(0) > 24 ? [[0, "middle"]] : [])
        .forEach(function (e) { ax += '<text x="' + (x(e[0]) + 4) + '" y="14" text-anchor="' + e[1] + '">' + e[0].toFixed(dec) + "</text>"; });
      o.axis = '<div class="aw-ticks"><svg aria-hidden="true" focusable="false" width="' + W + '" height="16" viewBox="0 0 ' + W +
        ' 16" shape-rendering="crispEdges">' + ax + "</svg></div>";
      return o;
    }
    var A0 = s.kind === "index" ? 100 : 0, u = num(s.lamp_unit) || 1, m = 0, k = 0, neg = 0, pos = 0;
    rows.forEach(function (r) { m = Math.max(m, Math.abs((num(r.value_display) || 0) - A0)); });
    while (m / u > MAX_LAMPS && k < 40) u = +(u * [2, 2.5, 2][k++ % 3]).toPrecision(6);
    var lit = rows.map(function (r, i) {
      var v = num(r.value_display), n2 = v == null ? 0 : Math.round(Math.abs(v - A0) / u);
      if (v != null && v < A0) neg = Math.max(neg, n2); else pos = Math.max(pos, n2);
      return n2;
    });
    var zero = (neg + 1) * P, w = zero + Math.max(pos, 1) * P;
    o.attrs = ' data-unit="' + u + '" data-pitch="' + P + '"';
    o.tip = "One lamp is " + u + (A0 ? " points from 100" : s.unit ? " " + s.unit : "") + ". The number beside the row is exact.";
    o.svg = rows.map(function (r, i) {
      var v = num(r.value_display), n2 = lit[i], f = v != null && v < A0 ? "down" : A0 ? (tierOf(v, s.ruler || s.family) || "ink") : "up";
      return svgOf(w, H, (n2 ? '<rect class="aw-lit" data-lit="' + n2 + '" data-fill="' + f + '" fill="url(#aw-lp-s-' + f + ')" x="' +
        (f === "down" ? zero - n2 * P : zero) + '" y="0" width="' + n2 * P + '" height="' + H + '"/>' : "") +
        '<rect class="aw-zero" x="' + (zero - 1) + '" y="0" width="1" height="' + H + '"/>');
    });
    return o;
  }
  function slRow(s, r, pic) {
    var v = num(r.value_display), d = v == null ? 0 : v - (s.kind === "index" ? 100 : 0), L = r.links || {};
    var href = L.overview || L.management, val = r.value_display == null ? "" : String(r.value_display);
    return '<li class="aw-row" data-id="' + esc(r.id) + '" data-value="' + esc(val) + '"><span class="aw-place" aria-hidden="true">' +
      r.rank + '</span><div class="aw-who"><span class="visually-hidden">' + ord(r.rank) + ", </span>" +
      (href ? '<a class="aw-name" href="' + esc(href) + '">' + esc(r.name) + "</a>" : '<span class="aw-name">' + esc(r.name) + "</span>") +
      (L.prospx ? ' <a class="aw-px" href="' + esc(L.prospx) + '" aria-label="' + esc(r.name + " on PROSPX") + '">PROSPX</a>' : "") +
      '<span class="aw-sub">' + esc([typeof r.id === "string" ? "" : r.club_code, r.context].filter(Boolean).join(" · ")) + "</span>" +
      ((r.flags || []).indexOf("graded_at_floor") >= 0 ? '<span class="aw-tag">graded at the floor</span>' : "") +
      '</div><span class="aw-val">' + (d ? '<span class="aw-' + (d > 0 ? "up" : "dn") + '">' + ico(d > 0 ? "ev-up" : "ev-down", 12) +
      "</span>" : "") + '<span class="aw-num">' + esc(val) + "</span>" + (s.unit ? ' <span class="aw-unit">' + esc(s.unit) + "</span>" : "") +
      "</span>" + pic + "</li>";
  }
  function slCard(doc, s) {
    var id = s.id, rows = s.blocked_on ? [] : (s.rows || []);
    var h = '<article class="aw-card" id="aw-sl-' + id + '" aria-labelledby="aw-slh-' + id + '"><header class="aw-card-h"><h3 id="aw-slh-' +
      id + '">' + esc(s.title) + "</h3>" + regChip(doc, s.registry) +
      (rows.length ? shareChip("superlative", ' data-sl="' + id + '"', "Share " + s.title + " as an image") : "") + "</header>";
    if (s.definition) h += '<p class="aw-rule">' + esc(s.definition) + "</p>";
    if (s.frame_label) h += '<p class="aw-frame">' + esc(s.frame_label) + "</p>";
    if (!rows.length) {
      h += stateBox("unmeasured", esc(s.blocked_on || "No player in this view clears the floor."));
    } else {
      var p = slPics(s, rows, slW());
      h += '<ol class="aw-sll" id="aw-sll-' + id + '" data-kind="' + esc(s.kind) + '"' + p.attrs + (p.tip ? ' title="' + esc(p.tip) + '"' : "") +
        ">" + rows.map(function (r, i) { return slRow(s, r, p.svg[i]); }).join("") + "</ol>" + p.axis;
      if (s.axis_label) h += '<p class="aw-frame">' + esc(s.axis_label) + "</p>";
      if (s.caption) h += '<p class="aw-note">' + esc(s.caption) + "</p>";
      if (rows.length > 3) {
        h += '<button type="button" class="aw-share aw-more" aria-expanded="false" aria-controls="aw-sll-' + id + '">Show ' + rows.length + "</button>";
      }
    }
    return h + '<p class="aw-foot"><a class="aw-chip" href="#' + esc(hashOf({ section: "method", season: doc.season, sl: id })) +
      '">How measured</a>' + (rows.length ? '<button type="button" class="aw-share" data-aw-csv="' + id + '">CSV</button>' : "") + "</p></article>";
  }
  function superlatives(doc) {
    var a = "", b = "";
    (doc.superlatives || []).forEach(function (s) { if (SL_REQ.indexOf(s.id) >= 0) a += slCard(doc, s); else b += slCard(doc, s); });
    return controls("superlatives") + stampLine(doc) + (a || b ? '<div class="aw-slg">' + a +
      '</div><h2 class="aw-gh">More from the site&#39;s numbers</h2><div class="aw-slg">' + b + "</div>"
      : stateBox("unmeasured", "No superlatives are on file for " + doc.season + "."));
  }
  function csv(id) {
    var doc = docFor(cx.state().season), s = doc && !doc.then && (doc.superlatives || []).filter(function (x) { return x.id === id; })[0];
    if (!s || !window.EephusCSV) return;
    var db = s.kind === "dumbbell";
    window.EephusCSV.downloadModel({ headers: ["Rank", "Name", "Club", s.unit || "Value"].concat(db ? ["From", "To"] : [], ["Context"]),
      rows: (s.rows || []).map(function (r) {
        return [r.rank, r.name, r.club_code, r.value_display].concat(db ? [fmt(r.from, 3), fmt(r.to, 3)] : [], [r.context || ""]);
      }) }, "awards-" + id.replace(/_/g, "-") + "-" + doc.season);
  }

  // ---- Rule and vote (AWARDS_8; AWARDS_PLAN 5.6) ------------------------------
  // The writers' 1st beside the rule's, season by season, newest first: plain
  // cells with no colour, no mark and no count of matches.
  function vote() {
    var rows = main.vote_table || [], by = {}, list = [], fin = false, fz = (main.stamp || {}).frozen_at;
    rows.forEach(function (r) {
      if (!by[r.season]) { by[r.season] = []; list.push(r.season); }
      by[r.season].push(r);
      if (r.writers_finish_of_rule_first != null) fin = true;
    });
    list.sort(function (a, b) { return b - a; });
    var tag = '<span class="aw-tag">computed after the fact</span>';
    var h = controls("vote") + '<p class="aw-rule">The writers vote on their own reading of value; the rule ranks one metric family. ' +
      "This table records both lists, season by season. It does not score either one: a different 1st place is a different answer " +
      "to a different question.</p><p class=\"aw-note\">A season tagged " + tag + " was computed by the same rule from the same files; " +
      "the site did not publish a selection that season.</p>";
    if (!by[main.season]) {
      h += '<p class="aw-note">' + esc("The writers' results for " + main.season + " are not on file yet." + (fz ? " The selection was frozen on " +
        dateLong(fz) + ((main.freeze || {}).after_finalists ? ", after the writers' finalists were named." : ", before the writers' results.") : "")) + "</p>";
    }
    if (!list.length) return h + stateBox("unmeasured", "The writers' results are not on file.");
    var cols = ["Award", "League", "Rule's 1st", "Writers' 1st"].concat(fin ? ["Rule's 1st in the vote"] : [], ["Writers' 1st on the rule"]);
    list.forEach(function (S) {
      var rs = by[S], late = rs.every(function (r) { return r.computed_after_the_fact; });
      h += '<div class="aw-scroll"><table class="aw-wt aw-vt" id="aw-v-' + S + '"><caption>' + S + (rs[0].note ? ", " + esc(rs[0].note) : "") +
        (late ? " " + tag : "") + "</caption><thead><tr>" + cols.map(function (c) { return '<th scope="col">' + esc(c) + "</th>"; }).join("") +
        "</tr></thead><tbody>" + rs.map(function (r) {
          var w = r.writers_first, p = r.rule_place_of_writers_first, f = r.writers_finish_of_rule_first;
          var c = [r.league, (r.rule_first || {}).name || "-", w ? w.name + (typeof w.id === "string" ? " (" + w.id.slice(1).toUpperCase() + ")" : "") : "-"]
            .concat(fin ? [f == null ? "-" : ord(f)] : [], [!w ? "-" : p ? ord(p) : "outside the rule's ballot"]);
          return '<tr><th scope="row">' + esc(TITLE[r.award] || r.award) + (!late && r.computed_after_the_fact ? " " + tag : "") + "</th>" +
            c.map(function (x) { return "<td>" + esc(x) + "</td>"; }).join("") + "</tr>";
        }).join("") + "</tbody></table></div>";
    });
    return h;
  }

  // ---- Method (AWARDS_8; AWARDS_PLAN 5.7 and 5.15) ----------------------------
  // Every rule, input, stamp, credit and claim on the page, all from the payload.
  function dl(pairs) {
    return '<dl class="aw-dl">' + pairs.filter(function (p) { return p[1] != null && p[1] !== ""; }).map(function (p) {
      return "<dt>" + p[0] + "</dt><dd>" + esc(p[1]) + "</dd>";
    }).join("") + "</dl>";
  }
  function gl(label, slug) { return '<span class="g-term" data-gl="' + slug + '">' + label + "</span>"; }
  function mCard(doc, id, title, reg, pairs, extra) {
    return '<article class="aw-card" id="aw-m-' + id + '"><header class="aw-card-h"><h3>' + esc(title) + "</h3>" + regChip(doc, reg) +
      "</header>" + dl(pairs) + (extra || "") + "</article>";
  }
  function method(doc) {
    var h = controls("method") + stampLine(doc) + '<p class="aw-rule">The eephus selection is the site&#39;s order for each award under a rule ' +
      "published on this page: one metric family, one frame, one playing-time floor and one tie rule per award. It answers a value " +
      "question with the site&#39;s own numbers; it does not try to guess how the writers vote, and no part of this page is a forecast.</p>" +
      '<h2 class="aw-gh">Awards</h2><div class="aw-slg">';
    AWARDS.forEach(function (A) {
      var r = doc.rules[A] || {}, n = (doc.ballot_rules || main.ballot_rules || {})[A] || {};
      var b = block(doc, A, "AL") || block(doc, A, "NL"), ms = b && b.compare ? b.compare.metrics || [] : [];
      h += mCard(doc, KEY[A], r.name || TITLE[A], r.registry, [["Rule", r.label], ["Floor", r.floor_label], ["Ties", r.tie_label],
        ["Two-way", r.two_way_label], ["Eligibility", r.eligibility_label],
        ["Ballot", n.n ? n.n + " places; points " + (n.points || []).join(", ") : null], ["Not published", r.blocked_on]],
        ms.length ? '<ul class="aw-ml">' + ms.map(function (m) {
          return "<li>" + esc(m.label + ": " + (m.producer || "")) + (m.registry ? " " + regChip(doc, m.registry) : "") + "</li>";
        }).join("") + "</ul>" : "");
    });
    h += '</div><h2 class="aw-gh">Superlatives</h2><div class="aw-slg">';
    (doc.superlatives || []).forEach(function (s) {
      var st = s.stamp || {};
      h += mCard(doc, s.id, s.title, s.registry, [["Measure", s.definition], ["Floor", s.floor_label], ["Frame", s.frame_label],
        ["Picture", s.axis_label], ["Note", s.caption], ["Input", s.producer],
        ["Pool", s.blocked_on || s.n_pool == null ? null : s.n_pool + " clear the floor"],
        ["Projections build", st.generated_at ? [dateLong(st.generated_at), st.label_shape, st.train_hash && "train hash " + st.train_hash]
          .filter(Boolean).join(", ") : null], ["Not published", s.blocked_on]]);
    });
    h += "</div>";
    var sm = doc === main ? main.stamps || {} : {}, ks = Object.keys(sm);
    if (ks.length) {
      h += '<details class="aw-d"><summary>Input files (' + ks.length + ')</summary><div class="aw-scroll"><table class="aw-wt">' +
        "<caption>Input files read by this build</caption><thead><tr><th scope=\"col\">File</th><th scope=\"col\">Generated</th>" +
        '<th scope="col">As of</th><th scope="col">Hash</th></tr></thead><tbody>' + ks.map(function (f) {
          var x = sm[f] || {};
          return '<tr><th scope="row">' + esc(f) + "</th><td>" + [x.generated_at, x.as_of, x.sha1_12].map(function (v) {
            return esc(v || "-");
          }).join("</td><td>") + "</td></tr>";
        }).join("") + "</tbody></table></div></details>";
    }
    h += '<h2 class="aw-gh">Credits</h2><ul class="aw-ml aw-credits">' + (doc.credits || []).map(function (c) {
      return "<li>" + esc(c).replace(/(https?:\/\/[^\s<]+)/g, '<a href="$1" rel="noopener">$1</a>') + "</li>";
    }).join("") + '</ul><h2 class="aw-gh">What this page does not claim</h2><ol class="aw-ml aw-claims">' +
      (doc.what_this_page_does_not_claim || []).map(function (c) { return "<li>" + esc(c) + "</li>"; }).join("") +
      '</ol><h2 class="aw-gh">Colours and terms</h2><p class="aw-rule">Colours rank a number against its own metric on the site&#39;s ' +
      gl("value ruler", "value_ruler") + ". Terms: " + [gl("eWAR", "ewar"), gl("HEM+", "hem_plus"), gl("xHEM+", "xhem_plus"),
      gl("SEM+", "sem_plus"), gl("xSEM+", "xsem_plus"), gl("REM+", "rem_plus"), gl("DEM+", "dem_plus"), gl("xwOBA", "xwoba"),
      gl("WPA", "wpa"), gl("Leverage Index", "leverage_index"), gl("realized mWPA", "realized_mwpa")].join(", ") + ".</p>" +
      (T ? '<div class="aw-cmp-key">' + T.keyHTML() + "</div>" : "");
    return h;
  }

  function on(f) { return function (c, a) { use(c); return f(a); }; }
  window.EephusAwardsTabs = { superlatives: on(superlatives), vote: on(vote), method: on(method), csv: on(csv) };
})();
