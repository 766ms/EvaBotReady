import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Permite el acceso desde los túneles de Cloudflare (cualquier subdominio).
    allowedHosts: ['.trycloudflare.com'],

    // Las llamadas a /api/... se reenvían al backend de Django (uvicorn en el puerto 8000).
    // Así el navegador ve un solo origen: la cookie de sesión y el CSRF funcionan sin CORS.
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: false },
    },
  },
})