'use client';

import { useEffect, useState } from 'react';
import { MessageSquare, Clock, Trash2 } from 'lucide-react';
import type { ConversationSession } from '@/types';
import GlassCard from '@/components/ui/GlassCard';

export default function ConversationList() {
  const [sessions, setSessions] = useState<ConversationSession[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const clientId = localStorage.getItem('elixpo_client_id') || 'anonymous';
    fetch(`/api/conversations?clientId=${encodeURIComponent(clientId)}`)
      .then((r) => r.json())
      .then((data) => {
        if (Array.isArray(data)) setSessions(data);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-40">
        <p className="text-txt-muted text-sm">Loading conversations...</p>
      </div>
    );
  }

  if (!sessions.length) {
    return (
      <div className="flex flex-col items-center justify-center h-60 text-center">
        <MessageSquare size={40} className="text-[#444] mb-4" />
        <p className="text-txt-secondary text-lg font-medium">No saved conversations</p>
        <p className="text-txt-muted text-sm mt-1">Your search conversations will appear here</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {sessions.map((session) => (
        <GlassCard key={session.id} hover className="p-4">
          <div className="flex items-start justify-between">
            <div className="flex-1 min-w-0">
              <h3 className="text-white font-medium text-sm truncate">
                {session.title || 'Untitled conversation'}
              </h3>
              <div className="flex items-center gap-3 mt-2 text-txt-muted text-xs">
                <span className="flex items-center gap-1">
                  <Clock size={12} />
                  {new Date(session.updatedAt).toLocaleDateString()}
                </span>
                <span className="flex items-center gap-1">
                  <MessageSquare size={12} />
                  {session.messageCount || 0} messages
                </span>
              </div>
            </div>
            <button className="p-1.5 text-[#555] hover:text-red-400 transition-colors rounded hover:bg-[#333]">
              <Trash2 size={14} />
            </button>
          </div>
        </GlassCard>
      ))}
    </div>
  );
}
