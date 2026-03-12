import { initializeApp } from "firebase/app";
import { getAuth, onAuthStateChanged } from "firebase/auth";
import { getFunctions, httpsCallable } from "firebase/functions";
import { getFirestore } from "firebase/firestore";

import { renderLoginForm, signOut } from "./auth";
import { renderHomepage } from "./pages/homepage";
import { renderDashboard } from "./pages/dashboard";
import { renderRetrospect } from "./pages/retrospect";
import { renderChat } from "./pages/chat";

const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID
};

const app = initializeApp(firebaseConfig);
const auth = getAuth(app);
const db = getFirestore(app);
const functions = getFunctions(app);

const root = document.getElementById("app");

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

async function runSync(button, callableName, payload = {}) {
  const original = button.textContent;
  button.disabled = true;
  button.textContent = "Syncing...";
  const status = document.getElementById("sync-status");
  try {
    const call = httpsCallable(functions, callableName);
    const result = await call(payload);
    status.textContent = result?.data?.message || "Sync complete.";
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

  document.getElementById("logout").addEventListener("click", () => signOut(app));
  document.getElementById("sync-quick").addEventListener("click", (event) => {
    runSync(event.currentTarget, "sync_quick");
  });
  document.getElementById("sync-full").addEventListener("click", (event) => {
    runSync(event.currentTarget, "sync_full", { earliest_year: 2017 });
  });
  document.getElementById("sync-enriched").addEventListener("click", (event) => {
    const year = Number(document.getElementById("sync-year").value || new Date().getFullYear());
    runSync(event.currentTarget, "sync_enriched_year", { year });
  });

  const ctx = { app, auth, db, functions };
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

onAuthStateChanged(auth, (user) => {
  if (!user) {
    renderLoginForm(root, app, () => {
      window.location.hash = "#/homepage";
      renderRoute();
    });
    return;
  }
  renderRoute();
});

window.addEventListener("hashchange", () => {
  if (auth.currentUser) {
    renderRoute();
  }
});
