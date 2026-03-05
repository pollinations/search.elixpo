import type { SearchMessage } from '@/types';

const CACHE_PREFIX = 'elixpo_conv_';
const INDEX_KEY = 'elixpo_conv_index';
const DEFAULT_TTL_MS = 30 * 60 * 1000; // 30 minutes

interface CachedConversation {
  sessionId: string;
  messages: SearchMessage[];
  updatedAt: number;
  expiresAt: number;
  savedToDb: boolean;
}

interface ConversationIndex {
  sessions: { id: string; title: string; updatedAt: number; expiresAt: number }[];
}

function getKey(sessionId: string): string {
  return `${CACHE_PREFIX}${sessionId}`;
}

export function getCachedConversation(sessionId: string): SearchMessage[] | null {
  try {
    const raw = localStorage.getItem(getKey(sessionId));
    if (!raw) return null;
    const cached: CachedConversation = JSON.parse(raw);
    if (Date.now() > cached.expiresAt) {
      localStorage.removeItem(getKey(sessionId));
      removeFromIndex(sessionId);
      return null;
    }
    return cached.messages;
  } catch {
    return null;
  }
}

export function setCachedConversation(
  sessionId: string,
  messages: SearchMessage[],
  savedToDb = false
): void {
  try {
    const now = Date.now();
    const cached: CachedConversation = {
      sessionId,
      messages,
      updatedAt: now,
      expiresAt: now + DEFAULT_TTL_MS,
      savedToDb,
    };
    localStorage.setItem(getKey(sessionId), JSON.stringify(cached));

    // Update index
    const firstUserMsg = messages.find((m) => m.role === 'user');
    const title = firstUserMsg?.content.slice(0, 100) || 'New conversation';
    updateIndex(sessionId, title, now, cached.expiresAt);
  } catch {
    // localStorage full or unavailable
  }
}

export function markCachedAsSaved(sessionId: string): void {
  try {
    const raw = localStorage.getItem(getKey(sessionId));
    if (!raw) return;
    const cached: CachedConversation = JSON.parse(raw);
    cached.savedToDb = true;
    localStorage.setItem(getKey(sessionId), JSON.stringify(cached));
  } catch {
    // ignore
  }
}

export function isCachedSaved(sessionId: string): boolean {
  try {
    const raw = localStorage.getItem(getKey(sessionId));
    if (!raw) return false;
    return JSON.parse(raw).savedToDb;
  } catch {
    return false;
  }
}

export function removeCachedConversation(sessionId: string): void {
  localStorage.removeItem(getKey(sessionId));
  removeFromIndex(sessionId);
}

export function getConversationIndex(): ConversationIndex['sessions'] {
  try {
    const raw = localStorage.getItem(INDEX_KEY);
    if (!raw) return [];
    const index: ConversationIndex = JSON.parse(raw);
    const now = Date.now();
    // Filter expired
    return index.sessions.filter((s) => s.expiresAt > now);
  } catch {
    return [];
  }
}

function updateIndex(sessionId: string, title: string, updatedAt: number, expiresAt: number): void {
  try {
    const sessions = getConversationIndex().filter((s) => s.id !== sessionId);
    sessions.unshift({ id: sessionId, title, updatedAt, expiresAt });
    // Keep max 50 entries
    const trimmed = sessions.slice(0, 50);
    localStorage.setItem(INDEX_KEY, JSON.stringify({ sessions: trimmed }));
  } catch {
    // ignore
  }
}

function removeFromIndex(sessionId: string): void {
  try {
    const sessions = getConversationIndex().filter((s) => s.id !== sessionId);
    localStorage.setItem(INDEX_KEY, JSON.stringify({ sessions }));
  } catch {
    // ignore
  }
}

export function cleanupExpiredCache(): void {
  try {
    const now = Date.now();
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (!key?.startsWith(CACHE_PREFIX)) continue;
      const raw = localStorage.getItem(key);
      if (!raw) continue;
      try {
        const cached: CachedConversation = JSON.parse(raw);
        if (now > cached.expiresAt) {
          localStorage.removeItem(key);
        }
      } catch {
        localStorage.removeItem(key!);
      }
    }
    // Clean index too
    const sessions = getConversationIndex();
    localStorage.setItem(INDEX_KEY, JSON.stringify({ sessions }));
  } catch {
    // ignore
  }
}
