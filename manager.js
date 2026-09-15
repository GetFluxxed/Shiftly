const $ = (selector) => document.querySelector(selector);
const now = new Date();
$("#manager-date").textContent = now.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }).toUpperCase();

let reports = [];
const authGate = $("#manager-auth-gate");
const managerGrid = $(".manager-grid");
const loginForm = $("#login-form");
const authError = $("#auth-error");

function showLogin() {
  authGate.classList.remove("hidden");
  managerGrid.classList.add("hidden");
}

function showManager() {
  authGate.classList.add("hidden");
  managerGrid.classList.remove("hidden");
  loadReports();
}

function renderInbox() {
  const inbox = $("#report-inbox");
  if (!reports.length) {
    inbox.innerHTML = '<div class="inbox-empty">No shift reports have been submitted yet.</div>';
    return;
  }
  inbox.innerHTML = reports.map((report, index) => `
    <button class="report-row" type="button" data-index="${index}">
      <span><strong>${report.employee || "Crewmember"}</strong><small>${report.shift} shift · ${report.date}</small></span>
      <span class="report-state">${report.status}</span>
      <span class="report-arrow">→</span>
    </button>
  `).join("");
  inbox.querySelectorAll(".report-row").forEach((row) => row.addEventListener("click", () => createManagerBriefing(reports[Number(row.dataset.index)])));
}

function createManagerBriefing(report) {
  const briefing = report.briefing || {};
  $("#manager-empty").classList.add("hidden");
  $("#manager-result").classList.remove("hidden");
  $("#manager-result-date").textContent = report.date.toUpperCase();
  $("#manager-result-title").textContent = `${report.employee || "Crewmember"} · ${report.shift} shift`;
  $("#manager-result-summary").textContent = report.notes;
  $("#manager-result-status").textContent = report.status.toUpperCase();
  $("#manager-briefing").classList.toggle("hidden", report.status !== "completed");
  $("#manager-pending").classList.toggle("hidden", report.status !== "pending" && report.status !== "processing");
  $("#manager-failed").classList.toggle("hidden", report.status !== "failed");
  if (report.status === "failed") $("#manager-failed").textContent = report.error || "Briefing generation failed.";
  if (report.status !== "completed") return;
  const insights = [...(briefing.wins || []), ...(briefing.risks || [])];
  $("#manager-insights").innerHTML = (insights.length ? insights : ["Review the submitted report and follow up with the team member if needed."])
    .map((item) => `<div class="insight"><span class="insight-mark">↳</span><span>${item}</span></div>`).join("");
  $("#manager-next-step").innerHTML = `<strong>Manager follow-up</strong>${briefing.follow_up || "Choose one action, assign an owner, and carry it into the next shift handoff."}`;
}

function loadReports() {
  fetch("/api/reports")
    .then(async (response) => {
      const payload = await response.json();
      if (response.status === 401) {
        showLogin();
        return;
      }
      if (!response.ok) throw new Error(payload.error || "Reports could not be loaded.");
      reports = payload.reports;
      $("#manager-count").textContent = `${reports.length} RECEIVED`;
      renderInbox();
      if (reports.some((report) => report.status === "pending" || report.status === "processing")) {
        window.setTimeout(loadReports, 2500);
      }
    })
    .catch(() => {
      $("#manager-count").textContent = "UNAVAILABLE";
    });
}

loginForm.addEventListener("submit", (event) => {
  event.preventDefault();
  authError.classList.add("hidden");
  fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ storeCode: $("#manager-store-code").value, password: $("#manager-password").value, role: "manager" }),
  })
    .then(async (response) => {
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Unable to sign in.");
      return payload;
    })
    .then(showManager)
    .catch((error) => {
      authError.textContent = error.message;
      authError.classList.remove("hidden");
    });
});

fetch("/api/auth/status")
  .then((response) => response.json())
  .then((payload) => payload.authenticated ? showManager() : showLogin())
  .catch(showLogin);
