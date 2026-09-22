const $ = (selector) => document.querySelector(selector);
const now = new Date();
$("#manager-date").textContent = now.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }).toUpperCase();

let reports = [];
let managerContext = null;
let managerGeneration = 0;
let checkingManager = null;
function clearManagerPrivate() {
  managerGeneration += 1;
  reports = [];
  ["#report-inbox", "#manager-result-date", "#manager-result-title", "#manager-result-summary", "#manager-result-status", "#manager-insights", "#manager-next-step", "#manager-failed", "#manager-list", "#weekly-overview", "#manager-count", "#manager-store-name"].forEach((selector) => { $(selector).textContent = ""; });
  $("#heads-up-input").value = "";
  $("#manager-heads-up").textContent = "No manager notes have been posted yet.";
  $("#manager-name").textContent = "Manager";
  $("#manager-result").classList.add("hidden");
  $("#manager-empty").classList.remove("hidden");
  $("#heads-up-modal").close?.();
}
async function refreshManagerContext() {
  if (checkingManager) return checkingManager;
  checkingManager = (async () => {
    const response = await fetch("/api/accounts/status", { cache: "no-store" });
    let payload = await response.json();
    if (!response.ok) throw new Error("Please sign in again.");
    if (!payload.authenticated && payload.reauthenticationRequired) {
      const legacy = await fetch("/api/auth/status", { cache: "no-store" });
      payload = await legacy.json();
      if (!legacy.ok) throw new Error("Please sign in again.");
    }
    if (!payload.authenticated) throw new Error("Please sign in again.");
    if (payload.actor && !payload.actor.capabilities.includes("reports.view")) {
      clearManagerPrivate();
      window.location.replace(payload.actor.capabilities.includes("reports.submit") ? "/crew.html" : "/accounts.html");
      return false;
    }
    if (!payload.actor && payload.role !== "manager") throw new Error("Manager sign-in is required.");
    const signature = (value) => value.actor ? `${value.actor.userId}:${value.actor.storeId}:${value.actor.capabilities.join(',')}` : `legacy:${value.role}`;
    const changed = managerContext && signature(managerContext) !== signature(payload);
    const initial = !managerContext;
    if (changed) clearManagerPrivate();
    managerContext = payload;
    applyManagerIdentity(payload);
    const capabilities = payload.actor?.capabilities || [];
    $("#manager-account-link").classList.toggle("hidden", !payload.actor);
    $("#manager-inventory-link").classList.toggle("hidden", !capabilities.includes("inventory.view"));
    $("#heads-up-update").classList.toggle("hidden", Boolean(payload.actor) && !capabilities.includes("reports.manage"));
    $("#add-manager").classList.toggle("hidden", Boolean(payload.actor) && !capabilities.includes("memberships.manage"));
    $("#add-manager").textContent = payload.actor ? "Manage team" : "Add New";
    document.querySelector('.brand').href = payload.actor && !capabilities.includes("reports.submit") ? "/accounts.html" : "/crew.html";
    $("#manager-store-name").textContent = payload.actor ? payload.stores?.find((store) => store.storeId === payload.actor.storeId)?.storeName || 'Your selected store' : '';
    document.querySelector('main').style.visibility = 'visible';
    if (initial || changed) showManager();
    return !changed;
  })();
  try { return await checkingManager; }
  catch (error) {
    clearManagerPrivate();
    document.querySelector('main').style.visibility = 'hidden';
    window.location.replace('/');
    return false;
  } finally { checkingManager = null; }
}
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
  if (payload.actor?.displayName || payload.managerName) $("#manager-name").textContent = payload.actor?.displayName || payload.managerName;
}

function loadHeadsUp() {
  const generation = managerGeneration;
  fetch("/api/heads-up")
    .then((response) => response.json())
    .then((payload) => {
      if (generation !== managerGeneration) return;
      $("#heads-up-input").value = payload.message || "";
      $("#manager-heads-up").textContent = payload.message || "No manager notes have been posted yet.";
    })
    .catch(() => {});
}

function loadManagers() {
  const generation = managerGeneration;
  fetch("/api/managers")
    .then(async (response) => {
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Manager accounts unavailable.");
      return payload;
    })
    .then((payload) => {
      if (generation !== managerGeneration) return;
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
      if (generation !== managerGeneration) return;
      $("#manager-list").innerHTML = '<p class="failed-message">Manager accounts are temporarily unavailable.</p>';
    });
}

