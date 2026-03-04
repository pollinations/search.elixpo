import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './src/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        bg: {
          deep: '#0c0f0a',
          card: 'rgba(16, 24, 12, 0.8)',
          'card-glass': 'rgba(255,255,255,0.05)',
          'card-glass-hover': 'rgba(255,255,255,0.08)',
          overlay: 'rgba(12, 15, 10, 0.95)',
          surface: '#111',
          elevated: '#1a1a1a',
        },
        lime: {
          main: '#a3e635',
          light: '#bef264',
          dim: 'rgba(163, 230, 53, 0.15)',
          border: 'rgba(163, 230, 53, 0.3)',
          glow: 'rgba(163, 230, 53, 0.6)',
        },
        sage: {
          main: '#86efac',
          dim: 'rgba(134, 239, 172, 0.15)',
          border: 'rgba(134, 239, 172, 0.3)',
        },
        honey: {
          main: '#fbbf24',
          dim: 'rgba(251, 191, 36, 0.15)',
          border: 'rgba(251, 191, 36, 0.3)',
        },
        lavender: {
          main: '#c4b5fd',
          light: '#d8b4fe',
          dim: 'rgba(196, 181, 253, 0.15)',
          border: 'rgba(168, 85, 247, 0.3)',
        },
        txt: {
          primary: '#f5f5f4',
          secondary: 'rgba(245, 245, 244, 0.8)',
          muted: 'rgba(245, 245, 244, 0.7)',
          subtle: 'rgba(255, 255, 255, 0.5)',
          disabled: 'rgba(255, 255, 255, 0.4)',
        },
        bdr: {
          light: 'rgba(255, 255, 255, 0.1)',
          medium: 'rgba(255, 255, 255, 0.15)',
          strong: 'rgba(255, 255, 255, 0.2)',
          hover: 'rgba(255, 255, 255, 0.3)',
        },
      },
      fontFamily: {
        body: ['"DM Sans"', '-apple-system', 'BlinkMacSystemFont', 'sans-serif'],
        display: ['"Space Grotesk"', '"DM Sans"', 'sans-serif'],
        mono: ['"SF Mono"', 'Monaco', 'Inconsolata', 'monospace'],
      },
      backgroundImage: {
        'gradient-card': 'linear-gradient(135deg, rgba(255,255,255,0.05) 0%, rgba(255,255,255,0.02) 100%)',
        'gradient-page': 'linear-gradient(135deg, #0c0f0a 0%, #0f1410 50%, #0c0f0a 100%)',
        'gradient-accent': 'linear-gradient(90deg, #a3e635, #86efac, #fbbf24)',
        'gradient-text-hero': 'linear-gradient(135deg, #f5f5f4 0%, #a3e635 30%, #86efac 60%, #fbbf24 100%)',
        'gradient-code': 'linear-gradient(135deg, #1a1b1c 0%, #212223 100%)',
      },
      boxShadow: {
        'card': '0 8px 32px 0 rgba(0, 0, 0, 0.37)',
        'card-hover': '0 20px 40px -10px rgba(0,0,0,0.4)',
        'card-lg': '0 25px 50px -10px rgba(0,0,0,0.5)',
        'glow-lime': '0 0 20px rgba(163, 230, 53, 0.6)',
        'button': '0 8px 25px rgba(0,0,0,0.3)',
      },
      animation: {
        'sparkle': 'rotate 1.5s linear infinite',
        'dots': 'dots 1.5s infinite',
      },
      keyframes: {
        rotate: {
          '0%': { transform: 'rotate(0deg)' },
          '100%': { transform: 'rotate(360deg)' },
        },
        dots: {
          '0%, 20%': { opacity: '0' },
          '50%': { opacity: '1' },
          '100%': { opacity: '0' },
        },
      },
    },
  },
  plugins: [],
};

export default config;
