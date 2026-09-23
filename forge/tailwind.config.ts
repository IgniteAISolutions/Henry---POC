import type { Config } from 'tailwindcss';

export default {
  content: ['./src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: { 950: '#08090B', 900: '#0E1013', 850: '#141619', 800: '#1B1E23', 700: '#282C33', 600: '#3A3F48' },
        chalk: { 50: '#F7F8F9', 200: '#D6D9DE', 400: '#9AA1AC', 500: '#7A828E' },
        forge: { 500: '#E4342B', 600: '#C42920', 400: '#F2564D' },
        signal: { ok: '#3FB950', warn: '#D8A114', bad: '#E4342B' },
      },
      fontFamily: {
        sans: ['ui-sans-serif', 'system-ui', '-apple-system', 'Segoe UI', 'Inter', 'Helvetica Neue', 'Arial', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Consolas', 'monospace'],
      },
      boxShadow: { panel: '0 1px 0 0 rgba(255,255,255,0.04) inset, 0 8px 24px -12px rgba(0,0,0,0.8)' },
    },
  },
  plugins: [],
} satisfies Config;
