/**
 * AuthContext — manages user authentication state across the app.
 * Stores token + user in localStorage for persistence across refreshes.
 */

import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { api } from '../api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(() => localStorage.getItem('ims_token'));
  const [loading, setLoading] = useState(true);

  // On mount, verify the stored token
  useEffect(() => {
    async function verify() {
      if (!token) {
        setLoading(false);
        return;
      }
      try {
        const userData = await api.getMe(token);
        setUser(userData);
      } catch {
        // Token expired or invalid
        localStorage.removeItem('ims_token');
        setToken(null);
      }
      setLoading(false);
    }
    verify();
  }, []);

  const login = useCallback(async (email, password) => {
    const result = await api.login({ email, password });
    localStorage.setItem('ims_token', result.token);
    setToken(result.token);
    setUser(result.user);
    return result;
  }, []);

  const signup = useCallback(async (data) => {
    const result = await api.signup(data);
    localStorage.setItem('ims_token', result.token);
    setToken(result.token);
    setUser(result.user);
    return result;
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem('ims_token');
    setToken(null);
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, token, loading, login, signup, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within AuthProvider');
  return context;
}
