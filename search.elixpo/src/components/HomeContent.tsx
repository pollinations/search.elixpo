'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { EyeOff, Eye } from 'lucide-react';
import Sidebar from '@/components/layout/Sidebar';
import SearchInput, { type SearchPayload } from '@/components/search/SearchInput';
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
  const [incognito, setIncognito] = useState(() => {
    if (typeof window !== 'undefined') {
      return window.localStorage.getItem('elixpo_incognito') === '1';
    }
    return false;
  });

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

  const toggleIncognito = useCallback(() => {
    setIncognito((prev) => {
      const next = !prev;
      window.localStorage.setItem('elixpo_incognito', next ? '1' : '0');
      return next;
    });
  }, []);

  const handleSend = useCallback(
    (payload: SearchPayload) => {
      if (sessionId) {
        sendQuery(payload.query, sessionId, {
          images: payload.images,
          deepSearch: payload.deepSearch,
          incognito,
        });
      }
    },
    [sessionId, sendQuery, incognito]
  );

  const handleNewSearch = useCallback(() => {
    loadedRef.current = null;
    newSession();
    clearMessages();
  }, [newSession, clearMessages]);

  const isLanding = messages.length === 0;

  return (
    <div className="h-screen flex bg-[#18191a]">
      <Sidebar onNewSearch={handleNewSearch} />

      <main className="flex-1 flex flex-col h-full overflow-hidden">
        {/* Top bar with incognito toggle */}
        <div className="flex items-center justify-end px-4 py-2 shrink-0">
          <button
            onClick={toggleIncognito}
            title={incognito ? 'Incognito mode ON — chats are not saved' : 'Incognito mode OFF — chats are saved'}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
              incognito
                ? 'bg-[#444ce7]/15 text-[#6ea8fe] border border-[#444ce7]/30'
                : 'text-[#666] hover:text-[#999] hover:bg-[#222]'
            }`}
          >
            {incognito ? <EyeOff size={14} /> : <Eye size={14} />}
            {incognito ? 'Incognito' : ''}
          </button>
        </div>

        {isLanding ? (
          /* Landing: centered branding + search */
          <div className="flex-1 flex flex-col items-center justify-center px-4 -mt-10">
            <h1 className="text-5xl font-display font-bold text-gradient-hero mb-10 select-none">
              Lix-Search
            </h1>
            <SearchInput onSend={handleSend} disabled={isSearching} showPills />
          </div>
        ) : (
          /* Conversation: results + pinned input at bottom */
          <>
            <SearchResults messages={messages} statusText={statusText} />
            <div className="mb-3">
              <SearchInput onSend={handleSend} disabled={isSearching} />
            </div>
          </>
        )}
      </main>
    </div>
  );
}
