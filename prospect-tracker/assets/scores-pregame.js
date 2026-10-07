/* Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
 * Unauthorized copying of this file, via any medium is strictly prohibited
 * Proprietary and confidential
 * Written by Noah J. Dengler (@ARKNDJL), 2026 */

/* The pregame context (SCORES_6, plan 4, 9 and 10; owner answer SC-MODEL:
   model only, cards and game). It prints, before first pitch only, the values
   the scores job copied from served files into a Preview card's pre block,
   each by its home page's own rule; it computes no number of its own.

   ONE EXPORT. EephusScoresPregame.card(c, ix, H) is the card's model line,
   panel(c, ix, H) the game view's pregame section with the posted lineups,
   note(root) keeps one copy of the site's betting note beside a day view that
   prints a model number. H is the host's helpers: esc, labelled, player, now
   (the server clock) and gated (the Diamond check). */
(function () {
  "use strict";

  // The Sports Betting board's own rule (assets/betting.js pct): one decimal.
  function pctB(v) { return (v == null || isNaN(v)) ? "-" : (Number(v) * 100).toFixed(1) + "%"; }
  // PROSPX's rule (efvGradeDisplay): eFV to the nearest point.
  function efvG(v) { return (v != null) ? Math.round(Number(v)) : null; }
  // The In-Game Management page's rule (assets/management.js num(v, 0)).
  function num0(v) { return Number(v).toFixed(0); }
  function isNum(x) { return typeof x === "number" && isFinite(x); }

  var ABSENT = {
    starter: "The betting board priced a different listed starter.",
    season: "This page shows the model's number for regular-season games only."
  };
  var SHOWN = "Shown as the Sports Betting board serves it; this page prices nothing.";
  var PRE = { scheduled: 1, pregame: 1, delayed: 1 };

  function code(t) { return (t && (t.code || t.short)) || ""; }
  function last(full) { var s = String(full || "").split(" "); return s.length > 1 ? s.slice(1).join(" ") : s[0]; }
  // Before first pitch only: a Preview state, no inning yet, and the server
  // clock still short of the scheduled start.
  function open(c, H) {
    return !!(c && c.pre && PRE[c.state] && !(c.sit && c.sit.inning) && c.wp == null &&
      H.now() < Date.parse(c.start || ""));
  }
  // The model block, when the page may print it: copied from a board that was
  // not stale, and from the preview slice whenever the Diamond check is gated.
  function model(c, H) {
    var m = open(c, H) ? c.pre.model : null;
    if (!m || m.absent || m.stale_board !== false || !isNum(m.p_home) || !isNum(m.p_away)) return null;
    if (H.gated() && m.board !== "preview") return null;
    return m;
  }
  function note() {
    var t = document.getElementById("scores-betnote");
    return t ? t.innerHTML : "";
  }

  function card(c, ix, H) {
    var m = model(c, H);
    if (!m) return "";
    return H.labelled(ix, "betting_game_prob", "Eephus model: " + H.esc(code(c.away)) + " " + pctB(m.p_away) + ", " +
      H.esc(code(c.home)) + " " + pctB(m.p_home), "p", "sc-row");
  }

  // The posted lineups; eFV rides on a row only inside the labelled block, so
  // without its registry row the list prints with no grade at all.
  function lineups(c, ix, H) {
    var L = (c.pre && c.pre.lineups) || {}, E = (c.pre && c.pre.efv) || {};
    return ["away", "home"].map(function (side) {
      var P = L[side] || [];
      function list(efv) {
        var rows = P.map(function (p) {
          var g = efv ? E[String(p.id)] : null;
          return "<li>" + H.player(p.id, p.name) + ' <span class="sc-dim">' + H.esc(p.pos || "") + "</span>" +
            (isNum(g) ? ' <span class="sc-efv">eFV ' + efvG(g) + "</span>" : "") + "</li>";
        }).join("");
        return rows ? '<ol class="sc-lineup">' + rows + "</ol>" : '<p class="sc-dim">Lineups not posted yet</p>';
      }
      var any = P.some(function (p) { return isNum(E[String(p.id)]); });
      return "<h3>" + H.esc(code(c[side])) + "</h3>" + ((any && H.labelled(ix, "efv_v2", list(true), "div")) || list(false));
    }).join("");
  }

  function panel(c, ix, H) {
    var o = "", p = open(c, H) ? c.pre : {};
    var m = model(c, H), mine = m ? H.labelled(ix, "betting_game_prob", H.esc(code(c.away)) + " " + pctB(m.p_away) +
      "<br>" + H.esc(code(c.home)) + " " + pctB(m.p_home), "p") : "";
    if (mine) {
      o += '<h3>Eephus model</h3>' + mine +
        '<p class="sc-dim">Details: <span class="sc-verdict">' + H.esc(m.sentence) + "</span></p>" +
        '<p class="sc-dim">' + SHOWN + ' <a href="/betting/#section=teams">Sports Betting board</a></p>' + note();
    } else if (p.model && p.model.absent && ABSENT[p.model.absent]) {
      o += '<p class="sc-dim sc-absent">' + ABSENT[p.model.absent] + "</p>";
    }
    var rows = [];
    ["away", "home"].forEach(function (side) {
      var s = p[side] || {}, pr = c[side].probable, k = H.esc(code(c[side]));
      if (pr && isNum(s.sem_plus)) {
        rows.push(H.labelled(ix, "sem_plus", k + " probable " + H.esc(last(pr.name)) + ": SEM+ " + Math.round(s.sem_plus) +
          " (" + s.sem_season + " season)", "p"));
      }
      if (pr && s.two_start) {
        rows.push("<p>" + H.esc(last(pr.name)) + ": two starts in the next seven days" +
          (s.two_start.projected ? ", one projected" : "") + " (Fantasy)</p>");
      }
      if (isNum(s.hook_median_pitches)) {
        rows.push(H.labelled(ix, "mgmt_board_export", k + " starters leave at a median " + num0(s.hook_median_pitches) +
          " pitches this season", "p"));
      }
    });
    if (isNum(p.park_runs)) {
      rows.push("<p>Park runs index " + p.park_runs + " (" + H.esc(code(c.home)) +
        " home park; Baseball Savant, 3 seasons; 100 is neutral)</p>");
    }
    if (p.dfs) {
      rows.push("<p>DFS: " + ["away", "home"].map(function (s) {
        var k = code(c[s]);
        return '<a href="/fantasy/#m=dfs&amp;team=' + encodeURIComponent(k) + '">' + H.esc(k) + " players</a>";
      }).join(", ") + "</p>");
    }
    rows = rows.filter(Boolean);
    if (rows.length) o += '<div class="sc-pre">' + rows.join("") + "</div>";
    return '<div class="sc-pregame">' + o + "</div>" + lineups(c, ix, H);
  }

  // One copy of the betting note under a day view whose cards print a model number.
  function dayNote(root) {
    var wrap = root.querySelector(".sc-grid-wrap");
    if (!wrap) return;
    var has = !!wrap.querySelector('.sc-grid [data-model-id="betting_game_prob"]');
    var el = wrap.querySelector(".sc-betnote");
    if (has && !el) wrap.insertAdjacentHTML("beforeend", '<div class="sc-betnote">' + note() + "</div>");
    else if (!has && el) el.parentNode.removeChild(el);
  }

  window.EephusScoresPregame = { card: card, panel: panel, note: dayNote, open: open, pctB: pctB, efvG: efvG,
    num0: num0, ABSENT: ABSENT, SHOWN: SHOWN };
})();
