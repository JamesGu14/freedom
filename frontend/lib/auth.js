import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { API_BASE, SESSION_CLEARED_EVENT, clearSession, getRefreshToken, getToken, setToken } from "./api";

const AuthContext = createContext({
  token: null,
  username: null,
  roles: [],
  initialized: false,
  login: async () => {},
  logout: async () => {},
});

export const AuthProvider = ({ children }) => {
  const [tokenState, setTokenState] = useState(null);
  const [usernameState, setUsernameState] = useState(null);
  const [rolesState, setRolesState] = useState([]);
  const [initialized, setInitialized] = useState(false);

  useEffect(() => {
    const stored = getToken();
    setTokenState(stored);
    setInitialized(true);
  }, []);

  useEffect(() => {
    const handleSessionCleared = () => {
      setTokenState(null);
      setUsernameState(null);
      setRolesState([]);
    };

    if (typeof window !== "undefined") {
      window.addEventListener(SESSION_CLEARED_EVENT, handleSessionCleared);
    }

    return () => {
      if (typeof window !== "undefined") {
        window.removeEventListener(SESSION_CLEARED_EVENT, handleSessionCleared);
      }
    };
  }, []);

  useEffect(() => {
    if (!initialized || !tokenState) {
      if (initialized) {
        setUsernameState(null);
        setRolesState([]);
      }
      return;
    }

    const fetchMe = async () => {
      try {
        const res = await fetch(`${API_BASE}/auth/me`, {
          method: "GET",
          headers: { Authorization: `Bearer ${tokenState}` },
          credentials: "include",
        });
        if (res.status === 401) {
          clearSession();
          return;
        }
        if (!res.ok) return;
        const data = await res.json();
        const username = data?.username || null;
        const roles = Array.isArray(data?.roles) ? data.roles : [];
        setUsernameState(username);
        setRolesState(roles);
      } catch (err) {
        // ignore profile fetch failures
      }
    };

    fetchMe();
  }, [tokenState, initialized]);

  const login = async (username, password) => {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ username, password }),
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      const message = detail?.detail || `登录失败: ${res.status}`;
      throw new Error(message);
    }
    const data = await res.json();
    if (data?.access_token && data?.refresh_token) {
      setToken(data.access_token, data.refresh_token);
      setTokenState(data.access_token);
      setUsernameState(null);
      setRolesState([]);
    }
    return data;
  };

  const logout = async () => {
    try {
      const refreshToken = getRefreshToken();
      await fetch(`${API_BASE}/auth/logout`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
    } catch (err) {
      // ignore logout failures
    }
    clearSession();
  };

  const value = useMemo(
    () => ({
      token: tokenState,
      username: usernameState,
      roles: rolesState,
      initialized,
      login,
      logout,
    }),
    [tokenState, usernameState, rolesState, initialized]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = () => useContext(AuthContext);
