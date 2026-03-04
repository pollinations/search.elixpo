'use client';

import { ArrowLeft } from 'lucide-react';
import { useRouter } from 'next/navigation';
import GlassCard from '@/components/ui/GlassCard';

const placeholderArticles: Record<string, Array<{ title: string; excerpt: string; time: string }>> = {
  tech: [
    { title: 'The Rise of Multimodal AI Models', excerpt: 'How vision-language models are transforming industries from healthcare to creative arts.', time: '3h ago' },
    { title: 'WebAssembly 3.0 Draft Specification Released', excerpt: 'The new spec introduces garbage collection and improved interop with JavaScript.', time: '5h ago' },
    { title: 'Quantum Computing Achieves Error Correction Milestone', excerpt: 'Researchers demonstrate fault-tolerant quantum computation with logical qubits.', time: '8h ago' },
    { title: 'Open Source Database Challenges Cloud Giants', excerpt: 'New distributed database promises PostgreSQL compatibility with infinite scale.', time: '12h ago' },
  ],
  finance: [
    { title: 'Central Banks Signal Rate Pivot', excerpt: 'Major economies prepare for coordinated monetary policy shifts as inflation cools.', time: '2h ago' },
    { title: 'DeFi Protocol Reaches $100B TVL Milestone', excerpt: 'Decentralized finance continues its institutional adoption trajectory.', time: '6h ago' },
    { title: 'Green Bonds Market Expands Rapidly', excerpt: 'Sustainable finance instruments see record issuance in first quarter.', time: '10h ago' },
  ],
  sports: [
    { title: 'Championship Finals Set After Dramatic Semifinals', excerpt: 'Underdogs advance past favorites in thrilling overtime victories.', time: '1h ago' },
    { title: 'Olympic Committee Announces New Sports', excerpt: 'Breaking, climbing, and esports join the next Olympic Games.', time: '4h ago' },
    { title: 'Transfer Window Breaks Spending Records', excerpt: 'Top clubs invest heavily in young talent from emerging leagues.', time: '7h ago' },
  ],
  entertainment: [
    { title: 'Streaming Wars: New Player Enters Market', excerpt: 'Tech giant launches ad-supported streaming service with exclusive content deals.', time: '3h ago' },
    { title: 'AI-Generated Music Sparks Industry Debate', excerpt: 'Labels and artists grapple with copyright and creative authenticity questions.', time: '9h ago' },
    { title: 'Festival Season Lineup Announcements', excerpt: 'Major music festivals reveal headliners for upcoming summer season.', time: '1d ago' },
  ],
  arts: [
    { title: 'Major Museum Opens Digital Art Wing', excerpt: 'Interactive and immersive installations showcase the future of artistic expression.', time: '5h ago' },
    { title: 'Indigenous Art Gains Global Recognition', excerpt: 'International exhibitions celebrate First Nations and Aboriginal art traditions.', time: '8h ago' },
    { title: 'Street Art Transforms Urban Landscapes', excerpt: 'Cities commission large-scale murals as part of cultural revitalization efforts.', time: '1d ago' },
  ],
};

const categoryNames: Record<string, string> = {
  tech: 'Technology',
  finance: 'Finance',
  sports: 'Sports',
  entertainment: 'Entertainment',
  arts: 'Arts & Culture',
};

export default function CategoryPage({ category }: { category: string }) {
  const router = useRouter();
  const articles = placeholderArticles[category] || placeholderArticles.tech;
  const name = categoryNames[category] || 'Category';

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
        {articles.map((article, i) => (
          <GlassCard key={i} hover className="p-5">
            <h3 className="text-white font-medium text-base">{article.title}</h3>
            <p className="text-txt-muted text-sm mt-2 leading-relaxed">{article.excerpt}</p>
            <span className="text-txt-subtle text-xs mt-3 block">{article.time}</span>
          </GlassCard>
        ))}
      </div>

      <div className="text-center py-8">
        <p className="text-txt-subtle text-sm">
          More content coming soon — discover endpoints are under development
        </p>
      </div>
    </div>
  );
}
