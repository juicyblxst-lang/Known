import { getSession, signOut } from "./auth.js";

const API = window.KNOWN_API_URL || "";
let session = null;
let sessionId = null;
let customers = [];
let selectedCustomer = null;
let selectedOrders = [];

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const apiUrl = (path) => `${API}${path}`;

async function authenticatedFetch(path, options = {}) {
  if (!session) return null;
  let response = await fetch(apiUrl(path), { ...options, headers: { ...(options.headers || {}), Authorization: `Bearer ${session.accessToken}` } });
  if (response.status !== 401) return response;
  session = await getSession();
  if (!session) { await signOut(); location.href = "./"; return null; }
  return fetch(apiUrl(path), { ...options, headers: { ...(options.headers || {}), Authorization: `Bearer ${session.accessToken}` } });
}

function switchView(view) {
  const title = { overview: "Overview", customers: "Customers", inbox: "Inbox", settings: "Settings", conversation: "Customer workspace" }[view] || "Overview";
  $$(".view").forEach((node) => { node.hidden = node.id !== `view-${view}`; node.classList.toggle("active-view", node.id === `view-${view}`); });
  $$(".nav-item").forEach((button) => button.classList.toggle("active", button.dataset.view === view));
  $("#view-title").textContent = title;
  window.scrollTo({ top: 0, behavior: "smooth" });
}
function bindNavigation() { $$("[data-view]").forEach((button) => button.addEventListener("click", () => switchView(button.dataset.view))); }
function escapeDate(date = new Date()) { return new Intl.DateTimeFormat(undefined, { weekday: "long", day: "numeric", month: "long", year: "numeric" }).format(date); }
function getGreeting(hour) { if (hour < 12) return "Good morning"; if (hour < 18) return "Good afternoon"; return "Good evening"; }
function displayName(user) { const metadata = user?.user_metadata || {}; return metadata.full_name || metadata.name || metadata.first_name || user?.email?.split("@")[0] || "there"; }
function initials(name) { return (name || "K").trim().split(/\s+/).slice(0, 2).map((part) => part[0]).join("").toUpperCase() || "K"; }
function formatCount(value) { return new Intl.NumberFormat().format(Number(value || 0)); }
function setConnection(connected, text = "Connected") { const node = $("#connection"); if (!node) return; node.innerHTML = `<i></i>${text}`; node.classList.toggle("offline", !connected); }
function renderOverview() {
  const name = displayName(session?.user), now = new Date();
  $("#today-label").textContent = escapeDate(now).toUpperCase(); $("#greeting").textContent = `${getGreeting(now.getHours())}, ${name}.`;
  $("#stat-customers").textContent = formatCount(customers.length); $("#stat-history").textContent = customers.length ? "Available" : "—"; $("#stat-inbox").textContent = "Connected";
  $("#stat-import").textContent = customers.length ? "Complete" : "—"; $("#stat-import-detail").textContent = customers.length ? `${formatCount(customers.length)} customer records` : "No import recorded";
  $("#coverage-customers").textContent = customers.length ? `${formatCount(customers.length)} customer records imported` : "Waiting for a data source"; $("#coverage-customers-count").textContent = customers.length ? formatCount(customers.length) : "—"; $("#coverage-memory").textContent = customers.length ? "Available" : "—";
  const activity = $("#recent-activity"); activity.innerHTML = customers.length ? `<div class="activity-event"><span class="activity-dot">✣</span><div><strong>Customer history imported</strong><p>${formatCount(customers.length)} customer records are available in Known.</p><span class="activity-time">Available now</span></div></div>` : `<div class="empty-state">Your workspace is ready. Import customer history to start building memory.</div>`;
}
function renderCustomerDirectory(list = customers) {
  const container = $("#customer-directory"); $("#customer-count").textContent = formatCount(customers.length);
  if (!list.length) { container.innerHTML = `<div class="empty-state">No customers match your search.</div>`; return; }
  container.innerHTML = "";
  list.forEach((customer) => { const button = document.createElement("button"); button.type = "button"; button.className = `directory-row${selectedCustomer?.id === customer.id ? " active" : ""}`; button.innerHTML = `<span class="directory-avatar">${initials(customer.name)}</span><span class="directory-info"><strong></strong><small></small></span>`; button.querySelector("strong").textContent = customer.name || "Unnamed customer"; button.querySelector("small").textContent = [customer.tier, customer.email].filter(Boolean).join(" · ") || "Customer record"; button.addEventListener("click", () => selectCustomer(customer)); container.appendChild(button); });
}
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
async function loadCustomers() { const response = await authenticatedFetch("/api/customers"); if (!response) return; if (!response.ok) throw new Error(`Unable to load customers (${response.status})`); customers = await response.json(); renderOverview(); renderCustomerDirectory(); if (customers.length) await selectCustomer(customers[0]); }
function setupProfile() { const user = session.user, name = displayName(user); $("#profile-name").textContent = name; $("#profile-email").textContent = user?.email || "—"; $("#profile-avatar").textContent = initials(name); const profile = $("#profile-button"), menu = $("#profile-menu"); profile.addEventListener("click", () => { const open = profile.getAttribute("aria-expanded") === "true"; profile.setAttribute("aria-expanded", String(!open)); menu.hidden = open; }); $("#logout-button").addEventListener("click", async () => { await signOut(); location.href = "./"; }); }
function setupSettings() { const importToggle = $("#notify-import"), conversationToggle = $("#notify-conversations"); importToggle.checked = localStorage.getItem("known.notify.import") !== "false"; conversationToggle.checked = localStorage.getItem("known.notify.conversations") !== "false"; importToggle.addEventListener("change", () => localStorage.setItem("known.notify.import", String(importToggle.checked))); conversationToggle.addEventListener("change", () => localStorage.setItem("known.notify.conversations", String(conversationToggle.checked))); }
async function loadConversation(customer, newSession = false) { if (newSession) { sessionId = null; $("#conversation-session").textContent = "New session"; $("#messages").innerHTML = `<div class="empty-state">Start a new conversation with ${customer.name}.</div>`; return; } const id = sessionId || localStorage.getItem(`known.session.${customer.id}`); if (!id) { $("#conversation-session").textContent = "No conversation yet"; $("#messages").innerHTML = `<div class="empty-state">No conversation loaded.</div>`; return; } const response = await authenticatedFetch(`/api/sessions/${encodeURIComponent(id)}?customer_id=${encodeURIComponent(customer.id)}`); if (!response || !response.ok) return; const data = await response.json(); sessionId = data.session_id; $("#conversation-session").textContent = `Session: ${data.persistence}`; renderConversation(data.messages || []); }
function addMessage(label, text, className) { const el = document.createElement("div"); el.className = `msg ${className}`; el.innerHTML = `<small></small><p></p>`; el.querySelector("small").textContent = label; el.querySelector("p").textContent = text; $("#messages").appendChild(el); $("#messages").scrollTop = $("#messages").scrollHeight; }
function renderConversation(items) { $("#messages").innerHTML = ""; items.forEach((item) => addMessage(item.role === "assistant" ? "KNOWN" : selectedCustomer.name.toUpperCase(), item.content, item.role === "assistant" ? "agent-msg" : "customer-msg")); }
async function sendMessage(message) { const response = await authenticatedFetch("/api/support", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ customer_id: selectedCustomer.id, message, conversation_id: sessionId }) }); if (!response) return; const data = await response.json().catch(() => ({})); if (!response.ok) throw new Error(data.detail || `Support request failed (${response.status})`); sessionId = data.session_id; localStorage.setItem(`known.session.${selectedCustomer.id}`, sessionId); $("#conversation-session").textContent = `Session: ${data.persistence}`; renderConversation(data.conversation || []); }
function setupConversation() { $("#new-session").addEventListener("click", () => selectedCustomer && loadConversation(selectedCustomer, true)); $("#composer").addEventListener("submit", async (event) => { event.preventDefault(); if (!selectedCustomer) return; const input = $("#message"), button = event.currentTarget.querySelector("button"), message = input.value.trim(); if (!message) return; input.value = ""; button.disabled = true; try { await sendMessage(message); } catch (error) { addMessage("SYSTEM", error.message || "Unable to reach Known.", "agent-msg"); } finally { button.disabled = false; input.focus(); } }); }
async function openConversation() { if (!selectedCustomer) return; $("#conversation-title").textContent = selectedCustomer.name; $("#conversation-meta").textContent = [selectedCustomer.tier, selectedCustomer.email].filter(Boolean).join(" · "); $("#message").disabled = false; $("#composer button").disabled = false; await loadConversation(selectedCustomer); switchView("conversation"); }
window.addEventListener("known:gmail-session", async (event) => { const { customerId, sessionId: gmailSessionId } = event.detail || {}; const customer = customers.find((item) => item.id === customerId); if (!customer) return; selectedCustomer = customer; sessionId = gmailSessionId || null; await selectCustomer(customer, sessionId); await openConversation(); });
async function bootstrap() { try { bindNavigation(); setupSettings(); setupConversation(); session = await getSession(); if (!session) { location.href = "./login.html"; return; } setupProfile(); setConnection(true); await loadCustomers(); $("#customer-search").addEventListener("input", () => renderCustomerDirectory(getFilteredCustomers())); $("#detail-name").addEventListener("dblclick", openConversation); const params = new URLSearchParams(location.search); if (params.get("view") === "customers") switchView("customers"); } catch (error) { setConnection(false, "Unavailable"); $("#recent-activity").innerHTML = `<div class="empty-state">${error.message || "Unable to initialize Known."}</div>`; } }
bootstrap();
