const $ = (selector) => document.querySelector(selector);

const notes = $("#notes");
const generateButton = $("#generate-button");
const emptyResult = $("#empty-result");
const resultContent = $("#result-content");
const loadingState = $("#loading-state");
const toast = $("#toast");
const MAX_CHARS = 2000;

const today = new Date();
$("#today").textContent = today.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }).toUpperCase();

function showToast(message) {
  toast.textContent = message;
  toast.classList.add("show");
  window.setTimeout(() => toast.classList.remove("show"), 2400);
}

notes.addEventListener("input", () => {
  if (notes.value.length > MAX_CHARS) notes.value = notes.value.slice(0, MAX_CHARS);
  $("#character-count").textContent = `${notes.value.length.toLocaleString()} / ${MAX_CHARS.toLocaleString()}`;
});

function createBriefing() {
  const input = notes.value.trim();
  const employee = $("#employee").value.trim();
  const shift = $("#shift").value;
  if (!employee || !input) {
    showToast("Enter your name and meaningful shift notes.");
    notes.focus();
    return;
  }

  emptyResult.classList.add("hidden");
  resultContent.classList.add("hidden");
  loadingState.classList.remove("hidden");
  loadingState.style.display = "flex";
  generateButton.disabled = true;

  fetch("/api/reports", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ employee, shift, notes: input }),
  })
    .then(async (response) => {
      const payload = await response.json();
      if (!response.ok) {
        const error = new Error(payload.error || "The report could not be submitted.");
        error.status = response.status;
        throw error;
      }
      return payload;
    })
    .then((payload) => {
      $("#result-date").textContent = payload.date.toUpperCase();
      $("#result-summary").textContent = `${employee ? `${employee} · ` : ""}Your report was reviewed and submitted successfully for manager review.`;
      loadingState.classList.add("hidden");
      loadingState.style.display = "";
      resultContent.classList.remove("hidden");
      generateButton.disabled = false;
    })
    .catch((error) => {
      loadingState.classList.add("hidden");
      loadingState.style.display = "";
      emptyResult.classList.remove("hidden");
      generateButton.disabled = false;
      if (error.status === 422) {
        notes.focus();
        notes.select();
      }
      showToast(error.message);
    });
}

generateButton.addEventListener("click", createBriefing);
$("#new-button").addEventListener("click", () => {
  $("#employee").value = "";
  $("#shift").value = "opening";
  notes.value = "";
  notes.dispatchEvent(new Event("input"));
  resultContent.classList.add("hidden");
  emptyResult.classList.remove("hidden");
  generateButton.disabled = false;
  $("#employee").focus();
});
