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
  const data = await response.json();
  const node = $("#gmail-status"); const button = $("#connect-gmail");
  if (!node || !button) return;
  node.textContent = data.connected ? `Connected: ${data.email || "support inbox"}` : (data.configured ? "Not connected yet." : "Google OAuth is not configured on the backend.");
  button.textContent = data.connected ? "Reconnect Gmail" : "Connect Gmail";
}

async function connectGmail() {
  const response = await api("/api/integrations/gmail/connect");
  if (!response) return;
  if (response.redirected) { location.href = response.url; return; }
  if (response.ok) location.href = response.url;
  else alert((await response.json().catch(() => ({}))).detail || "Unable to start Gmail connection.");
}

async function importCsv() {
  const file = $("#csv-file")?.files?.[0]; const result = $("#setup-result");
  if (!file) { if (result) { result.hidden = false; result.textContent = "Choose a CSV file first."; } return; }
  const form = new FormData(); form.append("file", file);
  const response = await api("/api/import/csv", { method: "POST", body: form });
  const data = await response?.json().catch(() => ({}));
  if (result) { result.hidden = false; result.textContent = response?.ok ? `Imported ${data.customers} customers and ${data.orders} orders from ${data.rows} rows.` : (data?.detail || "Import failed."); }
  if (response?.ok) setTimeout(() => location.reload(), 700);
}

function renderInbox(messages, syncResult = null) {
  const list = $("#inbox-list"); const status = $("#inbox-status");
  if (!list || !status) return;
  if (syncResult) status.textContent = `Sync complete · ${syncResult.processed} processed · ${syncResult.matched} matched · ${syncResult.ignored} ignored`;
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
  $("#connect-gmail")?.addEventListener("click", connectGmail);
  $("#import-csv")?.addEventListener("click", importCsv);
  $("#sync-inbox")?.addEventListener("click", syncInbox);
  await refreshGmailStatus();
  const params = new URLSearchParams(location.search);
  if (params.has("gmail")) { history.replaceState({}, "", location.pathname); await refreshGmailStatus(); }
  const inbox = $("#view-inbox");
  if (inbox && !inbox.hidden) await syncInbox();
  setInterval(async () => { const current = $("#view-inbox"); if (current && !current.hidden) await syncInbox(); }, 60000);
}
init();
