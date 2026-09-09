import { authenticatedFetch } from "./auth.js";

const $ = (s) => document.querySelector(s);
const api = async (path, options = {}) => authenticatedFetch(path, options);
let inboxMessages = null;
let inboxLoading = false;
let inboxSyncing = false;
let inboxRefreshTimer = null;
let knownInboxIds = new Set();
let notificationBaselineReady = false;
let notificationCount = 0;

function injectNotificationUi() {
  if (!document.querySelector("#notification-stack")) {
    const stack = document.createElement("div");
    stack.id = "notification-stack";
    stack.setAttribute("aria-live", "polite");
    stack.setAttribute("aria-label", "Notifications");
    document.body.appendChild(stack);
  }
  if (!document.querySelector("#notification-style")) {
    const style = document.createElement("style");
    style.id = "notification-style";
    style.textContent = `
      #notification-stack{position:fixed;top:72px;right:22px;z-index:9000;width:min(380px,calc(100vw - 28px));display:flex;flex-direction:column;gap:10px;pointer-events:none}
      .known-notification{appearance:none;border:1px solid #dbe5df;background:#fff;color:#24332c;border-radius:13px;padding:13px 14px;display:grid;grid-template-columns:9px minmax(0,1fr) auto;gap:11px;align-items:start;text-align:left;box-shadow:0 18px 46px rgba(31,48,40,.16);cursor:pointer;pointer-events:auto;opacity:0;transform:translate3d(24px,-8px,0) scale(.98);transition:opacity .2s ease,transform .24s ease,box-shadow .2s ease}
      .known-notification.is-visible{opacity:1;transform:translate3d(0,0,0) scale(1)}
      .known-notification:hover{box-shadow:0 20px 52px rgba(31,48,40,.22);border-color:#c8d8ce}
      .known-notification-dot{width:8px;height:8px;border-radius:50%;background:#315d50;margin-top:5px;box-shadow:0 0 0 4px #edf4ef}
      .known-notification-copy{min-width:0;display:grid;gap:2px}
      .known-notification-copy strong{font-size:11px;line-height:1.2;font-weight:750;letter-spacing:.01em}
      .known-notification-copy small{font-size:9px;line-height:1.3;color:#6d7972;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
      .known-notification-copy p{margin:2px 0 0;font-size:11px;line-height:1.4;color:#34443b;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
      .known-notification-arrow{font-size:15px;line-height:1;color:#6a8176;padding-top:1px}
      @media(max-width:600px){#notification-stack{top:62px;right:14px;width:calc(100vw - 28px)}.known-notification{padding:12px}}
    `;
    document.head.appendChild(style);
  }
  const inboxNav = document.querySelector('[data-view="inbox"]');
  if (inboxNav && !inboxNav.querySelector(".known-inbox-badge")) {
    const badge = document.createElement("span");
    badge.className = "known-inbox-badge";
    badge.hidden = true;
    badge.style.cssText = "display:inline-grid;place-items:center;min-width:16px;height:16px;padding:0 4px;margin-left:auto;border-radius:99px;background:#315d50;color:#fff;font-size:8px;font-weight:750;line-height:1;";
    inboxNav.appendChild(badge);
  }
}

function notificationEnabled() {
  const toggle = $("#notify-conversations");
  if (toggle) return toggle.checked;
  const saved = localStorage.getItem("known.notify.conversations");
  return saved !== "false";
}

function messageKey(message) {
  return message?.external_message_id || `${message?.external_thread_id || "thread"}:${message?.received_at || ""}:${message?.sender_email || ""}:${message?.subject || ""}`;
}

function incrementNotificationBadge() {
  notificationCount += 1;
  const badge = document.querySelector(".known-inbox-badge");
  if (badge) { badge.textContent = notificationCount > 9 ? "9+" : String(notificationCount); badge.hidden = false; badge.style.display = "inline-grid"; }
  if (!document.hidden) return;
  document.title = "New email · Known";
}

function clearNotificationBadge() {
  notificationCount = 0;
  const badge = document.querySelector(".known-inbox-badge");
  if (badge) { badge.hidden = true; badge.style.display = "none"; }
  if (document.title === "New email · Known") document.title = "Known — Customer Workspace";
}

function dismissNotification(toast) {
  if (!toast) return;
  toast.classList.remove("is-visible");
  window.setTimeout(() => toast.remove(), 220);
}

