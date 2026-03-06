'use client';

import { useParams } from 'next/navigation';
import Sidebar from '@/components/layout/Sidebar';
import SidePanel from '@/components/layout/SidePanel';
import CategoryPage from '@/components/discover/CategoryPage';
import { useRouter } from 'next/navigation';

export default function DiscoverCategoryContent() {
  const params = useParams();
  const router = useRouter();
  const category = params.category as string;

  return (
    <div className="h-screen flex bg-[#18191a]">
      <Sidebar onNewSearch={() => router.push('/')} />
      <SidePanel />

      <main className="flex-1 flex flex-col h-full overflow-hidden">
        <div className="flex-1 overflow-y-auto custom-scrollbar p-8">
          <div className="max-w-3xl mx-auto">
            <CategoryPage category={category} />
          </div>
        </div>
      </main>
    </div>
  );
}
