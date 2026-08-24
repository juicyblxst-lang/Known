import { getSession, signOut } from "./auth.js";

const API = window.KNOWN_API_URL || "";
let session = null;
let customers = [];
let selectedCustomer = null;
let currentImport = null;

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const apiUrl = (path) => `${API}${path}`;

function displayName(user) {
  const metadata = user?.user_metadata || {};
  return metadata.full_name || metadata.name || metadata.first_name || user?.email?.split("@")[0] || "there";
}

function initials(value) {
  const text = String(value || "K").trim();
  return (text.includes("@") ? text.split("@")[0] : text).slice(0, 2).toUpperCase() || "K";
}

function formatCount(value) { return new Intl.NumberFormat().format(Number(value || 0)); }
function formatDate(date = new Date()) { return new Intl.DateTimeFormat(undefined, { weekday: "long", day: "numeric", month: "long", year: "numeric" }).format(date); }
function greeting(hour) { return hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening"; }

function openModal(id) {
  $("#modal-root").hidden = false;
  $$(".modal-card").forEach((modal) => { modal.hidden = modal.id !== id; });
}
function closeModal() {
  $("#modal-root").hidden = true;
  $$(".modal-card").forEach((modal) => { modal.hidden = true; });
}

function setConnection(connected, text = "Customer memory ready") {
  const node = $("#connection");
  if (!node) return;
  node.innerHTML = `<i></i>${text}`;
  node.classList.toggle("offline", !connected);
}

async function authenticatedFetch(path, options = {}) {
  if (!session) return null;
  let response = await fetch(apiUrl(path), { ...options, headers: { ...(options.headers || {}), Authorization: `Bearer ${session.accessToken}` } });
  if (response.status !== 401) return response;
  session = await getSession();
  if (!session) { await signOut(); location.href = "./landing.html"; return null; }
  return fetch(apiUrl(path), { ...options, headers: { ...(options.headers || {}), Authorization: `Bearer ${session.accessToken}` } });
}

function switchView(view) {
  const titles = { overview: "Overview", customers: "Customers", inbox: "Inbox", imported: "Imported", integration: "Integration", settings: "Settings" };
  $$(".view").forEach((node) => { node.hidden = node.id !== `view-${view}`; });
  $$(".nav-item").forEach((button) => button.classList.toggle("active", button.dataset.view === view));
  $("#search-results").hidden = true;
  window.scrollTo({ top: 0, behavior: "smooth" });
  if (view === "imported") renderImportedFiles();
}

function renderOverview() {
  const now = new Date();
  const name = displayName(session?.user);
  $("#today-label").textContent = formatDate(now).toUpperCase();
  $("#greeting").textContent = `${greeting(now.getHours())}, ${name}.`;
  $("#stat-customers").textContent = formatCount(customers.length);
  $("#stat-history").textContent = customers.length ? "Available" : "—";
  $("#stat-inbox").textContent = "Coming soon";
  const imports = getImportedFiles();
  const latest = imports[0];
  $("#stat-import").textContent = latest ? "Complete" : customers.length ? "Complete" : "—";
  $("#stat-import-detail").textContent = latest?.name || (customers.length ? `${formatCount(customers.length)} customer records` : "No import recorded");
  $("#coverage-customers").textContent = customers.length ? `${formatCount(customers.length)} customer records imported` : "Waiting for a data source";
  $("#coverage-customers-count").textContent = customers.length ? formatCount(customers.length) : "—";
  $("#coverage-memory").textContent = customers.length ? "Available" : "—";
  $("#recent-activity").innerHTML = customers.length
    ? `<div class="activity-event"><span class="activity-dot">✣</span><div><strong>Customer history imported</strong><p>${formatCount(customers.length)} customer records are available in Known. Open Customers to browse their history and memory.</p><span class="activity-time">Available now</span></div></div>`
    : `<div class="empty-state">Your workspace is ready. Import customer history to start building memory.</div>`;
}

function getFilteredCustomers(query = $("#customer-search")?.value || "") {
  const value = query.trim().toLowerCase();
  if (!value) return customers;
  return customers.filter((customer) => [customer.name, customer.email, customer.id, customer.tier].some((field) => String(field || "").toLowerCase().includes(value)));
}

function renderCustomerDirectory(list = customers) {
  const container = $("#customer-directory");
  $("#customer-count").textContent = formatCount(customers.length);
  container.innerHTML = "";
  if (!list.length) { container.innerHTML = `<div class="empty-state">No customers match your search.</div>`; return; }
  list.forEach((customer) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `directory-row${selectedCustomer?.id === customer.id ? " active" : ""}`;
    button.dataset.customerId = customer.id;
    button.innerHTML = `<span class="directory-avatar">${initials(customer.name)}</span><span class="directory-info"><strong></strong><small></small></span>`;
    button.querySelector("strong").textContent = customer.name || "Unnamed customer";
    button.querySelector("small").textContent = [customer.email, customer.tier].filter(Boolean).join(" · ") || "Customer record";
    button.onclick = () => selectCustomer(customer);
    container.appendChild(button);
  });
}

