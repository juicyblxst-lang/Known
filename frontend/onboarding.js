import { getSession, signOut } from "./auth.js";

(async function bootstrap() {
  const session = await getSession();
  if (!session) {
    location.href = "./login.html";
    return;
  }

  const $ = (selector) => document.querySelector(selector);
  const emailModal = $("#email-modal");
  const csvModal = $("#csv-modal");
  const open = (el) => { el.hidden = false; };
  const close = (el) => { el.hidden = true; };

  $("#sign-out").addEventListener("click", async () => {
    await signOut();
    location.href = "./login.html";
  });

  $("#connect-email").addEventListener("click", () => open(emailModal));
  $("#import-csv").addEventListener("click", () => open(csvModal));
  $("#email-cancel").addEventListener("click", () => close(emailModal));
  $("#csv-cancel").addEventListener("click", () => close(csvModal));

  $("#email-continue").addEventListener("click", () => {
    const email = $("#support-email").value.trim();
    $("#email-status").textContent = email
      ? "Support inbox setup is ready for the connection step."
      : "Enter your support email to continue.";
  });

  let csvText = "";
  $("#csv-file").addEventListener("change", async (event) => {
    const file = event.target.files?.[0];
    const summary = $("#csv-summary");
    const button = $("#csv-continue");
    const status = $("#csv-status");

    if (!file) {
      button.disabled = true;
      return;
    }
    if (!file.name.toLowerCase().endsWith(".csv")) {
      status.textContent = "Please choose a CSV file.";
      button.disabled = true;
      return;
    }

    csvText = await file.text();
    status.textContent = "Inspecting your CSV…";
    button.disabled = true;

    try {
      const response = await fetch("/api/imports/csv/inspect", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${session.accessToken}`,
        },
        body: JSON.stringify({ csv_text: csvText }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Could not inspect CSV");

      summary.hidden = false;
      summary.innerHTML = `<strong>${file.name}</strong><br>${Number(data.row_count || 0).toLocaleString()} data rows detected<br>Customers: ${Number(data.customer_count || 0).toLocaleString()}<br>Orders: ${Number(data.order_count || 0).toLocaleString()}<br>${(data.headers || []).length} columns detected`;
      status.textContent = "File inspected. Ready to import.";
      button.disabled = false;
    } catch (error) {
      status.textContent = error.message || "Could not inspect CSV.";
      button.disabled = true;
    }
  });

  $("#csv-continue").addEventListener("click", async () => {
    const button = $("#csv-continue");
    const status = $("#csv-status");
    button.disabled = true;
    status.textContent = "Importing your customer history…";

    try {
      const response = await fetch("/api/imports/csv/commit", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${session.accessToken}`,
        },
        body: JSON.stringify({ csv_text: csvText }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Import failed");

      status.textContent = `Imported ${Number(data.customers || 0).toLocaleString()} customers and ${Number(data.orders || 0).toLocaleString()} orders into Known.`;
      button.textContent = "Imported";
    } catch (error) {
      status.textContent = error.message || "Import failed.";
      button.disabled = false;
    }
  });
})();
