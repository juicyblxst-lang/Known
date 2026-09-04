import { getSession } from "./auth.js";

(async () => {
  const session = await getSession();
  const importToggle = document.querySelector("#notify-import");
  const conversationToggle = document.querySelector("#notify-conversations");
  if (!session || !importToggle || !conversationToggle) return;

  const request = async (path, options = {}) => fetch(path, {
    ...options,
    headers: { ...(options.headers || {}), Authorization: `Bearer ${session.accessToken}`, ...(options.body ? { "Content-Type": "application/json" } : {}) }
  });

  try {
    const response = await request("/api/settings/notifications");
    if (response.ok) {
      const data = await response.json();
      importToggle.checked = data.import_completed !== false;
      conversationToggle.checked = data.new_conversations !== false;
    }
  } catch (error) { console.warn("Unable to load notification settings", error); }

  let timer;
  const save = async () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      try {
        const response = await request("/api/settings/notifications", {
          method: "PATCH",
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
