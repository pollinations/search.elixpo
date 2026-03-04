export interface ParsedSSEEvent {
  eventType: string | null;
  data: string | null;
}

export function parseSSEChunk(chunk: string): ParsedSSEEvent[] {
  const events: ParsedSSEEvent[] = [];
  const parts = chunk.split('\n\n');

  for (const part of parts) {
    if (!part.trim()) continue;

    if (part.startsWith('data: [DONE]')) {
      events.push({ eventType: 'done', data: null });
      continue;
    }

    const match = part.match(/^data:\s*(.*)$/m);
    if (match) {
      try {
        const parsed = JSON.parse(match[1]);
        events.push({
          eventType: parsed.event_type || null,
          data: parsed.choices?.[0]?.delta?.content || null,
        });
      } catch {
        // skip malformed lines
      }
    }
  }

  return events;
}
