const form = document.querySelector("#sign-in-form");
const error = document.querySelector("#auth-error");
const signupForm = document.querySelector("#sign-up-form");
const signupError = document.querySelector("#signup-error");
const managerSignupForm = document.querySelector("#manager-sign-up-form");
const managerSignupError = document.querySelector("#manager-signup-error");
const signinSwitches = document.querySelectorAll(".auth-switch");
const managerSignupRequested = new URLSearchParams(window.location.search).get("manager") === "1";

function showOnly(formToShow) {
  form.classList.toggle("hidden", formToShow !== form);
  signupForm.classList.toggle("hidden", formToShow !== signupForm);
  managerSignupForm.classList.toggle("hidden", formToShow !== managerSignupForm);
  signinSwitches.forEach((switchElement) => switchElement.classList.toggle("hidden", formToShow !== form));
}

if (managerSignupRequested) showOnly(managerSignupForm);

document.querySelector("#show-signup").addEventListener("click", () => {
  showOnly(signupForm);
});

document.querySelector("#show-signin").addEventListener("click", () => {
  showOnly(form);
  signupError.classList.add("hidden");
});

document.querySelector("#show-manager-signup").addEventListener("click", () => {
  showOnly(managerSignupForm);
});

document.querySelector("#show-signin-from-manager").addEventListener("click", () => {
  showOnly(form);
  managerSignupError.classList.add("hidden");
});

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
    if (payload.reauthenticationRequired) {
      const legacy = await fetch("/api/auth/status", { cache: "no-store" });
      const session = await legacy.json();
      if (legacy.ok && session.authenticated) window.location.replace(workspaceFor(session));
    }
  } catch { /* Keep sign-in available if the connection is temporarily unavailable. */ }
})();

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  error.classList.add("hidden");
  try {
    const username = document.querySelector("#username").value.trim();
    const response = await fetch(username ? "/api/accounts/login" : "/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        storeCode: document.querySelector("#store-code").value.trim(),
        ...(username ? { username } : {}),
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

signupForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  signupError.classList.add("hidden");
  try {
    const response = await fetch("/api/auth/signup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        adminKey: document.querySelector("#signup-admin-key").value,
        storeName: document.querySelector("#signup-store-name").value.trim(),
        storeCode: document.querySelector("#signup-store-code").value.trim(),
        crewPassword: document.querySelector("#signup-crew-password").value,
        managerUsername: document.querySelector("#signup-manager-name").value.trim(),
        managerPassword: document.querySelector("#signup-manager-password").value,
        confirmPassword: document.querySelector("#signup-manager-confirm").value,
      }),
    });

    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Unable to create the workspace.");
    window.location.replace("/manager.html");
  } catch (signupRequestError) {
    signupError.textContent = signupRequestError.message;
    signupError.classList.remove("hidden");
  }
});

managerSignupForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  managerSignupError.classList.add("hidden");
  try {
    const response = await fetch("/api/auth/add-manager", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        adminKey: document.querySelector("#manager-signup-admin-key").value,
        storeCode: document.querySelector("#manager-signup-store-code").value.trim(),
        managerUsername: document.querySelector("#manager-signup-name").value.trim(),
        managerPassword: document.querySelector("#manager-signup-password").value,
        confirmPassword: document.querySelector("#manager-signup-confirm").value,
      }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Unable to create the manager account.");
    window.location.replace("/manager.html");
  } catch (managerSignupRequestError) {
    managerSignupError.textContent = managerSignupRequestError.message;
    managerSignupError.classList.remove("hidden");
  }
});

window.addEventListener("pagehide", () => document.querySelectorAll('input[type="password"]').forEach((input) => { input.value = ""; }));
