/* Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
 * Unauthorized copying of this file, via any medium is strictly prohibited
 * Proprietary and confidential
 * Written by Noah J. Dengler (@ARKNDJL), 2026 */

/* /standings/ charts (STANDINGS_5, behind standings_core.STANDINGS_CHARTS), loaded by
   standings.js on the first Race disclosure or the Charts view; drawn by
   EEPHUS_HUB.lineChart and scatter. Every plotted value is served except C1's y,
   W minus L of one race tuple. Two clubs at most carry colour; nothing past the last date. */
(() => {
  "use strict";
  const H = window.EEPHUS_HUB, X = window.EephusStandings || {}, MO = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(" ");
  const DV = { ALE: "AL East", ALC: "AL Central", ALW: "AL West", NLE: "NL East", NLC: "NL Central", NLW: "NL West" };
  const LG = { AL: "American League", NL: "National League" };
  const MK = [["div", "Division", 0], ["post", "Playoffs", 1], ["pen", "Pennant", 3, 0], ["ws", "World Series", 4, 1]];   // regular, post field
  const memo = {}, st = {}, defs = {}, V = ["var(--viz-1)", "var(--viz-2)"];
  const esc = s => String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  const num = x => typeof x === "number" && isFinite(x);
  const md = d => MO[+d.slice(5, 7) - 1] + " " + +d.slice(8);
  const lg = d => X.ymd(d, true);
  const sg = v => v == null ? "-" : (v > 0 ? "+" : "") + v;
  const p1 = v => num(v) ? v.toFixed(1) : "-";
  const f2 = v => v.toFixed(2);
  const rk = k => (a, b) => ((a.ranks || {})[k] || 99) - ((b.ranks || {})[k] || 99);
  const box = (k, m) => EephusState.html(k, esc(m), "stc-note");
  const day = (d, n) => new Date(Date.parse(d + "T00:00:00Z") + n * 864e5).toISOString().slice(0, 10);
  const btns = (cls, list, cur) => list.map(q => `<button type="button" class="${cls}" data-v="${q[0]}" aria-pressed="${q[0] === cur}">${esc(q[1])}</button>`).join("");
  const tbl = (hd, rows) => `<div class="table-scroll-x"><table class="stc-tbl"><thead><tr>${hd.map(h => `<th scope="col">${esc(h)}</th>`).join("")}</tr></thead><tbody>` +
    rows.map(r => "<tr>" + r.map((c, i) => i ? `<td>${esc(c)}</td>` : `<th scope="row">${esc(c)}</th>`).join("") + "</tr>").join("") + "</tbody></table></div>";
  // glossary ids (data-glmap): the first links the title, the rest print by abbreviation
  let GL = { h: {}, c: {} };
  const gt = (id, s) => id ? `<span data-gl="${esc(id)}">${s}</span>` : s;
  const terms = k => { const ids = (GL.c[k.slice(0, 2)] || []).slice(1);
    return ids.length ? ` <span class="stc-terms">Terms: ${ids.map(id => gt(id, esc(Object.keys(GL.h).find(a => GL.h[a] === id)))).join(", ")}.</span>` : ""; };
  const fig = (k, title, read, src, x) => `<figure class="stc-fig" data-k="${k}" tabindex="0"><figcaption><b>${gt((GL.c[k.slice(0, 2)] || [])[0], esc(title))}</b> <span>${esc(read)}</span>${terms(k)} <span class="stc-src">${esc(src)}</span></figcaption>${x || ""}` +
    '<div class="stc-chips" role="group" aria-label="Highlight clubs"></div><div class="stc-plot"></div><p class="stc-read" aria-live="polite"></p><details class="stc-num"><summary>Numbers</summary></details></figure>';

  // the highlight rule: the followed clubs, else the view's first two; a tap
  // fills an empty slot, else replaces the older; colour follows the club
  function state(k, clubs, mine) {
    const s = st[k] = st[k] || {};
    if (!s.hl) { const d = clubs.filter(c => mine.includes(c)).concat(clubs.filter(c => !mine.includes(c))); s.hl = [d[0], d[1]]; s.old = 0; }
    return s;
  }
  const col = (s, c) => V[s.hl.indexOf(c)] || "var(--text-tertiary)";
  const ord = (s, clubs) => clubs.filter(c => !s.hl.includes(c)).concat(s.hl.filter(c => clubs.includes(c)));

  // a time chart: v[c] aligned with xs (null where nothing is drawn); hv(c, i) the value held at i
  function tdef(k, sk, ctx, clubs, xs, v, hv, fv, o, aria, pre) {
    const n = xs.length, h = o.held;
    state(sk, clubs, ctx.mine);
    defs[k] = { t: 1, sk, clubs, n,
      draw: (s, w, g) => H.lineChart(ord(s, clubs).map(c => { const on = s.hl.includes(c); return { label: c, id: c, color: col(s, c), sw: on ? 2.5 : 1, nomark: !on, strong: on,
        sq: h && on, step: !!h, breaks: !h, end: c + " " + fv(hv(c, n - 1)), pts: xs.map((d, i) => ({ y: d, v: v[c][i] })) }; }),
      Object.assign({ xs, width: w, gap: 11, hits: false, table: false, geo: g, xfmt: md, pr: 60, fmt: fv, tickFmt: fv,
        xticks: xs.filter((d, i) => i && d.slice(5, 7) !== xs[i - 1].slice(5, 7)),
        aria: `${aria}, ${lg(xs[0])} to ${lg(xs[n - 1])}: ` + clubs.map(c => c + " " + fv(hv(c, n - 1))).join(", ") }, o,
        { height: Math.max(o.height || 220, clubs.length * 11 + 50) })),
      read: (s, i) => md(xs[i]) + (h && !h[xs[i]] ? " (no record that day; the last one is held)" : "") + ": " +
        clubs.filter(c => num(hv(c, i))).sort((a, b) => hv(b, i) - hv(a, i)).slice(0, 8).map(c => c + " " + fv(hv(c, i))).join(", "),
      table: () => (pre || "") + tbl(["Date"].concat(clubs), xs.map((d, i) => [d].concat(clubs.map(c => fv(v[c][i])))).filter(r => !h || h[r[0]]).reverse()) };
  }

  // C1 division race, one shared y and x domain
  function c1(ctx, R, dv, M) {
    const S = ctx.S, k = "c1-" + dv, v = {}, clubs = S.rows.filter(r => r.div === dv).sort(rk("div")).map(r => r.code);
    clubs.forEach(c => { v[c] = R.clubs[c].map(t => t[0] - t[1]); });   // the one named derivation
    tdef(k, k, ctx, clubs, R.dates, v, (c, i) => v[c][i], sg, { dom: [-M, M], refs: [{ v: 0, label: ".500", solid: 1 }] }, `Division race, ${DV[dv]}, ${S.season}, wins minus losses`);
    return fig(k, "Division race: " + DV[dv], "Wins minus losses after every date; the zero line is .500.", `Source: ${S.season}-race.json, from MLB's game results.`);
  }

  // C2 wild card race: the served wc_gap
  function c2(ctx, R, l) {
    const S = ctx.S, k = "c2-" + l, s0 = st[k] = st[k] || {}, all = R.dates, n = all.length, gap = R.wc_gap, v = {};
    const cut = day(all[n - 1], -60), from = s0.whole ? 0 : Math.max(0, all.findIndex(d => d >= cut)), xs = all.slice(from);
    const z = c => num(gap[c][n - 1]) ? gap[c][n - 1] : -99;
    let clubs = S.rows.filter(r => r.lg === l).map(r => r.code).filter(c => s0.all ? gap[c].slice(from).some(num) : z(c) > -11 && z(c) <= 10)
      .sort((a, b) => z(b) - z(a) || (a < b ? -1 : 1));
    if (!s0.all) clubs = clubs.slice(0, 8);
    clubs.forEach(c => { v[c] = gap[c].slice(from); });
    const hv = (c, i) => { if (i === xs.length - 1) while (i > 0 && !num(v[c][i])) i--; return v[c][i]; };
    tdef(k, k, ctx, clubs, xs, v, hv, sg, { refs: [{ v: 0, label: "Last wild card spot" }] }, `Wild card race, ${LG[l]}, ${S.season}, games from the last wild card spot`,
      '<p class="stc-tnote">Past dates: ties at the line are not broken.</p>');
    return fig(k, "Wild card race: " + LG[l], "Games ahead of (+) or behind (-) the club holding the last wild card spot on each date; that date's division leaders are left out.",
      `Source: ${S.season}-race.json, from MLB's game results.`,
      '<div class="stc-row">' + btns("stc-tg", [["whole", s0.whole ? "Last 60 days" : "Whole season"], ["all", s0.all ? "Clubs within 10 games" : "Show all clubs"]], "") + "</div>");
  }

  // C3 odds over time: the phist file as copied, steps held flat between records
  function c3(ctx, P) {
    const S = ctx.S, Rg = P.regular, Po = P.post, ra = Rg.as_of, pa = Po.as_of, s0 = st.c3 = st.c3 || {}, from = ctx.entry.phist_from;
    const mks = MK.filter(m => ra.length || m[3] != null && pa.length), xs = [], xi = {}, rec = {}, v = {};
    if (!mks.some(m => m[0] === s0.m)) s0.m = pa.length ? "pen" : "post";
    const m = mks.find(q => q[0] === s0.m), end = ra.concat(pa).sort().pop();
    for (let d = from; d <= end; d = day(d, 1)) { xi[d] = xs.length; xs.push(d); }
    [[ra, Rg.clubs, m[2]], [pa, Po.clubs, m[3]]].forEach(([ds, cl, f]) => ds.forEach((d, j) => {
      rec[d] = 1;
      if (f != null) for (const c in cl) { v[c] = v[c] || xs.map(() => null); const q = cl[c][j]; if (q && num(q[f])) v[c][xi[d]] = q[f] * 100; }
    }));
    const hv = (c, i) => { while (i > 0 && !num(v[c][i])) i--; return v[c][i]; }, e = xs.length - 1;
    const clubs = Object.keys(v).filter(c => hv(c, e) > 0).sort((a, b) => hv(b, e) - hv(a, e) || (a < b ? -1 : 1));
    const cap = ["Implied, no market."];
    [[ra, "playoff_odds_sim"], [pa, "postseason_bracket_sim"]].forEach(([b, id]) => {
      const g = (S.registry || []).find(r => r.model_id === id);
      if (b.length && g) cap.push(g.label + ", " + g.verdict + ".");
    });
    tdef("c3", "c3" + m[0], ctx, clubs, xs, v, hv, p1, { held: rec, height: 240, yticks: [0, 25, 50, 75, 100], tickFmt: q => q + "%",
      vrefs: P.switch_as_of ? [{ x: P.switch_as_of, label: "Postseason" }] : [] }, `Odds over time, ${m[1]}, ${S.season}, percent, ${Object.keys(rec).length} recorded dates held flat between records`);
    return box("unmeasured", "The daily odds record starts " + lg(from) + ".") + fig("c3", "Odds over time: " + m[1], cap.join(" "),
      `Source: ${S.season}-phist.json, ` + (ra.length ? `the ${Rg.source}${pa.length ? " and the bracket simulator's daily record" : ""}.`
        : `the bracket simulator's daily record; the ${Rg.source} holds no regular-season entry for this season.`),
      `<div class="stc-row" role="group" aria-label="Market">${btns("stc-mk", mks, m[0])}</div>`);
  }

  // C4 runs scored and allowed a game, the RA axis inverted
  function c4(ctx) {
    const S = ctx.S, k = S.k90, rows = S.rows.filter(r => num(r.rs_g) && num(r.ra_g)).sort(rk("mlb")), clubs = rows.map(r => r.code), all = [];
    const rd = rows.slice().sort((a, b) => b.rd - a.rd).map(r => r.code), tag = rd.slice(0, 3).concat(rd.slice(-3));
    rows.forEach(r => all.push(r.rs_g, r.ra_g));
    state("c4", clubs, ctx.mine);
    defs.c4 = { rows, clubs, at: r => [r.rs_g, r.ra_g],
      draw: (s, w, g) => {
        const nt = H.niceTicks(Math.min(...all), Math.max(...all), { pad: 0.02 }), a = nt.lo, b = nt.hi, lines = [{ pts: [[a, a], [b, b]], label: ".500", dash: "4 3", id: "iso500" }];
        if (num(k)) lines.push({ pts: [[a, k * a], [b, k * b]], label: "90-win pace", dash: "4 3", id: "iso90" });
        return H.scatter(ord(s, clubs).map(c => { const r = rows[clubs.indexOf(c)], h = s.hl.includes(c);
          return { x: r.rs_g, y: r.ra_g, id: c, shape: "sq", hollow: r.lg === "NL", color: col(s, c), ring: h, strong: h, tag: h || tag.includes(c) ? c : null, label: c }; }),
        { width: w, height: 300, xMin: a, xMax: b, yMin: a, yMax: b, nice: true, yInvert: true, lines, geo: g, xLabel: "Runs scored a game", yLabel: "Runs allowed a game, fewest at the top",
          aria: `Runs scored and allowed a game, ${S.season}: ` + rows.map(r => `${r.code} ${f2(r.rs_g)} and ${f2(r.ra_g)}`).join(", ") });
      },
      read: (s, i) => { const r = rows[i]; return `${r.code}: ${f2(r.rs_g)} runs scored and ${f2(r.ra_g)} allowed a game; run differential ${sg(r.rd)}.`; },
      table: () => tbl(["Club", "RS/G", "RA/G", "RD"], rows.map(r => [r.code, f2(r.rs_g), f2(r.ra_g), sg(r.rd)])) };
    return fig("c4", "Runs scored and allowed", "Per game; up and to the right is the strong corner; AL clubs filled, NL hollow." +
      (num(k) ? ` The 90-win pace line is runs allowed equal to ${k} times runs scored, from MLB's expected record exponent.`
        : " The 90-win pace line is not drawn: no expected record exponent is on file for this season."), `Source: ${S.season}.json, from MLB's standings.`);
  }

  // C5 record against expected record: dumbbells in text ink, never coloured
  function c5(ctx) {
    const S = ctx.S, ink = "var(--text-primary)", all = [], x0 = (S.rows[0] || {}).x_exp;
    const rows = S.rows.filter(r => r.x_wl && num(r.w_xw)).sort((a, b) => b.w_xw - a.w_xw || (a.code < b.code ? -1 : 1));
    rows.forEach(r => all.push(r.w, r.x_wl[0]));
    state("c5", [], []);
    defs.c5 = { rows, clubs: [], at: (r, i) => [r.w, i],
      draw: (s, w, g) => H.scatter([].concat(...rows.map((r, i) => [{ x: r.w, y: i, id: r.code + ".w", shape: "sq", color: ink, label: r.code },
        { x: r.x_wl[0], y: i, id: r.code + ".x", shape: "sq", hollow: 1, color: ink, label: r.code }])),
      { width: w, height: rows.length * 18 + 50, yMin: -0.6, yMax: rows.length - 0.4, xMin: Math.min(...all), xMax: Math.max(...all), nice: "x", yInvert: true, padR: 36, geo: g,
        xLabel: "Wins", lines: rows.map((r, i) => ({ pts: [[r.w, i], [r.x_wl[0], i]], id: r.code })),
        yTicks: rows.map((r, i) => ({ v: i, label: r.code })).concat(rows.map((r, i) => ({ v: i, label: sg(r.w_xw), right: 1, id: r.code }))),
        aria: `Record against expected record, ${S.season}: ` + rows.map(r => `${r.code} ${r.w} wins, ${r.x_wl[0]} expected, ${sg(r.w_xw)}`).join("; ") }),
      read: (s, i) => { const r = rows[i]; return `${r.code}: ${r.w} wins, ${r.x_wl[0]} expected wins (W - xW ${sg(r.w_xw)}).`; },
      table: () => tbl(["Club", "W", "xW", "W - xW"], rows.map(r => [r.code, r.w, r.x_wl[0], sg(r.w_xw)])) };
    return fig("c5", "Record against expected record", "Wins (filled) and expected wins from runs scored and allowed (hollow), sorted by wins minus expected wins.",
      `Source: ${S.season}.json, MLB's record and expected record${num(x0) ? ", Pythagorean, exponent " + x0 : ""}.`);
  }

  // drawing, the crosshair, tap to pin and the keys
  const dOf = f => defs[f.dataset.k], sOf = f => st[dOf(f).sk || f.dataset.k];
  function draw(f) {
    const d = dOf(f), s = sOf(f), p = f.querySelector(".stc-plot"), det = f.querySelector(".stc-num"), g = {};
    f.querySelector(".stc-chips").innerHTML = d.clubs.map(c => { const i = s.hl.indexOf(c);
      return `<button type="button" class="stc-chip" data-c="${c}" aria-pressed="${i >= 0}">${i >= 0 ? `<i class="stc-sw stc-sw${i + 1}"></i>` : ""}${c}</button>`; }).join("");
    p.innerHTML = d.draw(s, Math.max(280, p.clientWidth | 0), g);
    s.g = f._geo = g;
    if (det.open) det.innerHTML = "<summary>Numbers</summary>" + d.table(); else delete det.dataset.f;
    cross(f);
  }
  function cross(f) {
    const d = dOf(f), s = sOf(f), svg = f.querySelector("svg"), g = s.g, i = s.i, old = svg && svg.querySelector(".stc-x");
    if (old) old.remove();
    f.dataset.i = i == null ? "" : i;
    f.querySelector(".stc-read").textContent = i == null ? "" : d.read(s, i);
    if (i == null || !svg) return;
    const a = d.t ? null : d.at(d.rows[i], i), x = d.t ? g.x(g.xs[i]).toFixed(1) : 0;
    svg.insertAdjacentHTML("beforeend", d.t ? `<line class="stc-x" x1="${x}" y1="${g.PT}" x2="${x}" y2="${g.H - g.PB}" stroke="var(--text-secondary)"/>`
      : `<rect class="stc-x" x="${g.x(a[0]) - 7}" y="${g.y(a[1]) - 7}" width="14" height="14" fill="none" stroke="var(--text-primary)" stroke-width="1.5"/>`);
  }
  function near(f, ev) {
    const d = dOf(f), g = sOf(f).g, b = f.querySelector("svg").getBoundingClientRect(), k = g.W / b.width, px = (ev.clientX - b.left) * k, py = (ev.clientY - b.top) * k;
    if (d.t) return Math.max(0, Math.min(d.n - 1, Math.round((px - g.PL) / (g.W - g.PL - g.PR) * (d.n - 1))));
    let best = null, bd = 22;
    d.rows.forEach((r, i) => { const a = d.at(r, i), q = Math.hypot(g.x(a[0]) - px, g.y(a[1]) - py); if (q <= bd) { bd = q; best = i; } });
    return best;
  }
  function wire(root, ctx, redo) {
    const fo = t => t.closest && t.closest(".stc-fig");
    root.addEventListener("click", ev => {
      const t = ev.target, f = fo(t), b = t.closest("button"), c = b && b.dataset.c, val = b && b.dataset.v;
      if (b && b.classList.contains("stc-dv")) { ctx.setRoute("div", val); return redo(); }
      if (!f) return;
      const s = sOf(f);
      if (c) {
        if (!s.hl.includes(c)) { const i = s.hl[0] == null ? 0 : s.hl[1] == null ? 1 : s.old; if (i === s.old) s.old = 1 - i; s.hl[i] = c; }
        draw(f);
      } else if (val) { if (b.classList.contains("stc-mk")) st.c3.m = val; else st[f.dataset.k][val] = !st[f.dataset.k][val]; redo(); }
      else if (t.closest("svg")) { const i = near(f, ev); if (i == null || s.pin && s.i === i) { s.i = null; s.pin = false; } else { s.i = i; s.pin = true; } cross(f); }
    });
    ["pointermove", "pointerout"].forEach(type => root.addEventListener(type, ev => {
      const f = fo(ev.target), s = f && sOf(f);
      if (!s || s.pin || ev.pointerType === "touch") return;
      const i = type === "pointerout" ? (f.contains(ev.relatedTarget) ? s.i : null) : ev.target.closest("svg") ? near(f, ev) : s.i;
      if (i !== s.i) { s.i = i; cross(f); }
    }));
    root.addEventListener("keydown", ev => {
      const f = ev.target.matches(".stc-fig") && ev.target;
      if (!f) return;
      const d = dOf(f), s = sOf(f), n = d.t ? d.n : d.rows.length, k = ev.key, up = /Up|Left/.test(k);
      let i = s.i;
      if (k === "Escape") { s.i = null; s.pin = false; }
      else if (k === "Home" || k === "End") i = k === "Home" ? 0 : n - 1;
      else if (d.t && /Left|Right/.test(k)) i = i == null ? n - 1 : Math.max(0, Math.min(n - 1, i + (up ? -1 : 1)));
      else if (d.t && /Up|Down/.test(k)) {
        const cs = d.clubs.filter(c => c !== s.hl[1]);
        s.hl[0] = cs[(cs.indexOf(s.hl[0]) + (up ? -1 : 1) + cs.length) % cs.length]; s.old = 1;
        ev.preventDefault(); return draw(f);
      } else if (/^Arrow/.test(k)) i = i == null ? 0 : (i + (up ? -1 : 1) + n) % n;
      else return;
      ev.preventDefault();
      if (k !== "Escape") { s.i = i; s.pin = true; }
      cross(f);
    });
    root.addEventListener("toggle", ev => {
      const det = ev.target, f = det.matches(".stc-num") && fo(det);
      if (f && det.open && !det.dataset.f) { det.dataset.f = 1; det.innerHTML = "<summary>Numbers</summary>" + dOf(f).table(); }
    }, true);
  }
  const drawAll = el => el.querySelectorAll(".stc-fig").forEach(draw);
  const get = (ctx, p) => memo[p] || (memo[p] = ctx.get(p).then(r => r.json()).catch(e => { delete memo[p]; throw e; }));

  // a Race disclosure (ctx.div) or the Charts view
  function mount(el, ctx) {
    const S = ctx.S, e = ctx.entry || {}, Y = S.season, none = box("unmeasured", `Game-by-game results for ${Y} are not on file.`);
    const nodds = box("unmeasured", "The odds group has no record for this season.");
    const sec = (c, t, b) => `<section class="stc-sec" data-c="${c}"><h3 class="sp-boxhead">${t}</h3>${b}</section>`;
    const gw = ctx.wire || (() => 0);
    GL = ctx.gl || GL;
    if (!el._w) { el._w = 1; wire(el, ctx, () => mount(el, ctx)); }
    if (!el.firstChild) el.innerHTML = box("loading", "Loading the race.");
    return (e.race_rev ? get(ctx, `standings/${Y}-race.json?v=${encodeURIComponent(e.race_rev)}`) : Promise.resolve(null)).then(R => {
      const ok = R && R.dates.length, narrow = innerWidth < 768;
      let M = 1;
      if (ok) for (const c in R.clubs) R.clubs[c].forEach(t => { M = Math.max(M, Math.abs(t[0] - t[1])); });
      if (ctx.div) { el.innerHTML = ok ? c1(ctx, R, ctx.div, M) : none; drawAll(el); return gw(); }
      const dv = ctx.route.div || (S.rows.find(r => ctx.mine.includes(r.code)) || {}).div || "ALE";
      el.innerHTML = sec("race", "Division race", ok ? (narrow ? `<div class="stc-row" role="group" aria-label="Division">${btns("stc-dv", Object.entries(DV), dv)}</div>` : "") +
        '<div class="stc-grid3">' + Object.keys(DV).filter(d => !narrow || d === dv).map(d => c1(ctx, R, d, M)).join("") + "</div>" : none) +
        (ok ? sec("wc", "Wild card race", '<div class="stc-grid2">' + c2(ctx, R, "AL") + c2(ctx, R, "NL") + "</div>") : "") +
        sec("odds", "Odds over time", '<div class="stc-odds">' + (e.phist_rev ? box("loading", "Loading the odds record.") : nodds) + "</div>") +
        '<div class="stc-grid2">' + sec("runs", "Runs", c4(ctx)) + sec("xwl", "Expected record", c5(ctx)) + "</div>";
      drawAll(el);
      gw();
      const foc = ctx.route.chart && el.querySelector(`[data-c="${ctx.route.chart}"]`);
      if (foc && !el._f) { el._f = 1; foc.scrollIntoView(); }
      if (e.phist_rev) return get(ctx, `standings/${Y}-phist.json?v=${encodeURIComponent(e.phist_rev)}`).then(P => {
        const o = el.querySelector(".stc-odds");
        if (o) { o.innerHTML = P.regular.as_of.length + P.post.as_of.length ? c3(ctx, P) : nodds; drawAll(o); gw(); }
      });
    }).catch(() => { el.innerHTML = box("failed", "The race could not load."); });
  }

  window.EephusStandingsCharts = { mount };
})();
