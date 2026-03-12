import Plotly from "plotly.js-dist-min";
import { collection, getDocs, query, where } from "firebase/firestore";

import { COLORS, PLOTLY_LAYOUT } from "../theme";

function toDate(value) {
  if (!value) {
    return null;
  }
  if (typeof value.toDate === "function") {
    return value.toDate();
  }
  return new Date(value);
}

function hours(entries) {
  return entries.reduce((sum, entry) => sum + Number(entry.duration_seconds || 0), 0) / 3600;
}

function byYear(entries) {
  const map = new Map();
  for (const entry of entries) {
    const y = Number(entry.start_year || 0);
    if (!y) {
      continue;
    }
    if (!map.has(y)) {
      map.set(y, []);
    }
    map.get(y).push(entry);
  }
  return [...map.entries()].sort((a, b) => a[0] - b[0]);
}

async function availableYears(db) {
  const snap = await getDocs(collection(db, "time_entries"));
  const years = snap.docs
    .map((doc) => Number((doc.data() || {}).start_year || 0))
    .filter((y) => y > 0);
  return [...new Set(years)].sort((a, b) => a - b);
}

async function renderOnThisDay(section, db) {
  section.innerHTML = `
    <div class="panel row">
      <div>
        <label for="otd-date">Date</label>
        <input id="otd-date" type="date" value="${new Date().toISOString().slice(0, 10)}" />
      </div>
      <div style="align-self: end;">
        <button id="otd-run" class="button">Run</button>
      </div>
    </div>
    <div class="panel"><div id="otd-chart"></div></div>
    <div id="otd-details"></div>
  `;

  const run = async () => {
    const value = section.querySelector("#otd-date").value;
    const d = new Date(`${value}T00:00:00`);
    const month = d.getMonth() + 1;
    const day = d.getDate();

    const entriesQuery = query(
      collection(db, "time_entries"),
      where("start_month", "==", month),
      where("start_day", "==", day)
    );
    const snap = await getDocs(entriesQuery);
    const entries = snap.docs.map((doc) => ({ id: doc.id, ...(doc.data() || {}) }));

    const grouped = byYear(entries);
    Plotly.newPlot(
      "otd-chart",
      [
        {
          type: "bar",
          x: grouped.map(([year]) => year),
          y: grouped.map(([, rows]) => hours(rows)),
          marker: { color: COLORS.cyan }
        }
      ],
      {
        ...PLOTLY_LAYOUT,
        title: "On This Day Across Years",
        xaxis: { ...PLOTLY_LAYOUT.xaxis, title: "Year" },
        yaxis: { ...PLOTLY_LAYOUT.yaxis, title: "Hours" }
      },
      { responsive: true }
    );

    section.querySelector("#otd-details").innerHTML = grouped
      .map(([year, rows]) => {
        const top = rows
          .slice()
          .sort((a, b) => Number(b.duration_seconds || 0) - Number(a.duration_seconds || 0))[0];
        return `
          <details class="panel">
            <summary>${year} — ${hours(rows).toFixed(1)}h (${rows.length} entries)</summary>
            <p class="muted">Top activity: ${(top?.description || "(none)")} [${(top?.project_name || top?.project || "No Project")}]</p>
          </details>
        `;
      })
      .join("");
  };

  section.querySelector("#otd-run").addEventListener("click", run);
  await run();
}

async function renderWeekView(section, db) {
  section.innerHTML = `
    <div class="panel row">
      <div>
        <label for="week-input">ISO Week (1-53)</label>
        <input id="week-input" type="number" min="1" max="53" value="${Math.min(53, Math.max(1, Number(new Date().toISOString().slice(6, 8))))}" />
      </div>
      <div style="align-self: end;"><button id="week-run" class="button">Run</button></div>
    </div>
    <div class="panel"><div id="week-chart"></div></div>
  `;

  const run = async () => {
    const week = Number(section.querySelector("#week-input").value || 1);
    const entriesQuery = query(collection(db, "time_entries"), where("start_week", "==", week));
    const snap = await getDocs(entriesQuery);
    const entries = snap.docs.map((doc) => ({ id: doc.id, ...(doc.data() || {}) }));

    const grouped = byYear(entries);
    Plotly.newPlot(
      "week-chart",
      [
        {
          type: "bar",
          x: grouped.map(([year]) => year),
          y: grouped.map(([, rows]) => hours(rows)),
          marker: { color: COLORS.magenta }
        }
      ],
      {
        ...PLOTLY_LAYOUT,
        title: `Week ${week} Across Years`,
        xaxis: { ...PLOTLY_LAYOUT.xaxis, title: "Year" },
        yaxis: { ...PLOTLY_LAYOUT.yaxis, title: "Hours" }
      },
      { responsive: true }
    );
  };

  section.querySelector("#week-run").addEventListener("click", run);
  await run();
}

