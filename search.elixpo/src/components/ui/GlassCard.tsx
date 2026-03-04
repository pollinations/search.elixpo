'use client';

interface GlassCardProps {
  children: React.ReactNode;
  className?: string;
  hover?: boolean;
  onClick?: () => void;
}

export default function GlassCard({ children, className = '', hover = false, onClick }: GlassCardProps) {
  return (
    <div
      onClick={onClick}
      className={`
        bg-gradient-card backdrop-blur-[20px] border border-bdr-light rounded-2xl
        text-txt-primary transition-all duration-300
        ${hover ? 'hover:-translate-y-1 hover:border-bdr-hover hover:shadow-card-hover cursor-pointer' : ''}
        ${className}
      `}
    >
      {children}
    </div>
  );
}