function showCustomerNotification(message) {
  if (!notificationEnabled()) return;
  const stack = $("#notification-stack");
  if (!stack) return;
  const key = messageKey(message);
  const existing = [...stack.children].find((node) => node.dataset.notificationId === key);
  if (existing) return;

  const toast = document.createElement("button");
  toast.type = "button";
  toast.className = "known-notification";
  toast.dataset.notificationId = key;
  toast.innerHTML = `<span class="known-notification-dot" aria-hidden="true"></span><span class="known-notification-copy"><strong>New email</strong><small></small><p></p></span><span class="known-notification-arrow" aria-hidden="true">↗</span>`;
  toast.querySelector("small").textContent = message.sender_email || "Customer";
  toast.querySelector("p").textContent = message.subject || "New support message";
  toast.setAttribute("aria-label", `New email from ${message.sender_email || "customer"}. Open conversation.`);
  toast.addEventListener("click", () => {
    clearNotificationBadge();
    dismissNotification(toast);
    const detail = {
      customerId: message.customer_id || null,
      sessionId: message.session_id || (message.external_thread_id ? `gmail:${message.external_thread_id}` : null),
      senderEmail: message.sender_email || null,
      source: "notification"
    };
    window.dispatchEvent(new CustomEvent("known:gmail-session", { detail }));
    window.dispatchEvent(new CustomEvent("known:notification-open", { detail }));
  });
  stack.appendChild(toast);
  requestAnimationFrame(() => toast.classList.add("is-visible"));
  incrementNotificationBadge();
  window.setTimeout(() => dismissNotification(toast), 8000);
}

function notifyForNewMessages(messages) {
  const currentIds = new Set((messages || []).map(messageKey));
  if (!notificationBaselineReady) {
    knownInboxIds = currentIds;
    notificationBaselineReady = true;
    return;
  }
  const fresh = (messages || [])
    .filter((message) => !knownInboxIds.has(messageKey(message)))
    .sort((a, b) => Date.parse(a.received_at || "") - Date.parse(b.received_at || ""));
  knownInboxIds = currentIds;
  fresh.forEach(showCustomerNotification);
}

async function refreshGmailStatus() {
  const response = await api("/api/integrations/gmail/status").catch(() => null);
  if (!response) return null;
  const data = await response.json().catch(() => ({}));
  const node = $("#gmail-status"); const button = $("#connect-gmail");
  if (node && button) {
    node.textContent = data.connected ? `Connected: ${data.email || "support inbox"}` : (data.configured ? "Not connected yet." : "Google OAuth is not configured on the backend.");
    button.textContent = data.connected ? "Reconnect Gmail" : "Connect Gmail";
  }
  window.dispatchEvent(new CustomEvent("known:gmail-status", { detail: data }));
  return data;
}

async function connectGmail() {
  const response = await api("/api/gmail/connect");
  const data = await response?.json().catch(() => ({}));
  if (!response?.ok || !data.authorization_url) { alert(data?.detail || "Unable to start Gmail connection."); return; }
  location.href = data.authorization_url;
}

let csvInspection = null;
function showImportResult(message, hidden = false) { const result = $("#setup-result"); if (!result) return; result.hidden = hidden; result.textContent = message; }
function setCsvState(message) { const node = $("#csv-file-state"); if (node) node.textContent = message; }
async function readCsvFile(file) { const buffer = await file.arrayBuffer(); const bytes = new Uint8Array(buffer); if (bytes[0] === 0xff && bytes[1] === 0xfe) return new TextDecoder("utf-16le").decode(buffer); if (bytes[0] === 0xfe && bytes[1] === 0xff) return new TextDecoder("utf-16be").decode(buffer); return new TextDecoder("utf-8", { fatal: false }).decode(buffer); }
function openImportModal() { const modal = $("#csv-import-modal"); const complete = $("#csv-complete"); if (modal) modal.hidden = false; if (complete) complete.hidden = true; const bar = $("#csv-progress-bar"); if (bar) bar.style.width = "0%"; }
function updateImportProgress(percent, label, message = null) { const bar = $("#csv-progress-bar"); const progressLabel = $("#csv-progress-label"); const progressMessage = $("#csv-import-message"); if (bar) bar.style.width = `${Math.max(0, Math.min(100, percent))}%`; if (progressLabel) progressLabel.textContent = label; if (message && progressMessage) progressMessage.textContent = message; }
function finishImportModal() { updateImportProgress(100, "Import complete", "Your customers and orders are now stored in the Known workspace."); const complete = $("#csv-complete"); if (complete) complete.hidden = false; }

