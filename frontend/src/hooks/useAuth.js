import { useState, useMemo, useCallback, useEffect, useRef } from "react";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export function useAuth() {
  const [token, setToken] = useState(sessionStorage.getItem("stock_auth_token") || "");
  const [me, setMe] = useState(null);
  const [loginUsername, setLoginUsername] = useState("");
  const [loginLoading, setLoginLoading] = useState(false);
  const [loginError, setLoginError] = useState("");

  const authHeaders = useMemo(
    () => (token ? { Authorization: `Bearer ${token}` } : {}),
    [token],
  );
  const isAdmin = me?.role === "owner" || me?.role === "sub_admin";
  const isOwner = me?.role === "owner";

  const hydrateMe = useCallback(async (accessToken) => {
    const response = await axios.get(`${API}/auth/me`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    setMe(response.data);
    return response.data;
  }, []);

  // Bootstrap on mount — token is captured via ref to avoid re-running effect
  const tokenRef = useRef(token);
  tokenRef.current = token;
  useEffect(() => {
    const t = tokenRef.current;
    if (!t) return;
    hydrateMe(t).catch((err) => {
      console.error("Auth hydration failed:", err?.message);
      sessionStorage.removeItem("stock_auth_token");
      setToken("");
      setMe(null);
    });
  }, [hydrateMe]);

  // loginUsername captured via ref to keep onLogin stable
  const loginUsernameRef = useRef(loginUsername);
  loginUsernameRef.current = loginUsername;

  const onLogin = useCallback(async (e) => {
    e.preventDefault();
    const trimmed = loginUsernameRef.current.trim();
    if (!trimmed) return;
    setLoginLoading(true);
    setLoginError("");
    try {
      const response = await axios.post(`${API}/auth/access`, { username: trimmed });
      sessionStorage.setItem("stock_auth_token", response.data.token);
      setToken(response.data.token);
      setMe({
        role: response.data.role, credits: response.data.credits,
        user_key: response.data.user_key, username: response.data.username,
        admin_exempt: response.data.admin_exempt,
        fno_budget: response.data.fno_budget || 500000,
        account_risk_pct: response.data.account_risk_pct || 2.0,
      });
      setLoginUsername("");
    } catch (err) {
      setLoginError(err?.response?.data?.detail || "Login failed");
    } finally {
      setLoginLoading(false);
    }
  }, []);

  const onLogout = useCallback(async () => {
    try {
      await axios.post(`${API}/auth/logout`, {}, { headers: authHeaders });
    } catch (err) {
      console.error("Logout request failed:", err?.message);
    }
    sessionStorage.removeItem("stock_auth_token");
    setToken("");
    setMe(null);
  }, [authHeaders]);

  const syncCredits = useCallback((credits) => {
    setMe((prev) => (prev ? { ...prev, credits } : prev));
  }, []);

  return {
    token, me, setMe, authHeaders, isAdmin, isOwner,
    loginUsername, setLoginUsername, loginLoading, loginError,
    onLogin, onLogout, hydrateMe, syncCredits,
  };
}
