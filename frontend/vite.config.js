import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Backend port: 8000 by default. `--mode alt` (or RH_API_PORT) uses 8010, for when 8000 is taken.
export default defineConfig(({ mode }) => {
  const api = process.env.RH_API_PORT || (mode === 'alt' ? 8010 : 8000)
  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        '/api': `http://127.0.0.1:${api}`,
        '/ws': { target: `ws://127.0.0.1:${api}`, ws: true },
      },
    },
  }
})
