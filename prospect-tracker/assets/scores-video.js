/* Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
 * Unauthorized copying of this file, via any medium is strictly prohibited
 * Proprietary and confidential
 * Written by Noah J. Dengler (@ARKNDJL), 2026 */

/* /scores/ video, the lazy chunk (SCORES_4a, plan 6). assets/scores.js loads
   it on the first game-view open and calls mount() after each paint; it fills
   the empty .sc-v slots the game view leaves (Biggest plays, the Plays tab,
   the stars, the Video panel) from the game file's clip objects.

   SC-VIDEO (a), MLB's own embed player. Before a click a slot holds a poster
   button (a lazy MLB poster, a play disc, the duration) and "Video: MLB"; no
   frame exists and nothing is requested from the frame host. A click, Enter
   or Space replaces the button in place with a figure holding one frame of
   the clip's embed URL, "Video: MLB" and a "Close video" button. Opening a
   second clip removes the open frame (a cross-origin player cannot be paused
   from outside); Close and Escape remove it and return focus to the button.
   No autoplay parameter is added: the viewer presses play in MLB's player.

   The switch: index.json rules.video.embed false renders every clip as its
   link to MLB.com and no frame can be created. A poll never detaches an open
   frame: scores.js asks isOpen() first and hands the new game file to held(),
   which offers "Biggest plays changed. Show the new list" when the order
   moved. */
