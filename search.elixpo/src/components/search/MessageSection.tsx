'use client';

import type { SearchMessage } from '@/types';
import StreamingText from './StreamingText';
import SourceCards from './SourceCards';
import ImageGallery from './ImageGallery';
import LoadingDots from '@/components/ui/LoadingDots';

interface MessageSectionProps {
  userMessage: SearchMessage;
  assistantMessage: SearchMessage;
  statusText?: string;
}

export default function MessageSection({ userMessage, assistantMessage, statusText }: MessageSectionProps) {
  const showLoader = assistantMessage.isStreaming && !assistantMessage.content;

  return (
    <section className="flex flex-col items-start mt-8 w-full">
      {/* User query */}
      <div className="font-bold text-[1.8em] text-white break-words font-display leading-tight">
        <p>{userMessage.content}</p>
      </div>

      {/* Loading state */}
      {showLoader && (
        <div className="mt-4">
          <LoadingDots text={statusText || 'Searching'} />
        </div>
      )}

      {/* Status text during streaming */}
      {assistantMessage.isStreaming && assistantMessage.content && statusText && (
        <div className="mt-3 mb-2">
          <LoadingDots text={statusText} />
        </div>
      )}

      {/* Response content */}
      {assistantMessage.content && (
        <div className="mt-4 w-full">
          <StreamingText
            content={assistantMessage.content}
            isStreaming={assistantMessage.isStreaming}
          />
        </div>
      )}

      {/* Sources */}
      {(assistantMessage.sources?.length ?? 0) > 0 && (
        <SourceCards sources={assistantMessage.sources!} />
      )}

      {/* Images */}
      {(assistantMessage.images?.length ?? 0) > 0 && (
        <ImageGallery images={assistantMessage.images!} />
      )}
    </section>
  );
}
