import { createClient } from '@supabase/supabase-js';

export function renderLoginForm(container, supabase, onSuccess) {
  container.innerHTML = `
    <div class="main">
      <h2>Login Required</h2>
      <div class="panel" style="max-width: 460px;">
        <label for="email">Email</label>
        <input id="email" type="email" placeholder="you@example.com" />
        <div style="height: 10px;"></div>
        <label for="password">Password</label>
        <input id="password" type="password" placeholder="Password" />
        <div style="height: 12px;"></div>
        <button id="login-btn" class="button">Login</button>
        <p id="login-error" class="error" style="display: none;"></p>
      </div>
    </div>
  `;

  const emailInput = container.querySelector("#email");
  const passwordInput = container.querySelector("#password");
  const button = container.querySelector("#login-btn");
  const errorEl = container.querySelector("#login-error");

  const submit = async () => {
    errorEl.style.display = "none";
    button.disabled = true;
    button.textContent = "Logging in...";
    try {
      const { error } = await supabase.auth.signInWithPassword({
        email: emailInput.value.trim(),
        password: passwordInput.value
      });
      if (error) throw error;
      onSuccess();
    } catch (err) {
      errorEl.textContent = err.message || "Login failed.";
      errorEl.style.display = "block";
    } finally {
      button.disabled = false;
      button.textContent = "Login";
    }
  };

  button.addEventListener("click", submit);
  passwordInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      submit();
    }
  });
}

export async function signOut(supabase) {
  await supabase.auth.signOut();
}
