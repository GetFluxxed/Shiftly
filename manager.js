const $ = (selector) => document.querySelector(selector);
const now = new Date();
$("#manager-date").textContent = now.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }).toUpperCase();

let reports = [];
const authGate = $("#manager-auth-gate");
const managerGrid = $(".manager-grid");
const loginForm = $("#login-form");
const authError = $("#auth-error");
const formatLocalDate = (value, options = { month: "short", day: "numeric", year: "numeric" }) => (
  value ? new Date(value).toLocaleDateString("en-US", options) : ""
);
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (character) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[character]));

function showLogin() {
  authGate.classList.remove("hidden");
  managerGrid.classList.add("hidden");
}

function showManager() {
  authGate.classList.add("hidden");
  managerGrid.classList.remove("hidden");
  loadReports();
  loadHeadsUp();
  loadManagers();
  loadWeeklyOverview();
}

function applyManagerIdentity(payload) {
  if (payload.managerName) $("#manager-name").textContent = payload.managerName;
}

function loadHeadsUp() {
  fetch("/api/heads-up")
    .then((response) => response.json())
    .then((payload) => {
      $("#heads-up-input").value = payload.message || "";
      $("#manager-heads-up").textContent = payload.message || "No manager notes have been posted yet.";
    })
    .catch(() => {});
}

function loadManagers() {
  fetch("/api/managers")
    .then(async (response) => {
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Manager accounts unavailable.");
      return payload;
    })
    .then((payload) => {
      const managerList = $("#manager-list");
      const managers = [...payload.managers].sort((a, b) => {
        if (!a.lastSignIn && !b.lastSignIn) return a.name.localeCompare(b.name);
        if (!a.lastSignIn) return 1;
        if (!b.lastSignIn) return -1;
        const signInDifference = new Date(b.lastSignIn) - new Date(a.lastSignIn);
        return signInDifference || a.name.localeCompare(b.name);
      });
      if (!managers.length) {
        managerList.innerHTML = '<p class="pending-message">No manager accounts found.</p>';
        return;
      }
      managerList.innerHTML = managers.map((manager) => `
        <div class="manager-list-item">
          <strong>${escapeHtml(manager.name)}</strong>
          <small>${manager.lastSignIn ? `Last sign in · ${formatLocalDate(manager.lastSignIn)} ${new Date(manager.lastSignIn).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })}` : "No sign in recorded"}</small>
        </div>
      `).join("");
    })
    .catch(() => {
      $("#manager-list").innerHTML = '<p class="failed-message">Manager accounts are temporarily unavailable.</p>';
    });
}

function saveHeadsUp(event) {
  event.preventDefault();
  const modal = $("#heads-up-modal");
  const status = $("#heads-up-status");
  fetch("/api/heads-up", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: $("#heads-up-input").value }),
  })
    .then(async (response) => {
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Unable to save the note.");
      return payload;
    })
    .then((payload) => {
      $("#manager-heads-up").textContent = payload.message || "No manager notes have been posted yet.";
      status.classList.add("hidden");
      if (typeof modal.close === "function") modal.close();
      else modal.removeAttribute("open");
    })
    .catch((error) => {
      status.textContent = error.message;
      status.classList.remove("hidden");
    });
}

$("#heads-up-update").addEventListener("click", () => {
  const modal = $("#heads-up-modal");
  if (typeof modal.showModal === "function") {
    modal.showModal();
  } else {
    modal.setAttribute("open", "");
  }
  $("#heads-up-input").focus();
});
$("#heads-up-form").addEventListener("submit", saveHeadsUp);
$("#heads-up-cancel").addEventListener("click", () => {
  const modal = $("#heads-up-modal");
  if (typeof modal.close === "function") modal.close();
  else modal.removeAttribute("open");
});

function loadWeeklyOverview() {
  fetch("/api/weekly-overview")
    .then(async (response) => {
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Weekly overview unavailable.");
      return payload;
    })
    .then((payload) => {
      const points = [...(payload.wins || []), ...(payload.risks || [])];
      $("#weekly-overview").innerHTML = `<p>${escapeHtml(payload.summary || "No summary is available yet.")}</p>${points.length ? `<div class="weekly-points">${points.map((point) => `<div class="insight"><span class="insight-mark">↳</span><span>${escapeHtml(point)}</span></div>`).join("")}</div>` : ""}<p class="weekly-follow-up">${escapeHtml(payload.follow_up || "")}</p><small>${Number(payload.reportCount) || 0} report${payload.reportCount === 1 ? "" : "s"} from the last 7 days</small>`;
    })
    .catch((error) => {
      console.error("Weekly overview failed:", error);
      $("#weekly-overview").innerHTML = "<p class=\"failed-message\">Weekly overview is temporarily unavailable. Try refreshing the page.</p>";
    });
}

function renderInbox() {
  const inbox = $("#report-inbox");
  if (!reports.length) {
    inbox.innerHTML = '<div class="inbox-empty">No shift reports have been submitted yet.</div>';
    return;
  }
  inbox.innerHTML = reports.map((report, index) => `
    <button class="report-row" type="button" data-index="${index}">
      <span><strong>${report.employee || "Crewmember"}</strong><small>${report.shift} shift · ${formatLocalDate(report.date, { month: "short", day: "numeric" })}</small></span>
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
  $("#manager-result-date").textContent = formatLocalDate(report.date, { month: "short", day: "numeric" }).toUpperCase();
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
    .map((item) => `<div class="insight"><span class="insight-mark">↳</span><span>${escapeHtml(item)}</span></div>`).join("");
  $("#manager-next-step").innerHTML = `<strong>Manager follow-up</strong>${escapeHtml(briefing.follow_up || "Choose one action, assign an owner, and carry it into the next shift handoff.")}`;
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
      if (reports.length && !$("#manager-result").classList.contains("hidden")) {
        createManagerBriefing(reports[0]);
      } else if (reports.length) {
        createManagerBriefing(reports[0]);
      }
      if (reports.some((report) => report.status === "pending" || report.status === "processing")) {
        window.setTimeout(loadReports, 2500);
      }
    })
    .catch(() => {
      $("#manager-count").textContent = "UNAVAILABLE";
    });
}

$("#logout-button").addEventListener("click", () => {
    fetch("/api/auth/logout", { method: "POST" })
      .finally(() => window.location.replace("/"));
});

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
    .then((payload) => {
      applyManagerIdentity(payload);
      showManager();
    })
    .catch((error) => {
      authError.textContent = error.message;
      authError.classList.remove("hidden");
    });
});

fetch("/api/auth/status")
  .then((response) => response.json())
  .then((payload) => {
    applyManagerIdentity(payload);
    if (payload.authenticated && payload.role === "manager") showManager();
    else showLogin();
  })
  .catch(showLogin);
