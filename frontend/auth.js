let configPromise;

async function getConfig() {
  if (!configPromise) {
    configPromise = fetch("/api/config").then(async (response) => {
      if (!response.ok) throw new Error("Unable to load Known configuration.");
      return response.json();
    });
  }
  return configPromise;
}

export async function authConfigured() {
  const config = await getConfig();
  return Boolean(config.supabase_url && config.supabase_anon_key);
}

export async function getSession() {
  const config = await getConfig();
  if (!config.supabase_url || !config.supabase_anon_key) return null;
  const stored = localStorage.getItem("known.access_token");
  if (!stored) return null;
  const response = await fetch(`${config.supabase_url}/auth/v1/user`, {
    headers: { apikey: config.supabase_anon_key, Authorization: `Bearer ${stored}` },
  });
  if (!response.ok) {
    localStorage.removeItem("known.access_token");
    return null;
  }
  const user = await response.json();
  return { accessToken: stored, user };
}

export async function signIn(email, password) {
  const config = await getConfig();
  if (!config.supabase_url || !config.supabase_anon_key) {
    throw new Error("Supabase authentication is not configured.");
  }
  const response = await fetch(`${config.supabase_url}/auth/v1/token?grant_type=password`, {
    method: "POST",
    headers: { apikey: config.supabase_anon_key, "Content-Type": "application/json" },
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
