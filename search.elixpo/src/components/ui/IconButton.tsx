'use client';

import type { LucideIcon } from 'lucide-react';

interface IconButtonProps {
  icon: LucideIcon;
  onClick?: () => void;
  active?: boolean;
  title?: string;
  size?: number;
  className?: string;
  variant?: 'default' | 'primary' | 'ghost';
}

export default function IconButton({
  icon: Icon,
  onClick,
  active = false,
  title,
  size = 20,
  className = '',
  variant = 'default',
}: IconButtonProps) {
  const variants = {
    default: `bg-[#333] hover:bg-[#444] ${active ? 'text-white bg-[#444]' : 'text-[#888]'}`,
    primary: 'bg-[#444ce7] hover:bg-[#5558e8] text-white',
    ghost: `hover:bg-[#333] ${active ? 'text-white' : 'text-[#555]'}`,
  };

  return (
    <button
      onClick={onClick}
      title={title}
      className={`
        h-10 w-10 rounded-[10px] flex items-center justify-center
        transition-all duration-200 cursor-pointer
        ${variants[variant]}
        ${className}
      `}
    >
      <Icon size={size} />
    </button>
  );
}
