import { getSession, onboardingStatus, completeOnboarding } from "./auth.js";

(async function bootstrap() {
  const session = await getSession();
  if (!session) { location.href = "./login.html"; return; }
  try { const state = await onboardingStatus(session); if (state.completed) { location.href = "./index.html"; return; } } catch { /* allow onboarding to continue; backend remains authoritative */ }
  const $ = (s) => document.querySelector(s);
  const emailModal = $("#email-modal"), csvModal = $("#csv-modal");
  const open = (el) => { if (el) el.hidden = false; }, close = (el) => { if (el) el.hidden = true; };
  const finish = async (destination = "./index.html") => {
    try { await completeOnboarding(session); } catch (error) { console.warn("Unable to persist onboarding state", error); }
    sessionStorage.removeItem("known.new-user"); location.href = destination;
  };
  $("#skip-for-now").onclick = () => finish();
  $("#connect-email").onclick = () => open(emailModal);
  $("#import-csv").onclick = () => open(csvModal);
  $("#email-cancel").onclick = () => close(emailModal);
  $("#csv-cancel").onclick = () => close(csvModal);
  $("#email-continue").onclick = async () => {
    const button = $("#email-continue"), status = $("#email-status");
    button.disabled = true; status.textContent = "Opening Google…";
    try {
      const response = await fetch("/api/gmail/connect", { headers: { Authorization: `Bearer ${session.accessToken}` } });
      const data = await response.json();
      if (!response.ok || !data.authorization_url) throw new Error(data.detail || "Gmail connection is not configured.");
      location.href = data.authorization_url;
    } catch (error) { status.textContent = error.message || "Unable to connect Gmail."; button.disabled = false; }
  };
  let csvText = "";
  let fileName = "";
  const csvButton = $("#csv-continue"), status = $("#csv-status"), summary = $("#csv-summary");
  $("#csv-file").onchange = async (event) => {
    const file = event.target.files?.[0]; csvButton.disabled = true; if (!file) return;
    fileName = file.name;
    if (!file.name.toLowerCase().endsWith(".csv")) { status.textContent = "Please choose a CSV file."; return; }
    csvText = await file.text(); status.textContent = "Inspecting your CSV…";
    try {
      const response = await fetch("/api/imports/csv/inspect", { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${session.accessToken}` }, body: JSON.stringify({ csv_text: csvText, file_name: fileName }) });
      const data = await response.json(); if (!response.ok) throw new Error(data.detail || "Could not inspect CSV");
      summary.hidden = false; summary.innerHTML = `<strong>${file.name}</strong><br>${Number(data.row_count || 0).toLocaleString()} data rows detected<br>Customers: ${Number(data.customer_count || 0).toLocaleString()}<br>Orders: ${Number(data.order_count || 0).toLocaleString()}<br>${(data.headers || []).length} columns detected`;
      status.textContent = "File inspected. Ready to continue."; csvButton.textContent = "Next"; csvButton.disabled = false;
    } catch (error) { status.textContent = error.message || "Could not inspect CSV."; }
  };
  csvButton.onclick = async () => {
    if (!csvText) return; csvButton.disabled = true; status.textContent = "Importing your customer history…";
    try {
      const response = await fetch("/api/imports/csv/commit", { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${session.accessToken}` }, body: JSON.stringify({ csv_text: csvText, file_name: fileName }) });
      const data = await response.json(); if (!response.ok) throw new Error(data.detail || "Import failed");
      status.textContent = `Imported ${Number(data.customers || 0).toLocaleString()} customers and ${Number(data.orders || 0).toLocaleString()} orders.`;
      await finish("./index.html?imported=1");
    } catch (error) { status.textContent = error.message || "Import failed"; csvButton.disabled = false; }
  };
})();
