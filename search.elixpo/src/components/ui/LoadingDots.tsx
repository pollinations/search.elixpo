'use client';

export default function LoadingDots({ text }: { text?: string }) {
  return (
    <div className="flex items-center gap-2">
      <svg className="animate-sparkle w-5 h-5 text-txt-muted" viewBox="0 0 24 24" fill="currentColor">
        <path d="M12 2L13.09 8.26L18 6L15.74 10.91L22 12L15.74 13.09L18 18L13.09 15.74L12 22L10.91 15.74L6 18L8.26 13.09L2 12L8.26 10.91L6 6L10.91 8.26L12 2Z" />
      </svg>
      <span className="text-txt-muted text-sm loading-dots">{text || 'Thinking'}</span>
    </div>
  );
}
