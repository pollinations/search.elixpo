export const colors = {
  bg: {
    deep: '#0c0f0a',
    card: 'rgba(16, 24, 12, 0.8)',
    cardGlass: 'rgba(255,255,255,0.05)',
    cardGlassHover: 'rgba(255,255,255,0.08)',
    overlay: 'rgba(12, 15, 10, 0.95)',
    surface: '#111',
    elevated: '#1a1a1a',
  },
  lime: { main: '#a3e635', light: '#bef264', dim: 'rgba(163, 230, 53, 0.15)' },
  sage: { main: '#86efac', dim: 'rgba(134, 239, 172, 0.15)' },
  honey: { main: '#fbbf24', dim: 'rgba(251, 191, 36, 0.15)' },
  lavender: { main: '#c4b5fd', light: '#d8b4fe' },
} as const;

export const gradients = {
  accent: 'linear-gradient(90deg, #a3e635, #86efac, #fbbf24)',
  textHero: 'linear-gradient(135deg, #f5f5f4 0%, #a3e635 30%, #86efac 60%, #fbbf24 100%)',
} as const;
