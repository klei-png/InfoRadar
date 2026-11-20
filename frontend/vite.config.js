import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      // 开发模式：API 请求转发给 FastAPI（生产环境同源，无需代理）
      '^/(digests|items|ask|feedback|login|health)': 'http://localhost:8000',
    },
  },
  // Vitest：组件/工具测试需要 DOM 与 localStorage
  test: {
    environment: 'jsdom',
  },
})
