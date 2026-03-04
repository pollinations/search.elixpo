'use client';

import { useEffect, useState } from 'react';
import { ArrowLeft, ExternalLink } from 'lucide-react';
import { useRouter } from 'next/navigation';
import GlassCard from '@/components/ui/GlassCard';

interface DiscoverArticle {
  id: string;
  category: string;
  title: string;
  excerpt: string;
  sourceUrl?: string;
  sourceTitle?: string;
  generatedAt: string;
}

const placeholderArticles: Record<string, Array<{ title: string; excerpt: string; time: string }>> = {
  tech: [
    { title: 'The Rise of Multimodal AI Models', excerpt: 'How vision-language models are transforming industries from healthcare to creative arts.', time: '3h ago' },
    { title: 'WebAssembly 3.0 Draft Specification Released', excerpt: 'The new spec introduces garbage collection and improved interop with JavaScript.', time: '5h ago' },
    { title: 'Quantum Computing Achieves Error Correction Milestone', excerpt: 'Researchers demonstrate fault-tolerant quantum computation with logical qubits.', time: '8h ago' },
  ],
  finance: [
    { title: 'Central Banks Signal Rate Pivot', excerpt: 'Major economies prepare for coordinated monetary policy shifts as inflation cools.', time: '2h ago' },
    { title: 'DeFi Protocol Reaches $100B TVL Milestone', excerpt: 'Decentralized finance continues its institutional adoption trajectory.', time: '6h ago' },
  ],
  sports: [
    { title: 'Championship Finals Set After Dramatic Semifinals', excerpt: 'Underdogs advance past favorites in thrilling overtime victories.', time: '1h ago' },
    { title: 'Olympic Committee Announces New Sports', excerpt: 'Breaking, climbing, and esports join the next Olympic Games.', time: '4h ago' },
  ],
  entertainment: [
    { title: 'Streaming Wars: New Player Enters Market', excerpt: 'Tech giant launches ad-supported streaming service with exclusive content deals.', time: '3h ago' },
    { title: 'AI-Generated Music Sparks Industry Debate', excerpt: 'Labels and artists grapple with copyright and creative authenticity questions.', time: '9h ago' },
  ],
  arts: [
    { title: 'Major Museum Opens Digital Art Wing', excerpt: 'Interactive and immersive installations showcase the future of artistic expression.', time: '5h ago' },
    { title: 'Indigenous Art Gains Global Recognition', excerpt: 'International exhibitions celebrate First Nations and Aboriginal art traditions.', time: '8h ago' },
  ],
};

const categoryNames: Record<string, string> = {
  tech: 'Technology',
  finance: 'Finance',
  sports: 'Sports',
  entertainment: 'Entertainment',
  arts: 'Arts & Culture',
};

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const hours = Math.floor(diff / 3600000);
  if (hours < 1) return 'just now';
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export default function CategoryPage({ category }: { category: string }) {
  const router = useRouter();
  const name = categoryNames[category] || 'Category';
  const [articles, setArticles] = useState<DiscoverArticle[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    fetch(`/api/discover?category=${encodeURIComponent(category)}`)
      .then((r) => r.json())
      .then((data: DiscoverArticle[]) => {
        if (Array.isArray(data)) setArticles(data);
        setLoaded(true);
      })
      .catch(() => setLoaded(true));
  }, [category]);

  const fallback = placeholderArticles[category] || placeholderArticles.tech;
  const hasRealData = articles.length > 0;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <button
          onClick={() => router.push('/discover')}
          className="p-2 rounded-lg hover:bg-[#333] text-txt-muted hover:text-white transition-colors"
        >
          <ArrowLeft size={20} />
        </button>
        <h1 className="text-2xl font-bold text-white font-display">{name}</h1>
      </div>

      <div className="flex flex-col gap-4">
        {hasRealData
          ? articles.map((article) => (
              <GlassCard
                key={article.id}
                hover
                onClick={article.sourceUrl ? () => window.open(article.sourceUrl!, '_blank') : undefined}
                className="p-5"
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <h3 className="text-white font-medium text-base">{article.title}</h3>
                    <p className="text-txt-muted text-sm mt-2 leading-relaxed">{article.excerpt}</p>
                    <div className="flex items-center gap-3 mt-3">
                      {article.sourceTitle && (
                        <span className="text-xs text-txt-subtle">{article.sourceTitle}</span>
                      )}
                      <span className="text-txt-subtle text-xs">{timeAgo(article.generatedAt)}</span>
                    </div>
                  </div>
                  {article.sourceUrl && (
                    <ExternalLink size={14} className="text-[#555] shrink-0 mt-1 ml-3" />
                  )}
                </div>
              </GlassCard>
            ))
          : fallback.map((article, i) => (
              <GlassCard key={i} hover className="p-5">
                <h3 className="text-white font-medium text-base">{article.title}</h3>
                <p className="text-txt-muted text-sm mt-2 leading-relaxed">{article.excerpt}</p>
                <span className="text-txt-subtle text-xs mt-3 block">{article.time}</span>
              </GlassCard>
            ))}
      </div>

      {!hasRealData && loaded && (
        <div className="text-center py-8">
          <p className="text-txt-subtle text-sm">
            No generated content yet — trigger generation via POST /api/discover/generate
          </p>
        </div>
      )}
    </div>
  );
}
