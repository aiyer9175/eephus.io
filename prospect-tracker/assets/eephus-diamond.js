// eephus.io - the Diamond gating contract. ONE reader of the gate, site-wide.
// Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
//
// Written 2026-08-16. Before this file, every Diamond module client carried a
// private copy of the gate read: dynasty/redraft/dfs each had a dcfg() block
// that consulted EEPHUS_DIAMOND.isMember and EEPHUS_DIAMOND.previewRows, two
// keys assets/diamond-config.js has never defined, so the day the flag flipped
// a PAYING member would have been capped at 25 rows like everyone else.
// betting.js probed EephusAccount.isDiamond() synchronously at boot, before
// the deferred account layer could resolve a session, so a member's first
// paint would have been the preview slice. cards.js had no gate at all.
//
// This file is now the only script that reads window.EEPHUS_DIAMOND besides
// diamond.js (the pass page, another lane) and build_site's build-time parse.
// Module clients call window.EephusDiamond and nothing else.
//
// THE DEAD-MAN'S SWITCH. gating() answers false, with one console.warn naming
// why, whenever the flag is on but the account layer cannot answer (no
// window.EephusAccount, or EephusAccount.enabled() returns false because
// assets/eephus-config.js is absent). A gate nobody can pass is not a gate,
// it is an outage: every reader would be capped behind a join button that
// cannot complete a signup. The check runs at call time, never cached at
// script eval, because this file loads BEFORE eephus-account.js in the
// deferred order and the account layer's answer changes as sessions resolve.
(function () {
  "use strict";
  var W = (typeof window !== "undefined") ? window : this;

  function cfg() { return W.EEPHUS_DIAMOND || {}; }
  function account() { return W.EephusAccount || null; }

  var warned = false;
  function gating() {
    if (!cfg().gating) return false;
    var a = account();
    var ok = false;
    if (a && typeof a.enabled === "function") {
      try { ok = !!a.enabled(); } catch (e) { ok = false; }
    }
    if (!ok) {
      if (!warned) {
        warned = true;
        try {
          console.warn("EephusDiamond: the gating flag is on but the account " +
            "layer " + (a ? "is not configured (EephusAccount.enabled() is false)"
                          : "is absent (no window.EephusAccount)") +
            ", so nobody can sign in or hold a membership. The gate answers " +
            "OPEN rather than cap every reader behind a join button that " +
            "cannot complete.");
        } catch (e) { /* no console in this engine; the answer still holds */ }
      }
      return false;
    }
    return true;
  }

  // A safe probe, never a throw: absent account layer means not a member.
  function member() {
    var a = account();
    try { return !!(a && a.isDiamond && a.isDiamond()); } catch (e) { return false; }
  }

  // "Gated" as far as THIS paint can know. Entitlement is async (the session
  // and profile resolve after boot), so a caller must subscribe through
  // onEntitlement() below and re-render when the answer changes, not treat one
  // synchronous read as final.
  function gated() { return gating() && !member(); }

  // Per-module preview caps live in diamond-config.js (preview_rows) so the
  // config stays the one file that describes the gate. An unknown module, a
  // missing map, or a junk value all fall back to 25 rather than to zero.
  var DEFAULT_PREVIEW = 25;
  function previewRows(mod) {
    var map = cfg().preview_rows;
    if (!map || !Object.prototype.hasOwnProperty.call(map, mod)) return DEFAULT_PREVIEW;
    var n = map[mod];
    return (typeof n === "number" && isFinite(n) && n > 0) ? Math.floor(n) : DEFAULT_PREVIEW;
  }

  function price() {
    var c = cfg();
    return { month: c.price_usd_month, founding: c.founding_rate_usd };
  }

  // ---- entitlement subscription --------------------------------------------
  // onEntitlement(cb) fires cb({gating, member, gated}) once after
  // DOMContentLoaded (every deferred script, eephus-account.js included, has
  // executed by then) and again whenever an auth change moves the answer. The
  // auth hook is EephusAccount.onAuthChange (assets/eephus-account.js); it
  // fires on session/profile changes and once immediately when already ready,
  // so re-fires are filtered against the last snapshot each subscriber saw,
  // which is what keeps that immediate call from double-painting a page that
  // just rendered. No polling anywhere: if the account layer ever stops
  // exposing onAuthChange, subscribers still get the one post-DOM fire and the
  // account layer owes this seam a call.
  var SUBS = [];
  var DOM_FIRED = false;
  var AUTH_HOOKED = false;
  function snapshot() { return { gating: gating(), member: member(), gated: gated() }; }
  function keyOf(s) { return (s.gating ? "g" : "-") + (s.member ? "m" : "-"); }
  function fireOne(rec, s) {
    rec.fired = true;
    rec.key = keyOf(s);
    try { rec.cb(s); } catch (e) { /* a subscriber's error is not the gate's */ }
  }
  function fireAll(onlyChanged) {
    var s = snapshot(), k = keyOf(s);
    for (var i = 0; i < SUBS.length; i++) {
      var rec = SUBS[i];
      if (onlyChanged && rec.fired && rec.key === k) continue;
      fireOne(rec, s);
    }
  }
  function hookAuth() {
    if (AUTH_HOOKED) return;
    var a = account();
    if (!a || typeof a.onAuthChange !== "function") return;
    AUTH_HOOKED = true;
    try { a.onAuthChange(function () { fireAll(true); }); }
    catch (e) { AUTH_HOOKED = false; }
  }
  function onDomReady() {
    DOM_FIRED = true;
    hookAuth();
    fireAll(false);
  }
  function onEntitlement(cb) {
    if (typeof cb !== "function") return;
    var rec = { cb: cb, fired: false, key: null };
    SUBS.push(rec);
    // A subscriber arriving after DOMContentLoaded (a lazily injected fantasy
    // client) gets its initial fire immediately instead of never.
    if (DOM_FIRED) { hookAuth(); fireOne(rec, snapshot()); }
  }

  W.EephusDiamond = {
    config: cfg,
    gating: gating,
    member: member,
    gated: gated,
    previewRows: previewRows,
    price: price,
    onEntitlement: onEntitlement
  };

  if (typeof document !== "undefined" && document.addEventListener) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", onDomReady, { once: true });
    } else {
      onDomReady();
    }
  } else {
    DOM_FIRED = true; // no DOM in this engine; subscribers fire on arrival
  }
})();
