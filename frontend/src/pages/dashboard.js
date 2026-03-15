import Plotly from "plotly.js-dist-min";

import { COLORS, PLOTLY_LAYOUT, SCALE_NEON_HEATMAP } from "../theme";
import { aggregateHours, groupBy } from "../utils";

function toDate(value) {
  if (!value) {
    return null;
  }
  if (typeof value.toDate === "function") {
    return value.toDate();
  }
  return new Date(value);
}

function monthLabel(date) {
  return date.toLocaleDateString(undefined, { month: "short", year: "numeric" });
}

function getWeekNumber(date) {
  const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
  const dayNum = d.getUTCDay() || 7;
  d.setUTCDate(d.getUTCDate() + 4 - dayNum);
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  return Math.ceil((((d - yearStart) / 86400000) + 1) / 7);
}

function dayIndex(date) {
  const day = date.getDay();
  return day === 0 ? 6 : day - 1;
}

function parseTags(tagsStr) {
  if (!tagsStr) return [];
  try {
    return JSON.parse(tagsStr);
  } catch (e) {
    return [];
  }
}

function renderMetrics(container, entries) {
  const totalHours = aggregateHours(entries);
  const uniqueProjects = new Set(entries.map((e) => e.project_name || e.project || "").filter(Boolean)).size;
  const uniqueTags = new Set(entries.flatMap((e) => parseTags(e.tags))).size;
  const entriesCount = entries.length;

  const dateSet = new Set();
  for (const entry of entries) {
    const d = toDate(entry.start);
    if (d) {
      dateSet.add(d.toISOString().slice(0, 10));
    }
  }
  const dailyAverage = dateSet.size > 0 ? totalHours / dateSet.size : 0;

  container.innerHTML = `
    <div class="metric-grid">
      <div class="metric-card"><div class="metric-label">Total Hours</div><div class="metric-value">${totalHours.toFixed(1)}</div></div>
      <div class="metric-card"><div class="metric-label">Unique Projects</div><div class="metric-value">${uniqueProjects}</div></div>
      <div class="metric-card"><div class="metric-label">Unique Tags</div><div class="metric-value">${uniqueTags}</div></div>
      <div class="metric-card"><div class="metric-label">Entries</div><div class="metric-value">${entriesCount}</div></div>
      <div class="metric-card"><div class="metric-label">Daily Average</div><div class="metric-value">${dailyAverage.toFixed(1)}</div></div>
    </div>
  `;
}

function hoursBy(entries, keyFn) {
  const map = new Map();
  for (const entry of entries) {
    const key = keyFn(entry) || "(None)";
    const hours = Number(entry.duration_seconds || entry.duration || 0) / 3600;
    map.set(key, (map.get(key) || 0) + hours);
  }
  return [...map.entries()].sort((a, b) => b[1] - a[1]);
}

function renderBar(divId, rows, title, xLabel) {
  const labels = rows.map(([label]) => label);
  const values = rows.map(([, value]) => value);
  const trace = {
    type: "bar",
    x: values,
    y: labels,
    orientation: "h",
    marker: { color: COLORS.cyan }
  };
  Plotly.newPlot(
    divId,
    [trace],
    {
      ...PLOTLY_LAYOUT,
      title,
      xaxis: { ...PLOTLY_LAYOUT.xaxis, title: xLabel },
      yaxis: { ...PLOTLY_LAYOUT.yaxis, automargin: true },
      margin: { l: 160, r: 20, t: 60, b: 40 }
    },
    { responsive: true }
  );
}

function renderProjectPie(divId, rows) {
  const labels = rows.slice(0, 10).map(([label]) => label);
  const values = rows.slice(0, 10).map(([, value]) => value);
  Plotly.newPlot(
    divId,
    [
      {
        type: "pie",
        labels,
        values,
        hole: 0.5
      }
    ],
    {
      ...PLOTLY_LAYOUT,
      title: "Project Share (Top 10)"
    },
    { responsive: true }
  );
}

function renderMonthlyTrend(divId, entries) {
  const grouped = groupBy(entries, (entry) => {
    const d = toDate(entry.start);
    if (!d) {
      return "Unknown";
    }
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
  });

  const points = [...grouped.entries()]
    .map(([key, group]) => {
      if (key === "Unknown") {
        return null;
      }
      const d = toDate(group[0].start);
      return {
        key,
        label: monthLabel(d),
        hours: aggregateHours(group)
      };
    })
    .filter(Boolean)
    .sort((a, b) => a.key.localeCompare(b.key));

  Plotly.newPlot(
    divId,
    [
      {
        type: "scatter",
        mode: "lines+markers",
        x: points.map((p) => p.label),
        y: points.map((p) => p.hours),
        line: { color: COLORS.magenta, width: 2 },
        marker: { color: COLORS.cyan }
      }
    ],
    {
      ...PLOTLY_LAYOUT,
      title: "Monthly Trend",
      xaxis: { ...PLOTLY_LAYOUT.xaxis, title: "Month" },
      yaxis: { ...PLOTLY_LAYOUT.yaxis, title: "Hours" }
    },
    { responsive: true }
  );
}

