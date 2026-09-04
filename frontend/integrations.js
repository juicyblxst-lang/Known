import { authenticatedFetch } from "./auth.js";

const $ = (s) => document.querySelector(s);
const api = async (path, options = {}) => authenticatedFetch(path, options);

async function refreshGmailStatus() {
  const response = await api("/api/integrations/gmail/status").catch(() => null);
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
    showImportResult(`Imported ${Number(data.customers || 0).toLocaleString()} customers and ${Number(data.orders || 0).toLocaleString()} orders. Customer memory is ready.`, false); csvInspection = null; if (button) button.textContent = "Added"; finishImportModal();
  } catch (error) {
    const modal = $("#csv-import-modal"); if (modal) modal.hidden = true;
    const message = error?.message || "Import failed."; showImportResult(message, false);
    if (button) { button.disabled = false; button.textContent = "Add to Customers"; }
  }
}

function renderInbox(messages, syncResult = null) { const list = $("#inbox-list"); const status = $("#inbox-status"); if (!list || !status) return; if (syncResult) status.textContent = `Sync complete · ${syncResult.processed} processed · ${syncResult.matched} matched · ${syncResult.created || 0} new customers · ${syncResult.failed || 0} failed`; if (!messages.length) { list.innerHTML = ""; return; } list.innerHTML = ""; messages.forEach((message) => { const row = document.createElement("button"); row.type = "button"; row.className = "directory-row"; row.innerHTML = `<span class="directory-avatar">✉</span><span class="directory-info"><strong></strong><small></small></span>`; row.querySelector("strong").textContent = message.subject || "No subject"; row.querySelector("small").textContent = `${message.sender_email || "Unknown sender"} · ${message.body || ""}`; row.addEventListener("click", () => { if (message.customer_id) window.dispatchEvent(new CustomEvent("known:gmail-session", { detail: { customerId: message.customer_id, sessionId: message.session_id } })); }); list.appendChild(row); }); }
async function syncInbox() { const response = await api("/api/integrations/gmail/sync", { method: "POST" }); const data = await response?.json().catch(() => ({})); if (!response?.ok) { const node = $("#inbox-status"); if (node) node.textContent = data.detail || "Unable to sync Gmail."; return; } const messages = await api("/api/integrations/gmail/messages"); const messageData = await messages?.json().catch(() => ({ messages: [] })); renderInbox(messageData.messages || [], data); refreshGmailStatus(); }
async function init() { const fileInput = $("#csv-file"); const importButton = $("#import-csv"); if (importButton) importButton.disabled = true; fileInput?.addEventListener("change", () => inspectCsvFile(fileInput.files?.[0])); importButton?.addEventListener("click", importCsv); $("#go-to-customers")?.addEventListener("click", () => { location.href = "./index.html?view=customers"; }); $("#connect-gmail")?.addEventListener("click", connectGmail); $("#sync-inbox")?.addEventListener("click", syncInbox); await refreshGmailStatus(); const params = new URLSearchParams(location.search); if (params.has("gmail")) { history.replaceState({}, "", location.pathname); await refreshGmailStatus(); } const inbox = $("#view-inbox"); if (inbox && !inbox.hidden) await syncInbox(); setInterval(async () => { const current = $("#view-inbox"); if (current && !current.hidden) await syncInbox(); }, 60000); }
init();
