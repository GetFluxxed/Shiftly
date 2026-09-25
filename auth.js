const form = document.querySelector("#sign-in-form");
const error = document.querySelector("#auth-error");

function workspaceFor(payload) {
  if (payload.actor) {
    const capabilities = payload.actor.capabilities || [];
    return capabilities.includes("reports.view") ? "/manager.html" : capabilities.includes("reports.submit") ? "/crew.html" : "/accounts.html";
  }
  return payload.role === "manager" ? "/manager.html" : "/crew.html";
}

(async () => {
  try {
    const response = await fetch("/api/accounts/status", { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok) return; // Invalid named cookies must never trigger legacy fallback.
    if (payload.authenticated) return window.location.replace(workspaceFor(payload));
  } catch { /* Keep sign-in available if the connection is temporarily unavailable. */ }
})();

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  error.classList.add("hidden");
  try {
    const username = document.querySelector("#username").value.trim();
    const response = await fetch("/api/accounts/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username,
        password: document.querySelector("#password").value,
      }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Unable to sign in.");
    document.querySelector("#password").value = "";
    window.location.replace(workspaceFor(payload));
  } catch (loginError) {
    error.textContent = loginError.message;
    error.classList.remove("hidden");
  }
});

window.addEventListener("pagehide", () => document.querySelectorAll('input[type="password"]').forEach((input) => { input.value = ""; }));
