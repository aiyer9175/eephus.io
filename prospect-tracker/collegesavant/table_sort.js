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
  }
  document.addEventListener("click", (e) => {
    const th = e.target && e.target.closest && e.target.closest("th");
    if (!th) return;
    const table = th.closest("table");
    if (!table) return;
    if (table.hasAttribute("data-no-sort") || th.hasAttribute("data-no-sort")) return;
    if (table.querySelector("th.lb-th")) return; // leaderboard owns its sort
    sortTable(th);
  });
})();
