'use client';

import { usePathname } from 'next/navigation';
import { Lock, Plus, MoreHorizontal, Sparkles, Monitor, CreditCard, Palette, Film } from 'lucide-react';
import { useRouter } from 'next/navigation';

const discoverTopics = [
  { name: 'For You', icon: Sparkles, href: '/discover' },
  { name: 'Technology', icon: Monitor, href: '/discover/tech' },
  { name: 'Finance', icon: CreditCard, href: '/discover/finance' },
  { name: 'World Arts', icon: Palette, href: '/discover/arts' },
  { name: 'Entertainment', icon: Film, href: '/discover/entertainment' },
];

interface SidePanelProps {
  recentSearches?: Array<{ id: string; title: string }>;
}

export default function SidePanel({ recentSearches = [] }: SidePanelProps) {
  const pathname = usePathname();
  const router = useRouter();
  const isDiscover = pathname.startsWith('/discover');

  return (
    <aside className="w-[220px] h-full bg-[#1f2121a1] backdrop-blur-[5px] flex flex-col shrink-0 border-r border-[#333]/50">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-4 h-10">
        <p className="text-white text-sm font-medium">{isDiscover ? 'Discover' : 'Home'}</p>
        <Lock size={14} className="text-[#555] cursor-pointer hover:text-white transition-colors" />
      </div>

      <div className="w-[85%] mx-auto h-px bg-[#333] mt-3" />

      {isDiscover ? (
        /* Discover topics */
        <div className="mt-3 px-5">
          <span className="text-[#888] text-xs font-bold">Topics</span>
          <div className="mt-2 flex flex-col gap-1">
            {discoverTopics.map((topic) => (
              <button
                key={topic.name}
                onClick={() => router.push(topic.href)}
                className={`
                  flex items-center gap-2 px-2 py-1.5 rounded-lg text-sm transition-colors
                  ${pathname === topic.href ? 'text-white bg-[#333]' : 'text-[#ccc] hover:text-white hover:bg-[#333]'}
                `}
              >
                <topic.icon size={14} />
                <span className="truncate">{topic.name}</span>
              </button>
            ))}
          </div>
        </div>
      ) : (
        /* Library & Pages */
        <>
          <div className="mt-3 px-5">
            <div className="flex items-center justify-between">
              <span className="text-[#888] text-xs font-bold">Library</span>
              <Plus size={14} className="text-white cursor-pointer hover:bg-[#222] rounded p-0.5" />
            </div>
            <div className="mt-2 flex flex-col gap-1">
              {recentSearches.length > 0 ? (
                recentSearches.map((s) => (
                  <div
                    key={s.id}
                    className="flex items-center justify-between px-2 py-1 rounded-lg text-sm text-[#ccc] hover:text-white hover:bg-[#333] cursor-pointer transition-colors"
                  >
                    <span className="truncate">{s.title}</span>
                    <MoreHorizontal size={14} className="shrink-0 opacity-0 group-hover:opacity-100" />
                  </div>
                ))
              ) : (
                <p className="text-[#555] text-xs px-2">No recent searches</p>
              )}
            </div>
          </div>

          <div className="w-[85%] mx-auto h-px bg-[#333] mt-4" />

          <div className="mt-3 px-5">
            <div className="flex items-center justify-between">
              <span className="text-[#888] text-xs font-bold">Pages</span>
              <Plus size={14} className="text-white cursor-pointer hover:bg-[#222] rounded p-0.5" />
            </div>
            <div className="mt-2 flex flex-col gap-1">
              <div className="flex items-center justify-between px-2 py-1 rounded-lg text-sm text-[#ccc] hover:text-white hover:bg-[#333] cursor-pointer transition-colors">
                <span className="truncate">Bike Racing</span>
              </div>
              <div className="flex items-center justify-between px-2 py-1 rounded-lg text-sm text-[#ccc] hover:text-white hover:bg-[#333] cursor-pointer transition-colors">
                <span className="truncate">OS Writeup</span>
              </div>
            </div>
          </div>
        </>
      )}
    </aside>
  );
}
