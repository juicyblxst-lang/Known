import { getSession } from "./auth.js";

(async () => {
  const session = await getSession();
  if (!session) {
    window.location.replace("./login.html");
    return;
  }
  window.location.replace("./onboarding.html");
})();