function renderCustomerDetail(data) {
  selectedCustomer = data.customer;
  $("#detail-avatar").textContent = initials(data.customer?.name);
  $("#detail-name").textContent = data.customer?.name || "Customer";
  $("#detail-meta").textContent = [data.customer?.email, data.customer?.tier].filter(Boolean).join(" · ");
  $("#detail-email").textContent = data.customer?.email || "—";
  $("#detail-id").textContent = data.customer?.id || "—";
  const orderBody = $("#detail-orders");
  orderBody.innerHTML = "";
  const orders = data.orders || [];
  if (!orders.length) orderBody.innerHTML = `<div class="empty-state">No order history in this customer record.</div>`;
  orders.forEach((order) => {
    const row = document.createElement("div");
    row.className = "order";
    row.innerHTML = `<b></b><span class="status"></span><small></small>`;
    row.querySelector("b").textContent = order.id || "Order";
    row.querySelector(".status").textContent = order.status || "unknown";
    row.querySelector(".status").classList.add(order.status === "delivered" ? "delivered" : "delayed");
    row.querySelector("small").textContent = `$${Number(order.total || 0).toFixed(2)} · ${(order.items || []).map((item) => item?.name || item).join(", ") || "No items listed"}`;
    orderBody.appendChild(row);
  });
  const memoryBody = $("#detail-memory");
  memoryBody.innerHTML = "";
  const memories = data.memory || [];
  $("#memory-count").textContent = memories.length;
  if (!memories.length) memoryBody.innerHTML = `<div class="empty-state">No relevant memory has been surfaced yet.</div>`;
  memories.slice(0, 8).forEach((memory) => {
    const article = document.createElement("article");
    article.className = "memory-item";
    article.innerHTML = `<label></label><p></p>`;
    article.querySelector("label").textContent = memory.type || "MEMORY";
    article.querySelector("p").textContent = memory.content || "";
    memoryBody.appendChild(article);
  });
  renderCustomerDirectory(getFilteredCustomers());
}

async function selectCustomer(customer) {
  const response = await authenticatedFetch(`/api/workspace/${encodeURIComponent(customer.id)}`);
  if (!response) return;
  if (!response.ok) { $("#detail-meta").textContent = "Unable to load this customer right now."; return; }
  renderCustomerDetail(await response.json());
  switchView("customers");
}

async function loadCustomers() {
  const response = await authenticatedFetch("/api/customers");
  if (!response) return;
  if (!response.ok) throw new Error(`Unable to load customers (${response.status})`);
  customers = await response.json();
  renderOverview();
  renderCustomerDirectory();
  if (customers.length) await selectCustomer(customers[0]);
}

