'use client';

import { ImageIcon } from 'lucide-react';

interface ImageGalleryProps {
  images: string[];
}

export default function ImageGallery({ images }: ImageGalleryProps) {
  if (!images.length) return null;

  return (
    <div className="mt-4">
      <div className="flex items-center gap-2 mb-3 text-[#888]">
        <ImageIcon size={16} />
        <span className="text-sm">Images</span>
      </div>
      <div className="flex gap-3 overflow-x-auto no-scrollbar pb-2">
        {images.map((url, i) => (
          <a
            key={i}
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex-shrink-0"
          >
            <img
              src={url}
              alt={`Result ${i + 1}`}
              className="h-[150px] w-[150px] rounded-xl object-cover bg-[#222] border border-bdr-light hover:border-bdr-hover transition-colors"
              loading="lazy"
            />
          </a>
        ))}
      </div>
    </div>
  );
}
