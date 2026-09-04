import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// PRAHARI frontend build config (see docs/FRONTEND_BRIEF.md).
// base './' so FastAPI can serve dist/ from any path; dev proxy to the PRAHARI backend.
export default defineConfig({
  base: './',
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target: 'http://127.0.0.1:8001', changeOrigin: true },
    },
  },
  preview: {
    proxy: {
      '/api': { target: 'http://127.0.0.1:8001', changeOrigin: true },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          react: ['react', 'react-dom'],
          charts: ['recharts'],
          graph: ['d3-force'],
          motion: ['framer-motion'],
        },
      },
    },
  },
})
