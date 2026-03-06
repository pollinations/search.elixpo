'use client';

import { useEffect, useRef } from 'react';
import type { SearchMessage } from '@/types';
import MessageSection from './MessageSection';

interface SearchResultsProps {
  messages: SearchMessage[];
  statusText: string;
}

export default function SearchResults({ messages, statusText }: SearchResultsProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new content
  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [messages]);

  // Group messages into pairs (user + assistant)
  const pairs: Array<{ user: SearchMessage; assistant: SearchMessage }> = [];
  for (let i = 0; i < messages.length; i += 2) {
    if (messages[i] && messages[i + 1]) {
      pairs.push({ user: messages[i], assistant: messages[i + 1] });
    }
  }

  if (pairs.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <h1 className="text-3xl font-bold text-white font-display">
          What do you want to search?
        </h1>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="flex-1 overflow-y-auto custom-scrollbar"
    >
      <div className="max-w-[65%] mx-auto py-5 min-h-full flex flex-col gap-2">
        {pairs.map((pair, i) => (
          <MessageSection
            key={pair.user.id}
            userMessage={pair.user}
            assistantMessage={pair.assistant}
            statusText={i === pairs.length - 1 ? statusText : ''}
          />
        ))}
      </div>
    </div>
  );
}
