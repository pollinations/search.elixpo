export interface Source {
  title: string;
  url: string;
  description?: string;
  favicon?: string;
}

export interface SearchMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: Source[];
  images?: string[];
  isStreaming?: boolean;
}

export interface SSEEvent {
  event_type: string;
  content: string;
  choices?: Array<{
    index: number;
    delta: { role: string; content: string };
    finish_reason: string | null;
  }>;
}

export interface ConversationSession {
  id: string;
  title: string | null;
  createdAt: string;
  updatedAt: string;
  messageCount?: number;
}
