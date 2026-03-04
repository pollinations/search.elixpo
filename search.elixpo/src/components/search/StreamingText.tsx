'use client';

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface StreamingTextProps {
  content: string;
  isStreaming?: boolean;
}

export default function StreamingText({ content, isStreaming }: StreamingTextProps) {
  if (!content && isStreaming) {
    return null;
  }

  return (
    <div className="prose-elixpo text-white break-words text-[1.1em] leading-relaxed">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
      {isStreaming && (
        <span className="inline-block w-2 h-5 bg-lime-main ml-1 animate-pulse rounded-sm" />
      )}
    </div>
  );
}
