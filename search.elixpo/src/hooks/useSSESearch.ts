'use client';

import { useState, useCallback, useRef } from 'react';
import type { SearchMessage, Source } from '@/types';
import { setCachedConversation, markCachedAsSaved } from '@/lib/conversationCache';

interface SSESearchState {
  messages: SearchMessage[];
  isSearching: boolean;
  statusText: string;
}

function persistMessages(sessionId: string | null, messages: SearchMessage[]) {
  if (sessionId && messages.length > 0) {
    setCachedConversation(sessionId, messages);
  }
}

export function useSSESearch() {
  const [state, setState] = useState<SSESearchState>({
    messages: [],
    isSearching: false,
    statusText: '',
  });
  const abortRef = useRef<AbortController | null>(null);
  const sessionRef = useRef<string | null>(null);

  // Allow setting initial messages (loaded from cache/DB)
  const setMessages = useCallback((messages: SearchMessage[]) => {
    setState((prev) => ({ ...prev, messages }));
  }, []);

  const sendQuery = useCallback(async (query: string, sessionId: string) => {
    if (!query.trim() || state.isSearching) return;
    sessionRef.current = sessionId;

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

    const newMessages = [...state.messages, userMsg, assistantMsg];
    setState({
      messages: newMessages,
      isSearching: true,
      statusText: '',
    });
    persistMessages(sessionId, newMessages);

    abortRef.current = new AbortController();

    try {
      const res = await fetch('/api/search', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-xid': process.env.NEXT_PUBLIC_XID || '',
        },
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
            setState((prev) => {
              const updated = {
                ...prev,
                isSearching: false,
                statusText: '',
                messages: prev.messages.map((m) =>
                  m.id === assistantMsg.id ? { ...m, isStreaming: false } : m
                ),
              };
              persistMessages(sessionId, updated.messages);
              return updated;
            });
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

          if (content.startsWith('<TASK>')) {
            const taskText = content.replace(/<\/?TASK>/g, '');
            if (taskText === 'DONE') {
              setState((prev) => {
                const updated = {
                  ...prev,
                  isSearching: false,
                  statusText: '',
                  messages: prev.messages.map((m) =>
                    m.id === assistantMsg.id ? { ...m, isStreaming: false } : m
                  ),
                };
                persistMessages(sessionId, updated.messages);
                return updated;
              });
              saveToDB(sessionId, query, assistantMsg.id);
              return;
            }
            setState((prev) => ({ ...prev, statusText: taskText }));
            continue;
          }

          // Check for images first (non-greedy) to avoid sources regex eating image section
          const imagesMatch = content.match(/\*\*(?:Related|Similar) Images:\*\*([\s\S]*)/);
          // Sources regex stops before any image section
          const sourcesMatch = content.match(/\*\*Sources:\*\*([\s\S]*?)(?=\*\*(?:Related|Similar) Images:\*\*|$)/);

          if (imagesMatch) {
            const imagesText = imagesMatch[1];
            const imageUrlRegex = /(https?:\/\/[^\s)]+)/g;
            const images: string[] = [];
            let imageMatch;
            while ((imageMatch = imageUrlRegex.exec(imagesText)) !== null) {
              images.push(imageMatch[1]);
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
          }

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
          }

          if (sourcesMatch || imagesMatch) {
            const mainContent = content
              .replace(/\*\*Sources:\*\*[\s\S]*?(?=\*\*(?:Related|Similar) Images:\*\*|$)/i, '')
              .replace(/\*\*(?:Related|Similar) Images:\*\*[\s\S]*/i, '')
              .trim();
            if (mainContent) {
              appendContent(assistantMsg.id, mainContent, sessionId);
            }
          } else if (content.trim()) {
            appendContent(assistantMsg.id, content, sessionId);
          }
        }
      }

      // Stream ended without [DONE]
      setState((prev) => {
        const updated = {
          ...prev,
          isSearching: false,
          statusText: '',
          messages: prev.messages.map((m) =>
            m.id === assistantMsg.id ? { ...m, isStreaming: false } : m
          ),
        };
        persistMessages(sessionId, updated.messages);
        return updated;
      });
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

  const appendContent = (msgId: string, content: string, sessionId: string) => {
    setState((prev) => {
      const updated = {
        ...prev,
        messages: prev.messages.map((m) =>
          m.id === msgId ? { ...m, content: m.content + content } : m
        ),
      };
      // Persist every ~5 updates to avoid thrashing localStorage
      // We do a simple check: persist when content length crosses 500-char boundaries
      const msg = updated.messages.find((m) => m.id === msgId);
      if (msg && msg.content.length % 500 < content.length) {
        persistMessages(sessionId, updated.messages);
      }
      return updated;
    });
  };

  const saveToDB = async (sessionId: string, query: string, assistantMsgId: string) => {
    try {
      setState((prev) => {
        const assistant = prev.messages.find((m) => m.id === assistantMsgId);
        if (assistant && assistant.content) {
          fetch('/api/conversations', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'x-xid': process.env.NEXT_PUBLIC_XID || '',
            },
            body: JSON.stringify({
              sessionId,
              query,
              content: assistant.content,
              sources: assistant.sources,
              images: assistant.images,
            }),
          })
            .then(() => markCachedAsSaved(sessionId))
            .catch(() => {});
        }
        return prev;
      });
    } catch {
      // ignore
    }
  };

  const cancelSearch = useCallback(() => {
    abortRef.current?.abort();
    setState((prev) => {
      const updated = {
        ...prev,
        isSearching: false,
        statusText: '',
        messages: prev.messages.map((m) => (m.isStreaming ? { ...m, isStreaming: false } : m)),
      };
      if (sessionRef.current) {
        persistMessages(sessionRef.current, updated.messages);
      }
      return updated;
    });
  }, []);

  const clearMessages = useCallback(() => {
    setState({ messages: [], isSearching: false, statusText: '' });
  }, []);

  return {
    ...state,
    sendQuery,
    cancelSearch,
    clearMessages,
    setMessages,
  };
}
