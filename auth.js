const form = document.querySelector("#sign-in-form");
const error = document.querySelector("#auth-error");
const signupForm = document.querySelector("#sign-up-form");
const signupError = document.querySelector("#signup-error");
const managerSignupForm = document.querySelector("#manager-sign-up-form");
const managerSignupError = document.querySelector("#manager-signup-error");
const signinSwitches = document.querySelectorAll(".auth-switch");

function showOnly(formToShow) {
  form.classList.toggle("hidden", formToShow !== form);
  signupForm.classList.toggle("hidden", formToShow !== signupForm);
  managerSignupForm.classList.toggle("hidden", formToShow !== managerSignupForm);
  signinSwitches.forEach((switchElement) => switchElement.classList.toggle("hidden", formToShow !== form));
}

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
  try {
    const response = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        storeCode: document.querySelector("#store-code").value.trim(),
        password: document.querySelector("#password").value,
      }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Unable to sign in.");
    window.location.replace(payload.role === "manager" ? "/manager.html" : "/crew.html");
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
