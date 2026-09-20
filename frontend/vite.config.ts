import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      // 开发期把 API 请求转发到后端 FastAPI(:8000)，避免跨域
      '/v1': 'http://localhost:8000',
    },
  },
})