function renderHeatmap(divId, entries) {
  const grid = Array.from({ length: 7 }, () => Array.from({ length: 53 }, () => 0));
  for (const entry of entries) {
    const d = toDate(entry.start);
    if (!d) {
      continue;
    }
    const week = Math.min(Math.max(getWeekNumber(d), 1), 53) - 1;
    const day = dayIndex(d);
    grid[day][week] += Number(entry.duration_seconds || entry.duration || 0) / 3600;
  }

  Plotly.newPlot(
    divId,
    [
      {
        type: "heatmap",
        z: grid,
        x: Array.from({ length: 53 }, (_, i) => i + 1),
        y: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        colorscale: SCALE_NEON_HEATMAP,
        hovertemplate: "Week %{x}, %{y}: %{z:.2f}h<extra></extra>"
      }
    ],
    {
      ...PLOTLY_LAYOUT,
      title: "Daily Activity Heatmap",
      xaxis: { ...PLOTLY_LAYOUT.xaxis, title: "ISO Week" },
      yaxis: { ...PLOTLY_LAYOUT.yaxis, title: "Day" }
    },
    { responsive: true }
  );
}

function renderTopDescriptions(container, entries) {
  const rows = hoursBy(entries, (entry) => entry.description || "(no description)").slice(0, 15);
  const html = rows
    .map(([description, hours]) => `<tr><td>${description}</td><td>${hours.toFixed(1)}</td></tr>`)
    .join("");
  container.innerHTML = `
    <h3>Top Descriptions</h3>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Description</th><th>Hours</th></tr></thead>
        <tbody>${html}</tbody>
      </table>
    </div>
  `;
}

async function fetchEntries(supabase, mode, year, startDate, endDate) {
  let query = supabase.from("time_entries").select("*");
  if (mode === "year") {
    query = query.eq("start_year", Number(year));
  } else if (mode === "custom") {
    query = query.gte("start_date", startDate).lte("start_date", endDate);
  }

  const { data } = await query;
  return data || [];
}

async function getYearBounds(supabase) {
  const { data } = await supabase.from("time_entries").select("start_year");
  const years = (data || [])
    .map((row) => Number(row.start_year || 0))
    .filter((year) => Number.isFinite(year) && year > 0);
  if (years.length === 0) {
    return { min: new Date().getFullYear(), max: new Date().getFullYear() };
  }
  return { min: Math.min(...years), max: Math.max(...years) };
}

export async function renderDashboard(container, ctx) {
  const bounds = await getYearBounds(ctx.supabase);
  const thisYear = bounds.max;

  container.innerHTML = `
    <h2>Dashboard</h2>
    <div class="panel row">
      <div style="min-width: 180px;">
        <label for="filter-mode">Range</label>
        <select id="filter-mode">
          <option value="year">Single Year</option>
          <option value="all">All Time</option>
          <option value="custom">Custom Range</option>
        </select>
      </div>
      <div style="min-width: 180px;">
        <label for="filter-year">Year</label>
        <select id="filter-year">${Array.from({ length: bounds.max - bounds.min + 1 }, (_, i) => bounds.min + i)
          .reverse()
          .map((year) => `<option value="${year}" ${year === thisYear ? "selected" : ""}>${year}</option>`)
          .join("")}</select>
      </div>
      <div style="min-width: 180px;">
        <label for="filter-start">Start date</label>
        <input id="filter-start" type="date" value="${thisYear}-01-01" />
      </div>
      <div style="min-width: 180px;">
        <label for="filter-end">End date</label>
        <input id="filter-end" type="date" value="${thisYear}-12-31" />
      </div>
      <div style="align-self: end; min-width: 160px;">
        <button id="apply-filter" class="button">Apply Filters</button>
      </div>
    </div>

    <div id="dash-metrics"></div>

    <div class="panel"><div id="chart-project-bar"></div></div>
    <div class="panel"><div id="chart-project-pie"></div></div>
    <div class="panel"><div id="chart-tag-bar"></div></div>
    <div class="panel"><div id="chart-client-bar"></div></div>
    <div class="panel"><div id="chart-monthly"></div></div>
    <div class="panel"><div id="chart-heatmap"></div></div>
    <div class="panel" id="table-descriptions"></div>
  `;

  const modeEl = container.querySelector("#filter-mode");
  const yearEl = container.querySelector("#filter-year");
  const startEl = container.querySelector("#filter-start");
  const endEl = container.querySelector("#filter-end");

  const run = async () => {
    const mode = modeEl.value;
    const year = Number(yearEl.value);
    const entries = await fetchEntries(ctx.supabase, mode, year, startEl.value, endEl.value);

    renderMetrics(container.querySelector("#dash-metrics"), entries);
    renderBar("chart-project-bar", hoursBy(entries, (entry) => entry.project_name || entry.project), "Project Breakdown", "Hours");
    renderProjectPie("chart-project-pie", hoursBy(entries, (entry) => entry.project_name || entry.project));
    renderBar(
      "chart-tag-bar",
      hoursBy(entries.flatMap((entry) => parseTags(entry.tags).map((tag) => ({ ...entry, __tag: tag }))), (entry) => entry.__tag),
      "Tag Breakdown",
      "Hours"
    );
    renderBar("chart-client-bar", hoursBy(entries, (entry) => entry.client_name), "Client Breakdown", "Hours");
    renderMonthlyTrend("chart-monthly", entries);
    renderHeatmap("chart-heatmap", entries);
    renderTopDescriptions(container.querySelector("#table-descriptions"), entries);
  };

  container.querySelector("#apply-filter").addEventListener("click", run);
  await run();
}
