import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

// 页面版本，用于诊断信息
const APP_VERSION = '0.1.0'

export default defineConfig(({ mode }) => ({
  plugins: [vue()],
  define: {
    __APP_VERSION__: JSON.stringify(APP_VERSION),
  },
  server: {
    // 开发时把 /api 同源代理到后端（默认 8000 端口），避免浏览器跨域拦截
    proxy: {
      '/api': {
        target: loadEnv(mode, '.', '').CELLLENS_API_PROXY_TARGET || 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('/node_modules/zrender/')) return 'chart-renderer'
          if (id.includes('/node_modules/echarts/')) return 'chart-core'
          return undefined
        },
      },
    },
  },
}))
