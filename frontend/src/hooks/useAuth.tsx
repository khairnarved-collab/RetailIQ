import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, setUnauthorizedHandler, tokenStore } from "@/services/api";
import type { TokenResponse, User } from "@/services/types";

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<User>;
  register: (full_name: string, email: string, password: string) => Promise<User>;
  logout: () => void;
  refresh: () => Promise<void>;
  setUser: (u: User) => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const qc = useQueryClient();

  const logout = useCallback(() => {
    tokenStore.clear();
    setUser(null);
    qc.clear();
  }, [qc]);

  const refresh = useCallback(async () => {
    if (!tokenStore.get()) { setLoading(false); return; }
    try { setUser(await api.get<User>("/auth/me")); } catch { tokenStore.clear(); setUser(null); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { setUnauthorizedHandler(logout); void refresh(); }, [logout, refresh]);

  const login = useCallback(async (email: string, password: string) => {
    const r = await api.post<TokenResponse>("/auth/login", { email, password });
    tokenStore.set(r.access_token);
    setUser(r.user);
    return r.user;
  }, []);

  const register = useCallback(async (full_name: string, email: string, password: string) => {
    const r = await api.post<TokenResponse>("/auth/register", { full_name, email, password });
    tokenStore.set(r.access_token);
    setUser(r.user);
    return r.user;
  }, []);

  const value = useMemo(() => ({ user, loading, login, register, logout, refresh, setUser }), [user, loading, login, register, logout, refresh]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
