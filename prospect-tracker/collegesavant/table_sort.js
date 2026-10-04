// Generic click-to-sort for CollegeSavant's plain tables - the Team
// Tendencies, Pro Projections, and backtest boards, which render fixed
// <th class="tt-col"> headers with no sort of their own. Clicking a column
// header sorts the table by that column; clicking again reverses (so a
// double-click flips back). Numeric-aware (parses the leading number).
//
// Leaderboard tables carry their own sort - every sortable header there has
// class "lb-th" and a click re-renders the board from data. Those tables are
// skipped wholesale (a DOM reorder would be undone on the next re-render).
// Opt any table or header out with data-no-sort. Mirrors the prospx
// universal table sort so behavior matches the rest of the site.
(function () {
  function cellNum(txt) {
    const m = String(txt || "").replace(/,/g, "").match(/-?\d*\.?\d+/);
    if (!m) return null;
    const v = parseFloat(m[0]);
    return isFinite(v) ? v : null;
  }
  function sortTable(th) {
    const table = th.closest("table");
    if (!table || !table.tBodies || !table.tBodies.length) return;
    const tbody = table.tBodies[0];
    const rows = Array.prototype.slice.call(tbody.rows).filter((r) => r.cells && r.cells.length);
    if (rows.length < 2) return;
    const col = th.cellIndex;
    if (col < 0) return;
    const same = table.getAttribute("data-gen-col") === String(col);
    const dir = (same && table.getAttribute("data-gen-dir") === "asc") ? "desc" : "asc";
    table.setAttribute("data-gen-col", String(col));
    table.setAttribute("data-gen-dir", dir);
    const txt = (r) => (r.cells[col] ? (r.cells[col].textContent || "").trim() : "");
    const numeric = rows.filter((r) => cellNum(txt(r)) != null).length >= rows.length * 0.6;
    const sign = dir === "asc" ? 1 : -1;
    rows.sort((a, b) => {
      if (numeric) {
        const av = cellNum(txt(a)), bv = cellNum(txt(b));
        if (av == null && bv == null) return 0;
        if (av == null) return 1;
        if (bv == null) return -1;
        return sign * (av - bv);
      }
      return sign * txt(a).localeCompare(txt(b));
    });
    rows.forEach((r) => tbody.appendChild(r));
    if (table.tHead) {
      table.tHead.querySelectorAll("th[data-gen-sorted]").forEach((h) => h.removeAttribute("data-gen-sorted"));
    }
    th.setAttribute("data-gen-sorted", dir);
    if (table.tHead) {
      table.tHead.querySelectorAll("th[aria-sort]").forEach((h) => h.setAttribute("aria-sort", "none"));
    }
    th.setAttribute("aria-sort", dir === "asc" ? "ascending" : "descending");
  }
  function sortableTh(th) {
    const table = th && th.closest("table");
    if (!table) return false;
    if (table.hasAttribute("data-no-sort") || th.hasAttribute("data-no-sort")) return false;
    return !table.querySelector("th.lb-th"); // leaderboard owns its sort
  }
  // QREA01: every header this script sorts takes keyboard focus and says its
  // sort state. The apps render their tables after this script loads and on
  // every re-render, so a DOM observer arms each new header row as it lands.
  function arm() {
    document.querySelectorAll("table thead th:not([aria-sort])").forEach((th) => {
      if (!sortableTh(th)) return;
      th.tabIndex = 0;
      const d = th.getAttribute("data-gen-sorted");
      th.setAttribute("aria-sort", d === "asc" ? "ascending" : d === "desc" ? "descending" : "none");
    });
  }
  document.addEventListener("click", (e) => {
    const th = e.target && e.target.closest && e.target.closest("th");
    if (!th || !sortableTh(th)) return;
    sortTable(th);
  });
  // Enter or Space on the header itself sorts; the rows move under it, so
  // focus stays on the same header. A control inside a header keeps its keys.
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" && e.key !== " ") return;
    const th = e.target;
    if (!th || th.tagName !== "TH" || !th.closest("thead") || !sortableTh(th)) return;
    e.preventDefault();
    sortTable(th);
  });
  arm();
  if (typeof MutationObserver === "function") {
    new MutationObserver(arm).observe(document.documentElement, { childList: true, subtree: true });
  }
})();
