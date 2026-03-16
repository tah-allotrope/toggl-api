import { createClient } from '@supabase/supabase-js';

import { renderLoginForm, signOut } from "./auth";
import { triggerSync } from "./api";
import { renderHomepage } from "./pages/homepage";
import { renderDashboard } from "./pages/dashboard";
import { renderRetrospect } from "./pages/retrospect";
import { renderChat } from "./pages/chat";

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

function renderBootError(message) {
  root.innerHTML = `
    <div class="main">
      <h2>Configuration Error</h2>
      <div class="panel" style="max-width: 600px;">
        <p class="error">${message}</p>
      </div>
    </div>
  `;
}

const root = document.getElementById("app");

if (!supabaseUrl || !supabaseKey) {
  renderBootError("Missing Supabase frontend environment variables. Set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY.");
  throw new Error("Missing VITE_SUPABASE_URL or VITE_SUPABASE_ANON_KEY");
}

if (supabaseKey.startsWith("sb_secret_")) {
  renderBootError("Frontend is configured with a secret Supabase key. Replace it with the Supabase anon/publishable key.");
  throw new Error("Unsafe Supabase key configured in frontend");
}

const supabase = createClient(supabaseUrl, supabaseKey);

function navLink(hash, label, currentHash) {
  const active = currentHash === hash || (hash === "#/homepage" && (currentHash === "#/" || !currentHash));
  return `<a class="nav-link ${active ? "active" : ""}" href="${hash}">${label}</a>`;
}

function shellTemplate(currentHash) {
  return `
    <div class="app-shell">
      <aside class="sidebar">
        <h1>Toggl Time Journal</h1>
        <nav>
          ${navLink("#/homepage", "Homepage", currentHash)}
          ${navLink("#/dashboard", "Dashboard", currentHash)}
          ${navLink("#/retrospect", "Retrospect", currentHash)}
          ${navLink("#/chat", "Chat", currentHash)}
        </nav>

        <hr />
        <button id="sync-quick" class="button">Quick Sync (current year)</button>
        <button id="sync-full" class="button">Full Sync (all years)</button>

        <label for="sync-year">Enriched year</label>
        <input id="sync-year" type="number" min="2006" max="2100" value="${new Date().getFullYear()}" />
        <button id="sync-enriched" class="button">Run Enriched Sync</button>

        <hr />
        <button id="logout" class="button">Sign Out</button>
        <p id="sync-status" class="muted"></p>
      </aside>
      <main class="main" id="page-root"></main>
    </div>
  `;
}

async function runSync(button, syncType, payload = {}) {
  const original = button.textContent;
  button.disabled = true;
  button.textContent = "Syncing...";
  const status = document.getElementById("sync-status");
  try {
    const { data: { session } } = await supabase.auth.getSession();
    const result = await triggerSync(session, syncType, payload);
    status.textContent = result?.message || "Sync dispatched.";
  } catch (err) {
    status.textContent = `Sync failed: ${err.message || String(err)}`;
  } finally {
    button.disabled = false;
    button.textContent = original;
  }
}

async function renderRoute() {
  const hash = window.location.hash || "#/homepage";
  root.innerHTML = shellTemplate(hash);
  const pageRoot = document.getElementById("page-root");

  document.getElementById("logout").addEventListener("click", () => signOut(supabase));
  document.getElementById("sync-quick").addEventListener("click", (event) => {
    runSync(event.currentTarget, "quick");
  });
  document.getElementById("sync-full").addEventListener("click", (event) => {
    runSync(event.currentTarget, "full", { earliest_year: 2017 });
  });
  document.getElementById("sync-enriched").addEventListener("click", (event) => {
    const year = Number(document.getElementById("sync-year").value || new Date().getFullYear());
    runSync(event.currentTarget, "enriched", { year });
  });

  const ctx = { supabase };
  if (hash === "#/" || hash === "#/homepage") {
    await renderHomepage(pageRoot, ctx);
    return;
  }
  if (hash === "#/dashboard") {
    await renderDashboard(pageRoot, ctx);
    return;
  }
  if (hash === "#/retrospect") {
    await renderRetrospect(pageRoot, ctx);
    return;
  }
  if (hash === "#/chat") {
    await renderChat(pageRoot, ctx);
    return;
  }

  pageRoot.innerHTML = "<h2>Not Found</h2><p class='muted'>Unknown route.</p>";
}

supabase.auth.onAuthStateChange((event, session) => {
  if (event === 'SIGNED_OUT' || !session) {
    renderLoginForm(root, supabase, () => {
      window.location.hash = "#/homepage";
      renderRoute();
    });
  } else if (event === 'SIGNED_IN' || event === 'INITIAL_SESSION') {
    renderRoute();
  }
});

window.addEventListener("hashchange", async () => {
  const { data: { session } } = await supabase.auth.getSession();
  if (session) {
    renderRoute();
  }
});
