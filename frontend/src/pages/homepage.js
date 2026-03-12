import { collection, getDocs, query, where } from "firebase/firestore";

import { formatDuration } from "../utils";

function isoWeekOfDate(date) {
  const target = new Date(date.valueOf());
  const dayNr = (date.getDay() + 6) % 7;
  target.setDate(target.getDate() - dayNr + 3);
  const firstThursday = target.valueOf();
  target.setMonth(0, 1);
  if (target.getDay() !== 4) {
    target.setMonth(0, 1 + ((4 - target.getDay() + 7) % 7));
  }
  return 1 + Math.ceil((firstThursday - target) / 604800000);
}

function toDate(value) {
  if (!value) {
    return null;
  }
  if (typeof value.toDate === "function") {
    return value.toDate();
  }
  return new Date(value);
}

export async function renderHomepage(container, ctx) {
  container.innerHTML = `
    <h2>Homepage</h2>
    <p class="muted">Current week highlights tagged with <strong>Highlight</strong>.</p>
    <div id="home-cards" class="card-grid"></div>
  `;

  const cards = container.querySelector("#home-cards");
  cards.innerHTML = "<div class='panel'>Loading highlights...</div>";

  const now = new Date();
  const currentYear = now.getFullYear();
  const currentWeek = isoWeekOfDate(now);

  const entriesRef = collection(ctx.db, "time_entries");
  const entriesQuery = query(
    entriesRef,
    where("tags_json", "array-contains", "Highlight"),
    where("start_year", "==", currentYear),
    where("start_week", "==", currentWeek)
  );

  const snapshot = await getDocs(entriesQuery);
  const entries = snapshot.docs.map((doc) => ({ id: doc.id, ...(doc.data() || {}) }));
  entries.sort((a, b) => {
    const aStart = toDate(a.start)?.getTime() || 0;
    const bStart = toDate(b.start)?.getTime() || 0;
    return aStart - bStart;
  });

  if (entries.length === 0) {
    cards.innerHTML = "<div class='panel'>No Highlight-tagged entries found for this week.</div>";
    return;
  }

  cards.innerHTML = entries
    .map((entry) => {
      const start = toDate(entry.start);
      const dateLabel = start ? start.toLocaleDateString() : "Unknown date";
      const duration = formatDuration(Number(entry.duration_seconds || 0));
      const project = entry.project_name || entry.project || "(No Project)";
      const description = entry.description || "(no description)";
      return `
        <article class="entry-card">
          <h3>${project}</h3>
          <p>${description}</p>
          <p class="muted">${dateLabel} • ${duration}</p>
        </article>
      `;
    })
    .join("");
}
