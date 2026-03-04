'use client';

import Sidebar from '@/components/layout/Sidebar';
import SidePanel from '@/components/layout/SidePanel';
import DiscoverHub from '@/components/discover/DiscoverHub';
import { useRouter } from 'next/navigation';

export default function DiscoverPage() {
  const router = useRouter();

  return (
    <div className="h-screen flex bg-[#18191a]">
      <Sidebar onNewSearch={() => router.push('/')} />
      <SidePanel />

      <main className="flex-1 flex flex-col h-full overflow-hidden">
        <div className="flex-1 overflow-y-auto custom-scrollbar p-8">
          <div className="max-w-4xl mx-auto">
            <DiscoverHub />
          </div>
        </div>
      </main>
    </div>
  );
}
