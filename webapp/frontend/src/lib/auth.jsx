import { createContext, useContext, useState, useCallback } from 'react';

const AuthContext = createContext(null);

const STORAGE_KEY = 'nepl:auth';

function loadStored() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch { return null; }
}

export function AuthProvider({ children }) {
  const [auth, setAuth] = useState(loadStored);

  const login = useCallback((data) => {
    const rec = {
      token: data.access_token, role: data.role,
      tenantId: data.tenant_id, name: data.name,
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(rec));
    setAuth(rec);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    setAuth(null);
  }, []);

  const ROLE_ORDER = { viewer: 0, estimator: 1, approver: 2, admin: 3 };
  const hasRole = (min) => !!auth && ROLE_ORDER[auth.role] >= ROLE_ORDER[min];

  return (
    <AuthContext.Provider value={{ auth, login, logout, hasRole, isAuthenticated: !!auth }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