(function () {
  "use strict";

  var FRAME = /^https:\/\/streamable\.com\/m\/[a-z0-9-]+$/;
  var PAGE = /^https:\/\/www\.mlb\.com\/video\/[a-z0-9-]+$/;
  var POSTER = /^https:\/\/img\.mlbstatic\.com\/mlb-images\/image\/upload\/[^?#\s"'<>]+$/;
  var GAMEDAY = /^https:\/\/www\.mlb\.com\/gameday\/\d+$/;
  // MLB's own recap articles give their story-player frame this list; the
  // hand check of 2026-10-07 played a clip through it in installed Chrome.
  var SANDBOX = "allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox allow-forms " +
    "allow-modals allow-pointer-lock allow-top-navigation-by-user-activation";
  var CREDIT = '<p class="sc-vcredit">Video: MLB</p>';

  var S = { open: null, bound: null, repaint: null };

  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function isNum(x) { return typeof x === "number" && isFinite(x); }
  function mmss(sec) {
    if (!isNum(sec)) return "";
    var m = Math.floor(sec / 60), s = sec % 60;
    return m + ":" + (s < 10 ? "0" : "") + s;
  }
  function spoken(sec) {
    if (!isNum(sec)) return "";
    var m = Math.floor(sec / 60), s = sec % 60, out = [];
    if (m) out.push(m + (m === 1 ? " minute" : " minutes"));
    if (s || !m) out.push(s + (s === 1 ? " second" : " seconds"));
    return out.join(" ");
  }
  function ordinal(n) {
    var s = ["th", "st", "nd", "rd"], v = n % 100;
    return n + (s[(v - 20) % 10] || s[v] || s[0]);
  }
  function where(row) {
    return row && row.inning ? (row.half === "bottom" ? "bottom " : "top ") + ordinal(row.inning) : "";
  }
  function firstSentence(t) { return String(t || "").split(". ")[0].replace(/\.$/, ""); }
  function clipOf(g, id) { return id && g && g.clips && g.clips[id] ? g.clips[id] : null; }

  // ------------------------------------------------------------ markup
  function mlbLink(c, text) {
    if (!c || !PAGE.test(c.page || "")) return "";
    return '<a class="sc-vlink" href="' + esc(c.page) + '" target="_blank" rel="noopener noreferrer">' + esc(text) +
      '<span class="sr-only"> (opens MLB.com)</span></a>';
  }
  function playable(c, on) { return !!(on && c && FRAME.test(c.embed || "")); }
  function attrs(c, label, what) {
    return ' type="button" data-clip="' + esc(c.id) + '" data-what="' + esc(what) + '" aria-label="' +
      esc("Play video, " + spoken(c.dur_s) + ": " + label) + '"';
  }
  function posterBtn(c, label, what) {
    var p = c.poster || {};
    if (!POSTER.test(p.w480 || "")) return smallBtn(c, label, what, "Play video") + CREDIT;
    var set = esc(p.w480) + " 480w" + (POSTER.test(p.w960 || "") ? ", " + esc(p.w960) + " 960w" : "");
    return '<button class="sc-clip"' + attrs(c, label, what) + '><img loading="lazy" decoding="async" width="480" height="270" alt="" src="' +
      esc(p.w480) + '" srcset="' + set + '" sizes="(max-width: 520px) 92vw, 480px">' +
      '<span class="sc-disc" aria-hidden="true"></span><span class="sc-dur" aria-hidden="true">' + esc(mmss(c.dur_s)) + "</span></button>" + CREDIT;
  }
  function smallBtn(c, label, what, text) {
    return '<button class="sc-clip sc-clip-sm"' + attrs(c, label, what) + '><span class="sc-disc" aria-hidden="true"></span>' +
      esc(text + (isNum(c.dur_s) ? " " + mmss(c.dur_s) : "")) + "</button>";
  }
  function noClip(g, b) {
    var msg = b && b.clip_state === "pending" ? "No MLB clip for this play yet" : "No MLB clip for this play";
    var gd = g.links && GAMEDAY.test(g.links.gameday || "") ? ' <a class="sc-vlink" href="' + esc(g.links.gameday) +
      '" target="_blank" rel="noopener noreferrer">Gameday on MLB.com<span class="sr-only"> (opens MLB.com)</span></a>' : "";
    return '<p class="sc-dim sc-vnone">' + msg + "." + gd + "</p>";
  }
  function bigSlot(g, ab, on) {
    var b = null, rows = g.plays_big || [];
    for (var i = 0; i < rows.length; i++) if (rows[i].ab === ab) b = rows[i];
    if (!b) return "";
    var c = clipOf(g, b.clip), label = firstSentence(b.text) + ", " + where(b);
    if (!c) return noClip(g, b);
    return playable(c, on) ? posterBtn(c, label, b.text + ", " + where(b)) : mlbLink(c, "Watch on MLB.com");
  }
  function paSlot(g, ab, on) {
    var p = null, rows = g.plays || [], out = [];
    for (var i = 0; i < rows.length; i++) if (rows[i].ab === ab) p = rows[i];
    if (!p) return "";
    var c = clipOf(g, p.clip);
    if (c) out.push(playable(c, on) ? smallBtn(c, firstSentence(p.text) + ", " + where(p), p.text + ", " + where(p), "Play video")
      : mlbLink(c, "Watch on MLB.com"));
    (p.event_clips || []).forEach(function (e) {
      var ec = clipOf(g, e.clip), word = String(e.label || "").split(",")[0];
      if (ec) out.push(playable(ec, on) ? smallBtn(ec, e.label, e.label, word + " video") : mlbLink(ec, word + " on MLB.com"));
    });
    return out.join(" ");
  }
  function starSlot(g, id, on) {
    var s = null, rows = g.stars || [];
    for (var i = 0; i < rows.length; i++) if (String(rows[i].id) === String(id)) s = rows[i];
    var c = s && clipOf(g, s.clip);
    return playable(c, on) ? smallBtn(c, s.name, s.name, "Play video") : "";
  }
  function gameSlot(g, on) {
    var recap = null, cond = null;
    for (var k in (g.clips || {})) {
      if (g.clips[k].kind === "recap") recap = g.clips[k];
      else if (g.clips[k].kind === "condensed") cond = g.clips[k];
    }
    if (!recap && !cond) return "";
    var o = "<h3>Video</h3>";
    if (recap) o += playable(recap, on) ? posterBtn(recap, "game recap", "Game recap") : "<p>" + mlbLink(recap, "Recap on MLB.com") + "</p>";
    if (cond) o += "<p>" + (playable(cond, on) ? smallBtn(cond, "condensed game", "Condensed game", "Condensed game") : mlbLink(cond, "Condensed game on MLB.com")) + "</p>";
    return o;
  }
  function slotHTML(el, g, on) {
    var m = el.getAttribute("data-m");
    if (m === "big") return bigSlot(g, +el.getAttribute("data-k"), on);
    if (m === "pa") return paSlot(g, +el.getAttribute("data-k"), on);
    if (m === "star") return starSlot(g, el.getAttribute("data-k"), on);
    if (m === "game") return gameSlot(g, on);
    return "";
  }

  // ------------------------------------------------------------ the player
  function close(focus) {
    var o = S.open;
    S.open = null;
    if (!o) return;
    if (o.fig.parentNode) o.fig.parentNode.replaceChild(o.btn, o.fig);
    if (o.credit) o.credit.hidden = false;
    if (focus) o.btn.focus();
  }
  function activate(btn, g) {
    var c = clipOf(g, btn.getAttribute("data-clip"));
    if (!c || !FRAME.test(c.embed || "") || !S.on) return;
    close(false);
    var fig = document.createElement("figure");
    fig.className = "sc-vfig";
    var box = document.createElement("div");
    box.className = "sc-vframe";
    var fr = document.createElement("iframe");
    fr.setAttribute("src", c.embed);
    fr.setAttribute("title", "MLB video: " + (btn.getAttribute("data-what") || ""));
    fr.setAttribute("allow", "fullscreen; picture-in-picture");
    fr.setAttribute("allowfullscreen", "");
    fr.setAttribute("referrerpolicy", "strict-origin-when-cross-origin");
    fr.setAttribute("sandbox", SANDBOX);
    box.appendChild(fr);
    var cap = document.createElement("figcaption");
    cap.className = "sc-vcredit";
    cap.textContent = "Video: MLB";
    var x = document.createElement("button");
    x.type = "button";
    x.className = "sc-btn sc-vclose";
    x.textContent = "Close video";
    fig.appendChild(box); fig.appendChild(cap); fig.appendChild(x);
    btn.parentNode.replaceChild(fig, btn);
    // the figure carries its own credit; the poster's line under it hides
    var credit = fig.nextElementSibling && fig.nextElementSibling.classList.contains("sc-vcredit") ? fig.nextElementSibling : null;
    if (credit) credit.hidden = true;
    S.open = { fig: fig, btn: btn, credit: credit };
    x.focus();
  }
  function bind(root) {
    if (S.bound === root) return;
    S.bound = root;
    root.addEventListener("click", function (ev) {
      var t = ev.target.closest ? ev.target.closest(".sc-clip, .sc-vclose, .sc-vnew") : null;
      if (!t) return;
      if (t.classList.contains("sc-vclose")) close(true);
      else if (t.classList.contains("sc-vnew")) { close(false); if (S.repaint) S.repaint(); }
      else activate(t, S.g);
    });
    document.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape" && S.open) { ev.preventDefault(); close(true); }
    });
  }

  // ------------------------------------------------------------ the api
  // mount(root, g, ix, focusAb): fill the empty slots of the painted view.
  function mount(root, g, ix, focusAb) {
    var v = ix && ix.rules && ix.rules.video;
    S.on = !!(v && v.embed === true);
    S.g = g;
    bind(root);
    Array.prototype.forEach.call(root.querySelectorAll(".sc-v:not([data-done])"), function (el) {
      el.setAttribute("data-done", "1");
      el.innerHTML = slotHTML(el, g, S.on);
    });
    if (focusAb != null) {
      var b = root.querySelector('.sc-v[data-k="' + focusAb + '"] .sc-clip');
      var a = document.activeElement;
      if (b && (!a || a === document.body || (a.matches && a.matches(".sc-game-h, [data-focus]")))) b.focus();
    }
  }
  function isOpen(root) { return !!(S.open && root.contains(S.open.fig)); }
  // held(root, g, repaint): a poll arrived while a frame is open. Nothing is
  // re-rendered; when Biggest plays changed order a notice offers the list.
  function held(root, g, repaint) {
    S.repaint = repaint;
    var list = root.querySelector(".sc-bigs");
    if (!list) return;
    var shown = Array.prototype.map.call(list.querySelectorAll(".sc-big"), function (li) { return li.getAttribute("data-ab"); });
    var now = (g.plays_big || []).map(function (b) { return String(b.ab); });
    if (shown.join() === now.join() || root.querySelector(".sc-vnew")) return;
    var n = document.createElement("button");
    n.type = "button";
    n.className = "sc-btn sc-vnew";
    n.textContent = "Biggest plays changed. Show the new list";
    list.parentNode.insertBefore(n, list);
  }

  window.EephusScoresVideo = { mount: mount, isOpen: isOpen, held: held, close: close };
})();
