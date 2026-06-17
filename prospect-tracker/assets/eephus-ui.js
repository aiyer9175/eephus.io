// eephus.io - account + forum UI controller (Parts 1-7).
// Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
//
// Renders the visible account/social layer and talks to the data layer through
// window.EephusAccount. Loads on BOTH surfaces (editorial pages + the PROSPX
// app). Two modes:
// • LIVE - window.EephusAccount.enabled() (a real Supabase project is wired).
// • PREVIEW - no backend configured: a clearly-labeled local-only store so the
//     forum/flair/onboarding are fully viewable & clickable for review. Nothing
//     leaves the browser; switching on a real config takes over automatically.
// Reuses PROSPX primitives (headshots, clean team logos, formatMetric, prospect
// index) through the window.PROSPX shim the app exposes - single source of truth
// for any number/logo a post surfaces.
(function () {
  "use strict";

  var A = window.EephusAccount || null;
  var PX = function () { return window.PROSPX || {}; };
  var LIVE = function () { return !!(A && A.enabled()); };

  // ---- privacy-light analytics (inert without config) -----------------------
  // Mirrors the Supabase pattern: window.EEPHUS_ANALYTICS ships blank in
  // assets/eephus-config.js and is filled at deploy time. When src+domain are
  // set we self-inject the script (Plausible-compatible: data-domain + defer
  // src; GoatCounter works via the same shape with data-goatcounter). Blank
  // config = zero network traffic, zero cookies, no behavior change.
  (function mountAnalytics() {
    var cfg = window.EEPHUS_ANALYTICS;
    if (!cfg || !cfg.src || !cfg.domain) return;
    if (document.querySelector("script[data-eephus-analytics]")) return;
    var s = document.createElement("script");
    s.defer = true;
    s.src = cfg.src;
    s.setAttribute("data-eephus-analytics", "1");
    s.setAttribute("data-domain", cfg.domain);
    if (cfg.goatcounter) s.setAttribute("data-goatcounter", cfg.goatcounter);
    document.head.appendChild(s);
  })();

  // ---- tiny DOM/util helpers ------------------------------------------------
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function escAttr(s) { return esc(s); }
  function frag(html) { var t = document.createElement("template"); t.innerHTML = html; return t.content; }
  function elFromHTML(html) { var t = document.createElement("template"); t.innerHTML = html.trim(); return t.content.firstElementChild; }
  function qs(sel, root) { return (root || document).querySelector(sel); }
  function on(node, ev, sel, fn) {
    node.addEventListener(ev, function (e) {
      var t = e.target.closest(sel);
      if (t && node.contains(t)) fn(e, t);
    });
  }
  function timeAgo(iso) {
    var t = new Date(iso).getTime(); if (isNaN(t)) return "";
    var s = Math.max(1, Math.floor((Date.now() - t) / 1000));
    if (s < 60) return s + "s";
    var m = Math.floor(s / 60); if (m < 60) return m + "m";
    var h = Math.floor(m / 60); if (h < 24) return h + "h";
    var d = Math.floor(h / 24); if (d < 30) return d + "d";
    var mo = Math.floor(d / 30); if (mo < 12) return mo + "mo";
    return Math.floor(mo / 12) + "y";
  }
  function toast(msg, kind) {
    var wrap = qs(".eph-toast-wrap");
    if (!wrap) { wrap = document.createElement("div"); wrap.className = "eph-toast-wrap"; document.body.appendChild(wrap); }
    var t = document.createElement("div");
    t.className = "eph-toast" + (kind ? " " + kind : "");
    t.textContent = msg; wrap.appendChild(t);
    setTimeout(function () { t.style.opacity = "0"; t.style.transition = "opacity .4s"; setTimeout(function () { t.remove(); }, 400); }, 3200);
  }

  // ===========================================================================
  // PREVIEW store (local-only; used when no Supabase backend is configured)
  // ===========================================================================
  var PV = {
    KEY_PROFILE: "eph-preview.profile",
    KEY_COMMENTS: function (scope, key) { return "eph-preview.comments:" + scope + ":" + (key || ""); },
    KEY_VOTES: "eph-preview.votes",
    profile: function () { try { return JSON.parse(localStorage.getItem(this.KEY_PROFILE) || "null"); } catch (e) { return null; } },
    setProfile: function (p) { try { localStorage.setItem(this.KEY_PROFILE, JSON.stringify(p)); } catch (e) {} },
    clearProfile: function () { try { localStorage.removeItem(this.KEY_PROFILE); } catch (e) {} },
    comments: function (scope, key) { try { return JSON.parse(localStorage.getItem(this.KEY_COMMENTS(scope, key)) || "null"); } catch (e) { return null; } },
    saveComments: function (scope, key, list) { try { localStorage.setItem(this.KEY_COMMENTS(scope, key), JSON.stringify(list)); } catch (e) {} },
    votes: function () { try { return JSON.parse(localStorage.getItem(this.KEY_VOTES) || "{}"); } catch (e) { return {}; } },
    setVote: function (cid, v) { var all = this.votes(); if (v === 0) delete all[cid]; else all[cid] = v; try { localStorage.setItem(this.KEY_VOTES, JSON.stringify(all)); } catch (e) {} }
  };

  // Demo authors + a rich seeded thread so the checkpoint shows every feature.
  function seedThread(scope, key, entity) {
    var now = Date.now();
    var iso = function (minsAgo) { return new Date(now - minsAgo * 60000).toISOString(); };
    var authors = {
      scout_mendoza: { username: "scout_mendoza", role: "member", karma: 412, badges: ["beta_tester", "contributor"], fav_team: "LAD", fav_prospect: { name: "Roki Sasaki" } },
      farm_report:   { username: "farm_report", role: "moderator", karma: 980, badges: ["beta_tester"], fav_team: "BAL", fav_prospect: { name: "Samuel Basallo" } },
      pitchlab:      { username: "pitchlab", role: "member", karma: 57, badges: [], fav_team: "NYM", fav_prospect: { name: "Jett Williams" } }
    };
    var nm = (entity && (entity.player_name || entity.name)) || "this prospect";
    if (scope === "article") {
      return [
        {
          id: "seed1", parent_id: null, author: authors.pitchlab, score: 6, created_at: iso(220),
          body_md: "Good piece. The framing around **plate discipline as the leading indicator** matches what the boards have been saying. @scout_mendoza curious if you'd weight it differently for arms?"
        },
        {
          id: "seed2", parent_id: "seed1", author: authors.scout_mendoza, score: 3, created_at: iso(120),
          body_md: "Fair - for pitchers I lean on the `command` proxy first, but the through-line holds. The [methodology](/glossary/#view=methodology) backs it up."
        }
      ];
    }
    if (scope === "farm") {
      return [
        {
          id: "seed1", parent_id: null, author: authors.farm_report, score: 11, created_at: iso(520),
          body_md: "System take: the upper levels finally have **real depth**, not just a top-heavy big-three.\n\n- two ready-now bats at AAA\n- a sleeper arm jumping a level\n- the [methodology page](/glossary/#view=methodology) likes the pipeline's calibration\n\n> Top-5 farm if the AA arms hold velo."
        },
        {
          id: "seed2", parent_id: "seed1", author: authors.scout_mendoza, score: 4, created_at: iso(300),
          body_md: "Agreed @farm_report - and the IFA class adds a second wave behind it. The `consensus FV` curve for the org is trending up."
        }
      ];
    }
    return [
      {
        id: "seed1", parent_id: null, author: authors.scout_mendoza, score: 14, created_at: iso(640),
        body_md: "Quietly one of the cleaner risers on the board. The **swing decisions** finally caught up to the raw, and the FV trend says the room agrees:\n\n[[fv:THIS]]\n\nThree things I'm watching into next update:\n\n- in-zone contact holding above the org line\n- the [methodology page](/glossary/#view=methodology) backtest cohort\n- whether the power ticks from 55 → 60\n\n> If the hit tool is real, this is a top-15 name by July."
      },
      {
        id: "seed2", parent_id: "seed1", author: authors.farm_report, score: 5, created_at: iso(415),
        body_md: "Agreed @scout_mendoza - and the per-source spread is tightening, which usually precedes a consensus bump. `xwOBA` on the pull side is the tell."
      },
      {
        id: "seed3", parent_id: null, author: authors.pitchlab, score: 8, created_at: iso(180),
        body_md: "Tempering slightly. The surplus model still wants to see it against upper-level arms before I move off my number on " + nm + ".\n\nThat said, the dollar value is moving: $dvm:THIS\n\n[[poll:Where does his FV land by the next update?|Holds 60|Jumps to 65|Slips to 55]]"
      }
    ];
  }

  // ===========================================================================
  // Identity: a normalized profile object used everywhere (live or preview)
  // ===========================================================================
  function currentProfile() {
    if (LIVE()) {
      var p = A.profile();
      if (!p) return null;
      return { id: p.id, username: p.username, avatar_url: p.avatar_url, role: p.role, karma: p.karma, badges: p._badges || [], _live: true };
    }
    return PV.profile();
  }
  function isSignedIn() { return LIVE() ? A.isSignedIn() : !!PV.profile(); }

  // deterministic default-avatar color from a string (on-theme retro ramp)
  var AV_COLORS = ["#C9A227", "#1F7A3A", "#0E7C86", "#B91C1C", "#0E2B4D", "#7A4FB0", "#0E7C46"];
  function avatarTint(seed) { var h = 0, s = String(seed || "?"); for (var i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0; return AV_COLORS[h % AV_COLORS.length]; }
  function avatarHTML(profile, size) {
    size = size || "sm";
    var uname = (profile && profile.username) || "guest";
    if (profile && profile.avatar_url) {
      return '<img class="eph-avatar sz-' + size + '" src="' + escAttr(profile.avatar_url) + '" alt="' + escAttr(uname) + '" loading="lazy">';
    }
    var ch = uname.charAt(0).toUpperCase();
    return '<span class="eph-avatar sz-' + size + ' is-default" style="background:' + avatarTint(uname) + ';" aria-hidden="true">' + esc(ch) + '</span>';
  }

  // Part 2 - userFlair: circular avatar + name + #1 team (clean logo) + #1
  // prospect chip + badges/role. Used in comments, nav, profiles.
  var BADGE_ICON = { beta_tester: "🧪", contributor: "✍️", tenured_1y: "🎖️" };
  var BADGE_NAME = { beta_tester: "Beta Tester", contributor: "Contributor", tenured_1y: "Charter Member" };
  function flairHTML(profile, opts) {
    opts = opts || {};
    if (!profile) return "";
    var out = "";
    if (opts.avatar !== false) out += avatarHTML(profile, opts.size || "sm");
    var uname = esc(profile.username || "guest");
    out += '<a class="eph-uname" href="/prospx/#u=' + escAttr(profile.username) + '">' + uname + "</a>";
    // #1 team - clean (non-pixelated) logo
    var favTeam = profile.fav_team || (profile.favorites && firstNumberOne(profile.favorites, "team"));
    if (favTeam) {
      var logo = PX().teamLogoURL ? PX().teamLogoURL(favTeam) : null;
      if (logo) out += '<img class="eph-fav-team" src="' + escAttr(logo) + '" alt="' + escAttr(favTeam) + '" title="#1 team: ' + escAttr(favTeam) + '" loading="lazy">';
    }
    // #1 prospect chip
    var favPro = profile.fav_prospect || (profile.favorites && firstNumberOneProspect(profile));
    if (favPro && favPro.name) {
      var href = favPro.key ? ('/prospx/#player=' + escAttr(favPro.key)) : '#';
      out += '<a class="eph-fav-prospect" href="' + href + '" title="#1 prospect">' + esc(favPro.name) + "</a>";
    }
    // role + badges
    if (profile.role === "admin" || profile.role === "moderator") out += '<span class="eph-role ' + profile.role + '">' + esc(profile.role === "admin" ? "Admin" : "Mod") + "</span>";
    var badges = profile.badges || [];
    if (badges.length) {
      out += '<span class="eph-badges">';
      badges.slice(0, 4).forEach(function (b) { out += '<span class="eph-badge" title="' + escAttr(BADGE_NAME[b] || b) + '">' + (BADGE_ICON[b] || "🏅") + "</span>"; });
      out += "</span>";
    }
    return '<span class="eph-flair">' + out + "</span>";
  }
  function firstNumberOne(favs, kind) { var f = (favs || []).find(function (x) { return x.kind === kind && x.is_number_one; }); return f ? f.entity_key : null; }
  function firstNumberOneProspect(profile) {
    var f = (profile.favorites || []).find(function (x) { return x.kind === "prospect" && x.is_number_one; });
    if (!f) return null;
    var p = PX().findPlayer ? PX().findPlayer(f.entity_key) : null;
    return { key: f.entity_key, name: p ? (p.player_name || f.entity_key) : f.entity_key };
  }

  // ===========================================================================
  // Safe markdown - allowlist renderer (XSS-safe by construction) + embeds
  // ===========================================================================
  function safeLink(url) {
    var u = String(url || "").trim();
    if (/^https?:\/\//i.test(u) || /^\//.test(u)) return u; // absolute http(s) or site-root only
    return null; // reject javascript:, data:, etc.
  }
  function inline(escaped, ctx) {
    var s = escaped;
    // inline code first (protect its contents from further formatting)
    var codes = [];
    s = s.replace(/`([^`]+)`/g, function (m, c) { codes.push("<code>" + c + "</code>"); return "C" + (codes.length - 1) + ""; });
    // single-metric embed:  $dvm:KEY  -> metric chip
    s = s.replace(/\$dvm:([A-Za-z0-9_\-]+)/g, function (m, k) { return metricChip("$DvM+", k, ctx); });
    // links [text](url)
    s = s.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, function (m, txt, url) {
      var safe = safeLink(url); if (!safe) return txt;
      return '<a href="' + escAttr(safe) + '" target="_blank" rel="noopener nofollow">' + txt + "</a>";
    });
    // bold / italic
    s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    s = s.replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>");
    s = s.replace(/(^|[^_])_([^_\n]+)_/g, "$1<em>$2</em>");
    // @mentions (bare handle, not part of an email / embed keyword)
    s = s.replace(/(^|[\s(])@([A-Za-z0-9_]{2,20})\b/g, function (m, pre, name) {
      return pre + '<a class="eph-mention" href="/prospx/#u=' + escAttr(name) + '">@' + name + "</a>";
    });
    s = s.replace(/C(\d+)/g, function (m, i) { return codes[+i]; });
    return s;
  }
  // Part 6 - light client-side profanity mask (extensible; the authoritative
  // filter + rate-limits live server-side in migration 0003). Display-time.
  var PROFANITY = /\b(fuck(?:ing|er|ed)?|shit(?:ty)?|asshole|bitch|cunt|dickhead)\b/gi;
  // Mask with an inert placeholder (), not "*", so the stars can't be
  // re-interpreted as markdown emphasis; swapped to "*" after the render.
  function maskProfanity(s) { return String(s).replace(PROFANITY, function (w) { return w.charAt(0) + new Array(w.length).join(""); }); }
  // Reputation gates (active in LIVE; the server-side floor is migration 0003).
  var KARMA_LINK = 5, KARMA_DOWNVOTE = 10;
  function myKarma() { var p = currentProfile(); return (p && p.karma) || 0; }
  function gateLinks(md) {
    if (!LIVE() || isStaff()) return true;
    if (myKarma() >= KARMA_LINK) return true;
    if (/\]\(\s*https?:\/\//i.test(md) || /https?:\/\//i.test(md)) { toast("New accounts can't post links until " + KARMA_LINK + " karma - keeps spam out.", "err"); return false; }
    return true;
  }
  function gateDownvote() {
    if (!LIVE() || isStaff()) return true;
    if (myKarma() >= KARMA_DOWNVOTE) return true;
    toast("Downvoting unlocks at " + KARMA_DOWNVOTE + " karma.", "err"); return false;
  }
  function renderMarkdownSafe(md, ctx) {
    ctx = ctx || {};
    if (md == null) return "";
    var src = maskProfanity(String(md).replace(/\r\n/g, "\n"));
    // fenced code blocks → protected placeholders (escaped, no inline formatting)
    var blocks = [];
    src = src.replace(/```([\s\S]*?)```/g, function (m, code) {
      blocks.push("<pre><code>" + esc(code.replace(/^\n/, "").replace(/\n$/, "")) + "</code></pre>");
      return "" + (blocks.length - 1) + "";
    });
    var lines = src.split("\n");
    var html = [], i = 0;
    function flushPara(buf) { if (buf.length) html.push("<p>" + inline(esc(buf.join("\n")), ctx).replace(/\n/g, "<br>") + "</p>"); }
    var para = [];
    while (i < lines.length) {
      var line = lines[i];
      var codeM = line.match(/^(\d+)$/);
      // standalone embed line:  [[fv:KEY]] / [[player:KEY]]
      var embM = line.trim().match(/^\[\[(fv|player):([A-Za-z0-9_\-]+)\]\]$/);
      var pollM = line.trim().match(/^\[\[poll:(.+)\]\]$/i);
      if (codeM) { flushPara(para); para = []; html.push(blocks[+codeM[1]]); i++; continue; }
      if (pollM) { flushPara(para); para = []; html.push(pollEmbedHTML(pollM[1], ctx)); i++; continue; }
      if (embM) { flushPara(para); para = []; html.push(embM[1] === "fv" ? embedFvCard(embM[2], ctx) : embedPlayerChip(embM[2], ctx)); i++; continue; }
      if (/^\s*>\s?/.test(line)) {
        flushPara(para); para = [];
        var bq = [];
        while (i < lines.length && /^\s*>\s?/.test(lines[i])) { bq.push(lines[i].replace(/^\s*>\s?/, "")); i++; }
        html.push("<blockquote>" + inline(esc(bq.join("\n")), ctx).replace(/\n/g, "<br>") + "</blockquote>");
        continue;
      }
      if (/^\s*[-*]\s+/.test(line)) {
        flushPara(para); para = [];
        var items = [];
        while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) { items.push("<li>" + inline(esc(lines[i].replace(/^\s*[-*]\s+/, "")), ctx) + "</li>"); i++; }
        html.push("<ul>" + items.join("") + "</ul>");
        continue;
      }
      if (/^\s*\d+\.\s+/.test(line)) {
        flushPara(para); para = [];
        var oitems = [];
        while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) { oitems.push("<li>" + inline(esc(lines[i].replace(/^\s*\d+\.\s+/, "")), ctx) + "</li>"); i++; }
        html.push("<ol>" + oitems.join("") + "</ol>");
        continue;
      }
      if (line.trim() === "") { flushPara(para); para = []; i++; continue; }
      para.push(line); i++;
    }
    flushPara(para);
    // swap the inert profanity-mask placeholder back to visible asterisks
    return html.join("").replace(//g, "*");
  }

  // ---- PROSPX embeds (lightweight, on-theme, formatMetric-routed) -----------
  function resolvePlayer(key, ctx) {
    if (key === "THIS" || (ctx && key === ctx.entityKey)) return ctx && ctx.entity;
    return PX().findPlayer ? PX().findPlayer(key) : null;
  }
  function latestFv(p) {
    if (!p) return null;
    var pts = p.points || [];
    if (pts.length) { var l = pts[pts.length - 1]; return l.consensus_fv != null ? l.consensus_fv : l.consensus_fv_raw; }
    return p.fv_close != null ? p.fv_close : null;
  }
  function fmtFv(v) { if (v == null) return " - "; return PX().formatMetric ? PX().formatMetric(v, "fv") : String(Math.ceil(v)); }  // FV rounds UP
  function fvSparkSVG(points) {
    var vals = (points || []).map(function (p) { return p.consensus_fv != null ? p.consensus_fv : p.consensus_fv_raw; }).filter(function (v) { return v != null && !isNaN(v); });
    if (vals.length < 2) return "";
    var W = 320, H = 60, pad = 6, n = vals.length;
    var min = Math.min.apply(null, vals), max = Math.max.apply(null, vals), span = (max - min) || 1;
    var x = function (i) { return pad + i * (W - 2 * pad) / (n - 1); };
    var y = function (v) { return H - pad - ((v - min) / span) * (H - 2 * pad); };
    var line = "", area = "M " + pad + " " + (H - pad) + " ";
    vals.forEach(function (v, i) { var px = x(i).toFixed(1), py = y(v).toFixed(1); line += (i ? "L" : "M") + px + " " + py + " "; area += "L " + px + " " + py + " "; });
    area += "L " + (W - pad) + " " + (H - pad) + " Z";
    return '<svg viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none" role="img" aria-label="Consensus FV history">' +
      '<path class="eph-spark-area" d="' + area + '"/>' +
      '<path class="eph-spark-line" d="' + line.trim() + '"/>' +
      '<circle class="eph-spark-dot" cx="' + x(n - 1).toFixed(1) + '" cy="' + y(vals[n - 1]).toFixed(1) + '" r="3"/></svg>';
  }
  function embedFvCard(key, ctx) {
    var p = resolvePlayer(key, ctx);
    if (!p) return metricChip("FV", key, ctx);
    var fv = latestFv(p), holo = (fv != null && fv >= 60) ? " holo" : "";
    var photo = PX().headshotURL ? PX().headshotURL(p.mlbam_id || p.mlbam || p.mlbamId, 90) : null;
    var pts = p.points || [];
    var spark = fvSparkSVG(pts);
    return '<a class="eph-embed' + holo + '" href="/prospx/#player=' + escAttr(p.player_key) + '">' +
      '<div class="eph-embed-top">' +
        (photo ? '<img class="eph-embed-photo" src="' + escAttr(photo) + '" alt="" loading="lazy">' : "") +
        '<div class="eph-embed-id"><div class="eph-embed-name">' + esc(p.player_name || p.player_key) + "</div>" +
          '<div class="eph-embed-meta">' + esc(p.org || "") + (p.position ? " · " + esc(p.position) : "") + "</div></div>" +
        '<span class="eph-embed-fv' + holo + '">' + esc(fmtFv(fv)) + "</span>" +
      "</div>" +
      (spark ? '<div class="eph-embed-chart"><div class="eph-chart-label">Consensus FV · last ' + pts.length + ' obs</div>' + spark + "</div>" : "") +
      "</a>";
  }
  function embedPlayerChip(key, ctx) {
    var p = resolvePlayer(key, ctx);
    if (!p) return metricChip("Player", key, ctx);
    var fv = latestFv(p), holo = (fv != null && fv >= 60) ? " holo" : "";
    var photo = PX().headshotURL ? PX().headshotURL(p.mlbam_id || p.mlbam || p.mlbamId, 90) : null;
    return '<a class="eph-embed' + holo + '" href="/prospx/#player=' + escAttr(p.player_key) + '"><div class="eph-embed-top">' +
      (photo ? '<img class="eph-embed-photo" src="' + escAttr(photo) + '" alt="" loading="lazy">' : "") +
      '<div class="eph-embed-id"><div class="eph-embed-name">' + esc(p.player_name || p.player_key) + "</div>" +
      '<div class="eph-embed-meta">' + esc(p.org || "") + (p.position ? " · " + esc(p.position) : "") + "</div></div>" +
      '<span class="eph-embed-fv' + holo + '">' + esc(fmtFv(fv)) + "</span></div></a>";
  }
  function metricChip(label, key, ctx) {
    var p = resolvePlayer(key, ctx);
    var val = " - ";
    if (p) {
      if (/dvm/i.test(label)) { var d = p.dollar_dvm_plus != null ? p.dollar_dvm_plus : p.dvm_plus; val = d != null ? (PX().formatMetric ? PX().formatMetric(d, /\$/.test(label) ? "surplusM" : "plus") : String(d)) : " - "; }
      else val = fmtFv(latestFv(p));
    } else val = esc(key);
    return '<span class="eph-metric-chip"><span class="mk">' + esc(label) + "</span>" + val + "</span>";
  }

  // Part 7 - polls. `[[poll:Question?|Opt A|Opt B|...]]` inside a comment renders
  // a vote widget; votes are keyed by the host comment id (ctx.commentId) and
  // stored in poll_votes (LIVE) or localStorage (PREVIEW). Hydrated by wirePolls.
  function pollEmbedHTML(spec, ctx) {
    var parts = String(spec).split("|").map(function (s) { return s.trim(); }).filter(Boolean);
    if (parts.length < 3) return "";  // need a question + ≥2 options
    var q = parts[0], opts = parts.slice(1, 9), cid = (ctx && ctx.commentId) || "";
    var optHtml = opts.map(function (o, i) {
      return '<button class="eph-poll-opt" data-choice="' + i + '"><span class="eph-poll-bar"></span>' +
        '<span class="eph-poll-otext">' + esc(o) + '</span><span class="eph-poll-pct"></span></button>';
    }).join("");
    return '<div class="eph-poll" data-poll-cid="' + escAttr(cid) + '" data-poll-opts="' + escAttr(encodeURIComponent(JSON.stringify(opts))) + '">' +
      '<div class="eph-poll-q">' + esc(q) + "</div>" + optHtml + '<div class="eph-poll-foot" data-poll-total></div></div>';
  }
  function pvPoll(cid) { try { var s = localStorage.getItem("eph-preview.poll:" + cid); if (s) return JSON.parse(s); } catch (e) {} return { counts: { 0: 7, 1: 4, 2: 2 }, mine: null }; }
  function pvSetPoll(cid, choice) {
    var p = pvPoll(cid), counts = Object.assign({}, p.counts);
    if (p.mine != null) counts[p.mine] = Math.max(0, (counts[p.mine] || 1) - 1);
    counts[choice] = (counts[choice] || 0) + 1;
    try { localStorage.setItem("eph-preview.poll:" + cid, JSON.stringify({ counts: counts, mine: choice })); } catch (e) {}
  }
  function wirePolls(root) {
    qsa(".eph-poll", root).forEach(function (poll) {
      var cid = poll.getAttribute("data-poll-cid");
      function paint(res) {
        var counts = (res && res.counts) || {}, mine = res ? res.mine : null;
        var total = Object.keys(counts).reduce(function (s, k) { return s + (counts[k] || 0); }, 0);
        var voted = mine != null;
        poll.classList.toggle("voted", voted);
        qsa(".eph-poll-opt", poll).forEach(function (btn, i) {
          var n = counts[i] || 0, pct = total ? Math.round(n * 100 / total) : 0;
          btn.classList.toggle("mine", mine === i);
          qs(".eph-poll-bar", btn).style.width = (voted ? pct : 0) + "%";
          qs(".eph-poll-pct", btn).textContent = voted ? pct + "%" : "";
        });
        var foot = qs("[data-poll-total]", poll); if (foot) foot.textContent = total + (total === 1 ? " vote" : " votes") + (voted ? "" : " · tap to vote");
      }
      function load() { if (LIVE() && A.pollResults && cid) A.pollResults(cid).then(paint); else paint(pvPoll(cid)); }
      on(poll, "click", ".eph-poll-opt", function (e, btn) {
        if (!isSignedIn()) return openAuthModal("signin");
        var choice = parseInt(btn.getAttribute("data-choice"), 10);
        if (LIVE() && cid) A.castPoll(cid, choice).then(load); else { pvSetPoll(cid, choice); load(); }
      });
      load();
    });
  }

  // ===========================================================================
  // Modal scaffold
  // ===========================================================================
  var _openModal = null;
  function openModal(title, bodyNode, opts) {
    closeModal();
    opts = opts || {};
    var overlay = document.createElement("div");
    overlay.className = "eph-modal-overlay";
    var modal = document.createElement("div");
    modal.className = "eph-modal" + (opts.wide ? " wide" : "");
    modal.innerHTML = '<div class="eph-modal-head"><h2></h2><button class="eph-modal-close" aria-label="Close">✕</button></div><div class="eph-modal-body"></div>';
    qs(".eph-modal-head h2", modal).textContent = title;
    qs(".eph-modal-body", modal).appendChild(bodyNode);
    overlay.appendChild(modal);
    document.body.appendChild(overlay);
    overlay.addEventListener("click", function (e) { if (e.target === overlay) closeModal(); });
    qs(".eph-modal-close", modal).addEventListener("click", closeModal);
    _openModal = overlay;
    document.addEventListener("keydown", escClose);
    return modal;
  }
  function escClose(e) { if (e.key === "Escape") closeModal(); }
  function closeModal() { if (_openModal) { _openModal.remove(); _openModal = null; document.removeEventListener("keydown", escClose); } }

  // ===========================================================================
  // Part 1 - Auth modal (email + password primary; magic-link optional)
  // ===========================================================================
  function authBodyHTML(mode) {
    var live = LIVE();
    var req = live ? " required" : "";  // preview mode skips HTML5 required so "Continue (preview)" works with empty fields
    var seg = '<div class="eph-seg"><button data-seg="signin"' + (mode !== "signup" ? ' class="is-active"' : "") + ">Sign in</button>" +
      '<button data-seg="signup"' + (mode === "signup" ? ' class="is-active"' : "") + ">Create account</button></div>";
    var preview = live ? "" :
      '<div class="eph-formmsg info">Accounts go live when the Supabase backend is configured. ' +
      'Continue in <strong>preview mode</strong> to explore profiles, flair, and the forum locally - nothing leaves this browser.</div>';
    var signin =
      '<form data-form="signin">' +
        '<div class="eph-field"><label>Email</label><input class="eph-input" type="email" name="email" autocomplete="email"' + req + "></div>" +
        '<div class="eph-field"><label>Password</label><input class="eph-input" type="password" name="password" autocomplete="current-password"' + req + "></div>" +
        '<div class="eph-formmsg" data-msg hidden></div>' +
        '<button class="eph-btn block" type="submit">' + (live ? "Sign in" : "Continue (preview)") + "</button>" +
        '<p class="eph-altline"><button type="button" class="eph-link" data-act="magic">Email me a sign-in link</button> · <button type="button" class="eph-link" data-act="reset">Forgot password?</button></p>' +
      "</form>";
    var signup =
      '<form data-form="signup">' +
        '<div class="eph-field"><label>Username</label><input class="eph-input" name="username" autocomplete="username" maxlength="20" pattern="[A-Za-z0-9_]{3,20}"' + req + ">" +
          '<div class="eph-hint" data-uname-hint>3–20 chars · letters, numbers, underscore</div></div>' +
        '<div class="eph-field"><label>Email</label><input class="eph-input" type="email" name="email" autocomplete="email"' + req + "></div>" +
        '<div class="eph-field"><label>Password</label><input class="eph-input" type="password" name="password" autocomplete="new-password" minlength="8"' + req + ">" +
          '<div class="eph-hint">8+ characters</div></div>' +
        '<div class="eph-formmsg" data-msg hidden></div>' +
        '<button class="eph-btn block" type="submit">' + (live ? "Create account" : "Create (preview)") + "</button>" +
        '<p class="eph-altline">We\'ll send a confirmation email before you can post.</p>' +
      "</form>";
    var wrap = document.createElement("div");
    wrap.innerHTML = seg + preview + '<div data-pane="signin"' + (mode === "signup" ? ' hidden' : "") + ">" + signin + "</div>" +
      '<div data-pane="signup"' + (mode !== "signup" ? ' hidden' : "") + ">" + signup + "</div>";
    return wrap;
  }
  function openAuthModal(mode) {
    var body = authBodyHTML(mode || "signin");
    var modal = openModal("eephus.io account", body);
    function showPane(seg) {
      qs('[data-seg="signin"]', body).classList.toggle("is-active", seg === "signin");
      qs('[data-seg="signup"]', body).classList.toggle("is-active", seg === "signup");
      qs('[data-pane="signin"]', body).hidden = seg !== "signin";
      qs('[data-pane="signup"]', body).hidden = seg !== "signup";
    }
    on(body, "click", "[data-seg]", function (e, t) { showPane(t.getAttribute("data-seg")); });
    function setMsg(form, text, kind) { var m = qs("[data-msg]", form); if (!m) return; m.hidden = !text; m.textContent = text || ""; m.className = "eph-formmsg" + (kind ? " " + kind : ""); }

    // live username availability check
    var unameInput = qs('[name="username"]', body);
    if (unameInput && LIVE()) {
      var t = null;
      unameInput.addEventListener("input", function () {
        var hint = qs("[data-uname-hint]", body); var v = unameInput.value;
        clearTimeout(t);
        if (!/^[A-Za-z0-9_]{3,20}$/.test(v)) { hint.className = "eph-hint"; hint.textContent = "3–20 chars · letters, numbers, underscore"; return; }
        t = setTimeout(function () { A.usernameAvailable(v).then(function (ok) { hint.className = "eph-hint " + (ok ? "ok" : "bad"); hint.textContent = ok ? "✓ available" : "✗ taken"; }); }, 350);
      });
    }

    on(body, "submit", '[data-form="signin"]', function (e, form) {
      e.preventDefault();
      var email = form.email.value.trim(), pw = form.password.value;
      if (!LIVE()) { return previewSignIn(email || "preview_fan"); }
      setMsg(form, "Signing in…", "info");
      A.signIn(email, pw).then(function (r) {
        if (r.error) return setMsg(form, friendlyAuthError(r.error), "err");
        closeModal(); afterAuth();
      });
    });
    on(body, "submit", '[data-form="signup"]', function (e, form) {
      e.preventDefault();
      var uname = form.username.value.trim(), email = form.email.value.trim(), pw = form.password.value;
      if (!LIVE()) { return previewSignIn(uname || "preview_fan"); }
      if (!/^[A-Za-z0-9_]{3,20}$/.test(uname)) return setMsg(form, "Pick a username: 3–20 letters, numbers, or underscore.", "err");
      setMsg(form, "Creating account…", "info");
      A.signUp(email, pw, uname).then(function (r) {
        if (r.error) return setMsg(form, friendlyAuthError(r.error), "err");
        showVerifyPanel(email);
      });
    });
    on(body, "click", '[data-act="magic"]', function (e, form) {
      e.preventDefault();
      var f = qs('[data-form="signin"]', body); var email = f.email.value.trim();
      if (!LIVE()) return previewSignIn("preview_fan");
      if (!email) return setMsg(f, "Enter your email first.", "err");
      A.signInWithLink(email).then(function (r) { setMsg(f, r.error ? friendlyAuthError(r.error) : "Check your email for a sign-in link.", r.error ? "err" : "ok"); });
    });
    on(body, "click", '[data-act="reset"]', function (e) {
      e.preventDefault();
      var f = qs('[data-form="signin"]', body); var email = f.email.value.trim();
      if (!LIVE()) return toast("Preview mode - password reset is a live-only flow.");
      if (!email) return setMsg(f, "Enter your email, then tap reset.", "err");
      A.resetPassword(email).then(function (r) { setMsg(f, r.error ? friendlyAuthError(r.error) : "Password-reset email sent.", r.error ? "err" : "ok"); });
    });

    function showVerifyPanel(email) {
      var v = document.createElement("div");
      v.innerHTML = '<div class="eph-verify"><div class="eph-vmark">📬</div><h3>Confirm your email</h3>' +
        '<p>We sent a confirmation link to <span class="em">' + esc(email) + "</span>.</p>" +
        "<p>Click it to verify, then you'll land back here signed in and ready to set your favorites.</p></div>" +
        '<button class="eph-btn ghost block" data-act="resend" style="margin-top:8px;">Resend confirmation</button>';
      var m = qs(".eph-modal-body"); m.innerHTML = ""; m.appendChild(v);
      qs('[data-act="resend"]', v).addEventListener("click", function () { A.resendVerification(email).then(function () { toast("Confirmation re-sent.", "ok"); }); });
    }
    return modal;
  }
  function friendlyAuthError(err) {
    var m = (err && err.message) || String(err || "Something went wrong.");
    if (/Invalid login/i.test(m)) return "Email or password is incorrect.";
    if (/already registered|already exists/i.test(m)) return "That email already has an account - try signing in.";
    if (/not confirmed/i.test(m)) return "Confirm your email first - check your inbox.";
    return m;
  }
  function previewSignIn(username) {
    username = (username || "preview_fan").replace(/[^A-Za-z0-9_]/g, "").slice(0, 20) || "preview_fan";
    PV.setProfile({ id: "preview", username: username, role: "member", karma: 0, badges: ["beta_tester"], favorites: [], _preview: true });
    closeModal(); toast("Preview mode - exploring as @" + username, "ok");
    refreshNav();
    if (!PV.profile().favorites || !PV.profile().favorites.length) openOnboarding();
    remountForumIfPresent();
  }
  function afterAuth() {
    refreshNav();
    var p = currentProfile();
    A.getFavorites && A.getFavorites().then(function (favs) {
      var hasOne = (favs || []).some(function (f) { return f.is_number_one; });
      if (!hasOne) openOnboarding();
    });
    remountForumIfPresent();
  }

  // ===========================================================================
  // Part 1 - Onboarding (#1 favorite team + #1 favorite prospect)
  // ===========================================================================
  var TEAMS = ["ARI","ATL","BAL","BOS","CHC","CWS","CIN","CLE","COL","DET","HOU","KC","LAA","LAD","MIA","MIL","MIN","NYM","NYY","ATH","PHI","PIT","SD","SF","SEA","STL","TB","TEX","TOR","WSH"];
  function openOnboarding() {
    var body = document.createElement("div");
    var teamGrid = TEAMS.map(function (t) {
      var logo = PX().teamLogoURL ? PX().teamLogoURL(t) : null;
      return '<div class="eph-team" data-team="' + escAttr(t) + '" title="' + escAttr(t) + '">' + (logo ? '<img src="' + escAttr(logo) + '" alt="' + escAttr(t) + '">' : esc(t)) + "</div>";
    }).join("");
    body.innerHTML =
      '<p class="eph-altline" style="margin:0 0 14px;text-align:left;color:var(--text-secondary);">Two quick picks - they become your flair next to your name.</p>' +
      '<div class="eph-ob-step"><div class="eph-ob-q">① Your #1 team</div><div class="eph-team-grid">' + teamGrid + "</div></div>" +
      '<div class="eph-ob-step"><div class="eph-ob-q">② Your #1 prospect</div><div class="eph-ac-wrap">' +
        '<input class="eph-input" data-prospect-search placeholder="Search prospects…" autocomplete="off">' +
        '<div class="eph-ac-list"></div></div><div class="eph-hint" data-prospect-pick></div></div>' +
      '<button class="eph-btn gold block" data-act="finish" style="margin-top:6px;">Save & continue</button>' +
      '<button class="eph-btn ghost block" data-act="skip" style="margin-top:8px;">Skip for now</button>';
    openModal("Welcome to eephus.io", body, { wide: true });

    var picked = { team: null, prospect: null };
    on(body, "click", ".eph-team", function (e, t) {
      qsa(".eph-team", body).forEach(function (x) { x.classList.remove("sel"); });
      t.classList.add("sel"); picked.team = t.getAttribute("data-team");
    });
    var search = qs("[data-prospect-search]", body), list = qs(".eph-ac-list", body), pickHint = qs("[data-prospect-pick]", body);
    search.addEventListener("input", function () {
      var q = search.value.trim().toLowerCase();
      if (q.length < 2) { list.classList.remove("open"); list.innerHTML = ""; return; }
      var pool = (PX().prospects ? PX().prospects() : []).filter(function (p) { return (p.player_name || "").toLowerCase().indexOf(q) >= 0; }).slice(0, 8);
      if (!pool.length) { list.classList.remove("open"); return; }
      list.innerHTML = pool.map(function (p) {
        var logo = (p.org && PX().teamLogoURL) ? PX().teamLogoURL(p.org) : null;
        return '<div class="eph-ac-item" data-key="' + escAttr(p.player_key) + '" data-name="' + escAttr(p.player_name) + '">' +
          (logo ? '<img class="ac-logo" src="' + escAttr(logo) + '" alt="">' : "") + esc(p.player_name) +
          '<span class="ac-meta">' + esc(p.org || "") + (p.position ? " · " + esc(p.position) : "") + "</span></div>";
      }).join("");
      list.classList.add("open");
    });
    on(body, "click", ".eph-ac-item", function (e, t) {
      picked.prospect = { key: t.getAttribute("data-key"), name: t.getAttribute("data-name") };
      search.value = picked.prospect.name; list.classList.remove("open");
      pickHint.className = "eph-hint ok"; pickHint.textContent = "✓ " + picked.prospect.name;
    });
    on(body, "click", '[data-act="skip"]', function () { closeModal(); });
    on(body, "click", '[data-act="finish"]', function () {
      // Reconcile: the #1 prospect (a curated favorite) is auto-added to the
      // broad watchlist so favoriting and tracking aren't redundant/confusing.
      if (LIVE()) {
        var ops = [];
        if (picked.team) ops.push(A.setNumberOne("team", picked.team));
        if (picked.prospect) ops.push(A.setNumberOne("prospect", picked.prospect.key));
        Promise.all(ops).then(function () {
          if (picked.prospect) ensureWatched("prospect", picked.prospect.key);
          toast("Favorites saved" + (picked.prospect ? " · #1 prospect added to your watchlist" : "") + ".", "ok");
          closeModal(); refreshNav(); remountForumIfPresent();
        });
      } else {
        var prof = PV.profile() || {}; prof.fav_team = picked.team; prof.fav_prospect = picked.prospect;
        prof.favorites = [];
        if (picked.team) prof.favorites.push({ kind: "team", entity_key: picked.team, is_number_one: true });
        if (picked.prospect) prof.favorites.push({ kind: "prospect", entity_key: picked.prospect.key, is_number_one: true });
        PV.setProfile(prof);
        if (picked.prospect) ensureWatched("prospect", picked.prospect.key);
        toast("Favorites saved (preview)" + (picked.prospect ? " · #1 prospect tracked" : "") + ".", "ok");
        closeModal(); refreshNav(); remountForumIfPresent();
      }
    });
  }
  function qsa(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  // ===========================================================================
  // Nav account control
  // ===========================================================================
  function refreshNav() {
    qsa(".eephus-nav-controls").forEach(injectNavInto);
  }
  function injectNavInto(controls) {
    var existing = qs(".eph-nav-account", controls);
    if (existing) existing.remove();
    var node = document.createElement("div");
    node.className = "eph-nav-account";
    var prof = currentProfile();
    if (isSignedIn() && prof) {
      node.innerHTML =
        '<button class="eph-acct-btn eph-bell" data-act="bell" title="Notifications" aria-label="Notifications">' +
          '<span aria-hidden="true">🔔</span><span class="eph-bell-count" hidden>0</span></button>' +
        '<button class="eph-acct-btn" data-act="menu">' + avatarHTML(prof, "sm") +
          '<span class="eph-acct-label">' + esc(prof.username) + "</span>" +
          (prof._preview ? '<span class="eph-demo-flag">preview</span>' : "") +
          '<span class="eph-caret">▼</span></button>' +
        '<div class="eph-acct-menu"><div class="eph-menu-head">' + avatarHTML(prof, "md") +
          '<div><div class="nm">' + esc(prof.username) + '</div><div class="kr">' + (prof.karma || 0) + ' karma</div></div></div>' +
          '<button data-act="profile">Profile</button>' +
          '<button data-act="feed">Your feed</button>' +
          '<button data-act="settings">Settings</button>' +
          '<button data-act="notifs">Notifications</button>' +
          (isStaff(prof) ? '<button data-act="mod">Moderation</button>' : "") +
          '<div class="eph-menu-sep"></div>' +
          '<button data-act="signout">Sign out</button></div>';
    } else {
      node.innerHTML = '<button class="eph-acct-btn" data-act="signin"><span aria-hidden="true">◔</span><span class="eph-acct-label">Sign in</span></button>';
    }
    controls.appendChild(node);
    var menu = qs(".eph-acct-menu", node);
    on(node, "click", '[data-act="signin"]', function () { openAuthModal("signin"); });
    on(node, "click", '[data-act="menu"]', function (e) { e.stopPropagation(); if (menu) menu.classList.toggle("open"); });
    on(node, "click", '[data-act="bell"]', function () { openNotifications(); });
    on(node, "click", '[data-act="signout"]', function () { doSignOut(); });
    on(node, "click", '[data-act="profile"]', function () { var p = currentProfile(); if (p) openProfile(p.username); });
    on(node, "click", '[data-act="feed"]', function () { openFeed(); });
    on(node, "click", '[data-act="settings"]', function () { openSettings(); });
    on(node, "click", '[data-act="notifs"]', function () { openNotifications(); });
    on(node, "click", '[data-act="mod"]', function () { openModeration(); });
    document.addEventListener("click", function (e) { if (menu && !node.contains(e.target)) menu.classList.remove("open"); });
    if (isSignedIn()) updateBellCount();
  }
  function isStaff(prof) { prof = prof || currentProfile(); return !!(prof && (prof.role === "admin" || prof.role === "moderator")); }
  function updateBellCount() {
    var p = (LIVE() && A.unreadCount) ? A.unreadCount() : Promise.resolve(previewNotifications().filter(function (n) { return !n.read; }).length);
    Promise.resolve(p).then(function (n) {
      qsa(".eph-bell .eph-bell-count").forEach(function (b) { b.textContent = n; b.hidden = !n; });
    });
  }
  function doSignOut() {
    _watchSynced = false; // re-sync the watchlist on the next sign-in
    if (LIVE()) A.signOut().then(function () { refreshNav(); remountForumIfPresent(); toast("Signed out."); });
    else { PV.clearProfile(); refreshNav(); remountForumIfPresent(); toast("Left preview mode."); }
  }

  // ---- minimal Settings + Notifications (full build is Part 5/2) ------------
  function openSettings() {
    var prof = currentProfile() || {};
    var body = document.createElement("div");
    body.innerHTML =
      '<div class="eph-field"><label>Avatar</label><div style="display:flex;align-items:center;gap:12px;">' + avatarHTML(prof, "lg") +
        '<input type="file" accept="image/png,image/jpeg,image/webp" data-s="avatar"></div>' +
        '<div class="eph-hint">PNG / JPEG / WebP · ≤ 2 MB · shown circular</div></div>' +
      '<div class="eph-field"><label>Username</label><input class="eph-input" data-s="username" value="' + escAttr(prof.username || "") + '" pattern="[A-Za-z0-9_]{3,20}"></div>' +
      '<div class="eph-field"><label>Self-entered X handle (display-only)</label><input class="eph-input" data-s="x" placeholder="@yourhandle" value="' + escAttr(prof.x_handle || "") + '"></div>' +
      '<div class="eph-field"><label>Notifications</label>' +
        '<label class="eph-altline" style="text-align:left;display:flex;gap:8px;align-items:center;"><input type="checkbox" data-s="n_reply" checked> Replies to your comments</label>' +
        '<label class="eph-altline" style="text-align:left;display:flex;gap:8px;align-items:center;"><input type="checkbox" data-s="n_mention" checked> @mentions</label>' +
        '<label class="eph-altline" style="text-align:left;display:flex;gap:8px;align-items:center;"><input type="checkbox" data-s="n_fv" checked> FV-change alerts (watchlist)</label>' +
        '<label class="eph-altline" style="text-align:left;display:flex;gap:8px;align-items:center;"><input type="checkbox" data-s="n_digest"> Email me the monthly digest</label></div>' +
      '<button class="eph-btn block" data-act="save">Save</button>' +
      '<button class="eph-btn ghost block" data-act="delete" style="margin-top:8px;color:var(--accent-red);border-color:var(--accent-red);">Delete account</button>';
    openModal("Settings", body);
    var av = qs('[data-s="avatar"]', body);
    if (av) av.addEventListener("change", function () {
      var f = av.files && av.files[0]; if (!f) return;
      if (f.size > 2 * 1024 * 1024) return toast("Image must be ≤ 2 MB.", "err");
      if (["image/png", "image/jpeg", "image/webp"].indexOf(f.type) < 0) return toast("Use PNG, JPEG, or WebP.", "err");
      if (LIVE()) A.uploadAvatar(f).then(function (r) { toast(r && r.error ? "Upload failed: " + friendlyAuthError(r.error) : "Avatar updated.", r && r.error ? "err" : "ok"); refreshNav(); });
      else { var rd = new FileReader(); rd.onload = function () { var p = PV.profile() || {}; p.avatar_url = rd.result; PV.setProfile(p); refreshNav(); toast("Avatar updated (preview).", "ok"); }; rd.readAsDataURL(f); }
    });
    on(body, "click", '[data-act="save"]', function () {
      var uname = qs('[data-s="username"]', body).value.trim();
      if (LIVE()) { A.updateProfile({ username: uname }).then(function (r) { toast(r.error ? "Couldn't save: " + friendlyAuthError(r.error) : "Saved.", r.error ? "err" : "ok"); refreshNav(); }); }
      else { var p = PV.profile() || {}; p.username = uname || p.username; p.x_handle = qs('[data-s="x"]', body).value.trim(); PV.setProfile(p); toast("Saved (preview).", "ok"); refreshNav(); }
      closeModal();
    });
    on(body, "click", '[data-act="delete"]', function () {
      if (!confirm("Delete your account? This removes your profile and favorites. Your comments remain as [deleted].")) return;
      if (LIVE()) toast("Account deletion runs server-side - wire the Edge Function before enabling.", "err");
      else { PV.clearProfile(); closeModal(); refreshNav(); remountForumIfPresent(); toast("Preview account cleared."); }
    });
  }
  var NOTIF_ICON = { reply: "↩", mention: "@", fv_change: "▲", follow: "✦", badge: "🏅" };
  function previewNotifications() {
    var now = Date.now();
    return [
      { id: "n1", type: "reply", read: false, created_at: new Date(now - 12 * 60000).toISOString(), payload: { from_name: "farm_report" } },
      { id: "n2", type: "mention", read: false, created_at: new Date(now - 95 * 60000).toISOString(), payload: { from_name: "scout_mendoza" } },
      { id: "n3", type: "fv_change", read: true, created_at: new Date(now - 3 * 86400000).toISOString(), payload: { player_name: "Jesús Made", old: 60, new: 62 } }
    ];
  }
  function notifRowHTML(n) {
    return '<div class="eph-notif' + (n.read ? "" : " unread") + '"><span class="eph-notif-ico ' + esc(n.type) + '">' + (NOTIF_ICON[n.type] || "•") + "</span>" +
      '<span class="eph-notif-txt">' + esc(notifText(n)) + "</span>" +
      '<span class="eph-notif-ts">' + timeAgo(n.created_at) + "</span></div>";
  }
  function openNotifications() {
    var body = document.createElement("div");
    body.innerHTML = '<div class="eph-formmsg info">Loading…</div>';
    openModal("Notifications", body);
    var src = (LIVE() && A.listNotifications) ? A.listNotifications(30) : Promise.resolve(previewNotifications());
    Promise.resolve(src).then(function (list) {
      list = list || [];
      if (!list.length) { body.innerHTML = '<div class="eph-formmsg info">No notifications yet. Replies, @mentions, and FV-change alerts for prospects you watch land here.</div>'; return; }
      body.innerHTML = '<div class="eph-notif-list">' + list.map(notifRowHTML).join("") + "</div>" +
        '<p class="eph-altline" style="text-align:left;">FV-change alerts fire monthly when grades update; replies &amp; mentions are near-real-time.</p>';
      if (LIVE() && A.markNotificationsRead) A.markNotificationsRead();
      qsa(".eph-bell .eph-bell-count").forEach(function (b) { b.hidden = true; });
    });
  }
  function notifText(n) {
    var p = n.payload || {};
    if (n.type === "reply") return (p.from_name ? "@" + p.from_name + " " : "Someone ") + "replied to your comment";
    if (n.type === "mention") return (p.from_name ? "@" + p.from_name + " " : "Someone ") + "mentioned you";
    if (n.type === "fv_change") return "FV " + (p.old != null ? p.old + " → " + p.new : "change") + " on " + (p.player_name || p.entity_key || "a prospect you watch");
    if (n.type === "follow") return (p.from_name ? "@" + p.from_name : "Someone") + " followed you";
    if (n.type === "badge") return "You earned the " + (p.badge || "") + " badge";
    return "Notification";
  }

  // ===========================================================================
  // Part 6 - Moderation view (staff only): report queue + grant-badge + ban.
  // ===========================================================================
  function previewReports() {
    var now = Date.now();
    return [
      { id: "r1", reason: "Spam / self-promotion", status: "open", created_at: new Date(now - 30 * 60000).toISOString(), comment: { body_md: "check out my store http://buy-prospect-shirts.example free shipping!!", author: "spammer99" } },
      { id: "r2", reason: "Personal attack", status: "open", created_at: new Date(now - 5 * 3600000).toISOString(), comment: { body_md: "that take is just dumb, do you even watch baseball", author: "hot_take_harry" } }
    ];
  }
  function openModeration() {
    if (!isStaff()) return toast("Moderator access only.", "err");
    var body = document.createElement("div");
    body.innerHTML =
      '<div class="eph-field"><label>Grant badge</label><div style="display:flex;gap:6px;">' +
        '<input class="eph-input" data-m="badge-user" placeholder="username"><select class="eph-input" data-m="badge-slug" style="max-width:150px;">' +
        '<option value="beta_tester">Beta Tester</option><option value="contributor">Contributor</option><option value="tenured_1y">Charter</option></select>' +
        '<button class="eph-btn sm" data-act="grant">Grant</button></div></div>' +
      '<div class="eph-field"><label>Ban / suspend</label><div style="display:flex;gap:6px;">' +
        '<input class="eph-input" data-m="ban-user" placeholder="username"><input class="eph-input" data-m="ban-days" placeholder="days (blank = perma)" style="max-width:160px;">' +
        '<button class="eph-btn sm" data-act="ban" style="color:var(--accent-red);border-color:var(--accent-red);">Ban</button></div></div>' +
      '<div class="eph-mod-sec">Open reports</div><div data-reports><div class="eph-formmsg info">Loading…</div></div>';
    openModal("Moderation", body, { wide: true });
    function loadReports() {
      var src = (LIVE() && A.listReports) ? A.listReports() : Promise.resolve(previewReports());
      Promise.resolve(src).then(function (reports) {
        var el = qs("[data-reports]", body); reports = reports || [];
        if (!reports.length) { el.innerHTML = '<div class="eph-formmsg ok">Queue clear - no open reports.</div>'; return; }
        el.innerHTML = reports.map(function (r) {
          var c = r.comment || r.comments || {};
          return '<div class="eph-report" data-rid="' + escAttr(r.id) + '" data-cid="' + escAttr(r.comment_id || c.id || "") + '">' +
            '<div class="eph-report-head"><span class="eph-report-reason">' + esc(r.reason) + '</span><span class="eph-notif-ts">' + timeAgo(r.created_at) + "</span></div>" +
            '<div class="eph-report-body">' + esc((c.body_md || "").slice(0, 240)) + "</div>" +
            '<div class="eph-report-by">by @' + esc(c.author || "?") + "</div>" +
            '<div class="eph-c-foot"><button data-act="r-remove" class="danger">Remove comment</button><button data-act="r-resolve">Resolve</button><button data-act="r-dismiss">Dismiss</button></div></div>';
        }).join("");
      });
    }
    loadReports();
    on(body, "click", '[data-act="grant"]', function () {
      var u = qs('[data-m="badge-user"]', body).value.trim(), slug = qs('[data-m="badge-slug"]', body).value;
      if (!u) return;
      if (LIVE() && A.grantBadgeByUsername) A.grantBadgeByUsername(u, slug).then(function (r) { toast(r && r.error ? "Failed: " + friendlyAuthError(r.error) : "Granted " + slug + " to @" + u, r && r.error ? "err" : "ok"); });
      else toast("Granted " + slug + " to @" + u + " (preview).", "ok");
    });
    on(body, "click", '[data-act="ban"]', function () {
      var u = qs('[data-m="ban-user"]', body).value.trim(), days = qs('[data-m="ban-days"]', body).value.trim();
      if (!u) return;
      var until = days ? new Date(Date.now() + (parseInt(days, 10) || 1) * 86400000).toISOString() : null;
      if (LIVE() && A.banUserByUsername) A.banUserByUsername(u, until).then(function (r) { toast(r && r.error ? "Failed: " + friendlyAuthError(r.error) : "@" + u + (days ? " suspended " + days + "d" : " banned"), r && r.error ? "err" : "ok"); });
      else toast("@" + u + (days ? " suspended " + days + "d" : " banned") + " (preview).", "ok");
    });
    function resolveReport(btn, status, remove) {
      var row = btn.closest(".eph-report"); var rid = row.getAttribute("data-rid"), cid = row.getAttribute("data-cid");
      if (LIVE()) {
        if (remove && A.staffRemoveComment) A.staffRemoveComment(cid);
        if (A.setReportStatus) A.setReportStatus(rid, remove ? "resolved" : status);
      }
      row.remove(); toast(remove ? "Comment removed · report resolved." : "Report " + status + ".", "ok");
      remountForumIfPresent();
    }
    on(body, "click", '[data-act="r-remove"]', function (e, b) { resolveReport(b, "resolved", true); });
    on(body, "click", '[data-act="r-resolve"]', function (e, b) { resolveReport(b, "resolved", false); });
    on(body, "click", '[data-act="r-dismiss"]', function (e, b) { resolveReport(b, "dismissed", false); });
  }

  // ===========================================================================
  // Part 4 - Forum (per-prospect / per-farm thread)
  // ===========================================================================
  var _forumState = { scope: null, key: null, entity: null, sort: "top" };
  function remountForumIfPresent() { if (_forumState.scope) mountForum(_forumState.scope, _forumState.key, _forumState.entity); }

  function mountForum(scope, key, entity) {
    _forumState = { scope: scope, key: key, entity: entity, sort: _forumState.sort || "top" };
    // Preferred target: a tab/section mount point (#eph-forum-mount) the host page
    // renders for the Discussion tab. Fallback: append to the detail body/content.
    var mountEl = qs("#eph-forum-mount");
    var existing = qs("#eph-forum");
    if (existing) existing.remove();
    var sec = document.createElement("section");
    sec.className = "eph-forum" + (mountEl ? " in-tab" : ""); sec.id = "eph-forum";
    sec.innerHTML = '<div class="eph-forum-head"><h2>Discussion' + (LIVE() ? "" : '<span class="eph-demo-flag">preview</span>') +
      '</h2><div style="display:flex;gap:10px;align-items:center;"><span class="eph-count" data-count></span>' +
      '<button class="eph-btn sm ghost" data-act="share-thread" title="Share to X">Share ↗</button></div></div><div data-forum-inner></div>';
    if (mountEl) { mountEl.innerHTML = ""; mountEl.appendChild(sec); }
    else {
      var host = qs("#player-detail-body") || qs("#farm-detail-body") || qs("#content");
      if (!host) return;
      host.appendChild(sec);
    }
    var st = qs('[data-act="share-thread"]', sec);
    if (st) st.addEventListener("click", function () { shareToX(threadTitle() + " - discussion on eephus.io", shareUrl()); });
    loadAndRenderComments();
  }
  // Share-to-X via the standard web intent (a prefilled tweet URL - no API/login).
  function shareToX(text, url) {
    var intent = "https://twitter.com/intent/tweet?text=" + encodeURIComponent(text) + (url ? "&url=" + encodeURIComponent(url) : "");
    window.open(intent, "_blank", "noopener,noreferrer,width=560,height=440");
  }
  function shareUrl() { return (window.location.origin || "") + threadHref({ scope: _forumState.scope, entity_key: _forumState.key }); }

  function getComments() {
    if (LIVE()) {
      return A.getOrCreateThread(_forumState.scope, _forumState.key, threadTitle())
        .then(function (thread) {
          if (!thread) return { thread: null, comments: [] };
          return A.listComments(thread.id, _forumState.sort).then(function (cs) {
            return hydrateLiveComments(cs).then(function (list) { return { thread: thread, comments: list }; });
          });
        });
    }
    // preview
    var list = PV.comments(_forumState.scope, _forumState.key);
    if (!list) { list = seedThread(_forumState.scope, _forumState.key, _forumState.entity); PV.saveComments(_forumState.scope, _forumState.key, list); }
    return Promise.resolve({ thread: { id: "preview" }, comments: list });
  }
  function hydrateLiveComments(cs) {
    // map Supabase rows → the shape the renderer expects
    var ids = cs.map(function (c) { return c.id; });
    return (A.myVotes ? A.myVotes(ids) : Promise.resolve({})).then(function (mine) {
      return cs.map(function (c) {
        var pr = c.profiles || {};
        return {
          id: c.id, parent_id: c.parent_id, score: c.score, created_at: c.created_at, edited_at: c.edited_at,
          deleted: c.deleted, body_md: c.body_md, my_vote: mine[c.id] || 0,
          author: { id: c.author_id, username: pr.username, avatar_url: pr.avatar_url, role: pr.role, karma: pr.karma, badges: [] }
        };
      });
    });
  }
  function threadTitle() {
    var e = _forumState.entity;
    var nm = (e && (e.player_name || e.name)) || _forumState.key || "Discussion";
    return nm + (_forumState.scope === "farm" ? " - farm system" : "");
  }

  function loadAndRenderComments() {
    var inner = qs("#eph-forum [data-forum-inner]");
    if (!inner) return;
    inner.innerHTML = '<div class="eph-formmsg info">Loading discussion…</div>';
    getComments().then(function (res) { renderForum(res.comments || [], res.thread); })
      .catch(function () { inner.innerHTML = '<div class="eph-formmsg err">Could not load the discussion.</div>'; });
  }

  function sortComments(list) {
    var tops = list.filter(function (c) { return !c.parent_id; });
    var byId = {}; list.forEach(function (c) { byId[c.id] = c; });
    if (_forumState.sort === "recent") tops.sort(function (a, b) { return new Date(b.created_at) - new Date(a.created_at); });
    else if (_forumState.sort === "active") tops.sort(function (a, b) { return lastActivity(b, list) - lastActivity(a, list); });
    else tops.sort(function (a, b) { return (b.score - a.score) || (new Date(b.created_at) - new Date(a.created_at)); });
    return tops;
  }
  function lastActivity(top, list) {
    var t = new Date(top.created_at).getTime();
    list.forEach(function (c) { if (c.parent_id === top.id) t = Math.max(t, new Date(c.created_at).getTime()); });
    return t;
  }

  function renderForum(list, thread) {
    var ctx = { entity: _forumState.entity, entityKey: _forumState.key };
    var inner = qs("#eph-forum [data-forum-inner]"); if (!inner) return;
    var count = list.filter(function (c) { return !c.deleted; }).length;
    var cEl = qs("#eph-forum [data-count]"); if (cEl) cEl.textContent = count + (count === 1 ? " comment" : " comments");

    var sortBar = '<div class="eph-sort">' +
      ["top", "recent", "active"].map(function (s) {
        return '<button data-sort="' + s + '"' + (_forumState.sort === s ? ' class="is-active"' : "") + ">" + (s === "top" ? "Top" : s === "recent" ? "Recent" : "Active") + "</button>";
      }).join("") + "</div>";

    var compose = isSignedIn() ? composeHTML() :
      '<div class="eph-signedout"><p>Join the discussion - sign in to comment, vote, and track this prospect.</p>' +
      '<button class="eph-btn sm" data-act="signin">Sign in</button></div>';

    var tops = sortComments(list);
    var byParent = {}; list.forEach(function (c) { if (c.parent_id) (byParent[c.parent_id] = byParent[c.parent_id] || []).push(c); });
    var body = tops.map(function (c) {
      var replies = (byParent[c.id] || []).sort(function (a, b) { return new Date(a.created_at) - new Date(b.created_at); });
      return commentHTML(c, ctx, false) + replies.map(function (r) { return commentHTML(r, ctx, true); }).join("");
    }).join("");
    if (!tops.length) body = '<div class="eph-formmsg info">No comments yet - start the conversation.</div>';

    inner.innerHTML = sortBar + compose + '<div class="eph-comments">' + body + "</div>";
    wireForum(inner, ctx);
    wirePolls(inner);
  }

  function composeHTML(parentId, opts) {
    opts = opts || {};
    var pid = parentId ? ' data-parent="' + escAttr(parentId) + '"' : "";
    return '<div class="eph-compose"' + pid + '>' +
      '<div class="eph-compose-bar">' +
        '<button class="eph-md-btn" data-md="bold" title="Bold" type="button">B</button>' +
        '<button class="eph-md-btn" data-md="italic" title="Italic" type="button"><em>i</em></button>' +
        '<button class="eph-md-btn" data-md="link" title="Link" type="button">🔗</button>' +
        '<button class="eph-md-btn" data-md="quote" title="Quote" type="button">❝</button>' +
        '<button class="eph-md-btn" data-md="code" title="Code" type="button">&lt;/&gt;</button>' +
        '<button class="eph-md-btn" data-act="poll" title="Insert a poll" type="button">▦ Poll</button>' +
        '<button class="eph-embed-btn" data-act="embed" type="button">＋ Embed PROSPX</button>' +
      "</div>" +
      '<textarea placeholder="' + (parentId ? "Write a reply…" : "Share your read… **markdown** supported · @mention users · [[fv:key]] to embed a chart") + '"></textarea>' +
      '<div class="eph-mention-pop"></div>' +
      '<div class="eph-embed-pop"><h4>Embed a prospect</h4><input class="eph-embed-search" placeholder="Search prospects…"><div class="eph-ac-list"></div></div>' +
      '<div class="eph-compose-foot"><span class="eph-fyi">Embeds: <code>[[fv:key]]</code> chart · <code>[[player:key]]</code> card · <code>[[fv:THIS]]</code> = this page</span>' +
      '<button class="eph-btn sm" data-act="post"' + (opts.parent ? "" : "") + ">" + (parentId ? "Reply" : "Post comment") + "</button></div></div>";
  }

  function commentHTML(c, ctx, isReply) {
    var prof = c.author || {};
    var bodyHtml = c.deleted ? "<p>[deleted]</p>" : renderMarkdownSafe(c.body_md, Object.assign({}, ctx, { commentId: c.id }));
    var mine = currentProfile() && (currentProfile().id === (prof.id || null) || (!LIVE() && currentProfile().username === prof.username));
    var canVote = isSignedIn() && !mine && !c.deleted;
    var up = c.my_vote === 1 ? " on" : "", down = c.my_vote === -1 ? " on" : "";
    var staff = isStaff();
    return '<div class="eph-comment' + (isReply ? " is-reply" : "") + (c.deleted ? " is-deleted" : "") + '" data-cid="' + escAttr(c.id) + '" data-md="' + escAttr(encodeURIComponent(c.body_md || "")) + '">' +
      '<div class="eph-c-vote">' +
        '<button class="eph-vbtn up' + up + '" data-vote="1" ' + (canVote ? "" : "disabled") + ' aria-label="Upvote">▲</button>' +
        '<span class="eph-score" data-score>' + (c.score || 0) + "</span>" +
        '<button class="eph-vbtn down' + down + '" data-vote="-1" ' + (canVote ? "" : "disabled") + ' aria-label="Downvote">▼</button>' +
      "</div>" +
      '<div class="eph-c-main">' +
        '<div class="eph-c-head">' + flairHTML(prof, { size: "sm" }) +
          '<span class="eph-c-ts' + (c.edited_at ? " edited" : "") + '">' + timeAgo(c.created_at) + "</span></div>" +
        '<div class="eph-c-body">' + bodyHtml + "</div>" +
        '<div class="eph-c-foot">' +
          (!isReply && !c.deleted ? '<button data-act="reply">Reply</button>' : "") +
          (mine && !c.deleted ? '<button data-act="edit">Edit</button>' : "") +
          (mine && !c.deleted ? '<button data-act="del" class="danger">Delete</button>' : "") +
          (!c.deleted ? '<button data-act="sharex" title="Share to X">Share ↗</button>' : "") +
          (!mine && !c.deleted ? '<button data-act="report">Report</button>' : "") +
          (!mine && staff && !c.deleted ? '<button data-act="modremove" class="danger">Remove</button>' : "") +
        "</div>" +
        '<div data-reply-slot></div>' +
      "</div></div>";
  }

  function wireForum(inner, ctx) {
    on(inner, "click", '[data-sort]', function (e, t) { _forumState.sort = t.getAttribute("data-sort"); loadAndRenderComments(); });
    on(inner, "click", '[data-act="signin"]', function () { openAuthModal("signin"); });
    // compose toolbar + posting (top-level + reply composers)
    qsa(".eph-compose", inner).forEach(function (cmp) { wireCompose(cmp, ctx); });
    // voting (downvotes gated by reputation for new accounts)
    on(inner, "click", "[data-vote]", function (e, btn) {
      if (btn.disabled) return;
      var row = btn.closest(".eph-comment"); var cid = row.getAttribute("data-cid");
      var val = parseInt(btn.getAttribute("data-vote"), 10);
      if (val === -1 && !btn.classList.contains("on") && !gateDownvote()) return;
      doVote(cid, val, row);
    });
    // edit own comment
    on(inner, "click", '[data-act="edit"]', function (e, btn) {
      var row = btn.closest(".eph-comment"); var cid = row.getAttribute("data-cid");
      var bodyEl = qs(".eph-c-body", row); var foot = qs(".eph-c-foot", row);
      if (qs(".eph-edit", row)) return;
      var cur = decodeURIComponent(row.getAttribute("data-md") || "");
      bodyEl.insertAdjacentHTML("afterend", '<div class="eph-compose eph-edit"><textarea>' + esc(cur) + "</textarea>" +
        '<div class="eph-compose-foot"><span class="eph-fyi">Editing</span><span style="display:flex;gap:6px;">' +
        '<button class="eph-btn sm" data-act="saveedit">Save</button><button class="eph-btn sm ghost" data-act="canceledit">Cancel</button></span></div></div>');
      bodyEl.style.display = "none"; if (foot) foot.style.display = "none";
      qs(".eph-edit textarea", row).focus();
    });
    on(inner, "click", '[data-act="canceledit"]', function (e, btn) { loadAndRenderComments(); });
    on(inner, "click", '[data-act="saveedit"]', function (e, btn) {
      var row = btn.closest(".eph-comment"); var cid = row.getAttribute("data-cid");
      var md = qs(".eph-edit textarea", row).value.trim(); if (!md) return;
      if (!gateLinks(md)) return;
      var html = renderMarkdownSafe(md, ctx);
      if (LIVE()) A.editComment(cid, md, html).then(loadAndRenderComments);
      else { var list = PV.comments(_forumState.scope, _forumState.key) || []; list.forEach(function (c) { if (c.id === cid) { c.body_md = md; c.edited_at = new Date().toISOString(); } }); PV.saveComments(_forumState.scope, _forumState.key, list); loadAndRenderComments(); }
    });
    // staff removal (moderation)
    on(inner, "click", '[data-act="modremove"]', function (e, btn) {
      var cid = btn.closest(".eph-comment").getAttribute("data-cid");
      if (!confirm("Remove this comment as a moderator?")) return;
      if (LIVE() && A.staffRemoveComment) A.staffRemoveComment(cid).then(loadAndRenderComments);
      else { var list = PV.comments(_forumState.scope, _forumState.key) || []; list.forEach(function (c) { if (c.id === cid) { c.deleted = true; c.body_md = "[removed by moderator]"; } }); PV.saveComments(_forumState.scope, _forumState.key, list); loadAndRenderComments(); toast("Comment removed.", "ok"); }
    });
    on(inner, "click", '[data-act="reply"]', function (e, btn) {
      var row = btn.closest(".eph-comment"); var slot = qs("[data-reply-slot]", row);
      if (qs(".eph-compose", slot)) { slot.innerHTML = ""; return; }
      if (!isSignedIn()) return openAuthModal("signin");
      slot.innerHTML = composeHTML(row.getAttribute("data-cid"));
      wireCompose(qs(".eph-compose", slot), ctx);
      qs("textarea", slot).focus();
    });
    on(inner, "click", '[data-act="del"]', function (e, btn) {
      var cid = btn.closest(".eph-comment").getAttribute("data-cid");
      if (!confirm("Delete this comment?")) return;
      if (LIVE()) A.deleteComment(cid).then(loadAndRenderComments);
      else { var list = PV.comments(_forumState.scope, _forumState.key) || []; list.forEach(function (c) { if (c.id === cid) { c.deleted = true; c.body_md = "[deleted]"; } }); PV.saveComments(_forumState.scope, _forumState.key, list); loadAndRenderComments(); }
    });
    on(inner, "click", '[data-act="report"]', function (e, btn) {
      var cid = btn.closest(".eph-comment").getAttribute("data-cid");
      if (!isSignedIn()) return openAuthModal("signin");
      var reason = prompt("Report this comment - reason:");
      if (!reason) return;
      if (LIVE()) A.report(cid, reason).then(function () { toast("Reported to moderators.", "ok"); });
      else toast("Reported (preview).", "ok");
    });
    on(inner, "click", '[data-act="sharex"]', function (e, btn) {
      var row = btn.closest(".eph-comment");
      var md = decodeURIComponent(row.getAttribute("data-md") || "").replace(/\[\[[^\]]*\]\]/g, "").replace(/\s+/g, " ").trim();
      shareToX('"' + md.slice(0, 160) + '" - eephus.io', shareUrl());
    });
  }

  function wireCompose(cmp, ctx) {
    var ta = qs("textarea", cmp);
    on(cmp, "click", "[data-md]", function (e, b) { applyMd(ta, b.getAttribute("data-md")); });
    on(cmp, "click", '[data-act="poll"]', function () { insertAtCursor(ta, "\n[[poll:Better prospect - A or B?|Option A|Option B]]\n"); });
    on(cmp, "click", '[data-act="post"]', function () { submitComment(cmp, ta, ctx); });
    // embed picker
    var pop = qs(".eph-embed-pop", cmp), search = qs(".eph-embed-search", cmp), list = qs(".eph-ac-list", pop);
    on(cmp, "click", '[data-act="embed"]', function (e) { e.stopPropagation(); pop.classList.toggle("open"); if (pop.classList.contains("open")) search.focus(); });
    if (search) search.addEventListener("input", function () {
      var q = search.value.trim().toLowerCase();
      if (q.length < 2) { list.innerHTML = ""; return; }
      var pool = (PX().prospects ? PX().prospects() : []).filter(function (p) { return (p.player_name || "").toLowerCase().indexOf(q) >= 0; }).slice(0, 8);
      list.innerHTML = pool.map(function (p) { return '<div class="eph-ac-item" data-key="' + escAttr(p.player_key) + '">' + esc(p.player_name) + '<span class="ac-meta">' + esc(p.org || "") + "</span></div>"; }).join("");
    });
    on(pop, "click", ".eph-ac-item", function (e, t) {
      insertAtCursor(ta, "\n[[fv:" + t.getAttribute("data-key") + "]]\n"); pop.classList.remove("open");
    });
    // @mention autocomplete (live only)
    var mpop = qs(".eph-mention-pop", cmp);
    ta.addEventListener("input", function () {
      var m = textBeforeCursor(ta).match(/@([A-Za-z0-9_]{1,20})$/);
      if (!m || !LIVE()) { mpop.classList.remove("open"); return; }
      A.searchUsernames(m[1], 6).then(function (users) {
        if (!users.length) { mpop.classList.remove("open"); return; }
        mpop.innerHTML = users.map(function (u) { return '<div class="eph-mrow" data-uname="' + escAttr(u.username) + '">' + avatarHTML(u, "xs") + " @" + esc(u.username) + "</div>"; }).join("");
        positionMentionPop(ta, mpop); mpop.classList.add("open");
      });
    });
    on(mpop, "click", ".eph-mrow", function (e, t) {
      var uname = t.getAttribute("data-uname");
      ta.value = ta.value.replace(/@([A-Za-z0-9_]{1,20})$/, "@" + uname + " "); mpop.classList.remove("open"); ta.focus();
    });
    document.addEventListener("click", function (e) { if (!cmp.contains(e.target)) { if (pop) pop.classList.remove("open"); if (mpop) mpop.classList.remove("open"); } });
  }
  function positionMentionPop(ta, pop) { pop.style.left = "12px"; pop.style.top = (ta.offsetTop + 30) + "px"; }
  function textBeforeCursor(ta) { return ta.value.slice(0, ta.selectionStart); }
  function insertAtCursor(ta, text) {
    var s = ta.selectionStart, e = ta.selectionEnd;
    ta.value = ta.value.slice(0, s) + text + ta.value.slice(e);
    ta.selectionStart = ta.selectionEnd = s + text.length; ta.focus();
  }
  function applyMd(ta, kind) {
    var s = ta.selectionStart, e = ta.selectionEnd, sel = ta.value.slice(s, e) || "";
    var wrap = { bold: ["**", "**", "bold text"], italic: ["*", "*", "italic"], code: ["`", "`", "code"], quote: ["\n> ", "", "quote"], link: ["[", "](https://)", sel || "link text"] }[kind];
    if (!wrap) return;
    var text = wrap[0] + (sel || wrap[2]) + wrap[1];
    ta.value = ta.value.slice(0, s) + text + ta.value.slice(e);
    ta.focus(); ta.selectionStart = s + wrap[0].length; ta.selectionEnd = s + wrap[0].length + (sel || wrap[2]).length;
  }

  function submitComment(cmp, ta, ctx) {
    var md = ta.value.trim();
    if (!md) return;
    if (!isSignedIn()) return openAuthModal("signin");
    if (!gateLinks(md)) return;  // new-account link gate (server floor: migration 0003)
    var parentId = cmp.getAttribute("data-parent") || null;
    var btn = qs('[data-act="post"]', cmp); if (btn) btn.disabled = true;
    if (LIVE()) {
      A.getOrCreateThread(_forumState.scope, _forumState.key, threadTitle()).then(function (thread) {
        if (!thread) { toast("Sign in to post.", "err"); return; }
        var html = renderMarkdownSafe(md, ctx);
        return A.postComment(thread.id, parentId, md, html).then(function (r) {
          if (r.error) { toast("Couldn't post: " + friendlyAuthError(r.error), "err"); if (btn) btn.disabled = false; return; }
          var mentions = extractMentions(md);
          if (mentions.length && r.data) resolveAndNotifyMentions(r.data.id, mentions);
          loadAndRenderComments();
        });
      });
    } else {
      var list = PV.comments(_forumState.scope, _forumState.key) || [];
      var prof = PV.profile();
      list.push({ id: "pv" + Date.now(), parent_id: parentId, author: { id: "preview", username: prof.username, role: prof.role, badges: prof.badges, fav_team: prof.fav_team, fav_prospect: prof.fav_prospect }, score: 1, my_vote: 1, created_at: new Date().toISOString(), body_md: md });
      PV.saveComments(_forumState.scope, _forumState.key, list);
      PV.setVote("pv-self", 0);
      loadAndRenderComments();
      toast("Posted (preview).", "ok");
    }
  }
  function extractMentions(md) { var out = [], m, re = /(^|[\s(])@([A-Za-z0-9_]{2,20})\b/g; while ((m = re.exec(md))) out.push(m[2]); return out; }
  function resolveAndNotifyMentions(commentId, names) {
    Promise.all(names.map(function (n) { return A.profileByUsername(n); })).then(function (profs) {
      var ids = profs.filter(Boolean).map(function (p) { return p.id; });
      if (ids.length) A.addMentions(commentId, ids);
    });
  }

  function doVote(cid, val, row) {
    var scoreEl = qs("[data-score]", row), upBtn = qs(".eph-vbtn.up", row), downBtn = qs(".eph-vbtn.down", row);
    var cur = upBtn.classList.contains("on") ? 1 : downBtn.classList.contains("on") ? -1 : 0;
    var next = cur === val ? 0 : val;
    var delta = next - cur;
    scoreEl.textContent = (parseInt(scoreEl.textContent, 10) || 0) + delta;
    upBtn.classList.toggle("on", next === 1); downBtn.classList.toggle("on", next === -1);
    if (LIVE()) A.vote(cid, next).then(function (r) { if (r.error) { toast("Vote failed.", "err"); loadAndRenderComments(); } });
    else {
      var list = PV.comments(_forumState.scope, _forumState.key) || [];
      list.forEach(function (c) { if (c.id === cid) { c.score = (c.score || 0) + delta; c.my_vote = next; } });
      PV.saveComments(_forumState.scope, _forumState.key, list);
    }
  }

  // ===========================================================================
  // Part 2/7 - public profile modal (avatar · flair · karma · follow · activity).
  // Opened by clicking any username (.eph-uname); a modal avoids clashing with
  // the PROSPX hash router. Part 7 adds the follow button + recent activity.
  // ===========================================================================
  var PV_FOLLOWS = "eph-preview.follows";
  function pvFollows() { try { return JSON.parse(localStorage.getItem(PV_FOLLOWS) || "[]"); } catch (e) { return []; } }
  function pvSetFollow(uname, on) { var s = pvFollows().filter(function (u) { return u !== uname; }); if (on) s.push(uname); try { localStorage.setItem(PV_FOLLOWS, JSON.stringify(s)); } catch (e) {} }
  function openProfile(username) {
    if (!username) return;
    var body = document.createElement("div");
    body.innerHTML = '<div class="eph-formmsg info">Loading…</div>';
    openModal("@" + username, body);
    var demoAuthors = { scout_mendoza: { username: "scout_mendoza", role: "member", karma: 412, badges: ["beta_tester", "contributor"], fav_team: "LAD", fav_prospect: { name: "Roki Sasaki" } }, farm_report: { username: "farm_report", role: "moderator", karma: 980, badges: ["beta_tester"], fav_team: "BAL", fav_prospect: { name: "Samuel Basallo" } }, pitchlab: { username: "pitchlab", role: "member", karma: 57, badges: [], fav_team: "NYM", fav_prospect: { name: "Jett Williams" } } };
    var meProf = currentProfile();
    var profP = (LIVE() && A.profileByUsername) ? A.profileByUsername(username)
      : Promise.resolve((meProf && meProf.username === username) ? meProf : (demoAuthors[username] || { username: username, karma: 0, badges: [] }));
    profP.then(function (prof) {
      prof = prof || { username: username };
      var isSelf = meProf && (meProf.username === prof.username);
      var followBtn = (isSignedIn() && !isSelf) ? '<button class="eph-btn sm" data-act="follow">Follow</button>' : "";
      body.innerHTML =
        '<div style="display:flex;gap:16px;align-items:center;padding:2px 2px 16px;border-bottom:3px double var(--border);margin-bottom:14px;">' +
          avatarHTML(prof, "lg") +
          '<div style="flex:1;min-width:0;">' + flairHTML(prof, { avatar: false }) +
            '<div style="font-family:var(--font-retro-mono);font-size:12px;color:var(--text-tertiary);margin-top:6px;">' + (prof.karma || 0) + ' karma · <span data-followers> - </span> followers</div></div>' +
          followBtn +
        "</div>" +
        '<div class="eph-mod-sec">Recent activity</div><div data-activity><div class="eph-formmsg info">Loading…</div></div>';
      // follower count
      if (LIVE() && A.followCounts && prof.id) A.followCounts(prof.id).then(function (cc) { var el = qs("[data-followers]", body); if (el) el.textContent = cc.followers; });
      else { var el = qs("[data-followers]", body); if (el) el.textContent = (pvFollows().indexOf(prof.username) >= 0 ? 1 : 0); }
      // follow button state + wiring
      var fb = qs('[data-act="follow"]', body);
      if (fb) {
        function paint(on) { fb.textContent = on ? "Following ✓" : "Follow"; fb.classList.toggle("ghost", on); }
        var following = false;
        if (LIVE() && A.isFollowing && prof.id) A.isFollowing(prof.id).then(function (v) { following = v; paint(v); });
        else { following = pvFollows().indexOf(prof.username) >= 0; paint(following); }
        fb.addEventListener("click", function () {
          following = !following; paint(following);
          if (LIVE() && prof.id) (following ? A.follow(prof.id) : A.unfollow(prof.id));
          else pvSetFollow(prof.username, following);
          toast(following ? "Following @" + prof.username : "Unfollowed @" + prof.username, "ok");
        });
      }
      // recent activity
      var actEl = qs("[data-activity]", body);
      var actP = (LIVE() && A.userComments && prof.id) ? A.userComments(prof.id, 8) : Promise.resolve(previewUserActivity(prof.username));
      actP.then(function (rows) {
        actEl.innerHTML = (rows && rows.length) ? rows.map(activityRowHTML).join("")
          : '<div class="eph-formmsg info">No recent posts.</div>';
      });
    });
  }
  function previewUserActivity(uname) {
    var now = Date.now();
    return [
      { body_md: "Quietly one of the cleaner risers on the board…", created_at: new Date(now - 6 * 3600000).toISOString(), threads: { scope: "prospect", entity_key: "jesus_made", title: "Jesús Made" } },
      { body_md: "Agreed - the per-source spread is tightening.", created_at: new Date(now - 2 * 86400000).toISOString(), threads: { scope: "farm", entity_key: "BAL", title: "BAL farm system" } }
    ];
  }
  function activityRowHTML(r) {
    var t = r.threads || {}; var href = threadHref({ scope: t.scope, entity_key: t.entity_key, board_slug: t.board_slug });
    return '<a class="eph-thread-row" href="' + escAttr(href) + '"><span class="eph-thread-title">' + esc((r.body_md || "").slice(0, 90)) + '</span>' +
      '<span class="eph-thread-meta">' + esc(threadTitleText(t) || t.title || "") + " · " + timeAgo(r.created_at) + "</span></a>";
  }
  // Activity feed (followed users + watchlisted prospects).
  function openFeed() {
    var body = document.createElement("div");
    body.innerHTML = '<div class="eph-formmsg info">Loading your feed…</div>';
    openModal("Your feed", body);
    var src = (LIVE() && A.activityFeed) ? A.activityFeed(20) : Promise.resolve(previewFeed());
    Promise.resolve(src).then(function (rows) {
      rows = rows || [];
      if (!rows.length) { body.innerHTML = '<div class="eph-formmsg info">Follow some users (tap any username) and watchlist prospects - their activity shows up here.</div>'; return; }
      body.innerHTML = '<div class="eph-mod-sec">From people you follow + prospects you watch</div>' +
        '<div class="eph-thread-list">' + rows.map(function (r) {
          var pr = r.profiles || {};
          return '<div class="eph-thread-row" style="cursor:default;">' + avatarHTML(pr.username ? pr : { username: r.author || "user" }, "xs") +
            '<span class="eph-thread-title">' + esc((r.body_md || "").slice(0, 80)) + "</span>" +
            '<span class="eph-thread-meta">' + esc((r.threads && (threadTitleText(r.threads) || r.threads.title)) || "") + " · " + timeAgo(r.created_at) + "</span></div>";
        }).join("") + "</div>";
    });
  }
  function previewFeed() {
    var now = Date.now();
    return [
      { author: "farm_report", profiles: { username: "farm_report" }, body_md: "System take: the upper levels finally have real depth.", created_at: new Date(now - 40 * 60000).toISOString(), threads: { scope: "farm", entity_key: "BAL", title: "BAL farm system" } },
      { author: "scout_mendoza", profiles: { username: "scout_mendoza" }, body_md: "If the hit tool is real, this is a top-15 name by July.", created_at: new Date(now - 5 * 3600000).toISOString(), threads: { scope: "prospect", entity_key: "jesus_made", title: "Jesús Made" } }
    ];
  }

  // ===========================================================================
  // Part 3 - Account watchlist. Model: localStorage stays the UI source of truth
  // (so logged-out is byte-for-byte unchanged); the account is a synced mirror - 
  // pulled down on login (with a merge prompt for device-local extras) and pushed
  // up on every star toggle. Watchlist = the broad TRACKING set; favorites = a
  // curated SHOWCASE subset, so a #1 favorite is auto-tracked (reconciliation).
  // ===========================================================================
  var WL_KEY = "prospect-tracker.watchlist";
  var FWL_KEY = "prospect-tracker.farm-watchlist";
  var _watchSynced = false;
  function lsArr(k) { try { var a = JSON.parse(localStorage.getItem(k) || "[]"); return Array.isArray(a) ? a : []; } catch (e) { return []; } }
  function lsSetArr(k, a) { try { localStorage.setItem(k, JSON.stringify(a)); } catch (e) {} }
  function refreshWatchUI() {
    try {
      if (window.syncWatchlistButtons) window.syncWatchlistButtons();
      if (window.syncFarmWatchlistButtons) window.syncFarmWatchlistButtons();
      if (window.updateWatchlistTabBadge) window.updateWatchlistTabBadge();
      if (window.state && window.state.section === "watchlist" && window.renderWatchlist) window.renderWatchlist();
    } catch (e) {}
  }
  // mirror a local star toggle up to the signed-in account (called from prospx)
  function onWatchChange(type, key, isIn) {
    if (!LIVE() || !A.isSignedIn()) return; // logged-out → localStorage fallback only
    if (isIn) A.addWatch(type, key); else A.removeWatch(type, key);
  }
  // ensure an entity is on the watchlist (used to reconcile a #1 favorite → tracked)
  function ensureWatched(type, key) {
    var k = type === "farm" ? FWL_KEY : WL_KEY;
    var arr = lsArr(k); if (arr.indexOf(key) < 0) { arr.push(key); lsSetArr(k, arr); }
    if (LIVE() && A.isSignedIn()) A.addWatch(type, key);
    refreshWatchUI();
  }
  // on sign-in: pull account list, prompt-merge any device-local extras, reconcile
  function syncWatchlistOnLogin() {
    if (!LIVE() || !A.isSignedIn() || _watchSynced) return;
    _watchSynced = true;
    A.getWatchlist().then(function (rows) {
      var acct = { prospect: [], farm: [] };
      (rows || []).forEach(function (r) { if (acct[r.entity_type]) acct[r.entity_type].push(r.entity_key); });
      var newP = lsArr(WL_KEY).filter(function (k) { return acct.prospect.indexOf(k) < 0; });
      var newF = lsArr(FWL_KEY).filter(function (k) { return acct.farm.indexOf(k) < 0; });
      function accountOnly() { lsSetArr(WL_KEY, acct.prospect); lsSetArr(FWL_KEY, acct.farm); refreshWatchUI(); }
      function union() {
        lsSetArr(WL_KEY, acct.prospect.concat(newP)); lsSetArr(FWL_KEY, acct.farm.concat(newF));
        A.mergeLocalWatchlist({ prospect: newP, farm: newF }).then(refreshWatchUI);
        refreshWatchUI();
      }
      if (newP.length + newF.length > 0) openMergePrompt(newP.length + newF.length, union, accountOnly);
      else accountOnly();
    });
  }
  function openMergePrompt(n, onMerge, onKeep) {
    var body = document.createElement("div");
    body.innerHTML =
      '<div class="eph-formmsg info">You have <strong>' + n + "</strong> tracked item" + (n === 1 ? "" : "s") + " saved on this device that aren't on your account watchlist yet.</div>" +
      '<p class="eph-altline" style="text-align:left;color:var(--text-secondary);">Merge them into your eephus.io watchlist so they sync across devices and feed FV-change alerts?</p>' +
      '<button class="eph-btn block" data-act="merge">Merge ' + n + " into my account</button>" +
      '<button class="eph-btn ghost block" data-act="keep" style="margin-top:8px;">No, just use my account watchlist</button>';
    openModal("Sync your watchlist", body);
    on(body, "click", '[data-act="merge"]', function () { onMerge(); closeModal(); toast("Watchlist merged & synced.", "ok"); });
    on(body, "click", '[data-act="keep"]', function () { onKeep(); closeModal(); });
  }

  // ===========================================================================
  // Forums aggregation - homepage module + /forums index + article threads.
  // Hydrated client-side: LIVE queries Supabase threads (bump / Hot ordering);
  // unconfigured PREVIEW synthesizes a believable set from real prospects so the
  // module reads as a live destination. A thread bumps to the top on new comments
  // (last_activity_at) - the same row the homepage module and index surface first.
  // ===========================================================================
  function threadHref(t) {
    if (t.scope === "prospect") return "/prospx/#player=" + encodeURIComponent(t.entity_key) + "&ptab=discussion";
    if (t.scope === "farm") return "/prospx/#farm-org=" + encodeURIComponent(t.entity_key) + "&ftab=discussion";
    if (t.scope === "article") return "/articles/" + encodeURIComponent(t.entity_key) + "/";
    if (t.scope === "board") return "/forums/#board=" + encodeURIComponent(t.board_slug || "general");
    return "/forums/";
  }
  function threadTitleText(t) {
    if (t.title) return t.title;
    if (t.scope === "prospect") { var p = PX().findPlayer && PX().findPlayer(t.entity_key); return p ? p.player_name : t.entity_key; }
    if (t.scope === "farm") return (t.entity_key || "") + " farm system";
    return t.entity_key || "Discussion";
  }
  function threadScopeTag(t) { return ({ prospect: "Prospect", farm: "Farm", article: "Article", board: (t.board_slug || "Board") })[t.scope] || "Thread"; }
  function threadLogo(t) {
    if (!PX().teamLogoURL) return null;
    if (t.scope === "farm") return PX().teamLogoURL(t.entity_key);
    if (t.scope === "prospect" && PX().findPlayer) { var p = PX().findPlayer(t.entity_key); return p && p.org ? PX().teamLogoURL(p.org) : null; }
    return null;
  }
  function threadRowHTML(t) {
    var logo = threadLogo(t);
    var n = t.comment_count || 0;
    return '<a class="eph-thread-row" href="' + escAttr(threadHref(t)) + '">' +
      (logo ? '<img class="eph-thread-logo" src="' + escAttr(logo) + '" alt="" loading="lazy">' : '<span class="eph-thread-tag">' + esc(threadScopeTag(t)) + "</span>") +
      '<span class="eph-thread-title">' + esc(threadTitleText(t)) + "</span>" +
      '<span class="eph-thread-meta">' + n + " " + (n === 1 ? "comment" : "comments") + " · " + timeAgo(t.last_activity_at) + "</span></a>";
  }
  function previewThreads() {
    var now = Date.now(), counts = [14, 9, 7, 5, 4, 3];
    var pool = (PX().prospects ? PX().prospects() : []).slice().sort(function (a, b) { return (b.fv_close || 0) - (a.fv_close || 0); }).slice(0, 6);
    if (pool.length) {
      return pool.map(function (p, i) {
        return { scope: "prospect", entity_key: p.player_key, title: p.player_name, comment_count: counts[i] || 2, hot_score: (p.fv_close || 50) + (counts[i] || 2), last_activity_at: new Date(now - (i + 1) * 37 * 60000).toISOString() };
      });
    }
    // Editorial pages (home / forums index / article) have no PROSPX index - 
    // fall back to a static believable set so the module reads as a destination.
    var samples = [
      { scope: "prospect", entity_key: "jesus_made", title: "Jesús Made", comment_count: 14 },
      { scope: "prospect", entity_key: "roki_sasaki", title: "Roki Sasaki", comment_count: 11 },
      { scope: "farm", entity_key: "BAL", title: "BAL farm system", comment_count: 9 },
      { scope: "board", board_slug: "trades", title: "Trade deadline: who's actually available?", comment_count: 7 },
      { scope: "board", board_slug: "draft", title: "2026 Draft class - early risers", comment_count: 5 },
      { scope: "prospect", entity_key: "samuel_basallo", title: "Samuel Basallo", comment_count: 4 }
    ];
    return samples.map(function (s, i) { s.last_activity_at = new Date(now - (i + 1) * 41 * 60000).toISOString(); s.hot_score = s.comment_count * 3; return s; });
  }
  function loadThreads(order) {
    if (LIVE() && A.listThreads) return A.listThreads(order, 12);
    var t = previewThreads();
    if (order === "hot") t = t.slice().sort(function (a, b) { return b.hot_score - a.hot_score; });
    return Promise.resolve(t);
  }
  function mountForumsList(el) {
    var order = "active";  // bump (last activity) by default
    function draw() {
      el.innerHTML = '<div class="eph-forumlist-bar"><div class="eph-sort">' +
        '<button data-order="active"' + (order !== "hot" ? ' class="is-active"' : "") + ">Active</button>" +
        '<button data-order="hot"' + (order === "hot" ? ' class="is-active"' : "") + ">Hot</button></div>" +
        (LIVE() ? "" : '<span class="eph-demo-flag">preview</span>') + '</div><div class="eph-thread-list"><div class="eph-formmsg info">Loading discussions…</div></div>';
      loadThreads(order).then(function (threads) {
        var list = qs(".eph-thread-list", el); if (!list) return;
        list.innerHTML = threads.length ? threads.map(threadRowHTML).join("")
          : '<div class="eph-formmsg info">No discussions yet - start one from any prospect or farm page.</div>';
      });
    }
    on(el, "click", "[data-order]", function (e, b) { order = b.getAttribute("data-order"); draw(); });
    draw();
  }
  function autoMount() {
    var home = qs("#eph-home-forums"); if (home) mountForumsList(home);
    var idx = qs("#eph-forums-index"); if (idx) mountForumsList(idx);
    var art = qs("#eph-forum-mount[data-forum-scope]");
    if (art) mountForum(art.getAttribute("data-forum-scope"), art.getAttribute("data-forum-key"), { name: art.getAttribute("data-forum-title") });
  }

  // ===========================================================================
  // Boot
  // ===========================================================================
  function boot() {
    refreshNav();
    autoMount();
    if (A && A.onAuthChange) A.onAuthChange(function () { refreshNav(); remountForumIfPresent(); syncWatchlistOnLogin(); });
    // Any username (.eph-uname) opens the profile modal instead of navigating - 
    // avoids clashing with the PROSPX hash router; href stays as a no-JS fallback.
    document.addEventListener("click", function (e) {
      var a = e.target.closest && e.target.closest(".eph-uname");
      if (!a) return;
      var m = (a.getAttribute("href") || "").match(/#u=([A-Za-z0-9_]+)/);
      if (m) { e.preventDefault(); openProfile(m[1]); }
    });
  }
  var ready = (A && A.ready) ? A.ready() : Promise.resolve();
  ready.then(function () {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot, { once: true });
    else boot();
  });

  // Public surface used by PROSPX hooks + onboarding refresh.
  window.EephusUI = {
    mountForum: mountForum,
    openAuthModal: openAuthModal,
    openOnboarding: openOnboarding,
    refreshNav: refreshNav,
    flairHTML: flairHTML,
    renderMarkdownSafe: renderMarkdownSafe,
    onWatchChange: onWatchChange
  };
})();
