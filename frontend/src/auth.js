function normalizeAuthError(err) {
  const raw = (err?.message || "").toLowerCase();
  if (!raw) {
    return "Login failed. Please try again.";
  }
  if (raw.includes("forbidden use of secret api key")) {
    return "Login is temporarily unavailable due to a server configuration issue. Please contact the app owner.";
  }
  if (raw.includes("invalid login credentials") || raw.includes("invalid_grant")) {
    return "Invalid password.";
  }
  if (raw.includes("email") && raw.includes("not confirmed")) {
    return "Please confirm your email before logging in.";
  }
  if (raw.includes("network") || raw.includes("fetch")) {
    return "Network error while logging in. Please check your connection and retry.";
  }
  return err.message || "Login failed. Please try again.";
}

export function renderLoginForm(container, supabase, onSuccess, loginEmail, initialError = "") {
  container.innerHTML = `
    <div class="main">
      <h2>Login Required</h2>
      <form id="login-form" class="panel" style="max-width: 460px;">
        <label for="password">Password</label>
        <input id="password" name="password" type="password" autocomplete="current-password" placeholder="Password" required />
        <div style="height: 12px;"></div>
        <button id="login-btn" class="button" type="submit">Login</button>
        <p id="login-error" class="error" role="alert" aria-live="polite" style="display: ${initialError ? "block" : "none"};">${initialError}</p>
      </form>
    </div>
  `;

  const form = container.querySelector("#login-form");
  const passwordInput = container.querySelector("#password");
  const button = container.querySelector("#login-btn");
  const errorEl = container.querySelector("#login-error");

  const submit = async () => {
    errorEl.style.display = "none";
    button.disabled = true;
    button.textContent = "Logging in...";
    try {
      const { error } = await supabase.auth.signInWithPassword({
        email: loginEmail,
        password: passwordInput.value,
      });
      if (error) throw error;
      onSuccess();
    } catch (err) {
      errorEl.textContent = normalizeAuthError(err);
      errorEl.style.display = "block";
    } finally {
      button.disabled = false;
      button.textContent = "Login";
    }
  };

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!passwordInput.value) {
      errorEl.textContent = "Please enter your password.";
      errorEl.style.display = "block";
      return;
    }
    submit();
  });
}

export async function signOut(supabase) {
  await supabase.auth.signOut();
}