async function saveHeadsUp(event) {
  event.preventDefault();
  const renderedStoreId = managerContext?.actor?.storeId;
  if (!await refreshManagerContext()) return;
  const generation = managerGeneration;
  const modal = $("#heads-up-modal");
  const status = $("#heads-up-status");
  fetch("/api/heads-up", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: $("#heads-up-input").value, ...(renderedStoreId ? { expectedStoreId: renderedStoreId } : {}) }),
  })
    .then(async (response) => {
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Unable to save the note.");
      return payload;
    })
    .then((payload) => {
      if (generation !== managerGeneration) return;
      $("#manager-heads-up").textContent = payload.message || "No manager notes have been posted yet.";
      status.classList.add("hidden");
      if (typeof modal.close === "function") modal.close();
      else modal.removeAttribute("open");
    })
    .catch((error) => {
      if (generation !== managerGeneration) return;
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

function loadWeeklyOverview(attempt = 0) {
  const generation = managerGeneration;
  fetch("/api/weekly-overview")
    .then(async (response) => {
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Weekly overview unavailable.");
      return payload;
    })
    .then((payload) => {
      if (generation !== managerGeneration) return;
      if (payload.status === "pending") {
        $("#weekly-overview").textContent = attempt < 10
          ? "Preparing the weekly overview…"
          : "The weekly overview is still being prepared. Refresh the page in a moment.";
        if (attempt < 10) window.setTimeout(() => { if (generation === managerGeneration) loadWeeklyOverview(attempt + 1); }, 3000);
        return;
      }
      const points = [...(payload.wins || []), ...(payload.risks || [])];
      const total = Number(payload.reportCount) || 0;
      const included = Number(payload.includedReportCount) || 0;
      const coverage = payload.truncated
        ? `Partial overview: includes ${included} of ${total} reports from the last 7 days. Older reports are not included; review the inbox for the full week.`
        : `${total} report${total === 1 ? "" : "s"} from the last 7 days`;
      $("#weekly-overview").innerHTML = `<p>${escapeHtml(payload.summary || "No summary is available yet.")}</p>${points.length ? `<div class="weekly-points">${points.map((point) => `<div class="insight"><span class="insight-mark">↳</span><span>${escapeHtml(point)}</span></div>`).join("")}</div>` : ""}<p class="weekly-follow-up">${escapeHtml(payload.follow_up || "")}</p><small>${escapeHtml(coverage)}</small>`;
    })
    .catch((error) => {
      if (generation !== managerGeneration) return;
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
      <span><strong>${escapeHtml(report.employee || "Crewmember")}</strong><small>${escapeHtml(report.shift)} shift · ${formatLocalDate(report.date, { month: "short", day: "numeric" })}</small></span>
      <span class="report-state">${escapeHtml(report.status)}</span>
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
  const generation = managerGeneration;
  fetch("/api/reports")
    .then(async (response) => {
      const payload = await response.json();
      if (generation !== managerGeneration) return;
      if (response.status === 401 || response.status === 403) {
        clearManagerPrivate();
        window.location.replace("/");
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
        window.setTimeout(() => { if (generation === managerGeneration) loadReports(); }, 2500);
      }
    })
    .catch(() => {
      if (generation !== managerGeneration) return;
      $("#manager-count").textContent = "UNAVAILABLE";
    });
}

$("#logout-button").addEventListener("click", () => {
    fetch("/api/accounts/logout", { method: "POST" })
      .then((response) => { if (response.ok) { clearManagerPrivate(); window.location.replace("/"); } });
});

$("#add-manager").addEventListener("click", () => {
  if (managerContext?.actor) { window.location.assign("/accounts.html#team-section"); return; }
  fetch("/api/auth/logout", { method: "POST" })
    .finally(() => window.location.replace("/?manager=1"));
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

window.addEventListener('focus', refreshManagerContext);
document.addEventListener('visibilitychange', () => { if (!document.hidden) refreshManagerContext(); });
window.addEventListener('pageshow', () => {
  const wasHidden = document.querySelector('main').style.visibility === 'hidden';
  refreshManagerContext().then((current) => { if (current && wasHidden) showManager(); });
});
window.addEventListener('pagehide', () => { clearManagerPrivate(); document.querySelector('main').style.visibility = 'hidden'; });
refreshManagerContext();
