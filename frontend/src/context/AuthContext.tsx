import React, { createContext, useContext, useState, useEffect } from 'react';
import { api, SESSION_EXPIRED_EVENT } from '../api/client';
import { setFormatSettings } from '../utils/format';

export interface User {
  id: string;
  email: string;
  full_name: string;
  phone: string;
  designation: string;
  system_role: 'superadmin' | 'admin' | 'staff';
  is_active: boolean;
  /** Per-user exception: null = follow firm setting, true = allow, false = block */
  can_create_tasks: boolean | null;
  /** Final answer from the server (admins always true) */
  effective_can_create_tasks: boolean;
  /** Admin gave a temporary password: the user must set a new one before any other work */
  must_change_password: boolean;
  branches: Array<{ id: string; name: string; code: string; is_default: boolean }>;
}

export interface Firm {
  id: string;
  name: string;
  legal_name: string;
  timezone: string;
  date_format: string;
  long_due_days: number;
  staff_can_create_task: boolean;
  staff_can_complete: boolean;
  allow_pickup: boolean;
  fy_start_month: number;
  has_tasks: boolean;
  logo_url: string | null;
}

interface AuthContextType {
  user: User | null;
  firm: Firm | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [firm, setFirm] = useState<Firm | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = async () => {
    try {
      const data = await api.get('/api/v1/auth/me/');
      setUser(data.user);
      // Date format + time zone from Settings, used by every screen (utils/format.ts)
      setFormatSettings(data.firm?.date_format, data.firm?.timezone);
      setFirm(data.firm);
    } catch {
      setUser(null);
      setFirm(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  // Session expired on the server: go back to the login screen instead of failing silently
  useEffect(() => {
    const onExpired = () => {
      console.warn('[auth] session expired - showing login');
      setUser(null);
      setFirm(null);
    };
    window.addEventListener(SESSION_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, onExpired);
  }, []);

  const login = async (email: string, password: string) => {
    const data = await api.post('/api/v1/auth/login/', { email, password });
    setUser(data.user);
    await refresh();
  };

  const logout = async () => {
    try {
      await api.post('/api/v1/auth/logout/');
    } finally {
      setUser(null);
      setFirm(null);
    }
  };

  return (
    <AuthContext.Provider value={{ user, firm, loading, login, logout, refresh }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
