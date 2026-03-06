'use client';

import dynamic from 'next/dynamic';

const DiscoverCategoryContent = dynamic(() => import('@/components/DiscoverCategoryContent'), { ssr: false });

export default function DiscoverCategoryPage() {
  return <DiscoverCategoryContent />;
}