async function inspectCsvFile(file) {
  const button = $("#import-csv");
  if (!file) { csvInspection = null; if (button) { button.disabled = true; button.textContent = "Add to Customers"; } setCsvState("Choose a CSV file to continue."); showImportResult("Choose a CSV file to import.", false); return; }
  if (!file.name.toLowerCase().endsWith(".csv")) { csvInspection = null; if (button) { button.disabled = true; button.textContent = "Add to Customers"; } setCsvState("That file is not a CSV."); showImportResult("Please choose a CSV file.", false); return; }
  if (file.size > 5 * 1024 * 1024) { csvInspection = null; if (button) { button.disabled = true; button.textContent = "Add to Customers"; } setCsvState("This CSV is larger than 5 MB."); showImportResult("Please choose a CSV smaller than 5 MB.", false); return; }
  if (button) { button.disabled = true; button.textContent = "Inspecting…"; }
  setCsvState(`Reading ${file.name}…`); showImportResult(`Reading ${file.name}…`, false);
  try {
    const csvText = await readCsvFile(file);
    if (!csvText.trim()) throw new Error("The selected CSV is empty.");
    const response = await api("/api/imports/csv/inspect", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ csv_text: csvText, file_name: file.name }) });
    const data = await response?.json().catch(() => ({}));
    if (!response?.ok) throw new Error(data?.detail || `CSV inspection failed (${response?.status || "network"})`);
    csvInspection = { csvText, fileName: file.name, data };
    setCsvState(`${file.name} · ${Number(data.row_count || 0).toLocaleString()} rows · ${Number(data.customer_count || 0).toLocaleString()} customers`);
    showImportResult(`${file.name} is ready · ${Number(data.row_count || 0).toLocaleString()} rows · ${Number(data.customer_count || 0).toLocaleString()} customers · ${Number(data.order_count || 0).toLocaleString()} orders.`, false);
    if (button) { button.disabled = false; button.textContent = "Add to Customers"; }
  } catch (error) {
    csvInspection = null;
    const message = error?.message || "Could not inspect CSV.";
    setCsvState(message); showImportResult(message, false);
    if (button) { button.disabled = true; button.textContent = "Add to Customers"; }
  }
}

async function importCsv() {
  const button = $("#import-csv");
  if (!csvInspection) { await inspectCsvFile($("#csv-file")?.files?.[0]); return; }
  if (button) { button.disabled = true; button.textContent = "Adding…"; }
  openImportModal(); updateImportProgress(8, "Preparing…", `Preparing ${csvInspection.fileName} for your customer workspace.`); await new Promise((resolve) => setTimeout(resolve, 250)); updateImportProgress(25, "Uploading records…", "Sending the CSV records to Known.");
  try {
    const response = await api("/api/imports/csv/commit", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ csv_text: csvInspection.csvText, file_name: csvInspection.fileName }) });
    updateImportProgress(65, "Writing customers and orders…", "Saving customer records and order history to the workspace database.");
    const data = await response?.json().catch(() => ({}));
    if (!response?.ok) throw new Error(data?.detail || `Import failed (${response?.status || "network"})`);
    updateImportProgress(88, "Building customer memory…", "Initializing durable customer memory from the imported history."); await new Promise((resolve) => setTimeout(resolve, 300));
    showImportResult(`Imported ${Number(data.customers || 0).toLocaleString()} customers and ${Number(data.orders || 0).toLocaleString()} orders. Customer memory is ready.`, false); csvInspection = null; if (button) button.textContent = "Added"; finishImportModal(); window.dispatchEvent(new CustomEvent("known:import-complete", { detail: data }));
  } catch (error) {
    const modal = $("#csv-import-modal"); if (modal) modal.hidden = true;
    const message = error?.message || "Import failed."; showImportResult(message, false);
    if (button) { button.disabled = false; button.textContent = "Add to Customers"; }
  }
}

function renderInbox(messages, syncResult = null) {
  const list = $("#inbox-list"); const status = $("#inbox-status"); if (!list || !status) return;
  if (syncResult) status.textContent = `Sync complete · ${syncResult.processed} processed · ${syncResult.matched} matched · ${syncResult.created || 0} new customers · ${syncResult.failed || 0} failed`;
  if (!messages.length) { list.innerHTML = ""; if (!syncResult) status.textContent = "No processed support conversations yet."; return; }
  list.innerHTML = "";
  const grouped = new Map();
  messages.forEach((message) => {
    const key = message.session_id || (message.external_thread_id ? `gmail:${message.external_thread_id}` : message.external_message_id);
    const previous = grouped.get(key);
    if (!previous || Date.parse(message.received_at || "") > Date.parse(previous.received_at || "")) grouped.set(key, message);
  });
  [...grouped.values()].forEach((message) => {
    const row = document.createElement("button"); row.type = "button"; row.className = "directory-row";
    row.innerHTML = `<span class="directory-avatar">✉</span><span class="directory-info"><strong></strong><small></small></span>`;
    row.querySelector("strong").textContent = message.subject || "No subject";
    row.querySelector("small").textContent = `${message.sender_email || "Unknown sender"} · ${message.body || ""}`;
    row.addEventListener("click", () => {
      clearNotificationBadge();
      const customerId = message.customer_id || null;
      const sessionId = message.session_id || (message.external_thread_id ? `gmail:${message.external_thread_id}` : null);
      window.dispatchEvent(new CustomEvent("known:gmail-session", { detail: { customerId, sessionId, senderEmail: message.sender_email } }));
    });
    list.appendChild(row);
  });
}