function getImportedFiles() {
  try { return JSON.parse(localStorage.getItem("known.imported.files") || "[]"); } catch { return []; }
}
function saveImportedFile(file) {
  const existing = getImportedFiles().filter((item) => item.name !== file.name);
  existing.unshift({ ...file, importedAt: new Date().toISOString() });
  localStorage.setItem("known.imported.files", JSON.stringify(existing.slice(0, 20)));
}
function renderImportedFiles() {
  const list = $("#imported-list");
  const files = getImportedFiles();
  list.innerHTML = "";
  if (!files.length) { list.innerHTML = `<div class="empty-page"><div class="empty-icon">↓</div><h2>No CSV imports recorded yet.</h2><p>Import your existing customer history and it will appear here.</p><button id="empty-import-button" class="primary-button" type="button">Import CSV</button></div>`; $("#empty-import-button").onclick = () => openModal("import-modal"); return; }
  files.forEach((file) => {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "imported-row";
    row.innerHTML = `<span class="import-file-icon">CSV</span><span><strong></strong><small></small></span><span class="import-arrow">→</span>`;
    row.querySelector("strong").textContent = file.name;
    row.querySelector("small").textContent = `${formatCount(file.customers || 0)} customers · ${formatCount(file.orders || 0)} orders · imported ${new Date(file.importedAt).toLocaleDateString()}`;
    row.onclick = () => { $("#import-confirm-copy").textContent = `${file.name} contains ${formatCount(file.customers || 0)} customer records. Show those records in Customers?`; currentImport = file; openModal("import-confirm-modal"); };
    list.appendChild(row);
  });
}

function setupProfile() {
  const user = session.user;
  const name = displayName(user);
  $("#top-profile-name").textContent = name;
  $("#top-profile-avatar").textContent = initials(user?.email);
  $("#modal-profile-avatar").textContent = initials(user?.email);
  $("#profile-modal-title").textContent = `Hi, ${name}`;
  $("#modal-profile-email").textContent = user?.email || "—";
  $("#profile-button").onclick = () => openModal("profile-modal");
  $("#profile-logout").onclick = () => openModal("confirm-modal");
}

function setupSettings() {
  const importToggle = $("#notify-import");
  const conversationToggle = $("#notify-conversations");
  importToggle.checked = localStorage.getItem("known.notify.import") !== "false";
  conversationToggle.checked = localStorage.getItem("known.notify.conversations") !== "false";
  importToggle.onchange = () => localStorage.setItem("known.notify.import", String(importToggle.checked));
  conversationToggle.onchange = () => localStorage.setItem("known.notify.conversations", String(conversationToggle.checked));
}

function setupNavigation() {
  $$("[data-view]").forEach((button) => button.addEventListener("click", () => { switchView(button.dataset.view); closeSidebar(); }));
  $("#hamburger").onclick = () => openSidebar();
  $("#sidebar-close").onclick = () => closeSidebar();
  $("#sidebar-backdrop").onclick = () => closeSidebar();
  $("#back-button").onclick = () => openModal("confirm-modal");
  $("#customer-back").onclick = () => switchView("overview");
  $("#modal-backdrop").onclick = () => closeModal();
  $$("[data-close-modal]").forEach((button) => button.onclick = closeModal);
  $("#confirm-logout").onclick = async () => { await signOut(); location.href = "./landing.html"; };
  $("#shopify-coming").onclick = () => openModal("shopify-modal");
  $("#import-confirm-yes").onclick = () => { closeModal(); switchView("customers"); if (currentImport) { const match = customers.find((customer) => customer.id === currentImport.firstCustomerId); if (match) selectCustomer(match); } };
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") closeModal(); });
}

function openSidebar() { $("#sidebar").classList.add("open"); $("#sidebar-backdrop").hidden = false; }
function closeSidebar() { $("#sidebar").classList.remove("open"); $("#sidebar-backdrop").hidden = true; }

