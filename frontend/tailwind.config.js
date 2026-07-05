/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#0A1F44',
        brand: '#0B3D91',
        teal: '#0E7C7B',
        paper: '#F7F9FC',
        card: '#FFFFFF',
        line: '#E3E8F0',
        muted: '#5B6B85',
        rag: { red: '#E5484D', amber: '#E8A317', green: '#2E9E5B' },
      },
      fontFamily: {
        sans: [
          'system-ui', '-apple-system', 'Segoe UI', 'Roboto',
          'Helvetica', 'Arial', 'sans-serif',
        ],
      },
      boxShadow: {
        soft: '0 1px 2px rgba(10,31,68,0.04), 0 8px 28px rgba(10,31,68,0.06)',
        card: '0 1px 3px rgba(10,31,68,0.05), 0 12px 32px rgba(10,31,68,0.05)',
      },
    },
  },
  plugins: [],
}
