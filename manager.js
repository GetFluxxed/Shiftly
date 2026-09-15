const $ = (selector) => document.querySelector(selector);
const now = new Date();
$("#manager-date").textContent = now.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }).toUpperCase();

// Fixed manager instructions keep every briefing consistent and out of the employee flow.
const briefingInstructions = "Summarize the shift objectively for the store manager. Identify wins, operational risks, people or customer signals, and one concrete follow-up. Be concise, factual, and action-oriented.";
let reports = [];

function renderInbox() {
  const inbox = $("#report-inbox");
  if (!reports.length) {
    inbox.innerHTML = '<div class="inbox-empty">No shift reports have been submitted yet.</div>';
    return;
  }
  inbox.innerHTML = reports.map((report, index) => `
    <button class="report-row" type="button" data-index="${index}">
      <span><strong>${report.employee || "Crewmember"}</strong><small>${report.shift} shift · ${report.date}</small></span>
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
  $("#manager-result-summary").textContent = briefing.summary || report.notes || "Photo attached for review.";
  const insights = [...(briefing.wins || []), ...(briefing.risks || [])];
  $("#manager-insights").innerHTML = (insights.length ? insights : ["Review the submitted report and follow up with the team member if needed."])
    .map((item) => `<div class="insight"><span class="insight-mark">↳</span><span>${item}</span></div>`).join("");
  $("#manager-next-step").innerHTML = `<strong>Manager follow-up</strong>${briefing.follow_up || "Choose one action, assign an owner, and carry it into the next shift handoff."}`;
}

renderInbox();

fetch("/api/reports")
  .then((response) => response.json())
  .then((payload) => {
    reports = payload.reports;
    $("#manager-count").textContent = `${reports.length} RECEIVED`;
    renderInbox();
  })
  .catch(() => {
    $("#manager-count").textContent = "UNAVAILABLE";
  });