async function renderYearComparison(section, db) {
  const years = await availableYears(db);
  const fallback = new Date().getFullYear();
  const a = years[years.length - 2] || fallback - 1;
  const b = years[years.length - 1] || fallback;

  section.innerHTML = `
    <div class="panel row">
      <div>
        <label for="year-a">Year A</label>
        <select id="year-a">${years.map((y) => `<option value="${y}" ${y === a ? "selected" : ""}>${y}</option>`).join("")}</select>
      </div>
      <div>
        <label for="year-b">Year B</label>
        <select id="year-b">${years.map((y) => `<option value="${y}" ${y === b ? "selected" : ""}>${y}</option>`).join("")}</select>
      </div>
      <div style="align-self: end;"><button id="compare-run" class="button">Compare</button></div>
    </div>
    <div class="panel"><div id="compare-chart"></div></div>
    <div class="panel" id="compare-summary"></div>
  `;

  const run = async () => {
    const yearA = Number(section.querySelector("#year-a").value);
    const yearB = Number(section.querySelector("#year-b").value);
    const [snapA, snapB] = await Promise.all([
      getDocs(query(collection(db, "time_entries"), where("start_year", "==", yearA))),
      getDocs(query(collection(db, "time_entries"), where("start_year", "==", yearB)))
    ]);

    const entriesA = snapA.docs.map((doc) => ({ id: doc.id, ...(doc.data() || {}) }));
    const entriesB = snapB.docs.map((doc) => ({ id: doc.id, ...(doc.data() || {}) }));

    const monthly = (entries) => {
      const buckets = Array.from({ length: 12 }, () => 0);
      for (const entry of entries) {
        const d = toDate(entry.start);
        if (!d) {
          continue;
        }
        buckets[d.getMonth()] += Number(entry.duration_seconds || 0) / 3600;
      }
      return buckets;
    };

    const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    Plotly.newPlot(
      "compare-chart",
      [
        { type: "bar", name: String(yearA), x: months, y: monthly(entriesA), marker: { color: COLORS.cyan } },
        { type: "bar", name: String(yearB), x: months, y: monthly(entriesB), marker: { color: COLORS.magenta } }
      ],
      {
        ...PLOTLY_LAYOUT,
        title: `${yearA} vs ${yearB} Monthly Hours`,
        barmode: "group",
        xaxis: { ...PLOTLY_LAYOUT.xaxis, title: "Month" },
        yaxis: { ...PLOTLY_LAYOUT.yaxis, title: "Hours" }
      },
      { responsive: true }
    );

    section.querySelector("#compare-summary").innerHTML = `
      <h3>Year Summary</h3>
      <p>${yearA}: ${hours(entriesA).toFixed(1)}h • ${entriesA.length} entries</p>
      <p>${yearB}: ${hours(entriesB).toFixed(1)}h • ${entriesB.length} entries</p>
    `;
  };

  section.querySelector("#compare-run").addEventListener("click", run);
  await run();
}

export async function renderRetrospect(container, ctx) {
  container.innerHTML = `
    <h2>Retrospect</h2>
    <div class="row" style="margin-bottom: 12px;">
      <button class="button" id="tab-otd" style="width:auto;">On This Day</button>
      <button class="button" id="tab-week" style="width:auto;">Week View</button>
      <button class="button" id="tab-compare" style="width:auto;">Year vs Year</button>
    </div>
    <div id="retrospect-content"></div>
  `;

  const content = container.querySelector("#retrospect-content");

  const showOnThisDay = () => renderOnThisDay(content, ctx.db);
  const showWeek = () => renderWeekView(content, ctx.db);
  const showCompare = () => renderYearComparison(content, ctx.db);

  container.querySelector("#tab-otd").addEventListener("click", showOnThisDay);
  container.querySelector("#tab-week").addEventListener("click", showWeek);
  container.querySelector("#tab-compare").addEventListener("click", showCompare);

  await showOnThisDay();
}
