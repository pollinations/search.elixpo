'use client';

import Sidebar from '@/components/layout/Sidebar';
import SidePanel from '@/components/layout/SidePanel';
import ConversationList from '@/components/library/ConversationList';
import { useRouter } from 'next/navigation';

export default function LibraryContent() {
  const router = useRouter();

  return (
    <div className="h-screen flex bg-[#18191a]">
      <Sidebar onNewSearch={() => router.push('/')} />
      <SidePanel />

      <main className="flex-1 flex flex-col h-full overflow-hidden">
        <div className="flex-1 overflow-y-auto custom-scrollbar p-8">
          <div className="max-w-3xl mx-auto">
            <h1 className="text-2xl font-bold text-white font-display mb-6">Library</h1>
            <ConversationList />
          </div>
        </div>
      </main>
    </div>
  );
}
