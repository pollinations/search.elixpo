'use client';

import { useState, useEffect, useCallback } from 'react';

export interface AuthUser {
  id: string;
  email: string;
  displayName: string | null;
  avatar: string | null;
  provider: string;
  emailVerified: boolean;
  bio: string | null;
  location: string | null;
  website: string | null;
  company: string | null;
  jobTitle: string | null;
  theme: string;
  language: string;
  searchRegion: string;
  safeSearch: number;
  deepSearchDefault: boolean;
  tier: string;
  totalSearches: number;
  totalSessions: number;
  memberSince: string | null;
}

export function useAuth() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchUser = useCallback(async () => {
    try {
      const res = await fetch('/api/auth/me');
      if (res.ok) {
        const data = await res.json();
        setUser(data);

        // Claim any guest sessions for this browser
        const clientId = typeof window !== 'undefined'
          ? window.localStorage.getItem('elixpo_client_id')
          : null;
        if (clientId) {
          fetch('/api/sessions/claim', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'x-xid': process.env.NEXT_PUBLIC_XID || '' },
            body: JSON.stringify({ clientId }),
          }).catch(() => {});
        }
      } else {
        setUser(null);
      }
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchUser();
  }, [fetchUser]);

  const login = useCallback((returnTo?: string) => {
    const params = returnTo ? `?returnTo=${encodeURIComponent(returnTo)}` : '';
    window.location.href = `/api/auth/login${params}`;
  }, []);

  const logout = useCallback(async () => {
    await fetch('/api/auth/logout');
    setUser(null);
    window.location.href = '/';
  }, []);

  return { user, loading, login, logout, refetch: fetchUser };
}
