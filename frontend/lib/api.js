const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:9000/api";
const SESSION_CLEARED_EVENT = "auth:session-cleared";
let refreshPromise = null;

let migrationChecked = false;

const migrateLegacySession = () => {
  if (typeof window === "undefined" || migrationChecked) return;
  migrationChecked = true;
  // Previously we cleared session if refreshToken was missing, but that breaks
  // logins that only provide an access_token (e.g. from navigation URL).
};

let urlTokenProcessed = false;

const consumeUrlToken = () => {
  if (typeof window === "undefined" || urlTokenProcessed) return null;
  const params = new URLSearchParams(window.location.search);
  const token = params.get("token");
  if (token) {
    localStorage.setItem("access_token", token);
    params.delete("token");
    const newUrl =
      window.location.pathname +
      (params.toString() ? `?${params.toString()}` : "") +
      window.location.hash;
    window.history.replaceState({}, document.title, newUrl);
    urlTokenProcessed = true;
    return token;
  }
  urlTokenProcessed = true;
  return null;
};

const getToken = () => {
  if (typeof window === "undefined") return null;
  migrateLegacySession();
  const urlToken = consumeUrlToken();
  const localToken = localStorage.getItem("access_token");
  return urlToken || localToken;
};

const getRefreshToken = () => {
  if (typeof window === "undefined") return null;
  migrateLegacySession();
  return localStorage.getItem("refresh_token");
};

const setToken = (token, refreshToken) => {
  if (typeof window === "undefined") return;
  if (token) {
    localStorage.setItem("access_token", token);
  } else {
    localStorage.removeItem("access_token");
  }
  if (refreshToken) {
    localStorage.setItem("refresh_token", refreshToken);
  } else if (refreshToken === null) {
    localStorage.removeItem("refresh_token");
  }
};

const clearSession = () => {
  setToken(null, null);
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(SESSION_CLEARED_EVENT));
  }
};

const refreshAccessToken = async () => {
  const refreshToken = getRefreshToken();
  if (!refreshToken) {
    return null;
  }
  if (!refreshPromise) {
    refreshPromise = fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ refresh_token: refreshToken }),
    })
      .then(async (res) => {
        if (!res.ok) {
          return null;
        }
        const data = await res.json();
        if (!data?.access_token || !data?.refresh_token) {
          return null;
        }
        setToken(data.access_token, data.refresh_token);
        return data.access_token;
      })
      .catch(() => null)
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
};

export const apiFetch = async (path, options = {}, retry = true) => {
  const url = path.startsWith("http") ? path : `${API_BASE}${path}`;
  const runRequest = async (overrideToken) => {
    const headers = {
      ...(options.headers || {}),
    };
    const token = overrideToken || getToken();
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }

    return fetch(url, {
      ...options,
      headers,
      credentials: "include",
    });
  };

  let res = await runRequest();
  const skipRefresh = path === "/auth/login" || path === "/auth/refresh" || path === "/auth/logout";

  if (res.status === 401 && retry && !skipRefresh) {
    const nextToken = await refreshAccessToken();
    if (nextToken) {
      res = await runRequest(nextToken);
    }
  }

  if (res.status === 401) {
    clearSession();
    if (typeof window !== "undefined") {
      window.location.href = "/management/navigation";
    }
  }

  return res;
};

const resetAuthStateForTests = () => {
  refreshPromise = null;
};

export { API_BASE, SESSION_CLEARED_EVENT, clearSession, getRefreshToken, getToken, migrateLegacySession, resetAuthStateForTests, setToken };
