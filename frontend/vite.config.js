import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': new URL('./src', import.meta.url).pathname,
    },
  },
  server: {
    proxy: {
      '/api': {
        // OPTIFULL_API: otro backend local, ej. si el 8080 ya lo usa el agente (serve_dashboard.py --agente)
        target: process.env.OPTIFULL_API || 'http://localhost:8080',
        changeOrigin: true,
      },
    },
  },
})
