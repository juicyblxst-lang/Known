import { getSession, authenticatedFetch } from "./auth.js";

(async () => {
  const session = await getSession();
  const importToggle = document.querySelector("#notify-import");
  const conversationToggle = document.querySelector("#notify-conversations");
  if (!session || !importToggle || !conversationToggle) return;

  try {
    const response = await authenticatedFetch("/api/settings/notifications");
    if (response.ok) {
      const data = await response.json();
      importToggle.checked = data.import_completed !== false;
      conversationToggle.checked = data.new_conversations !== false;
      localStorage.setItem("known.notify.import", String(importToggle.checked));
      localStorage.setItem("known.notify.conversations", String(conversationToggle.checked));
    }
  } catch (error) { console.warn("Unable to load notification settings", error); }

  let timer;
  const save = async () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      try {
        const response = await authenticatedFetch("/api/settings/notifications", {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ import_completed: importToggle.checked, new_conversations: conversationToggle.checked })
        });
        if (!response.ok) throw new Error("settings save failed");
        localStorage.setItem("known.notify.import", String(importToggle.checked));
        localStorage.setItem("known.notify.conversations", String(conversationToggle.checked));
      } catch (error) { console.warn("Unable to save notification settings", error); }
    }, 150);
  };
  importToggle.addEventListener("change", save);
  conversationToggle.addEventListener("change", save);
})();