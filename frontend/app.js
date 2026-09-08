import { getSession, signOut, onboardingStatus, invalidateSession, authenticatedFetch } from "./auth.js";

const API = window.KNOWN_API_URL || "";
let session = null;
let sessionId = null;
let customers = [];
let selectedCustomer = null;
let selectedOrders = [];
let gmailConnected = false;
let awaitingNewSessionMessage = false;

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const apiUrl = (path) => `${API}${path}`;

function switchView(view) {
  const title = { overview: "Overview", customers: "Customers", inbox: "Inbox", settings: "Settings", conversation: "Customer workspace" }[view] || "Overview";
  $$(".view").forEach((node) => { node.hidden = node.id !== `view-${view}`; node.classList.toggle("active-view", node.id === `view-${view}`); });
  $$(".nav-item").forEach((button) => button.classList.toggle("active", button.dataset.view === view));
  $("#view-title").textContent = title;
  window.dispatchEvent(new CustomEvent("known:view-change", { detail: { view } }));
  window.scrollTo({ top: 0, behavior: "smooth" });
}
function bindNavigation() { $$("[data-view]").forEach((button) => button.addEventListener("click", () => switchView(button.dataset.view))); }
function escapeDate(date = new Date()) { return new Intl.DateTimeFormat(undefined, { weekday: "long", day: "numeric", month: "long", year: "numeric" }).format(date); }
function getGreeting(hour) { if (hour < 12) return "Good morning"; if (hour < 18) return "Good afternoon"; return "Good evening"; }
function displayName(user) { const metadata = user?.user_metadata || {}; return metadata.full_name || metadata.name || metadata.first_name || user?.email?.split("@")[0] || "there"; }
function initials(name) { return (name || "K").trim().split(/\s+/).slice(0, 2).map((part) => part[0]).join("").toUpperCase() || "K"; }
function formatCount(value) { return new Intl.NumberFormat().format(Number(value || 0)); }
function setConnection(connected, text = "Connected") { const node = $("#connection"); if (!node) return; node.innerHTML = `<i></i>${text}`; node.classList.toggle("offline", !connected); }
async function refreshGmailStatus() {
  try {
    const response = await authenticatedFetch("/api/integrations/gmail/status");
    if (!response.ok) throw new Error(`Gmail status failed (${response.status})`);
    const data = await response.json();
    gmailConnected = Boolean(data.connected);
    setConnection(gmailConnected, gmailConnected ? `Gmail · ${data.email || "connected"}` : "Gmail not connected");
    return data;
  } catch (error) {
    gmailConnected = false;
    setConnection(false, "Gmail status unavailable");
    return null;
  }
}
function showSetupNotice(message) {
  const status = $(".setup-status");
  const title = $(".setup-body strong");
  const copy = $(".setup-body p");
  if (status) status.textContent = message;
  if (title && message === "Import complete") title.textContent = "Customer history is ready.";
  if (copy && message === "Import complete") copy.textContent = "Your customers and orders are now available in Known. Connect your support inbox to start automatic support.";
  if (title && message === "Gmail connected") title.textContent = "Known is ready to receive support email.";
  if (copy && message === "Gmail connected") copy.textContent = "Your support Gmail is connected. Customer emails will be processed automatically and surfaced in Inbox.";
}
function renderOverview() {
  const name = displayName(session?.user), now = new Date();
  $("#today-label").textContent = escapeDate(now).toUpperCase(); $("#greeting").textContent = `${getGreeting(now.getHours())}, ${name}.`;
  $("#stat-customers").textContent = formatCount(customers.length); $("#stat-history").textContent = customers.length ? "Available" : "—"; $("#stat-inbox").textContent = gmailConnected ? "Connected" : "Not connected";
  $("#stat-import").textContent = customers.length ? "Complete" : "—"; $("#stat-import-detail").textContent = customers.length ? `${formatCount(customers.length)} customer records` : "No import recorded";
  $("#coverage-customers").textContent = customers.length ? `${formatCount(customers.length)} customer records imported` : "Waiting for a data source"; $("#coverage-customers-count").textContent = customers.length ? formatCount(customers.length) : "—"; $("#coverage-memory").textContent = customers.length ? "Available" : "—";
  $("#coverage-inbox").textContent = gmailConnected ? "Support Gmail connected" : "Connect your support inbox";
  const activity = $("#recent-activity"); activity.innerHTML = customers.length ? `<div class="activity-event"><span class="activity-dot">✣</span><div><strong>Customer history imported</strong><p>${formatCount(customers.length)} customer records are available in Known.</p><span class="activity-time">Available now</span></div></div>` : `<div class="empty-state">Your workspace is ready. Import customer history to start building memory.</div>`;
}
function renderCustomerDirectory(list = customers) { const container = $("#customer-directory"); $("#customer-count").textContent = formatCount(customers.length); if (!list.length) { container.innerHTML = `<div class="empty-state">No customers match your search.</div>`; return; } container.innerHTML = ""; list.forEach((customer) => { const button = document.createElement("button"); button.type = "button"; button.className = `directory-row${selectedCustomer?.id === customer.id ? " active" : ""}`; button.innerHTML = `<span class="directory-avatar">${initials(customer.name)}</span><span class="directory-info"><strong></strong><small></small></span>`; button.querySelector("strong").textContent = customer.name || "Unnamed customer"; button.querySelector("small").textContent = [customer.tier, customer.email].filter(Boolean).join(" · ") || "Customer record"; button.addEventListener("click", () => selectCustomer(customer)); container.appendChild(button); }); }
function renderCustomerDetail(data) {
  selectedCustomer = data.customer; selectedOrders = data.orders || [];
  $("#detail-avatar").textContent = initials(data.customer?.name); $("#detail-name").textContent = data.customer?.name || "Customer"; $("#detail-meta").textContent = data.customer ? [data.customer.tier, data.customer.email].filter(Boolean).join(" · ") : "Customer information will appear here."; $("#detail-email").textContent = data.customer?.email || "—"; $("#detail-id").textContent = data.customer?.id || "—";
  const orderBody = $("#detail-orders"); orderBody.innerHTML = "";
  if (!selectedOrders.length) orderBody.innerHTML = `<div class="empty-state">No order history in this customer record.</div>`;
  else selectedOrders.forEach((order) => { const row = document.createElement("div"); row.className = "order"; const statusClass = order.status === "delivered" ? "delivered" : "delayed"; row.innerHTML = `<b></b><span class="status ${statusClass}"></span><small></small>`; row.querySelector("b").textContent = order.id || "Order"; row.querySelector(".status").textContent = order.status || "unknown"; row.querySelector("small").textContent = `$${Number(order.total || 0).toFixed(2)} · ${(order.items || []).join(", ") || "No items listed"}`; orderBody.appendChild(row); });
  const memoryBody = $("#detail-memory"); memoryBody.innerHTML = ""; const memories = data.memory || []; $("#memory-count").textContent = String(memories.length);
  if (!memories.length) memoryBody.innerHTML = `<div class="empty-state">No relevant memory has been surfaced yet.</div>`;
  else memories.slice(0, 8).forEach((memory) => { const article = document.createElement("article"); article.className = "memory-item"; article.innerHTML = `<label></label><p></p>`; article.querySelector("label").textContent = memory.type || "MEMORY"; article.querySelector("p").textContent = memory.content || ""; memoryBody.appendChild(article); });
  renderCustomerDirectory(getFilteredCustomers());
}
function getFilteredCustomers() { const query = $("#customer-search")?.value.trim().toLowerCase() || ""; if (!query) return customers; return customers.filter((customer) => [customer.name, customer.email, customer.tier].filter(Boolean).some((value) => String(value).toLowerCase().includes(query))); }
async function selectCustomer(customer, preferredSessionId = null) { const response = await authenticatedFetch(`/api/workspace/${encodeURIComponent(customer.id)}`); if (!response) return; if (!response.ok) { $("#detail-meta").textContent = "Unable to load this customer right now."; return; } const data = await response.json(); renderCustomerDetail(data); if (preferredSessionId) { sessionId = preferredSessionId; localStorage.setItem(`known.session.${customer.id}`, preferredSessionId); } switchView("customers"); }
async function loadCustomers() { const response = await authenticatedFetch("/api/customers"); if (!response) return; if (!response.ok) { const error = new Error(`Unable to load customers (${response.status})`); error.status = response.status; throw error; } customers = await response.json(); renderOverview(); renderCustomerDirectory(); if (customers.length) await selectCustomer(customers[0]); }
function setupProfile() { const user = session.user, name = displayName(user); $("#profile-name").textContent = name; $("#profile-email").textContent = user?.email || "—"; $("#profile-avatar").textContent = initials(name); const profile = $("#profile-button"), menu = $("#profile-menu"); profile.addEventListener("click", () => { const open = profile.getAttribute("aria-expanded") === "true"; profile.setAttribute("aria-expanded", String(!open)); menu.hidden = open; }); $("#logout-button").addEventListener("click", async () => { await signOut(); location.href = "./"; }); }
function setConversationLoading(loading) {
  const node = $("#conversation-session");
  if (!node) return;
  node.innerHTML = loading ? `<span class="conversation-spinner" aria-label="Refreshing conversation"></span>` : "";
  node.classList.toggle("is-loading", loading);
}
async function loadConversation(customer, newSession = false) {
  if (newSession) {
    sessionId = null;
    awaitingNewSessionMessage = true;
    setConversationLoading(false);
    $("#messages").innerHTML = `<div class="empty-state">Waiting for a new message from ${customer.name}.</div>`;
    return;
  }
  const id = sessionId || localStorage.getItem(`known.session.${customer.id}`);
  if (!id) { setConversationLoading(false); $("#messages").innerHTML = `<div class="empty-state">No conversation loaded.</div>`; return; }
  setConversationLoading(true);
  const response = await authenticatedFetch(`/api/sessions/${encodeURIComponent(id)}?customer_id=${encodeURIComponent(customer.id)}`);
  if (!response) { setConversationLoading(false); $("#messages").innerHTML = `<div class="empty-state">The conversation could not be loaded.</div>`; return; }
  if (!response.ok) { setConversationLoading(false); $("#messages").innerHTML = `<div class="empty-state">This conversation is no longer available.</div>`; return; }
  const data = await response.json(); sessionId = data.session_id; awaitingNewSessionMessage = false; localStorage.setItem(`known.session.${customer.id}`, sessionId); setConversationLoading(false); renderConversation(data.messages || []);
}
function addMessage(label, text, className) { const el = document.createElement("div"); el.className = `msg ${className}`; el.innerHTML = `<small></small><p></p>`; el.querySelector("small").textContent = label; el.querySelector("p").textContent = text; $("#messages").appendChild(el); $("#messages").scrollTop = $("#messages").scrollHeight; }
function renderConversation(items) { $("#messages").innerHTML = ""; if (!items.length) { $("#messages").innerHTML = `<div class="empty-state">No messages in this conversation yet.</div>`; return; } items.forEach((item) => addMessage(item.role === "assistant" ? "KNOWN" : selectedCustomer.name.toUpperCase(), item.content, item.role === "assistant" ? "agent-msg" : "customer-msg")); }
async function sendMessage(message) { const response = await authenticatedFetch("/api/support", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ customer_id: selectedCustomer.id, message, conversation_id: sessionId }) }); if (!response) return; const data = await response.json().catch(() => ({})); if (!response.ok) { const error = new Error(data.detail || `Support request failed (${response.status})`); error.status = response.status; throw error; } sessionId = data.session_id; awaitingNewSessionMessage = false; localStorage.setItem(`known.session.${selectedCustomer.id}`, sessionId); setConversationLoading(false); renderConversation(data.conversation || []); }
function setupConversation() { $("#new-session").addEventListener("click", () => selectedCustomer && loadConversation(selectedCustomer, true)); $("#composer").addEventListener("submit", async (event) => { event.preventDefault(); if (!selectedCustomer) return; const input = $("#message"), button = event.currentTarget.querySelector("button"), message = input.value.trim(); if (!message) return; input.value = ""; button.disabled = true; try { await sendMessage(message); } catch (error) { addMessage("SYSTEM", error.message || "Unable to reach Known.", "agent-msg"); } finally { button.disabled = false; input.focus(); } }); }
async function openConversation(customer) {
  if (!customer) return;
  awaitingNewSessionMessage = false;
  $("#conversation-title").textContent = customer.name || "Customer";
  $("#conversation-meta").textContent = [customer.tier, customer.email].filter(Boolean).join(" · ");
  $("#message").disabled = false; $("#composer button").disabled = false;
  setConversationLoading(true);
  $("#messages").innerHTML = "";
  switchView("conversation");
  try { await loadConversation(customer); } catch (error) { console.error("Known conversation load failed:", error); setConversationLoading(false); $("#messages").innerHTML = `<div class="empty-state">The conversation could not be loaded right now.</div>`; }
}
window.addEventListener("known:gmail-session", async (event) => {
  const { customerId, sessionId: gmailSessionId, senderEmail } = event.detail || {};
  const customer = customers.find((item) => item.id === customerId) || customers.find((item) => senderEmail && String(item.email || "").toLowerCase() === String(senderEmail).toLowerCase());
  if (!customer) {
    $("#inbox-status").textContent = "This conversation is not linked to a customer record.";
    return;
  }
  selectedCustomer = customer;
  sessionId = gmailSessionId || (awaitingNewSessionMessage ? null : localStorage.getItem(`known.session.${customer.id}`)) || null;
  if (sessionId) localStorage.setItem(`known.session.${customer.id}`, sessionId);
  await openConversation(customer);
});
window.addEventListener("known:inbox-refresh", async (event) => {
  const activeView = $("#view-conversation");
  if (!selectedCustomer || !activeView || activeView.hidden) return;
  const messages = event.detail?.messages || [];
  if (awaitingNewSessionMessage && !sessionId) {
    const newest = messages.find((message) => message.customer_id === selectedCustomer.id && (message.session_id || message.external_thread_id));
    if (newest) {
      const newestSessionId = newest.session_id || `gmail:${newest.external_thread_id}`;
      sessionId = newestSessionId;
      localStorage.setItem(`known.session.${selectedCustomer.id}`, newestSessionId);
      awaitingNewSessionMessage = false;
      await loadConversation(selectedCustomer);
    }
    return;
  }
  if (!sessionId) return;
  const currentSession = messages.some((message) => {
    const messageSessionId = message.session_id || (message.external_thread_id ? `gmail:${message.external_thread_id}` : null);
    return message.customer_id === selectedCustomer.id && messageSessionId === sessionId;
  });
  if (currentSession) await loadConversation(selectedCustomer);
});
window.addEventListener("known:gmail-status", (event) => { const data = event.detail || {}; gmailConnected = Boolean(data.connected); setConnection(gmailConnected, gmailConnected ? `Gmail · ${data.email || "connected"}` : "Gmail not connected"); renderOverview(); });
async function bootstrap() { try { bindNavigation(); setupConversation(); session = await getSession(); if (!session) { location.href = "./login.html"; return; } const onboarding = await onboardingStatus(session); setupProfile(); await loadCustomers(); await refreshGmailStatus(); const params = new URLSearchParams(location.search); if (params.get("imported") === "1") { showSetupNotice("Import complete"); } if (params.get("gmail") === "connected") { showSetupNotice("Gmail connected"); } if (params.has("imported") || params.has("gmail")) history.replaceState({}, document.title, location.pathname); if (params.get("view") === "customers") switchView("customers"); } catch (error) { console.error("Known dashboard bootstrap failed:", error); if (error?.status === 401) { invalidateSession(); location.href = "./login.html"; return; } setConnection(false, "Degraded"); renderOverview(); $("#customer-search")?.addEventListener("input", () => renderCustomerDirectory(getFilteredCustomers())); $("#detail-name")?.addEventListener("dblclick", openConversation); }
}
bootstrap();
