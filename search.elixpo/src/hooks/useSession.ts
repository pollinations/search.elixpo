'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';

function generateSessionId(): string {
  const chars = 'abcdefghijklmnopqrstuvwxyz0123456789';
  let result = 'sess_';
  for (let i = 0; i < 16; i++) {
    result += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return result;
}

export function useSession(initialSessionId?: string) {
  const router = useRouter();
  const [sessionId, setSessionId] = useState<string>(initialSessionId || '');
  const [clientId, setClientId] = useState<string>('');

  useEffect(() => {
    if (typeof window === 'undefined') return;

    // Use URL-provided session ID or generate a new one
    if (!sessionId) {
      const id = generateSessionId();
      setSessionId(id);
      router.replace(`/c/${id}`);
    }

    let client = window.localStorage.getItem('elixpo_client_id');
    if (!client) {
      client = `client_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
      window.localStorage.setItem('elixpo_client_id', client);
    }
    setClientId(client);
  }, []);

  const newSession = useCallback(() => {
    const id = generateSessionId();
    setSessionId(id);
    router.push(`/c/${id}`);
    return id;
  }, [router]);

  return { sessionId, clientId, newSession };
}
