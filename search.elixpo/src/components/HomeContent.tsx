'use client';

import { useCallback, useEffect, useRef } from 'react';
import Sidebar from '@/components/layout/Sidebar';
import SidePanel from '@/components/layout/SidePanel';
import SearchInput from '@/components/search/SearchInput';
import SearchResults from '@/components/search/SearchResults';
import { useSSESearch } from '@/hooks/useSSESearch';
import { useSession } from '@/hooks/useSession';
import { getCachedConversation, cleanupExpiredCache } from '@/lib/conversationCache';

interface HomeContentProps {
  initialSessionId?: string;
}

export default function HomeContent({ initialSessionId }: HomeContentProps) {
  const { sessionId, newSession } = useSession(initialSessionId);
  const { messages, isSearching, statusText, sendQuery, clearMessages, setMessages } = useSSESearch();
  const loadedRef = useRef<string | null>(null);

  // Load conversation when session changes (page load or navigation)
  useEffect(() => {
    if (!sessionId || loadedRef.current === sessionId) return;
    loadedRef.current = sessionId;

    // Try localStorage first (instant)
    const cached = getCachedConversation(sessionId);
    if (cached && cached.length > 0) {
      setMessages(cached);
      return;
    }

    // Fall back to Postgres
    fetch(`/api/conversations/${sessionId}`, {
      headers: { 'x-xid': process.env.NEXT_PUBLIC_XID || '' },
    })
      .then((res) => res.json())
      .then((data) => {
        if (data.messages && data.messages.length > 0) {
          setMessages(data.messages);
        }
      })
      .catch(() => {});
  }, [sessionId, setMessages]);

  // Cleanup expired localStorage entries on mount
  useEffect(() => {
    cleanupExpiredCache();
  }, []);

  const handleSend = useCallback(
    (query: string) => {
      if (sessionId) {
        sendQuery(query, sessionId);
      }
    },
    [sessionId, sendQuery]
  );

  const handleNewSearch = useCallback(() => {
    loadedRef.current = null;
    newSession();
    clearMessages();
  }, [newSession, clearMessages]);

  return (
    <div className="h-screen flex bg-[#18191a]">
      <Sidebar onNewSearch={handleNewSearch} />
      <SidePanel />

      <main className="flex-1 flex flex-col h-full overflow-hidden">
        <SearchResults messages={messages} statusText={statusText} />
        <div className="mb-3">
          <SearchInput onSend={handleSend} disabled={isSearching} />
        </div>
      </main>
    </div>
  );
}
