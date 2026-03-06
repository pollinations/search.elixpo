'use client';

import dynamic from 'next/dynamic';

const LibraryContent = dynamic(() => import('@/components/LibraryContent'), { ssr: false });

export default function LibraryPage() {
  return <LibraryContent />;
}
