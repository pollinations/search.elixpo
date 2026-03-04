'use client';

import { TrendingUp, Sparkles, Monitor, CreditCard, Palette, Film, Trophy } from 'lucide-react';
import GlassCard from '@/components/ui/GlassCard';
import { useRouter } from 'next/navigation';

const categories = [
  { name: 'Technology', icon: Monitor, color: 'text-lime-main', href: '/discover/tech', count: 42 },
  { name: 'Finance', icon: CreditCard, color: 'text-honey-main', href: '/discover/finance', count: 28 },
  { name: 'Sports', icon: Trophy, color: 'text-sage-main', href: '/discover/sports', count: 35 },
  { name: 'Entertainment', icon: Film, color: 'text-lavender-main', href: '/discover/entertainment', count: 19 },
  { name: 'Arts & Culture', icon: Palette, color: 'text-[#f87171]', href: '/discover/arts', count: 15 },
];

const trendingTopics = [
  { title: 'AI breakthroughs in protein folding', category: 'Technology', time: '2h ago' },
  { title: 'Global markets react to rate decision', category: 'Finance', time: '4h ago' },
  { title: 'Major space telescope discovers new exoplanets', category: 'Science', time: '6h ago' },
  { title: 'Open-source LLM achieves new benchmarks', category: 'Technology', time: '8h ago' },
  { title: 'Renewable energy surpasses fossil fuels', category: 'Environment', time: '12h ago' },
  { title: 'New cybersecurity threats emerge from quantum computing', category: 'Technology', time: '1d ago' },
];

export default function DiscoverHub() {
  const router = useRouter();

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-white font-display flex items-center gap-3">
          <Sparkles size={28} className="text-lime-main" />
          Discover
        </h1>
        <p className="text-txt-muted mt-2">Explore trending topics and curated content</p>
      </div>

      {/* Categories grid */}
      <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4">
        {categories.map((cat) => (
          <GlassCard
            key={cat.name}
            hover
            onClick={() => router.push(cat.href)}
            className="p-4 flex flex-col items-center text-center gap-3"
          >
            <cat.icon size={28} className={cat.color} />
            <span className="text-white text-sm font-medium">{cat.name}</span>
            <span className="text-txt-muted text-xs">{cat.count} topics</span>
          </GlassCard>
        ))}
      </div>

      {/* Trending */}
      <div>
        <h2 className="text-lg font-semibold text-white font-display flex items-center gap-2 mb-4">
          <TrendingUp size={20} className="text-honey-main" />
          Trending Now
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {trendingTopics.map((topic, i) => (
            <GlassCard key={i} hover className="p-4">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-white text-sm font-medium leading-snug">{topic.title}</p>
                  <div className="flex items-center gap-2 mt-2">
                    <span className="text-xs px-2 py-0.5 rounded-full bg-bg-card-glass text-txt-muted border border-bdr-light">
                      {topic.category}
                    </span>
                    <span className="text-xs text-txt-subtle">{topic.time}</span>
                  </div>
                </div>
              </div>
            </GlassCard>
          ))}
        </div>
      </div>
    </div>
  );
}
