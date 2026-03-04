'use client';

import { Search, Plus, Home, Globe, BookOpen } from 'lucide-react';
import { usePathname, useRouter } from 'next/navigation';
import IconButton from '@/components/ui/IconButton';

interface SidebarProps {
  onNewSearch: () => void;
}

export default function Sidebar({ onNewSearch }: SidebarProps) {
  const pathname = usePathname();
  const router = useRouter();

  const isActive = (path: string) => pathname === path;

  return (
    <aside className="w-[60px] h-full bg-[#18191a] border-r border-[#333] flex flex-col items-center py-6 shrink-0">
      <div className="w-5 h-5 mb-8 opacity-80">
        <svg viewBox="0 0 24 24" fill="none" className="w-full h-full invert">
          <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2" />
          <path d="M12 6v12M6 12h12" stroke="currentColor" strokeWidth="2" />
        </svg>
      </div>

      <div className="flex flex-col items-center gap-4">
        <IconButton
          icon={Plus}
          onClick={onNewSearch}
          title="New Search"
          variant="default"
          className="rounded-full"
        />

        <div className="w-8 h-px bg-[#333] my-2" />

        <IconButton
          icon={Home}
          onClick={() => router.push('/')}
          active={isActive('/')}
          title="Home"
          variant="ghost"
        />
        <IconButton
          icon={Globe}
          onClick={() => router.push('/discover')}
          active={isActive('/discover')}
          title="Discover"
          variant="ghost"
        />
        <IconButton
          icon={BookOpen}
          onClick={() => router.push('/library')}
          active={isActive('/library')}
          title="Library"
          variant="ghost"
        />
      </div>
    </aside>
  );
}
