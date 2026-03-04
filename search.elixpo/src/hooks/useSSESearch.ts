'use client';

import { useState, useCallback, useRef } from 'react';
import type { SearchMessage, Source } from '@/types';

interface SSESearchState {
  messages: SearchMessage[];
  isSearching: boolean;
  statusText: string;
}

export function useSSESearch() {
  const [state, setState] = useState<SSESearchState>({
    messages: [],
    isSearching: false,
    statusText: '',
  });
  const abortRef = useRef<AbortController | null>(null);

  const sendQuery = useCallback(async (query: string, sessionId: string) => {
    if (!query.trim() || state.isSearching) return;

    // Add user message
    const userMsg: SearchMessage = {
      id: `user_${Date.now()}`,
      role: 'user',
      content: query,
    };

    const assistantMsg: SearchMessage = {
      id: `asst_${Date.now()}`,
      role: 'assistant',
      content: '',
      sources: [],
      images: [],
      isStreaming: true,
    };

    setState((prev) => ({
      messages: [...prev.messages, userMsg, assistantMsg],
      isSearching: true,
      statusText: '',
    }));

    abortRef.current = new AbortController();

    try {
      const res = await fetch('/api/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, session_id: sessionId, stream: true }),
        signal: abortRef.current.signal,
      });

      if (!res.body) return;

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split('\n\n');
        buffer = parts.pop() || '';

        for (const part of parts) {
          if (part.startsWith('data: [DONE]')) {
            setState((prev) => ({
              ...prev,
              isSearching: false,
              statusText: '',
              messages: prev.messages.map((m) =>
                m.id === assistantMsg.id ? { ...m, isStreaming: false } : m
              ),
            }));

            // Save to DB
            const lastAssistant = state.messages.find((m) => m.id === assistantMsg.id);
            saveToDB(sessionId, query, assistantMsg.id);
            return;
          }

          const match = part.match(/^data:\s*(.*)$/m);
          if (!match) continue;

          let data;
          try {
            data = JSON.parse(match[1]);
          } catch {
            continue;
          }

          const content = data.choices?.[0]?.delta?.content || '';
          const eventType = data.event_type;

          // Task events (SSE status updates like "Searching the web...")
          if (content.startsWith('<TASK>')) {
            const taskText = content.replace(/<\/?TASK>/g, '');
            if (taskText === 'DONE') {
              setState((prev) => ({
                ...prev,
                isSearching: false,
                statusText: '',
                messages: prev.messages.map((m) =>
                  m.id === assistantMsg.id ? { ...m, isStreaming: false } : m
                ),
              }));
              saveToDB(sessionId, query, assistantMsg.id);
              return;
            }
            setState((prev) => ({ ...prev, statusText: taskText }));
            continue;
          }

          // Parse sources and images from content
          const sourcesMatch = content.match(/\*\*Sources:\*\*([\s\S]*)/);
          const imagesMatch = content.match(/\*\*Related Images:\*\*([\s\S]*)/);

          if (sourcesMatch) {
            const sourcesText = sourcesMatch[1];
            const linkRegex = /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g;
            const sources: Source[] = [];
            let linkMatch;
            while ((linkMatch = linkRegex.exec(sourcesText)) !== null) {
              sources.push({ title: linkMatch[1], url: linkMatch[2] });
            }
            if (sources.length > 0) {
              setState((prev) => ({
                ...prev,
                messages: prev.messages.map((m) =>
                  m.id === assistantMsg.id
                    ? { ...m, sources: [...(m.sources || []), ...sources] }
                    : m
                ),
              }));
            }
            // Also append the non-source part of content
            const mainContent = content.replace(/\*\*Sources:\*\*[\s\S]*/i, '').trim();
            if (mainContent) {
              appendContent(assistantMsg.id, mainContent);
            }
          } else if (imagesMatch) {
            const imagesText = imagesMatch[1];
            const imageUrlRegex = /(https?:\/\/[^\s)]+)/g;
            const images: string[] = [];
            let imageMatch;
            while ((imageMatch = imageUrlRegex.exec(imagesText)) !== null) {
              // Only include images with h= param (as per original filter)
              if (/[?&]h=\w+/i.test(imageMatch[1])) {
                images.push(imageMatch[1]);
              }
            }
            if (images.length > 0) {
              setState((prev) => ({
                ...prev,
                messages: prev.messages.map((m) =>
                  m.id === assistantMsg.id
                    ? { ...m, images: [...(m.images || []), ...images] }
                    : m
                ),
              }));
            }
            const mainContent = content.replace(/\*\*Related Images:\*\*[\s\S]*/i, '').trim();
            if (mainContent) {
              appendContent(assistantMsg.id, mainContent);
            }
          } else if (content.trim()) {
            appendContent(assistantMsg.id, content);
          }
        }
      }

      // Stream ended without [DONE]
      setState((prev) => ({
        ...prev,
        isSearching: false,
        statusText: '',
        messages: prev.messages.map((m) =>
          m.id === assistantMsg.id ? { ...m, isStreaming: false } : m
        ),
      }));
      saveToDB(sessionId, query, assistantMsg.id);
    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'AbortError') return;
      setState((prev) => ({
        ...prev,
        isSearching: false,
        statusText: '',
        messages: prev.messages.map((m) =>
          m.id === assistantMsg.id
            ? { ...m, content: m.content || 'An error occurred. Please try again.', isStreaming: false }
            : m
        ),
      }));
    }
  }, [state.isSearching]);

  const appendContent = (msgId: string, content: string) => {
    setState((prev) => ({
      ...prev,
      messages: prev.messages.map((m) =>
        m.id === msgId ? { ...m, content: m.content + content } : m
      ),
    }));
  };

  const saveToDB = async (sessionId: string, query: string, assistantMsgId: string) => {
    try {
      // Get latest state from ref
      setState((prev) => {
        const assistant = prev.messages.find((m) => m.id === assistantMsgId);
        if (assistant && assistant.content) {
          fetch('/api/conversations', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              sessionId,
              query,
              content: assistant.content,
              sources: assistant.sources,
              images: assistant.images,
            }),
          }).catch(() => {}); // fire and forget
        }
        return prev;
      });
    } catch {
      // ignore DB save errors
    }
  };

  const cancelSearch = useCallback(() => {
    abortRef.current?.abort();
    setState((prev) => ({
      ...prev,
      isSearching: false,
      statusText: '',
      messages: prev.messages.map((m) => (m.isStreaming ? { ...m, isStreaming: false } : m)),
    }));
  }, []);

  const clearMessages = useCallback(() => {
    setState({ messages: [], isSearching: false, statusText: '' });
  }, []);

  return {
    ...state,
    sendQuery,
    cancelSearch,
    clearMessages,
  };
}
