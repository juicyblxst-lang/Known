import { getSession } from "./auth.js";

const API = window.KNOWN_API_URL || "";
const $ = (s) => document.querySelector(s);
const api = async (path, options = {}) => {
  const session = await getSession();
  if (!session) return null;
  return fetch(`${API}${path}`, { ...options, headers: { ...(options.headers || {}), Authorization: `Bearer ${session.accessToken}` } });
};

async function refreshGmailStatus() {
  const response = await api("/api/integrations/gmail/status");
  if (!response) return;
  const data = await response.json().catch(() => ({}));
  const node = $("#gmail-status"); const button = $("#connect-gmail");
  if (!node || !button) return;
  node.textContent = data.connected ? `Connected: ${data.email || "support inbox"}` : (data.configured ? "Not connected yet." : "Google OAuth is not configured on the backend.");
  button.textContent = data.connected ? "Reconnect Gmail" : "Connect Gmail";
}

async function connectGmail() {
  const response = await api("/api/gmail/connect");
  const data = await response?.json().catch(() => ({}));
  if (!response?.ok || !data.authorization_url) { alert(data?.detail || "Unable to start Gmail connection."); return; }
  location.href = data.authorization_url;
}

let csvInspection = null;

function showImportResult(message, hidden = false) {
  const result = $("#setup-result");
  if (!result) return;
  result.hidden = hidden;
  result.textContent = message;
}

async function inspectCsvFile(file) {
  const button = $("#import-csv");
  if (!file) {
    csvInspection = null;
    if (button) button.disabled = true;
    showImportResult("Choose a CSV file to import.", false);
    return;
  }
  if (!file.name.toLowerCase().endsWith(".csv")) {
    csvInspection = null;
    if (button) button.disabled = true;
    showImportResult("Please choose a CSV file.", false);
    return;
  }

  if (button) { button.disabled = true; button.textContent = "Inspecting…"; }
  showImportResult(`Reading ${file.name}…`, false);
  try {
    const csvText = await file.text();
    const response = await api("/api/imports/csv/inspect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ csv_text: csvText, file_name: file.name })
    });
    const data = await response?.json().catch(() => ({}));
    if (!response?.ok) throw new Error(data?.detail || `CSV inspection failed (${response?.status || "network"})`);
    csvInspection = { csvText, fileName: file.name, data };
    showImportResult(`${file.name} is ready · ${Number(data.row_count || 0).toLocaleString()} rows · ${Number(data.customer_count || 0).toLocaleString()} customers · ${Number(data.order_count || 0).toLocaleString()} orders.`, false);
    if (button) { button.disabled = false; button.textContent = "Import"; }
  } catch (error) {
    csvInspection = null;
    showImportResult(error.message || "Could not inspect CSV.", false);
    if (button) { button.disabled = true; button.textContent = "Import"; }
  }
}

async function importCsv() {
  const button = $("#import-csv");
  if (!csvInspection) {
    await inspectCsvFile($("#csv-file")?.files?.[0]);
    return;
  }
  if (button) { button.disabled = true; button.textContent = "Importing…"; }
  showImportResult(`Importing ${csvInspection.fileName}…`, false);
  try {
    const response = await api("/api/imports/csv/commit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ csv_text: csvInspection.csvText, file_name: csvInspection.fileName })
    });
    const data = await response?.json().catch(() => ({}));
    if (!response?.ok) throw new Error(data?.detail || `Import failed (${response?.status || "network"})`);
    showImportResult(`Imported ${Number(data.customers || 0).toLocaleString()} customers and ${Number(data.orders || 0).toLocaleString()} orders. Customer memory is ready.`, false);
    csvInspection = null;
    if (button) button.textContent = "Imported";
    setTimeout(() => location.reload(), 900);
  } catch (error) {
    showImportResult(error.message || "Import failed.", false);
    if (button) { button.disabled = false; button.textContent = "Import"; }
  }
}

function renderInbox(messages, syncResult = null) {
  const list = $("#inbox-list"); const status = $("#inbox-status");
  if (!list || !status) return;
  if (syncResult) status.textContent = `Sync complete · ${syncResult.processed} processed · ${syncResult.matched} matched · ${syncResult.created || 0} new customers · ${syncResult.failed || 0} failed`;
  if (!messages.length) { list.innerHTML = ""; return; }
  list.innerHTML = "";
  messages.forEach((message) => {
    const row = document.createElement("button"); row.type = "button"; row.className = "directory-row";
    row.innerHTML = `<span class="directory-avatar">✉</span><span class="directory-info"><strong></strong><small></small></span>`;
    row.querySelector("strong").textContent = message.subject || "No subject";
    row.querySelector("small").textContent = `${message.sender_email || "Unknown sender"} · ${message.body || ""}`;
    row.addEventListener("click", () => {
      if (!message.customer_id) return;
      window.dispatchEvent(new CustomEvent("known:gmail-session", { detail: { customerId: message.customer_id, sessionId: message.session_id } }));
    });
    list.appendChild(row);
  });
}

async function syncInbox() {
  const response = await api("/api/integrations/gmail/sync", { method: "POST" });
  const data = await response?.json().catch(() => ({}));
  if (!response?.ok) { const node = $("#inbox-status"); if (node) node.textContent = data.detail || "Unable to sync Gmail."; return; }
  const messages = await api("/api/integrations/gmail/messages");
  const messageData = await messages?.json().catch(() => ({ messages: [] }));
  renderInbox(messageData.messages || [], data);
  refreshGmailStatus();
}

async function init() {
  const fileInput = $("#csv-file");
  const importButton = $("#import-csv");
  if (importButton) importButton.disabled = true;
  fileInput?.addEventListener("change", () => inspectCsvFile(fileInput.files?.[0]));
  importButton?.addEventListener("click", importCsv);
  $("#connect-gmail")?.addEventListener("click", connectGmail);
  $("#sync-inbox")?.addEventListener("click", syncInbox);
  await refreshGmailStatus();
  const params = new URLSearchParams(location.search);
  if (params.has("gmail")) { history.replaceState({}, "", location.pathname); await refreshGmailStatus(); }
  const inbox = $("#view-inbox");
  if (inbox && !inbox.hidden) await syncInbox();
  setInterval(async () => { const current = $("#view-inbox"); if (current && !current.hidden) await syncInbox(); }, 60000);
}
init();
