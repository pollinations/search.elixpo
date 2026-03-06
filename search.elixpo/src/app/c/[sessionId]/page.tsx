'use client';

import dynamic from 'next/dynamic';
import { useParams } from 'next/navigation';

const HomeContent = dynamic(() => import('@/components/HomeContent'), { ssr: false });

export default function ConversationPage() {
  const params = useParams<{ sessionId: string }>();
  return <HomeContent initialSessionId={params.sessionId} />;
}
