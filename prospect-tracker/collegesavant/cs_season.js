// CollegeSavant season bar, shared by the hitter and the pitcher app.
//
// Each app header carries one slot ([data-cs-season]) that this file fills
// with two things, both computed from the season file the app loaded:
//   1. the dataset badge: the season, the pool's scope and, for a season
//      older than the one the files were cut in, the word "archive"
//      (for example "2025 · Big Ten · archive" or "2026 · national");
//   2. the season picker: one select listing the seasons the app's files
//      hold, newest first. The choice is kept for the browser session under
//      one key, so Hitters and Pitchers open on the same season when both
//      files hold it; a fresh session opens on the newest season.
// The apps pass their own pool (yearPool) and pool text (poolText), so no
// season, scope or count is written here or in the page markup.
(function () {
  "use strict";

  var KEY = "collegesavant.season";

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  // "Big Ten only" reads as "Big Ten" on the chip; "national" stays.
  function scopeLabel(scope) {
    return scope === "Big Ten only" ? "Big Ten" : (scope || "");
  }

  // A season earlier than the year the files were received is a finished
  // season held as an archive; the received year itself is the live cut.
  function isArchive(year, received) {
    var cut = Number(String(received || "").slice(0, 4));
    return Number.isFinite(cut) && Number(year) < cut;
  }

  function badgeText(year, pool, received) {
    var parts = [String(year)];
    var scope = scopeLabel(pool && pool.scope);
    if (scope) parts.push(scope);
    if (isArchive(year, received)) parts.push("archive");
    return parts.join(" · ");
  }

  function badgeTitle(year, poolLine, received) {
    var cut = String(received || "").slice(0, 4);
    return "The " + year + " pool: " + poolLine + ". "
      + (isArchive(year, received)
        ? "Archive: a finished season, older than the " + cut + " cut the files were received in (" + received + ")."
        : "A cut taken during the " + year + " season (files received " + received + ").");
  }

  // The session's season, when this app's files hold it.
  function recall(years) {
    try {
      var v = Number(window.sessionStorage.getItem(KEY));
      return years.indexOf(v) >= 0 ? v : null;
    } catch (e) {
      return null;
    }
  }

  function remember(year) {
    try { window.sessionStorage.setItem(KEY, String(year)); } catch (e) { /* storage blocked */ }
  }

  // opts: {years, year, pool, poolText(year), received, side, loading, loadingText}
  function html(opts) {
    var year = opts.year;
    var archive = isArchive(year, opts.received);
    var out = '<span class="cs-dataset' + (archive ? " is-archive" : "") + '" data-cs-dataset title="'
      + esc(badgeTitle(year, opts.poolText(year), opts.received)) + '">'
      + esc(badgeText(year, opts.pool, opts.received)) + "</span>";
    if ((opts.years || []).length > 1) {
      out += '<label class="cs-season-pick"><span class="cs-season-lab">Season</span>'
        + '<select class="select-box year-select cs-season-select' + (opts.loading ? " is-loading" : "")
        + '" data-cs-season-select aria-label="Season, shared by Hitters and Pitchers"'
        + (opts.loading ? ' aria-busy="true" title="' + esc(opts.loadingText || "") + '"' : "") + ">"
        + opts.years.map(function (y) {
          return '<option value="' + y + '"' + (y === year ? " selected" : "") + ">"
            + esc(y + " · " + opts.poolText(y)) + "</option>";
        }).join("")
        + "</select></label>";
    }
    return out;
  }

  // Fills the header slot and wires the picker to opts.onPick(year).
  function mount(opts) {
    var slot = document.querySelector("[data-cs-season]");
    if (!slot) return;
    slot.innerHTML = html(opts);
    var sel = slot.querySelector("[data-cs-season-select]");
    if (sel && opts.onPick) {
      sel.addEventListener("change", function (e) {
        remember(Number(e.target.value));
        opts.onPick(Number(e.target.value));
      });
    }
  }

  window.CSSeason = {
    KEY: KEY,
    badgeText: badgeText,
    isArchive: isArchive,
    recall: recall,
    remember: remember,
    html: html,
    mount: mount,
  };
})();
