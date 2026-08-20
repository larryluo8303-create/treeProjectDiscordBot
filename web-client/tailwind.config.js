/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: '#0F1419',
        surface: '#1A2332',
        'surface-light': '#243447',
        primary: '#3B82F6',
        'primary-dark': '#2563EB',
        success: '#10B981',
        warning: '#F59E0B',
        danger: '#EF4444',
        info: '#06B6D4',
        'text-main': '#F1F5F9',
        'text-secondary': '#94A3B8',
        'text-muted': '#64748B',
        border: '#334155',
        'input-bg': '#1E293B',
        'user-bubble': '#3B82F6',
        'bot-bubble': '#1E293B',
        accent: '#8B5CF6',
      },
    },
  },
  plugins: [],
};
