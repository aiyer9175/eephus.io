// eephus.io - account layer client (Parts 1-7).
// Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
//
// The ONE boundary between the static front-end and Supabase. Everything the
// account/social layer needs (auth, profiles, favorites, watchlist, comments,
// votes, notifications) goes through `window.EephusAccount`.
//
// GRACEFUL DEGRADATION is the contract: if `window.EEPHUS_SUPABASE` is absent or
// blank (no `assets/eephus-config.js`), the Supabase SDK is never touched and
// every method is a safe no-op returning an empty/neutral value. The site then
// behaves exactly as it does today, logged-out, with the localStorage watchlist
// still working. Nothing here may throw on the happy logged-out path.
//
// SECURITY: the anon key shipped in eephus-config.js is public by design - Row-
// Level Security in supabase/migrations/0001_accounts_forums.sql, not the key,
// guards data. The service-role key is NEVER referenced here (pipeline-only).
(function () {
  "use strict";

  var CFG = (typeof window !== "undefined" && window.EEPHUS_SUPABASE) || null;
  var CONFIGURED = !!(CFG && CFG.url && CFG.anonKey);
  var SDK_URL = "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2";

  // The SDK is fetched ONLY when configured (so the logged-out/today path and
  // the test harness make zero external requests). Cached promise; resolves
  // once the UMD global `supabase.createClient` is available.
  var _sdkPromise = null;
  function _ensureSdk() {
    if (!CONFIGURED) return Promise.reject(new Error("accounts disabled"));
    if (window.supabase && window.supabase.createClient) return Promise.resolve();
    if (_sdkPromise) return _sdkPromise;
    _sdkPromise = new Promise(function (resolve, reject) {
      var s = document.createElement("script");
      s.src = SDK_URL; s.async = true;
      s.onload = function () {
        (window.supabase && window.supabase.createClient) ? resolve() : reject(new Error("SDK loaded but no createClient"));
      };
      s.onerror = function () { reject(new Error("failed to load supabase-js")); };
      document.head.appendChild(s);
    });
    return _sdkPromise;
  }

  // Lazily-created Supabase client (UMD global `supabase.createClient`). Returns
  // null until the SDK has loaded; bootstrap awaits _ensureSdk() before UI runs.
  var _client = null;
  var _initError = null;
  function client() {
    if (!CONFIGURED) return null;
    if (_client || _initError) return _client;
    if (!window.supabase || !window.supabase.createClient) return null; // SDK not ready yet
    try {
      _client = window.supabase.createClient(CFG.url, CFG.anonKey, {
        auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true }
      });
    } catch (e) {
      _initError = e;
      _client = null;
    }
    return _client;
  }

  // ---- internal session cache ------------------------------------------------
  var _session = null;          // current Supabase session or null
  var _profile = null;          // cached own profile row or null
  var _ready = false;
  var _readyResolvers = [];
  var _authListeners = [];

  function _notifyAuth() {
    for (var i = 0; i < _authListeners.length; i++) {
      try { _authListeners[i](_session, _profile); } catch (e) { /* listener errors are non-fatal */ }
    }
  }
  function _resolveReady() {
    _ready = true;
    var rs = _readyResolvers; _readyResolvers = [];
    rs.forEach(function (r) { try { r(); } catch (e) {} });
  }

  // Pull the caller's own profile row (or null). Cached; pass force=true to refetch.
  function _loadOwnProfile(force) {
    var c = client();
    if (!c || !_session) { _profile = null; return Promise.resolve(null); }
    if (_profile && !force) return Promise.resolve(_profile);
    return c.from("profiles").select("*").eq("id", _session.user.id).maybeSingle()
      .then(function (res) { _profile = res && res.data ? res.data : null; return _profile; })
      .catch(function () { return null; });
  }

  function _bootstrap() {
    // Load the SDK (configured only), create the client, then read the session.
    _ensureSdk().then(function () {
      var c = client();
      if (!c) { _resolveReady(); return; }
      c.auth.onAuthStateChange(function (_event, session) {
        _session = session || null;
        _loadOwnProfile(true).then(function () { _notifyAuth(); });
      });
      return c.auth.getSession()
        .then(function (res) {
          _session = (res && res.data && res.data.session) || null;
          return _loadOwnProfile(true);
        })
        .then(function () { _notifyAuth(); });
    })
    .catch(function () { /* unconfigured / offline / blocked - stay logged-out */ })
    .finally(function () { _resolveReady(); });
  }

  // Tiny helper: run a query builder, return {data,error}; never throw upward.
  function _safe(promise, fallback) {
    return Promise.resolve(promise).then(
      function (res) { return res; },
      function (err) { return { data: (fallback === undefined ? null : fallback), error: err }; }
    );
  }

  // ===========================================================================
  // Public API
  // ===========================================================================
  var Account = {
    // --- capability / lifecycle ----------------------------------------------
    enabled: function () { return CONFIGURED && !!client(); },
    ready: function () {
      if (_ready) return Promise.resolve();
      return new Promise(function (resolve) { _readyResolvers.push(resolve); });
    },
    session: function () { return _session; },
    user: function () { return _session ? _session.user : null; },
    isSignedIn: function () { return !!_session; },
    isVerified: function () {
      return !!(_session && _session.user && _session.user.email_confirmed_at);
    },
    profile: function () { return _profile; },
    onAuthChange: function (cb) {
      if (typeof cb !== "function") return function () {};
      _authListeners.push(cb);
      // fire once with current state if already known
      if (_ready) { try { cb(_session, _profile); } catch (e) {} }
      return function off() {
        var i = _authListeners.indexOf(cb);
        if (i >= 0) _authListeners.splice(i, 1);
      };
    },

    // --- auth (email + password primary; magic link optional secondary) ------
    // Username is passed in metadata so handle_new_user() honors it at signup.
    signUp: function (email, password, username) {
      var c = client();
      if (!c) return Promise.resolve({ data: null, error: new Error("accounts disabled") });
      var redirect = (window.location.origin || "") + "/auth/";
      return _safe(c.auth.signUp({
        email: email,
        password: password,
        options: { data: { username: username || "" }, emailRedirectTo: redirect }
      }));
    },
    signIn: function (email, password) {
      var c = client();
      if (!c) return Promise.resolve({ data: null, error: new Error("accounts disabled") });
      return _safe(c.auth.signInWithPassword({ email: email, password: password }));
    },
    // Optional secondary: passwordless sign-in link to the same email identity.
    signInWithLink: function (email) {
      var c = client();
      if (!c) return Promise.resolve({ data: null, error: new Error("accounts disabled") });
      var redirect = (window.location.origin || "") + "/auth/";
      return _safe(c.auth.signInWithOtp({ email: email, options: { emailRedirectTo: redirect } }));
    },
    resetPassword: function (email) {
      var c = client();
      if (!c) return Promise.resolve({ data: null, error: new Error("accounts disabled") });
      var redirect = (window.location.origin || "") + "/auth/reset/";
      return _safe(c.auth.resetPasswordForEmail(email, { redirectTo: redirect }));
    },
    updatePassword: function (newPassword) {
      var c = client();
      if (!c) return Promise.resolve({ data: null, error: new Error("accounts disabled") });
      return _safe(c.auth.updateUser({ password: newPassword }));
    },
    resendVerification: function (email) {
      var c = client();
      if (!c) return Promise.resolve({ data: null, error: new Error("accounts disabled") });
      return _safe(c.auth.resend({ type: "signup", email: email }));
    },
    signOut: function () {
      var c = client();
      if (!c) return Promise.resolve({ error: null });
      return _safe(c.auth.signOut());
    },

    // --- profiles ------------------------------------------------------------
    updateProfile: function (patch) {
      var c = client();
      if (!c || !_session) return Promise.resolve({ data: null, error: new Error("not signed in") });
      // role/karma are pinned server-side (trigger) even if passed - harmless.
      return _safe(
        c.from("profiles").update(patch).eq("id", _session.user.id).select().maybeSingle()
          .then(function (res) { if (res && res.data) _profile = res.data; return res; })
      );
    },
    profileByUsername: function (username) {
      var c = client();
      if (!c) return Promise.resolve(null);
      return _safe(
        c.from("profiles").select("*").eq("username", username).maybeSingle()
      ).then(function (res) { return res && res.data ? res.data : null; });
    },
    // @mention autocomplete - prefix match on username.
    searchUsernames: function (prefix, limit) {
      var c = client();
      if (!c || !prefix) return Promise.resolve([]);
      return _safe(
        c.from("profiles").select("id,username,avatar_url")
          .ilike("username", prefix.replace(/[%_]/g, "") + "%")
          .limit(limit || 6)
      ).then(function (res) { return (res && res.data) || []; });
    },
    usernameAvailable: function (username) {
      var c = client();
      if (!c) return Promise.resolve(true);
      return _safe(
        c.from("profiles").select("id").eq("username", username).maybeSingle()
      ).then(function (res) { return !(res && res.data); });
    },
    getUserBadges: function (userId) {
      var c = client();
      if (!c) return Promise.resolve([]);
      return _safe(
        c.from("user_badges").select("badge_slug,awarded_at,badges(name,description,icon)")
          .eq("user_id", userId)
      ).then(function (res) { return (res && res.data) || []; });
    },

    // --- favorites (curated showcase subset; one #1 per kind) ----------------
    getFavorites: function (userId) {
      var c = client();
      var uid = userId || (_session && _session.user.id);
      if (!c || !uid) return Promise.resolve([]);
      return _safe(
        c.from("favorites").select("*").eq("user_id", uid)
      ).then(function (res) { return (res && res.data) || []; });
    },
    addFavorite: function (kind, entityKey, isNumberOne) {
      var c = client();
      if (!c || !_session) return Promise.resolve({ error: new Error("not signed in") });
      var row = {
        user_id: _session.user.id, kind: kind, entity_key: entityKey,
        is_number_one: !!isNumberOne
      };
      // unique partial index enforces one #1 per (user,kind) - clear the old #1 first.
      var pre = isNumberOne
        ? c.from("favorites").update({ is_number_one: false })
            .eq("user_id", _session.user.id).eq("kind", kind).eq("is_number_one", true)
        : Promise.resolve();
      return _safe(Promise.resolve(pre).then(function () {
        return c.from("favorites").upsert(row, { onConflict: "user_id,kind,entity_key" });
      }));
    },
    removeFavorite: function (kind, entityKey) {
      var c = client();
      if (!c || !_session) return Promise.resolve({ error: new Error("not signed in") });
      return _safe(
        c.from("favorites").delete()
          .eq("user_id", _session.user.id).eq("kind", kind).eq("entity_key", entityKey)
      );
    },
    setNumberOne: function (kind, entityKey) { return this.addFavorite(kind, entityKey, true); },

    // --- watchlist (broad tracking set; private; feeds FV alerts) -------------
    getWatchlist: function () {
      var c = client();
      if (!c || !_session) return Promise.resolve([]);
      return _safe(
        c.from("watchlist").select("entity_type,entity_key").eq("user_id", _session.user.id)
      ).then(function (res) { return (res && res.data) || []; });
    },
    addWatch: function (entityType, entityKey) {
      var c = client();
      if (!c || !_session) return Promise.resolve({ error: new Error("not signed in") });
      return _safe(
        c.from("watchlist").upsert(
          { user_id: _session.user.id, entity_type: entityType, entity_key: entityKey },
          { onConflict: "user_id,entity_type,entity_key" }
        )
      );
    },
    removeWatch: function (entityType, entityKey) {
      var c = client();
      if (!c || !_session) return Promise.resolve({ error: new Error("not signed in") });
      return _safe(
        c.from("watchlist").delete()
          .eq("user_id", _session.user.id).eq("entity_type", entityType).eq("entity_key", entityKey)
      );
    },
    // Union a logged-out localStorage watchlist into the account (merge-on-login).
    // `local` = { prospect: [keys], farm: [orgs] }. Never destructive server-side.
    mergeLocalWatchlist: function (local) {
      var c = client();
      if (!c || !_session) return Promise.resolve({ merged: 0 });
      var rows = [];
      (local && local.prospect || []).forEach(function (k) {
        rows.push({ user_id: _session.user.id, entity_type: "prospect", entity_key: k });
      });
      (local && local.farm || []).forEach(function (k) {
        rows.push({ user_id: _session.user.id, entity_type: "farm", entity_key: k });
      });
      if (!rows.length) return Promise.resolve({ merged: 0 });
      return _safe(
        c.from("watchlist").upsert(rows, { onConflict: "user_id,entity_type,entity_key" })
      ).then(function (res) { return { merged: rows.length, error: res && res.error }; });
    },

    // --- Diamond entitlement (supabase/migrations/0005_diamond.sql) ----------
    // profiles.diamond_until is a timestamptz: NULL or past = not a member, a
    // future timestamp = member until then. The column is service-role only
    // (the guard_profile_privileged_cols trigger silently pins any client write
    // to it), so a truthy answer here is a real entitlement, not something the
    // browser talked itself into.
    //
    // CLIENT SIDE IS DISPLAY ONLY. This decides whether to show a members badge
    // or an upsell. It is not a security boundary and must never be the only
    // thing standing between a non-member and members-only DATA: on a static
    // site that data has to arrive over RLS or an edge function. See
    // assets/diamond-config.js for the same warning attached to the gate flag.
    isDiamond: function () {
      var p = _profile;
      if (!p || !p.diamond_until) return false;
      var t = Date.parse(p.diamond_until);
      return isFinite(t) && t > Date.now();
    },
    // Expiry as a Date (or null) so a UI can render "renews on ..." without
    // re-parsing the raw column and inventing a second date convention.
    diamondUntil: function () {
      var p = _profile;
      if (!p || !p.diamond_until) return null;
      var t = Date.parse(p.diamond_until);
      return isFinite(t) ? new Date(t) : null;
    },

    // --- bets (personal tracker; owner-only rows) -----------------------------
    // The same adapter shape as the watchlist, one level up: it works LOGGED
    // OUT against localStorage and switches to the `bets` table when a session
    // exists. A user should be able to log a bet the first time they see the
    // page, without an account, and still have it when they make one.
    //
    // A bet row is {id, sport, market, selection, odds, stake, placed_at,
    // settled_at, result, payload}. `odds` is AMERICAN odds at placement and
    // `result` is one of open|won|lost|void, matching the bet_result enum.
    // Local rows carry a "local:" id prefix so a caller can tell the two apart
    // and so a merge can rewrite them without colliding with server uuids.
    //
    // MERGE IS NOT AUTOMATIC. mergeLocalBets() is exposed for the tracker UI to
    // call behind a prompt, the same way the watchlist merge is never silent
    // (supabase/FRONTEND_INTEGRATION.md Part 3).
    _betsKey: "eephus.bets.v1",
    _localBets: function () {
      try {
        var raw = window.localStorage.getItem(Account._betsKey);
        var arr = raw ? JSON.parse(raw) : [];
        return Array.isArray(arr) ? arr : [];
      } catch (e) { return []; }          // private mode / quota / bad JSON
    },
    _setLocalBets: function (rows) {
      try { window.localStorage.setItem(Account._betsKey, JSON.stringify(rows || [])); }
      catch (e) { /* storage unavailable: the session keeps working in memory */ }
    },
    // Strip the client-only fields before a row goes to Postgres. user_id is
    // stamped by the caller; id is left to the table default unless a server
    // row is being updated.
    _betPayload: function (bet) {
      bet = bet || {};
      return {
        sport: bet.sport || "mlb",
        market: bet.market || "moneyline",
        selection: bet.selection || "",
        odds: bet.odds == null ? 0 : Math.round(Number(bet.odds)),
        stake: bet.stake == null ? 1 : Number(bet.stake),
        placed_at: bet.placed_at || new Date().toISOString(),
        settled_at: bet.settled_at || null,
        result: bet.result || "open",
        payload: bet.payload || {}
      };
    },
    listBets: function (limit) {
      var c = client();
      if (!c || !_session) {
        var rows = Account._localBets().slice().sort(function (a, b) {
          return String(b.placed_at || "").localeCompare(String(a.placed_at || ""));
        });
        return Promise.resolve(limit ? rows.slice(0, limit) : rows);
      }
      var q = c.from("bets").select("*").eq("user_id", _session.user.id)
        .order("placed_at", { ascending: false });
      if (limit) q = q.limit(limit);
      return _safe(q).then(function (res) { return (res && res.data) || []; });
    },
    addBet: function (bet) {
      var row = Account._betPayload(bet);
      var c = client();
      if (!c || !_session) {
        row.id = "local:" + Date.now() + ":" + Math.random().toString(36).slice(2, 8);
        var rows = Account._localBets();
        rows.push(row);
        Account._setLocalBets(rows);
        return Promise.resolve({ data: row, error: null, local: true });
      }
      row.user_id = _session.user.id;
      return _safe(c.from("bets").insert(row).select().maybeSingle());
    },
    updateBet: function (id, patch) {
      var c = client();
      if (!c || !_session) {
        var rows = Account._localBets(), hit = null;
        rows = rows.map(function (r) {
          if (r.id !== id) return r;
          hit = Object.assign({}, r, patch || {});
          return hit;
        });
        if (!hit) return Promise.resolve({ data: null, error: new Error("no such bet"), local: true });
        Account._setLocalBets(rows);
        return Promise.resolve({ data: hit, error: null, local: true });
      }
      return _safe(
        c.from("bets").update(patch || {}).eq("id", id).eq("user_id", _session.user.id)
          .select().maybeSingle()
      );
    },
    deleteBet: function (id) {
      var c = client();
      if (!c || !_session) {
        Account._setLocalBets(Account._localBets().filter(function (r) { return r.id !== id; }));
        return Promise.resolve({ error: null, local: true });
      }
      return _safe(
        c.from("bets").delete().eq("id", id).eq("user_id", _session.user.id)
      );
    },
    // Copy every locally-stored bet into the account, then clear local. Call it
    // from a prompt, never on your own. Returns {merged, error}. Non-destructive
    // server-side: it only inserts.
    mergeLocalBets: function () {
      var c = client();
      if (!c || !_session) return Promise.resolve({ merged: 0 });
      var local = Account._localBets();
      if (!local.length) return Promise.resolve({ merged: 0 });
      var uid = _session.user.id;
      var rows = local.map(function (b) {
        var row = Account._betPayload(b);
        row.user_id = uid;                  // the "local:" id is deliberately dropped
        return row;
      });
      return _safe(c.from("bets").insert(rows)).then(function (res) {
        // Only clear the device copy once the server took the rows. A failed
        // merge that wiped local storage would be a data-loss bug.
        if (!(res && res.error)) Account._setLocalBets([]);
        return { merged: rows.length, error: res && res.error };
      });
    },

    // --- threads / comments --------------------------------------------------
    // Canonical thread for an entity (prospect/farm/article); creates on demand.
    getOrCreateThread: function (scope, entityKey, title, boardSlug) {
      var c = client();
      if (!c) return Promise.resolve(null);
      var q = c.from("threads").select("*").eq("scope", scope);
      q = entityKey == null ? q.is("entity_key", null) : q.eq("entity_key", entityKey);
      return _safe(q.maybeSingle()).then(function (res) {
        if (res && res.data) return res.data;
        if (!_session) return null; // logged-out users can read but not create
        var row = {
          scope: scope, entity_key: entityKey || null, title: title || "Discussion",
          created_by: _session.user.id, board_slug: boardSlug || null
        };
        return _safe(c.from("threads").insert(row).select().maybeSingle())
          .then(function (r2) { return r2 && r2.data ? r2.data : null; });
      });
    },
    // Aggregate threads for the homepage module + /forums index. order:
    // 'active' = bump (last_activity_at desc) | 'hot' = hot_score desc.
    listThreads: function (order, limit) {
      var c = client();
      if (!c) return Promise.resolve([]);
      var col = order === "hot" ? "hot_score" : "last_activity_at";
      return _safe(
        c.from("threads")
          .select("id,scope,entity_key,board_slug,title,comment_count,last_activity_at,hot_score")
          .order(col, { ascending: false }).limit(limit || 12)
      ).then(function (res) { return (res && res.data) || []; });
    },
    listComments: function (threadId, sort) {
      var c = client();
      if (!c || !threadId) return Promise.resolve([]);
      var sel = "id,thread_id,parent_id,author_id,body_md,body_html,score,created_at,edited_at,deleted," +
        "profiles:author_id(username,avatar_url,role,karma,created_at)";
      var q = c.from("comments").select(sel).eq("thread_id", threadId);
      if (sort === "top") q = q.order("score", { ascending: false }).order("created_at", { ascending: true });
      else q = q.order("created_at", { ascending: true }); // recent/active resolve client-side
      return _safe(q).then(function (res) { return (res && res.data) || []; });
    },
    postComment: function (threadId, parentId, bodyMd, bodyHtml) {
      var c = client();
      if (!c || !_session) return Promise.resolve({ data: null, error: new Error("not signed in") });
      var row = {
        thread_id: threadId, parent_id: parentId || null, author_id: _session.user.id,
        body_md: bodyMd, body_html: bodyHtml
      };
      return _safe(c.from("comments").insert(row).select().maybeSingle());
    },
    editComment: function (commentId, bodyMd, bodyHtml) {
      var c = client();
      if (!c || !_session) return Promise.resolve({ error: new Error("not signed in") });
      return _safe(
        c.from("comments").update({ body_md: bodyMd, body_html: bodyHtml, edited_at: new Date().toISOString() })
          .eq("id", commentId).select().maybeSingle()
      );
    },
    deleteComment: function (commentId) {
      var c = client();
      if (!c || !_session) return Promise.resolve({ error: new Error("not signed in") });
      // soft-delete keeps thread structure intact ([deleted]).
      return _safe(
        c.from("comments").update({ deleted: true, body_md: "[deleted]", body_html: "<p>[deleted]</p>" })
          .eq("id", commentId)
      );
    },
    addMentions: function (commentId, userIds) {
      var c = client();
      if (!c || !_session || !userIds || !userIds.length) return Promise.resolve({ error: null });
      var rows = userIds.map(function (uid) { return { comment_id: commentId, mentioned_user_id: uid }; });
      return _safe(c.from("mentions").upsert(rows, { onConflict: "comment_id,mentioned_user_id" }));
    },

    // --- votes (one per user/comment; ±1; no self-vote enforced server-side) -
    vote: function (commentId, value) {
      var c = client();
      if (!c || !_session) return Promise.resolve({ error: new Error("not signed in") });
      if (value === 0) {
        return _safe(c.from("votes").delete()
          .eq("user_id", _session.user.id).eq("comment_id", commentId));
      }
      return _safe(c.from("votes").upsert(
        { user_id: _session.user.id, comment_id: commentId, value: value },
        { onConflict: "user_id,comment_id" }
      ));
    },
    myVotes: function (commentIds) {
      var c = client();
      if (!c || !_session || !commentIds || !commentIds.length) return Promise.resolve({});
      return _safe(
        c.from("votes").select("comment_id,value")
          .eq("user_id", _session.user.id).in("comment_id", commentIds)
      ).then(function (res) {
        var map = {};
        ((res && res.data) || []).forEach(function (v) { map[v.comment_id] = v.value; });
        return map;
      });
    },
    report: function (commentId, reason) {
      var c = client();
      if (!c || !_session) return Promise.resolve({ error: new Error("not signed in") });
      return _safe(c.from("reports").insert({
        comment_id: commentId, reporter_id: _session.user.id, reason: reason
      }));
    },

    // --- moderation (staff only; RLS enforces) -------------------------------
    listReports: function () {
      var c = client();
      if (!c) return Promise.resolve([]);
      return _safe(
        c.from("reports").select("id,comment_id,reason,status,created_at,comments(body_md,profiles:author_id(username))")
          .eq("status", "open").order("created_at", { ascending: false }).limit(50)
      ).then(function (res) {
        return ((res && res.data) || []).map(function (r) {
          var cm = r.comments || {}, pr = cm.profiles || {};
          return { id: r.id, comment_id: r.comment_id, reason: r.reason, status: r.status, created_at: r.created_at, comment: { body_md: cm.body_md, author: pr.username } };
        });
      });
    },
    setReportStatus: function (id, status) {
      var c = client(); if (!c) return Promise.resolve({});
      return _safe(c.from("reports").update({ status: status }).eq("id", id));
    },
    staffRemoveComment: function (id) {
      var c = client(); if (!c) return Promise.resolve({});
      return _safe(c.from("comments").update({ deleted: true, body_md: "[removed by moderator]", body_html: "<p>[removed by moderator]</p>" }).eq("id", id));
    },
    grantBadgeByUsername: function (username, slug) {
      var c = client(); if (!c) return Promise.resolve({ error: new Error("accounts disabled") });
      return Account.profileByUsername(username).then(function (p) {
        if (!p) return { error: new Error("no such user") };
        return _safe(c.from("user_badges").upsert({ user_id: p.id, badge_slug: slug, awarded_by: (_session && _session.user.id) }, { onConflict: "user_id,badge_slug" }));
      });
    },
    banUserByUsername: function (username, untilISO) {
      var c = client(); if (!c) return Promise.resolve({ error: new Error("accounts disabled") });
      return Account.profileByUsername(username).then(function (p) {
        if (!p) return { error: new Error("no such user") };
        return _safe(c.from("profiles").update({ banned_until: untilISO }).eq("id", p.id));
      });
    },

    // --- avatar upload (Storage bucket 'avatars'; ≤2MB png/jpeg/webp) --------
    uploadAvatar: function (file) {
      var c = client();
      if (!c || !_session) return Promise.resolve({ error: new Error("not signed in") });
      if (file.size > 2 * 1024 * 1024) return Promise.resolve({ error: new Error("Image must be ≤ 2 MB") });
      if (["image/png", "image/jpeg", "image/webp"].indexOf(file.type) < 0) return Promise.resolve({ error: new Error("Use PNG, JPEG, or WebP") });
      var ext = (file.name.split(".").pop() || "png").toLowerCase();
      var path = _session.user.id + "/avatar_" + Date.now() + "." + ext;
      return _safe(c.storage.from("avatars").upload(path, file, { upsert: true, cacheControl: "3600" })).then(function (res) {
        if (res && res.error) return res;
        var pub = c.storage.from("avatars").getPublicUrl(path);
        var url = pub && pub.data && pub.data.publicUrl;
        return Account.updateProfile({ avatar_url: url }).then(function () { return { data: { url: url } }; });
      });
    },

    // --- Part 7: social graph (follow) + activity feed -----------------------
    follow: function (userId) {
      var c = client(); if (!c || !_session) return Promise.resolve({ error: new Error("not signed in") });
      return _safe(c.from("follows").upsert({ follower_id: _session.user.id, followee_id: userId }, { onConflict: "follower_id,followee_id" }));
    },
    unfollow: function (userId) {
      var c = client(); if (!c || !_session) return Promise.resolve({ error: new Error("not signed in") });
      return _safe(c.from("follows").delete().eq("follower_id", _session.user.id).eq("followee_id", userId));
    },
    isFollowing: function (userId) {
      var c = client(); if (!c || !_session) return Promise.resolve(false);
      return _safe(c.from("follows").select("followee_id").eq("follower_id", _session.user.id).eq("followee_id", userId).maybeSingle())
        .then(function (r) { return !!(r && r.data); });
    },
    followCounts: function (userId) {
      var c = client(); if (!c) return Promise.resolve({ followers: 0, following: 0 });
      return Promise.all([
        _safe(c.from("follows").select("follower_id", { count: "exact", head: true }).eq("followee_id", userId)),
        _safe(c.from("follows").select("followee_id", { count: "exact", head: true }).eq("follower_id", userId))
      ]).then(function (rs) { return { followers: (rs[0] && rs[0].count) || 0, following: (rs[1] && rs[1].count) || 0 }; });
    },
    getFollowingIds: function () {
      var c = client(); if (!c || !_session) return Promise.resolve([]);
      return _safe(c.from("follows").select("followee_id").eq("follower_id", _session.user.id))
        .then(function (r) { return ((r && r.data) || []).map(function (x) { return x.followee_id; }); });
    },
    // Personalized feed: recent comments from people you follow.
    activityFeed: function (limit) {
      var c = client(); if (!c || !_session) return Promise.resolve([]);
      return Account.getFollowingIds().then(function (ids) {
        if (!ids.length) return [];
        return _safe(
          c.from("comments").select("id,thread_id,body_md,created_at,author_id,threads(scope,entity_key,title),profiles:author_id(username,avatar_url)")
            .in("author_id", ids).eq("deleted", false).order("created_at", { ascending: false }).limit(limit || 20)
        ).then(function (r) { return (r && r.data) || []; });
      });
    },
    // recent comments by a single user (for their profile)
    userComments: function (userId, limit) {
      var c = client(); if (!c) return Promise.resolve([]);
      return _safe(
        c.from("comments").select("id,thread_id,body_md,created_at,threads(scope,entity_key,title)")
          .eq("author_id", userId).eq("deleted", false).order("created_at", { ascending: false }).limit(limit || 10)
      ).then(function (r) { return (r && r.data) || []; });
    },

    // --- Part 7: polls (one poll per comment; votes keyed by comment) --------
    pollResults: function (commentId) {
      var c = client(); if (!c) return Promise.resolve({ counts: {}, mine: null });
      return _safe(c.from("poll_votes").select("choice,user_id").eq("comment_id", commentId)).then(function (r) {
        var counts = {}, mine = null, me = _session && _session.user.id;
        ((r && r.data) || []).forEach(function (v) { counts[v.choice] = (counts[v.choice] || 0) + 1; if (v.user_id === me) mine = v.choice; });
        return { counts: counts, mine: mine };
      });
    },
    castPoll: function (commentId, choice) {
      var c = client(); if (!c || !_session) return Promise.resolve({ error: new Error("not signed in") });
      return _safe(c.from("poll_votes").upsert({ comment_id: commentId, user_id: _session.user.id, choice: choice }, { onConflict: "comment_id,user_id" }));
    },

    // --- notifications -------------------------------------------------------
    listNotifications: function (limit) {
      var c = client();
      if (!c || !_session) return Promise.resolve([]);
      return _safe(
        c.from("notifications").select("*").eq("user_id", _session.user.id)
          .order("created_at", { ascending: false }).limit(limit || 30)
      ).then(function (res) { return (res && res.data) || []; });
    },
    unreadCount: function () {
      var c = client();
      if (!c || !_session) return Promise.resolve(0);
      return _safe(
        c.from("notifications").select("id", { count: "exact", head: true })
          .eq("user_id", _session.user.id).eq("read", false)
      ).then(function (res) { return (res && typeof res.count === "number") ? res.count : 0; });
    },
    markNotificationsRead: function (ids) {
      var c = client();
      if (!c || !_session) return Promise.resolve({ error: null });
      var q = c.from("notifications").update({ read: true }).eq("user_id", _session.user.id);
      if (ids && ids.length) q = q.in("id", ids);
      else q = q.eq("read", false);
      return _safe(q);
    },
    getNotificationPrefs: function () {
      var c = client();
      if (!c || !_session) return Promise.resolve(null);
      return _safe(
        c.from("notification_prefs").select("*").eq("user_id", _session.user.id).maybeSingle()
      ).then(function (res) { return res && res.data ? res.data : null; });
    },
    setNotificationPrefs: function (patch) {
      var c = client();
      if (!c || !_session) return Promise.resolve({ error: new Error("not signed in") });
      var row = Object.assign({ user_id: _session.user.id }, patch);
      return _safe(c.from("notification_prefs").upsert(row, { onConflict: "user_id" }));
    },

    // --- realtime (reply/mention/vote push) - optional, no-op if unavailable -
    subscribeNotifications: function (cb) {
      var c = client();
      if (!c || !_session || typeof cb !== "function") return function () {};
      try {
        var ch = c.channel("notif:" + _session.user.id)
          .on("postgres_changes",
            { event: "INSERT", schema: "public", table: "notifications", filter: "user_id=eq." + _session.user.id },
            function (payload) { try { cb(payload.new); } catch (e) {} })
          .subscribe();
        return function () { try { c.removeChannel(ch); } catch (e) {} };
      } catch (e) { return function () {}; }
    }
  };

  // Expose + kick off session bootstrap (no-op when unconfigured).
  if (typeof window !== "undefined") {
    window.EephusAccount = Account;
    if (CONFIGURED) {
      if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", _bootstrap, { once: true });
      } else { _bootstrap(); }
    } else {
      _resolveReady(); // ready immediately; everything is a no-op
    }
  }
})();
