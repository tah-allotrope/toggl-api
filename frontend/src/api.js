const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");

function endpoint(path) {
  if (!API_BASE_URL) {
    throw new Error("VITE_API_BASE_URL is not configured");
  }
  return `${API_BASE_URL}${path}`;
}

async function authHeaders(auth) {
  const user = auth.currentUser;
  if (!user) {
    throw new Error("You must be signed in");
  }
  const token = await user.getIdToken();
  return {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`
  };
}

export async function callApi(auth, path, payload = {}) {
  const response = await fetch(endpoint(path), {
    method: "POST",
    headers: await authHeaders(auth),
    body: JSON.stringify(payload)
  });

  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = body?.detail || body?.error || response.statusText || "Request failed";
    throw new Error(message);
  }
  return body;
}

export async function triggerSync(auth, syncType, payload = {}) {
  return callApi(auth, "/sync", {
    sync_type: syncType,
    ...payload
  });
}
