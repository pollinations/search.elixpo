'use client';

import { useCallback } from 'react';
import Sidebar from '@/components/layout/Sidebar';
import SidePanel from '@/components/layout/SidePanel';
import SearchInput from '@/components/search/SearchInput';
import SearchResults from '@/components/search/SearchResults';
import { useSSESearch } from '@/hooks/useSSESearch';
import { useSession } from '@/hooks/useSession';

export default function HomeContent() {
  const { sessionId, newSession } = useSession();
  const { messages, isSearching, statusText, sendQuery, clearMessages } = useSSESearch();

  const handleSend = useCallback(
    (query: string) => {
      if (sessionId) {
        sendQuery(query, sessionId);
      }
    },
    [sessionId, sendQuery]
  );

  const handleNewSearch = useCallback(() => {
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
