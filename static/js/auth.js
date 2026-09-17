// static/js/auth.js
// ──────────────────────────────────────────────────────────────
// Token handling + authenticated fetch (PROJ-407)
//
// Tokens live in localStorage. That's readable by any script on
// the page, so an XSS bug would expose them — the mitigation is
// that access tokens expire in 15 minutes and refresh tokens
// rotate on use, so a stolen pair has a short useful life.
// HttpOnly cookies would be stronger but need server-side
// session handling and CSRF protection.
// ──────────────────────────────────────────────────────────────

const ACCESS_KEY = "af_access_token";
const REFRESH_KEY = "af_refresh_token";

const Auth = {
  get accessToken() {
    return localStorage.getItem(ACCESS_KEY);
  },

  get refreshToken() {
    return localStorage.getItem(REFRESH_KEY);
  },

  save(access, refresh) {
    localStorage.setItem(ACCESS_KEY, access);
    if (refresh) localStorage.setItem(REFRESH_KEY, refresh);
  },

  clear() {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },

  isLoggedIn() {
    return Boolean(this.accessToken);
  },

  async login(email, password) {
    const res = await fetch("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Login failed");
    }
    const data = await res.json();
    this.save(data.access_token, data.refresh_token);
    return data;
  },

  async register(orgName, email, password) {
    const res = await fetch("/orgs/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ org_name: orgName, email, password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Registration failed");
    }
    return await res.json();
  },

  // Returns true if a new access token was obtained.
  async tryRefresh() {
    const refresh = this.refreshToken;
    if (!refresh) return false;
    const res = await fetch("/auth/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refresh }),
    });
    if (!res.ok) {
      this.clear();
      return false;
    }
    const data = await res.json();
    this.save(data.access_token, data.refresh_token);
    return true;
  },

  async logout() {
    const refresh = this.refreshToken;
    if (refresh) {
      // Revoke server-side so the refresh token can't be reused.
      await fetch("/auth/logout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refresh }),
      }).catch(() => {});
    }
    this.clear();
    window.location.href = "/login";
  },

  async me() {
    const res = await authFetch("/auth/me");
    return res.ok ? await res.json() : null;
  },

  async org() {
    const res = await authFetch("/orgs/me");
    return res.ok ? await res.json() : null;
  },
};

/**
 * fetch() with the bearer token attached.
 * On a 401 it refreshes once and retries; if that fails the user
 * is sent to the login page rather than left with a silent error.
 */
async function authFetch(url, options = {}) {
  const withAuth = (token) => {
    const headers = new Headers(options.headers || {});
    if (token) headers.set("Authorization", `Bearer ${token}`);
    return { ...options, headers };
  };

  let res = await fetch(url, withAuth(Auth.accessToken));

  if (res.status === 401 || res.status === 403) {
    const refreshed = await Auth.tryRefresh();
    if (refreshed) {
      res = await fetch(url, withAuth(Auth.accessToken));
    } else {
      Auth.clear();
      window.location.href = "/login?expired=1";
      throw new Error("Session expired");
    }
  }

  return res;
}

// Pages that need a session call this on load.
function requireAuth() {
  if (!Auth.isLoggedIn()) {
    window.location.href = "/login";
    return false;
  }
  return true;
}