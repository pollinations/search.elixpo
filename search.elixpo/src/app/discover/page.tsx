'use client';

import dynamic from 'next/dynamic';

const DiscoverContent = dynamic(() => import('@/components/DiscoverContent'), { ssr: false });

export default function DiscoverPage() {
  return <DiscoverContent />;
}
