import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig, loadEnv } from 'vite'
import path from 'node:path'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, __dirname, 'VITE_')
  const backendUrl = (process.env.VITE_API_BASE_URL || env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').trim()
  return {
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    proxy: {
      '/api': {
        target: backendUrl,
        changeOrigin: true,
        ws: true,
      },
      '/media': {
        target: backendUrl,
        changeOrigin: true,
      },
    },
  },
  }
})