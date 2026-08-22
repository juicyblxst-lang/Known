const API = window.KNOWN_API_URL || "";
const customerId = "demo-customer";
let sessionId = null;

const form = document.querySelector("#composer");
const input = document.querySelector("#message");
const messages = document.querySelector("#messages");
const sessionLabel = document.querySelector("#session");

function addMessage(label, text, className) {
  const el = document.createElement("div");
  el.className = `msg ${className}`;
  const small = document.createElement("small");
  small.textContent = label;
  const p = document.createElement("p");
  p.textContent = text;
  el.append(small, p);
  messages.appendChild(el);
  messages.scrollTop = messages.scrollHeight;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = input.value.trim();
  if (!message) return;
  input.value = "";
  addMessage("MAYA · NOW", message, "customer-msg");
  const button = form.querySelector("button");
  button.disabled = true;
  button.textContent = "…";
  try {
    const url = new URL(`${API}/api/support`, window.location.href);
    url.searchParams.set("session_id", sessionId || `${customerId}:default`);
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        customer: { id: customerId, name: "Maya Chen", email: "maya@example.com", tier: "vip" },
        message,
        conversation: [],
        orders: [],
      }),
    });
    if (!response.ok) throw new Error(`Support request failed (${response.status})`);
    const data = await response.json();
    sessionId = data.session_id;
    sessionLabel.textContent = `Session: ${data.persistence}`;
    addMessage("KNOWN · NOW", data.reply, "agent-msg");
  } catch (error) {
    addMessage("SYSTEM", error.message || "Unable to reach Known.", "agent-msg");
  } finally {
    button.disabled = false;
    button.textContent = "Send";
    input.focus();
  }
});
