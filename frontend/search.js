import { getSession } from "./auth.js";

const input = document.querySelector("#global-search");
const results = document.querySelector("#search-results");
const topbarLeft = document.querySelector(".topbar-left");
let timer = null;

function renderEmpty(text) {
  results.innerHTML = `<div class="search-empty"></div>`;
  results.querySelector(".search-empty").textContent = text;
  results.hidden = false;
}

async function search(query) {
  const session = await getSession();
  if (!session) return;
  const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`, { headers: { Authorization: `Bearer ${session.accessToken}` } });
  if (!response.ok) { renderEmpty("Search is unavailable right now."); return; }
  const data = await response.json();
  results.innerHTML = "";
  const customers = data.customers || [];
  const orders = data.orders || [];
  if (!customers.length && !orders.length) { renderEmpty("No customer or order found."); return; }

  customers.forEach((customer) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "search-result";
    const strong = document.createElement("strong");
    const small = document.createElement("small");
    strong.textContent = customer.name || "Customer";
    small.textContent = customer.email || customer.id || "Customer record";
    button.append(strong, small);
    button.onclick = () => openCustomer(customer.id);
    results.appendChild(button);
  });

  orders.forEach((order) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "search-result";
    const strong = document.createElement("strong");
    const small = document.createElement("small");
    strong.textContent = `Order ${order.id || ""}`;
    small.textContent = `Customer record · ${order.status || "unknown"}`;
    button.append(strong, small);
    button.onclick = () => openCustomer(order.customer_id);
    results.appendChild(button);
  });
  results.hidden = false;
}

function openCustomer(customerId) {
  input.value = "";
  results.hidden = true;
  document.querySelector('[data-view="customers"]')?.click();
  requestAnimationFrame(() => {
    const row = document.querySelector(`.directory-row[data-customer-id="${CSS.escape(customerId)}"]`);
    row?.click();
  });
}

input?.addEventListener("input", () => {
  clearTimeout(timer);
  const query = input.value.trim();
  if (!query) { results.hidden = true; return; }
  timer = setTimeout(() => search(query).catch(() => renderEmpty("Search is unavailable right now.")), 180);
});

document.addEventListener("click", (event) => {
  if (topbarLeft && !topbarLeft.contains(event.target)) results.hidden = true;
});
