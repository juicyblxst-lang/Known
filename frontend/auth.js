let configPromise;
let refreshPromise = null;

async function getConfig() {
  if (!configPromise) configPromise = fetch("/api/config").then(async (response) => { if (!response.ok) throw new Error("Unable to load Known configuration."); return response.json(); });
  return configPromise;
}
async function supabaseRequest(path, options = {}) {
  const config = await getConfig();
  if (!config.supabase_url || !config.supabase_anon_key) throw new Error("Supabase authentication is not configured.");
  return fetch(`${config.supabase_url}/auth/v1${path}`, { ...options, headers: { apikey: config.supabase_anon_key, ...(options.body ? {"Content-Type":"application/json"}:{}), ...(options.headers || {}) } });
}
export async function authConfigured(){ const config=await getConfig(); return Boolean(config.supabase_url&&config.supabase_anon_key); }
function clearSession(){localStorage.removeItem("known.access_token");localStorage.removeItem("known.refresh_token");}
function saveSession(data){if(!data?.access_token||!data?.refresh_token) throw new Error("Authentication did not return a valid session.");localStorage.setItem("known.access_token",data.access_token);localStorage.setItem("known.refresh_token",data.refresh_token);}
export function invalidateSession(){clearSession();sessionStorage.removeItem("known.new-user");}
async function fetchUser(accessToken){const response=await supabaseRequest("/user",{headers:{Authorization:`Bearer ${accessToken}`}});return response.ok?response.json():null;}
async function refreshSession(){
  if (refreshPromise) return refreshPromise;
  const refreshToken=localStorage.getItem("known.refresh_token");
  if(!refreshToken)return null;
  refreshPromise=(async()=>{
    try{
      const response=await supabaseRequest("/token?grant_type=refresh_token",{method:"POST",body:JSON.stringify({refresh_token:refreshToken})});
      const data=await response.json().catch(()=>({}));
      if(!response.ok){clearSession();return null;}
      saveSession(data);
      const user=await fetchUser(data.access_token);
      if(!user){clearSession();return null;}
      return {accessToken:data.access_token,user};
    }catch{clearSession();return null;}
    finally{refreshPromise=null;}
  })();
  return refreshPromise;
}
export async function refreshCurrentSession(){ return refreshSession(); }

export async function authenticatedFetch(path, options = {}) {
  let session = await getSession();
  if (!session) { const error = new Error("Your session has expired. Please sign in again."); error.status = 401; throw error; }
  const request = (accessToken) => fetch(path, { ...options, headers: { ...(options.headers || {}), Authorization: `Bearer ${accessToken}` } });
  let response = await request(session.accessToken);
  if (response.status !== 401) return response;
  session = await refreshSession();
  if (!session) { const error = new Error("Your session has expired. Please sign in again."); error.status = 401; throw error; }
  response = await request(session.accessToken);
  if (response.status === 401) { const error = new Error("Your Known session is no longer valid. Please sign in again."); error.status = 401; throw error; }
  return response;
}

export async function handleAuthCallback(){
  const hash=window.location.hash?.slice(1); if(!hash)return null;
  const params=new URLSearchParams(hash); const accessToken=params.get("access_token"); const refreshToken=params.get("refresh_token");
  if(params.get("error")) throw new Error(params.get("error_description")||"Email verification failed.");
  if(!accessToken||!refreshToken)return null;
  saveSession({access_token:accessToken,refresh_token:refreshToken}); const user=await fetchUser(accessToken);
  if(!user){clearSession();throw new Error("Email verification succeeded, but the session could not be verified.");}
  window.history.replaceState({},document.title,window.location.pathname+window.location.search); return {accessToken,user};
}
export async function getSession({forceRefresh=false}={}){
  const callbackSession=await handleAuthCallback(); if(callbackSession)return callbackSession;
  if(forceRefresh)return refreshSession();
  const accessToken=localStorage.getItem("known.access_token"); if(!accessToken)return null;
  try{const user=await fetchUser(accessToken);if(user)return {accessToken,user};}catch{}
  return refreshSession();
}
export async function onboardingStatus(session,{retryAuth=true}={}){
  let response=await fetch("/api/onboarding/status",{headers:{Authorization:`Bearer ${session.accessToken}`}});
  if(response.status===401&&retryAuth){
    const refreshed=await getSession({forceRefresh:true});
    if(refreshed){
      session=refreshed;
      response=await fetch("/api/onboarding/status",{headers:{Authorization:`Bearer ${session.accessToken}`}});
    }
  }
  if(!response.ok){const error=new Error(response.status===401?"Your Known session is no longer valid. Please sign in again.":"Unable to verify onboarding state.");error.status=response.status;throw error;}
  return response.json();
}
export async function completeOnboarding(session){const response=await authenticatedFetch("/api/onboarding/complete",{method:"POST"});if(!response.ok)throw new Error("Unable to save onboarding state.");return response.json();}
export async function signIn(email,password){const response=await supabaseRequest("/token?grant_type=password",{method:"POST",body:JSON.stringify({email,password})});const data=await response.json();if(!response.ok)throw new Error(data.error_description||data.msg||data.message||"Unable to sign in.");saveSession(data);const user=await fetchUser(data.access_token);if(!user){clearSession();throw new Error("Sign-in succeeded but the user session could not be verified.");}sessionStorage.removeItem("known.new-user");return {accessToken:data.access_token,user};}
export async function signUp(email,password,name){const redirectTo=`${window.location.origin}/login.html`;const response=await supabaseRequest("/signup",{method:"POST",body:JSON.stringify({email,password,data:{name,preferred_name:name},redirect_to:redirectTo})});const data=await response.json();if(!response.ok)throw new Error(data.error_description||data.msg||data.message||"Unable to create account.");sessionStorage.setItem("known.new-user","true");if(data.access_token&&data.refresh_token){saveSession(data);return {session:{accessToken:data.access_token,user:data.user},requiresEmailConfirmation:false};}return {session:null,requiresEmailConfirmation:true};}
export async function signOut(){const accessToken=localStorage.getItem("known.access_token");clearSession();sessionStorage.removeItem("known.new-user");if(!accessToken)return;try{await supabaseRequest("/logout",{method:"POST",headers:{Authorization:`Bearer ${accessToken}`}});}catch{}}
