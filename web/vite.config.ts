import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Served by Flask at /app from web/dist. In development `npm run dev`
// proxies API calls to the Flask server on :5000.
export default defineConfig({
  plugins: [react()],
  base: '/app/',
  build: { outDir: 'dist' },
  server: {
    proxy: { '/api': 'http://127.0.0.1:5000' },
  },
})
