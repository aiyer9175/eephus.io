/* Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
 * Unauthorized copying of this file, via any medium is strictly prohibited
 * Proprietary and confidential
 * Written by Noah J. Dengler (@ARKNDJL), 2026 */

/* The scores page's About view (SCORES_3 copy; a lazy chunk since SC7-4, so
   the eager scores.js keeps its budget). ONE EXPORT: EephusScoresAbout.html(ix,
   latest, H) returns the view's paragraphs from the scores index and
   latest.json alone; H is the page's helper set (esc, labelled, comma, isNum).
   No fetch, no route and no number of its own. */
(function () {
  "use strict";

  function html(ix, latest, H) {
    var esc = H.esc, labelled = H.labelled, comma = H.comma, isNum = H.isNum;
    var acc = (ix.accuracy && ix.accuracy.mlb_wp) || {}, rules = ix.rules || {}, o = "";
    var p1 = "Win probability is MLB's live model, read from its public feed after every plate appearance.";
    var pv = acc.pregame_values || {}, keys = Object.keys(pv);
    if (keys.length && keys.every(function (k) { return k === "500"; })) {
      p1 += " It starts every game at 50 percent, so it is not a pregame forecast.";
    }
    p1 += " Inside a game it moves with the situation and, by this site's own check, also carries some team strength; it can trail the score by one play.";
    if (isNum(acc.feed_brier) && isNum(acc.base_rate_brier) && isNum(acc.n_plays) && (acc.seasons || []).length) {
      p1 += " In this site's own check over " + comma(acc.n_plays) + " regular-season plays from the " +
        (acc.seasons.length > 1 ? acc.seasons.slice(0, -1).join(", ") + " and " + acc.seasons[acc.seasons.length - 1] + " seasons" : acc.seasons[0] + " season") +
        " (no postseason game is in the check), it scored a Brier of " + acc.feed_brier.toFixed(4) + ", against " + acc.base_rate_brier.toFixed(4) +
        " for a constant base rate (lower is better).";
    }
    p1 += " Where MLB's feed has no number for a plate appearance, the line has a gap.";
    o += labelled(ix, "scores_mlb_wp", esc(p1), "p") || "<p>" + esc(p1) + "</p>";
    var s = rules.stars || {};
    if (s.rule) {
      var p2 = "Stars of the Game is a rule, not an award. Each player is ranked by win probability added, from MLB's live model: hitters by their plate appearances, pitchers by the batters they faced.";
      if (isNum(s.min_outs)) p2 += " A pitcher who records " + s.min_outs + " or more outs without losing win probability is credited instead with his runs prevented against the league rate when that is larger, so a starter's work in a lopsided game still counts.";
      if (s.first_star_winner) p2 += " The first star comes from the winning team, so he can rank below the second star.";
      p2 += " Ties go to the player whose plate appearances carried more leverage. Fielding, and base running inside a plate appearance, are not credited to anyone.";
      o += "<h3>Stars of the Game</h3><p>" + esc(p2) + "</p>";
    }
    var pl = rules.plays || {};
    if (pl.rule) {
      var words = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"];
      o += "<h3>Biggest plays</h3><p>" + esc("The " + (words[pl.n] || pl.n) + " plate appearances that moved MLB's win probability most.") + "</p>";
      var w = (latest.window || {})[latest.today];
      if (w && isNum(w.clips_of) && w.clips_of > 0 && isNum(w.clips_matched)) {
        o += "<p>" + esc("Clips matched today: " + w.clips_matched + " of " + w.clips_of + " biggest plays.") + "</p>";
      }
    }
    o += "<h3>Source</h3><p>Scores, box scores and play data come from MLB's public StatsAPI feed.</p>";
    if (ix.copyright) o += '<p class="sc-dim">' + esc(ix.copyright) + "</p>";
    return o;
  }

  window.EephusScoresAbout = { html: html };
})();
