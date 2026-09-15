const form = document.querySelector("#sign-in-form");
const error = document.querySelector("#auth-error");

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
