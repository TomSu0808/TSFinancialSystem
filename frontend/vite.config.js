import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const backendPort = process.env.BACKEND_PORT || '8000'

// 前端 :5173，把 /api 代理到后端 :8000，避免跨域、贴近上云后的同源部署
export default defineConfig({
  plugins: [react()],
  server: {
    host: true, // 允许局域网/手机访问
    port: 5173,
    proxy: {
      '/api': `http://localhost:${backendPort}`,
    },
  },
})
