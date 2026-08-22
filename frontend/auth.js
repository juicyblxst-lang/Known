const SUPABASE_URL = window.KNOWN_SUPABASE_URL || "";
const SUPABASE_ANON_KEY = window.KNOWN_SUPABASE_ANON_KEY || "";

export function authConfigured() {
  return Boolean(SUPABASE_URL && SUPABASE_ANON_KEY);
}

export async function getSession() {
  if (!authConfigured()) return null;
  const stored = localStorage.getItem("known.access_token");
  if (!stored) return null;
  const response = await fetch(`${SUPABASE_URL}/auth/v1/user`, {
    headers: { apikey: SUPABASE_ANON_KEY, Authorization: `Bearer ${stored}` },
  });
  if (!response.ok) {
    localStorage.removeItem("known.access_token");
    return null;
  }
  const user = await response.json();
  return { accessToken: stored, user };
}

export async function signIn(email, password) {
  if (!authConfigured()) throw new Error("Supabase authentication is not configured.");
  const response = await fetch(`${SUPABASE_URL}/auth/v1/token?grant_type=password`, {
    method: "POST",
    headers: { apikey: SUPABASE_ANON_KEY, "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error_description || data.msg || "Unable to sign in.");
  localStorage.setItem("known.access_token", data.access_token);
  return getSession();
}

export function signOut() {
  localStorage.removeItem("known.access_token");
}
