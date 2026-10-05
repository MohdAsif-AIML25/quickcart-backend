import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // In development the browser talks only to Vite (localhost:5173).
    // Vite forwards every /api/... request to FastAPI and removes the /api prefix.
    // Same origin for the browser -> no CORS configuration needed.
    // In production, nginx does exactly the same job (see nginx.conf).
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
