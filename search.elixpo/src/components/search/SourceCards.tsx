'use client';

import { BookOpen, ExternalLink } from 'lucide-react';
import type { Source } from '@/types';

interface SourceCardsProps {
  sources: Source[];
}

export default function SourceCards({ sources }: SourceCardsProps) {
  if (!sources.length) return null;

  return (
    <div className="mt-4">
      <div className="flex items-center gap-2 mb-3 text-[#888]">
        <BookOpen size={16} />
        <span className="text-sm">Sources</span>
      </div>
      <div className="flex gap-3 overflow-x-auto no-scrollbar pb-2">
        {sources.map((source, i) => {
          let domain = '';
          try {
            domain = new URL(source.url).hostname;
          } catch {
            domain = '';
          }
          return (
            <a
              key={i}
              href={source.url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex-shrink-0 w-[240px] h-[110px] bg-[#222] rounded-xl py-3 px-3 flex flex-col justify-between hover:bg-[#2a2a2a] cursor-pointer transition-colors border border-transparent hover:border-bdr-light group"
            >
              <div className="flex items-center gap-2 w-full">
                <img
                  src={`https://www.google.com/s2/favicons?domain=${domain}&sz=32`}
                  alt=""
                  className="w-4 h-4 rounded"
                />
                <span className="text-[#ccc] text-xs truncate flex-1">{domain}</span>
                <ExternalLink size={12} className="text-[#555] opacity-0 group-hover:opacity-100 transition-opacity" />
              </div>
              <p className="text-white text-sm line-clamp-3 mt-2 leading-snug">
                {source.title || source.description || domain}
              </p>
            </a>
          );
        })}
      </div>
    </div>
  );
}
