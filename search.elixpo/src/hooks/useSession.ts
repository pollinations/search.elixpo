'use client';

import { useState, useEffect, useCallback } from 'react';

function generateSessionId(): string {
  const chars = 'abcdefghijklmnopqrstuvwxyz0123456789';
  let result = 'sess_';
  for (let i = 0; i < 16; i++) {
    result += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return result;
}

export function useSession() {
  const [sessionId, setSessionId] = useState<string>('');
  const [clientId, setClientId] = useState<string>('');

  useEffect(() => {
    if (typeof window === 'undefined') return;
    let stored = window.localStorage.getItem('elixpo_session_id');
    if (!stored) {
      stored = generateSessionId();
      window.localStorage.setItem('elixpo_session_id', stored);
    }
    setSessionId(stored);

    let client = window.localStorage.getItem('elixpo_client_id');
    if (!client) {
      client = `client_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
      window.localStorage.setItem('elixpo_client_id', client);
    }
    setClientId(client);
  }, []);

  const newSession = useCallback(() => {
    if (typeof window === 'undefined') return '';
    const id = generateSessionId();
    window.localStorage.setItem('elixpo_session_id', id);
    setSessionId(id);
    return id;
  }, []);

  return { sessionId, clientId, newSession };
}
