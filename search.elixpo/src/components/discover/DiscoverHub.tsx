'use client';

import { useEffect, useState } from 'react';
import { TrendingUp, Sparkles, Monitor, CreditCard, Palette, Film, Trophy } from 'lucide-react';
import GlassCard from '@/components/ui/GlassCard';
import { useRouter } from 'next/navigation';

interface DiscoverArticle {
  id: string;
  category: string;
  title: string;
  excerpt: string;
  sourceUrl?: string;
  sourceTitle?: string;
  generatedAt: string;
}

const categories = [
  { name: 'Technology', slug: 'tech', icon: Monitor, color: 'text-lime-main', href: '/discover/tech' },
  { name: 'Finance', slug: 'finance', icon: CreditCard, color: 'text-honey-main', href: '/discover/finance' },
  { name: 'Sports', slug: 'sports', icon: Trophy, color: 'text-sage-main', href: '/discover/sports' },
  { name: 'Entertainment', slug: 'entertainment', icon: Film, color: 'text-lavender-main', href: '/discover/entertainment' },
  { name: 'Arts & Culture', slug: 'arts', icon: Palette, color: 'text-[#f87171]', href: '/discover/arts' },
];

const fallbackTopics = [
  { title: 'AI breakthroughs in protein folding', category: 'Technology', time: '2h ago' },
  { title: 'Global markets react to rate decision', category: 'Finance', time: '4h ago' },
  { title: 'Major space telescope discovers new exoplanets', category: 'Science', time: '6h ago' },
  { title: 'Open-source LLM achieves new benchmarks', category: 'Technology', time: '8h ago' },
  { title: 'Renewable energy surpasses fossil fuels', category: 'Environment', time: '12h ago' },
  { title: 'New cybersecurity threats emerge from quantum computing', category: 'Technology', time: '1d ago' },
];

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const hours = Math.floor(diff / 3600000);
  if (hours < 1) return 'just now';
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

const categoryNameMap: Record<string, string> = {
  tech: 'Technology',
  finance: 'Finance',
  sports: 'Sports',
  entertainment: 'Entertainment',
  arts: 'Arts & Culture',
};

export default function DiscoverHub() {
  const router = useRouter();
  const [trending, setTrending] = useState<DiscoverArticle[]>([]);
  const [categoryCounts, setCategoryCounts] = useState<Record<string, number>>({});
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    fetch('/api/discover')
      .then((r) => r.json())
      .then((articles: DiscoverArticle[]) => {
        if (Array.isArray(articles) && articles.length > 0) {
          setTrending(articles.slice(0, 6));
          const counts: Record<string, number> = {};
          articles.forEach((a) => {
            counts[a.category] = (counts[a.category] || 0) + 1;
          });
          setCategoryCounts(counts);
        }
        setLoaded(true);
      })
      .catch(() => setLoaded(true));
  }, []);

  const displayTopics = trending.length > 0
    ? trending.map((a) => ({
        title: a.title,
        category: categoryNameMap[a.category] || a.category,
        time: timeAgo(a.generatedAt),
        url: a.sourceUrl,
      }))
    : fallbackTopics.map((t) => ({ ...t, url: undefined }));

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-white font-display flex items-center gap-3">
          <Sparkles size={28} className="text-lime-main" />
          Discover
        </h1>
        <p className="text-txt-muted mt-2">Explore trending topics and curated content</p>
      </div>

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
            <span className="text-txt-muted text-xs">
              {categoryCounts[cat.slug] || 0} articles
            </span>
          </GlassCard>
        ))}
      </div>

      <div>
        <h2 className="text-lg font-semibold text-white font-display flex items-center gap-2 mb-4">
          <TrendingUp size={20} className="text-honey-main" />
          Trending Now
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {displayTopics.map((topic, i) => (
            <GlassCard
              key={i}
              hover
              onClick={topic.url ? () => window.open(topic.url!, '_blank') : undefined}
              className="p-4"
            >
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
        {!loaded && (
          <p className="text-txt-subtle text-sm text-center mt-4">Loading...</p>
        )}
      </div>
    </div>
  );
}