async function loadInboxMessages({showLoading = false} = {}) {
  if (inboxLoading) return inboxMessages;
  if (inboxMessages) { renderInbox(inboxMessages); return inboxMessages; }
  if (showLoading) { const status = $("#inbox-status"); if (status) status.textContent = "Loading inbox…"; }
  inboxLoading = true;
  try {
    const messages = await api(`/api/integrations/gmail/messages?_=${Date.now()}`, { cache: "no-store" });
    const messageData = await messages?.json().catch(() => ({ messages: [] }));
    if (messages?.ok) inboxMessages = messageData.messages || [];
    renderInbox(inboxMessages || []);
    knownInboxIds = new Set((inboxMessages || []).map(messageKey));
    notificationBaselineReady = true;
    return inboxMessages || [];
  } finally { inboxLoading = false; }
}

async function refreshInboxMessages() {
  if (inboxLoading) return inboxMessages || [];
  inboxLoading = true;
  try {
    const response = await api(`/api/integrations/gmail/messages?_=${Date.now()}`, { cache: "no-store" });
    const data = await response?.json().catch(() => ({ messages: [] }));
    if (!response?.ok) return inboxMessages || [];
    const nextMessages = data.messages || [];
    notifyForNewMessages(nextMessages);
    inboxMessages = nextMessages;
    renderInbox(inboxMessages);
    window.dispatchEvent(new CustomEvent("known:inbox-refresh", { detail: { messages: inboxMessages } }));
    return inboxMessages;
  } finally { inboxLoading = false; }
}

async function syncInbox({background = false} = {}) {
  if (inboxSyncing) return inboxMessages || [];
  inboxSyncing = true;
  try {
    if (!background) await loadInboxMessages({showLoading: !inboxMessages});
    const response = await api("/api/integrations/gmail/sync", { method: "POST" });
    const data = await response?.json().catch(() => ({}));
    if (!response?.ok) { const node = $("#inbox-status"); if (node) node.textContent = data.detail || "Unable to sync Gmail."; await refreshGmailStatus(); return inboxMessages || []; }
    await refreshInboxMessages();
    renderInbox(inboxMessages || [], data);
    await refreshGmailStatus();
    return inboxMessages || [];
  } finally { inboxSyncing = false; }
}

function startInboxRefresh() {
  if (inboxRefreshTimer) return;
  inboxRefreshTimer = window.setInterval(() => {
    refreshInboxMessages().catch((error) => console.warn("Live inbox refresh failed:", error));
  }, 1000);
}

async function handleViewChange(event) {
  const view = event.detail?.view;
  if (view === "settings") await refreshGmailStatus();
  if (view === "inbox") {
    clearNotificationBadge();
    await loadInboxMessages({showLoading: !inboxMessages});
    refreshInboxMessages().catch((error) => console.warn("Background inbox refresh failed:", error));
  }
}

function init() {
  injectNotificationUi();
  document.addEventListener("visibilitychange", () => { if (!document.hidden) clearNotificationBadge(); });
  const fileInput = $("#csv-file"); const importButton = $("#import-csv"); if (importButton) importButton.disabled = true; fileInput?.addEventListener("change", () => inspectCsvFile(fileInput.files?.[0])); importButton?.addEventListener("click", importCsv); $("#go-to-customers")?.addEventListener("click", () => { location.href = "./index.html?view=customers&imported=1"; }); $("#connect-gmail")?.addEventListener("click", connectGmail); $("#sync-inbox")?.addEventListener("click", () => syncInbox()); window.addEventListener("known:view-change", handleViewChange); window.addEventListener("known:import-complete", async () => { await refreshGmailStatus(); }); startInboxRefresh(); loadInboxMessages().catch((error) => console.warn("Initial inbox load failed:", error)); refreshGmailStatus();
}
init();