function setupSearch() {
  const input = $("#global-search");
  const results = $("#search-results");
  const render = () => {
    const query = input.value.trim().toLowerCase();
    results.innerHTML = "";
    if (!query) { results.hidden = true; return; }
    const customerMatches = customers.filter((customer) => [customer.name, customer.email, customer.id].some((field) => String(field || "").toLowerCase().includes(query))).slice(0, 8);
    const orderMatches = [];
    if (!customerMatches.length && selectedCustomer) orderMatches.push(...(selectedCustomer.orders || []).filter((order) => String(order.id || "").toLowerCase().includes(query)).slice(0, 5));
    if (!customerMatches.length && !orderMatches.length) { results.innerHTML = `<div class="search-empty">No customer or order found.</div>`; results.hidden = false; return; }
    customerMatches.forEach((customer) => { const button = document.createElement("button"); button.type = "button"; button.className = "search-result"; button.innerHTML = `<strong></strong><small></small>`; button.querySelector("strong").textContent = customer.name || "Customer"; button.querySelector("small").textContent = customer.email || customer.id; button.onclick = () => { input.value = ""; results.hidden = true; selectCustomer(customer); }; results.appendChild(button); });
    orderMatches.forEach((order) => { const button = document.createElement("button"); button.type = "button"; button.className = "search-result"; button.innerHTML = `<strong>Order ${order.id}</strong><small>Order history</small>`; button.onclick = () => { input.value = ""; results.hidden = true; switchView("customers"); }; results.appendChild(button); });
    results.hidden = false;
  };
  input.addEventListener("input", render);
  document.addEventListener("click", (event) => { if (!$(".topbar-left").contains(event.target)) results.hidden = true; });
}

function setupDashboardImport() {
  const fileInput = $("#dashboard-csv-file");
  const summary = $("#dashboard-csv-summary");
  const status = $("#dashboard-csv-status");
  const next = $("#dashboard-csv-next");
  let csvText = "";
  let fileName = "";
  $("#new-import-button").onclick = () => openModal("import-modal");
  fileInput.onchange = async (event) => {
    const file = event.target.files?.[0];
    next.disabled = true;
    summary.hidden = true;
    if (!file) return;
    fileName = file.name;
    if (!file.name.toLowerCase().endsWith(".csv")) { status.textContent = "Please choose a CSV file."; return; }
    csvText = await file.text();
    status.textContent = "Inspecting your CSV…";
    try {
      const response = await authenticatedFetch("/api/imports/csv/inspect", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ csv_text: csvText }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Could not inspect CSV");
      summary.hidden = false;
      summary.innerHTML = `<strong>${fileName}</strong><br>${formatCount(data.row_count)} rows · ${formatCount(data.customer_count)} customers · ${formatCount(data.order_count)} orders`;
      status.textContent = "File inspected. Ready to import.";
      next.disabled = false;
    } catch (error) { status.textContent = error.message || "Could not inspect CSV."; }
  };
  next.onclick = async () => {
    if (!csvText) return;
    next.disabled = true;
    status.textContent = "Importing your customer history…";
    try {
      const response = await authenticatedFetch("/api/imports/csv/commit", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ csv_text: csvText }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Import failed");
      saveImportedFile({ name: fileName, customers: data.customers || 0, orders: data.orders || 0 });
      status.textContent = `Imported ${formatCount(data.customers || 0)} customers and ${formatCount(data.orders || 0)} orders.`;
      setTimeout(async () => { closeModal(); fileInput.value = ""; csvText = ""; await loadCustomers(); switchView("customers"); }, 350);
    } catch (error) { status.textContent = error.message || "Import failed."; next.disabled = false; }
  };
}

async function bootstrap() {
  try {
    session = await getSession();
    if (!session) { location.href = "./login.html"; return; }
    setupNavigation();
    setupProfile();
    setupSettings();
    setupSearch();
    setupDashboardImport();
    setConnection(true);
    await loadCustomers();
    $("#customer-search").addEventListener("input", () => renderCustomerDirectory(getFilteredCustomers()));
    renderImportedFiles();
  } catch (error) {
    setConnection(false, "Unavailable");
    $("#recent-activity").innerHTML = `<div class="empty-state">${error.message || "Unable to initialize Known."}</div>`;
  }
}

bootstrap();
