import { getSession, signOut } from "./auth.js";

(async function bootstrap() {
  const session = await getSession();
  if (!session) { location.href = "./login.html"; return; }
  const $ = (s) => document.querySelector(s);
  const emailModal = $("#email-modal"), csvModal = $("#csv-modal");
  const open = (el) => { el.hidden = false; }, close = (el) => { el.hidden = true; };
  $("#sign-out").onclick = async () => { await signOut(); location.href = "./login.html"; };
  $("#connect-email").onclick = () => open(emailModal);
  $("#import-csv").onclick = () => open(csvModal);
  $("#email-cancel").onclick = () => close(emailModal);
  $("#csv-cancel").onclick = () => close(csvModal);
  $("#email-continue").onclick = () => {
    const email = $("#support-email").value.trim();
    $("#email-status").textContent = email ? "Support inbox setup is ready for the connection step." : "Enter your support email to continue.";
  };

  let csvText = "";
  const csvButton = $("#csv-continue"), status = $("#csv-status"), summary = $("#csv-summary");
  $("#csv-file").onchange = async (event) => {
    const file = event.target.files?.[0];
    csvButton.disabled = true;
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".csv")) { status.textContent = "Please choose a CSV file."; return; }
    csvText = await file.text();
    status.textContent = "Inspecting your CSV…";
    try {
      const response = await fetch("/api/imports/csv/inspect", { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${session.accessToken}` }, body: JSON.stringify({ csv_text: csvText }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Could not inspect CSV");
      summary.hidden = false;
      summary.innerHTML = `<strong>${file.name}</strong><br>${Number(data.row_count || 0).toLocaleString()} data rows detected<br>Customers: ${Number(data.customer_count || 0).toLocaleString()}<br>Orders: ${Number(data.order_count || 0).toLocaleString()}<br>${(data.headers || []).length} columns detected`;
      status.textContent = "File inspected. Ready to continue.";
      csvButton.textContent = "Next";
      csvButton.disabled = false;
    } catch (error) { status.textContent = error.message || "Could not inspect CSV."; }
  };

  csvButton.onclick = async () => {
    if (!csvText) return;
    csvButton.disabled = true;
    status.textContent = "Importing your customer history…";
    try {
      const response = await fetch("/api/imports/csv/commit", { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${session.accessToken}` }, body: JSON.stringify({ csv_text: csvText }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Import failed");
      status.textContent = `Imported ${Number(data.customers || 0).toLocaleString()} customers and ${Number(data.orders || 0).toLocaleString()} orders.`;
      setTimeout(() => { window.location.href = "./index.html"; }, 500);
    } catch (error) { status.textContent = error.message || "Import failed."; csvButton.disabled = false; }
  };
})();
