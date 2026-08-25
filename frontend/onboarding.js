import { getSession } from "./auth.js";

(async function bootstrap() {
  const session = await getSession();
  if (!session) { location.href = "./login.html"; return; }
  if (sessionStorage.getItem("known.new-user") !== "true") { location.href = "./index.html"; return; }
  const $ = (s) => document.querySelector(s);
  const emailModal = $("#email-modal"), csvModal = $("#csv-modal");
  const open = (el) => { el.hidden = false; }, close = (el) => { el.hidden = true; };
  $("#skip-for-now").onclick = () => { sessionStorage.removeItem("known.new-user"); location.href = "./index.html"; };
  $("#connect-email").onclick = () => open(emailModal);
  $("#import-csv").onclick = () => open(csvModal);
  $("#email-cancel").onclick = () => close(emailModal);
  $("#csv-cancel").onclick = () => close(csvModal);
  $("#email-continue").onclick = () => {
    const email = $("#support-email").value.trim();
    $("#email-status").textContent = email ? "Support inbox setup is ready for the connection step." : "Enter your support email to continue.";
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
      const response = await fetch("/api/imports/csv/inspect", { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${session.accessToken}` }, body: JSON.stringify({ csv_text: csvText }) });
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
      sessionStorage.removeItem("known.new-user");
      location.href = "./index.html?imported=1";
    } catch (error) { status.textContent = error.message || "Import failed"; csvButton.disabled = false; }
  };
})();
