import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],

  server: {
    // Port aligned with .env.example FRONTEND_PORT
    port: 5173,
    proxy: {
      // Forward /api/* to the FastAPI backend during development
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      // Forward /ws to the FastAPI WebSocket endpoint
      '/ws': {
        target: 'ws://127.0.0.1:8000',
        ws: true,
        changeOrigin: true,
      },
    },
  },
})
