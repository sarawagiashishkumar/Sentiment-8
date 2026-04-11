import { useState, useMemo, useCallback, useEffect } from "react";
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

  // Bootstrap on mount
  useEffect(() => {
    if (!token) return;
    hydrateMe(token).catch(() => {
      sessionStorage.removeItem("stock_auth_token");
      setToken("");
      setMe(null);
    });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const onLogin = useCallback(async (e) => {
    e.preventDefault();
    const trimmed = loginUsername.trim();
    if (!trimmed) return;
    setLoginLoading(true);
    setLoginError("");
    try {
      const response = await axios.post(`${API}/auth/access`, { username: trimmed });
      sessionStorage.setItem("stock_auth_token", response.data.token);
      setToken(response.data.token);
      await hydrateMe(response.data.token);
    } catch (err) {
      setLoginError(err?.response?.data?.detail || "Login failed");
    } finally {
      setLoginLoading(false);
    }
  }, [loginUsername, hydrateMe]);

  const onLogout = useCallback(() => {
    sessionStorage.removeItem("stock_auth_token");
    setToken("");
    setMe(null);
  }, []);

  return {
    token, me, authHeaders, isAdmin, isOwner,
    loginUsername, setLoginUsername, loginLoading, loginError,
    onLogin, onLogout,
  };
}
