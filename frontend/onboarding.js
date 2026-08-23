import { getSession, signOut } from "./auth.js";

(async function bootstrap() {
  const session = await getSession();
  if (!session) {
    location.href = "./login.html";
    return;
  }

  document.querySelector("#sign-out").addEventListener("click", async () => {
    await signOut();
    location.href = "./login.html";
  });
})();
