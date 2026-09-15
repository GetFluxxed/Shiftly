const form = document.querySelector("#sign-in-form");
const error = document.querySelector("#auth-error");
const signupForm = document.querySelector("#sign-up-form");
const signupError = document.querySelector("#signup-error");
const signupSwitch = document.querySelector(".auth-switch");

document.querySelector("#show-signup").addEventListener("click", () => {
  form.classList.add("hidden");
  signupSwitch.classList.add("hidden");
  signupForm.classList.remove("hidden");
});

document.querySelector("#show-signin").addEventListener("click", () => {
  signupForm.classList.add("hidden");
  form.classList.remove("hidden");
  signupSwitch.classList.remove("hidden");
  signupError.classList.add("hidden");
});

fetch("/api/auth/status")
  .then((response) => response.json())
  .then((payload) => {
    if (payload.role === "manager") window.location.replace("/manager.html");
    if (payload.role === "crew") window.location.replace("/crew.html");
  })
  .catch(() => {});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  error.classList.add("hidden");
  const role = document.querySelector('input[name="role"]:checked').value;
  try {
    const response = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        storeCode: document.querySelector("#store-code").value.trim(),
        password: document.querySelector("#password").value,
        role,
      }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Unable to sign in.");
    window.location.replace(role === "manager" ? "/manager.html" : "/crew.html");
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
