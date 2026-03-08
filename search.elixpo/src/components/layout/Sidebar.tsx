'use client';

import { useState, useRef, useEffect } from 'react';
import {
  Plus, Home, Globe, BookOpen, TrendingUp, MoreHorizontal,
  LogIn, LogOut, User, Bell,
} from 'lucide-react';
import { usePathname, useRouter } from 'next/navigation';
import { useAuth } from '@/hooks/useAuth';

interface SidebarProps {
  onNewSearch: () => void;
}

interface RecentSession {
  id: string;
  title: string | null;
  updatedAt: string;
}

const moreItems = [
  { label: 'Travel', icon: Globe, href: '/discover/travel' },
  { label: 'Academic', icon: BookOpen, href: '/discover/academic' },
  { label: 'Patents', icon: TrendingUp, href: '/discover/patents' },
];

export default function Sidebar({ onNewSearch }: SidebarProps) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, loading, login, logout } = useAuth();
  const [recents, setRecents] = useState<RecentSession[]>([]);
  const [menuOpen, setMenuOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const moreRef = useRef<HTMLDivElement>(null);

  const isActive = (path: string) =>
    path === '/' ? pathname === '/' : pathname.startsWith(path);

  // Fetch recent searches
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const clientId = window.localStorage.getItem('elixpo_client_id') || '';
    if (!clientId) return;
    fetch(`/api/conversations?clientId=${encodeURIComponent(clientId)}&limit=8`)
      .then((r) => r.json())
      .then((data) => {
        if (Array.isArray(data)) setRecents(data);
      })
      .catch(() => {});
  }, []);

  // Close dropdowns on outside click
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
      if (moreRef.current && !moreRef.current.contains(e.target as Node)) setMoreOpen(false);
    }
    if (menuOpen || moreOpen) document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [menuOpen, moreOpen]);

  return (
    <aside className="w-[240px] h-full bg-[#171717] flex flex-col shrink-0 border-r border-[#2a2b2d]">
      {/* New Thread */}
      <div className="px-3 pt-4 pb-2">
        <button
          onClick={onNewSearch}
          className="w-full flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-sm text-[#ccc] hover:text-white hover:bg-[#2a2b2d] transition-colors"
        >
          <Plus size={18} />
          <span>New Thread</span>
        </button>
      </div>

      {/* Navigation */}
      <nav className="px-3 flex flex-col gap-0.5">
        <NavItem icon={Home} label="Home" href="/" active={isActive('/')} onClick={() => router.push('/')} />
        <NavItem icon={BookOpen} label="History" href="/library" active={isActive('/library')} onClick={() => router.push('/library')} />
        <NavItem icon={Globe} label="Discover" href="/discover" active={isActive('/discover')} onClick={() => router.push('/discover')} />
        <NavItem icon={TrendingUp} label="Finance" href="/discover/finance" active={isActive('/discover/finance')} onClick={() => router.push('/discover/finance')} />

        {/* More with popover */}
        <div className="relative" ref={moreRef}>
          <button
            onClick={() => setMoreOpen(!moreOpen)}
            className={`
              w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-sm transition-colors
              ${moreOpen ? 'text-white bg-[#2a2b2d]' : 'text-[#999] hover:text-white hover:bg-[#222]'}
            `}
          >
            <MoreHorizontal size={18} />
            <span>More</span>
          </button>

          {moreOpen && (
            <div className="absolute left-full top-0 ml-1 w-44 bg-[#232425] border border-[#333] rounded-xl shadow-card-lg py-1.5 z-50">
              {moreItems.map((item) => (
                <button
                  key={item.label}
                  onClick={() => { setMoreOpen(false); router.push(item.href); }}
                  className="w-full flex items-center gap-2.5 px-4 py-2 text-sm text-[#ccc] hover:text-white hover:bg-[#2a2b2d] transition-colors"
                >
                  <item.icon size={15} />
                  {item.label}
                </button>
              ))}
            </div>
          )}
        </div>
      </nav>

      {/* Divider */}
      <div className="mx-4 my-3 h-px bg-[#2a2b2d]" />

      {/* Recent searches */}
      <div className="flex-1 overflow-y-auto custom-scrollbar px-3">
        <p className="px-3 text-[#666] text-xs font-medium mb-2">Recent</p>
        <div className="flex flex-col gap-0.5">
          {recents.length > 0 ? (
            recents.map((s) => (
              <button
                key={s.id}
                onClick={() => router.push(`/c/${s.id}`)}
                className={`
                  w-full flex items-center gap-2.5 px-3 py-1.5 rounded-lg text-sm transition-colors text-left
                  ${pathname === `/c/${s.id}`
                    ? 'text-white bg-[#2a2b2d]'
                    : 'text-[#999] hover:text-white hover:bg-[#222]'}
                `}
              >
                <span className="truncate flex-1">{s.title || 'Untitled'}</span>
              </button>
            ))
          ) : (
            <p className="px-3 text-[#444] text-xs">No recent searches</p>
          )}
        </div>
      </div>

      {/* Bottom: user section */}
      <div className="px-3 pb-4 pt-2 border-t border-[#2a2b2d] relative" ref={menuRef}>
        {!loading && (
          user ? (
            <button
              onClick={() => setMenuOpen(!menuOpen)}
              className="w-full flex items-center gap-2.5 px-2 py-2 rounded-xl hover:bg-[#222] transition-colors"
            >
              <div className="w-8 h-8 rounded-full overflow-hidden shrink-0">
                {user.avatar ? (
                  <img src={user.avatar} alt="" className="w-full h-full object-cover" />
                ) : (
                  <div className="w-full h-full bg-[#333] flex items-center justify-center text-white text-xs font-medium">
                    {(user.displayName || user.email)[0].toUpperCase()}
                  </div>
                )}
              </div>
              <span className="text-sm text-[#ccc] truncate flex-1 text-left">
                {user.displayName || user.email.split('@')[0]}
              </span>
              <Bell size={15} className="text-[#666] shrink-0" />
            </button>
          ) : (
            <button
              onClick={() => login(pathname)}
              className="w-full flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-sm text-[#999] hover:text-white hover:bg-[#222] transition-colors"
            >
              <LogIn size={18} />
              <span>Sign in</span>
            </button>
          )
        )}

        {/* User dropdown */}
        {menuOpen && user && (
          <div className="absolute bottom-full left-3 right-3 mb-1 bg-[#232425] border border-[#333] rounded-xl shadow-card-lg py-1.5 z-50">
            <div className="flex items-center gap-2.5 px-4 py-2.5 border-b border-[#2a2b2d]">
              <div className="w-8 h-8 rounded-full overflow-hidden shrink-0">
                {user.avatar ? (
                  <img src={user.avatar} alt="" className="w-full h-full object-cover" />
                ) : (
                  <div className="w-full h-full bg-[#333] flex items-center justify-center text-white text-xs font-medium">
                    {(user.displayName || user.email)[0].toUpperCase()}
                  </div>
                )}
              </div>
              <div className="min-w-0">
                <p className="text-white text-sm font-medium truncate">{user.displayName || 'User'}</p>
                <p className="text-[#666] text-xs truncate">{user.email}</p>
              </div>
            </div>
            <button
              onClick={() => { setMenuOpen(false); router.push('/profile'); }}
              className="w-full flex items-center gap-2.5 px-4 py-2 text-sm text-[#ccc] hover:text-white hover:bg-[#2a2b2d] transition-colors"
            >
              <User size={15} />
              Profile & Settings
            </button>
            <div className="h-px bg-[#2a2b2d] mx-3" />
            <button
              onClick={() => { setMenuOpen(false); logout(); }}
              className="w-full flex items-center gap-2.5 px-4 py-2 text-sm text-red-400 hover:text-red-300 hover:bg-[#2a2b2d] transition-colors"
            >
              <LogOut size={15} />
              Sign out
            </button>
          </div>
        )}
      </div>
    </aside>
  );
}

function NavItem({ icon: Icon, label, active, onClick }: {
  icon: typeof Home; label: string; href: string; active: boolean; onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`
        w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-sm transition-colors
        ${active ? 'text-white bg-[#2a2b2d]' : 'text-[#999] hover:text-white hover:bg-[#222]'}
      `}
    >
      <Icon size={18} />
      <span>{label}</span>
    </button>
  );
}
