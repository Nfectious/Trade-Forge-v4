'use client';

import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { api, setAccessToken, tryRefreshToken } from './api';

interface User {
  id: string;
  email: string;
  role: string;
  status: string;
  tier: string;
  email_verified: boolean;
  created_at: string;
}

interface AuthContextType {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshUser = async () => {
    try {
      // No in-memory token → try to restore one via the httpOnly refresh cookie.
      // This handles page refreshes where the memory token has been cleared.
      const { getStoredAccessToken } = await import('./api');
      if (!getStoredAccessToken()) {
        const restored = await tryRefreshToken();
        if (!restored) {
          setUser(null);
          return;
        }
      }
      const response = await api.get('/auth/me');
      setUser(response.data);
    } catch {
      setUser(null);
      setAccessToken(null);
    }
  };

  useEffect(() => {
    refreshUser().finally(() => setLoading(false));
  }, []);

  const login = async (email: string, password: string) => {
    const response = await api.post('/auth/login', { email, password });
    const { access_token } = response.data;
    // Store in memory only — never localStorage
    setAccessToken(access_token);
    await refreshUser();
  };

  const logout = async () => {
    try {
      // Tell server to revoke refresh token and clear the httpOnly cookie
      await api.post('/auth/logout');
    } catch {
      // Best-effort
    } finally {
      setAccessToken(null);
      setUser(null);
    }
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
