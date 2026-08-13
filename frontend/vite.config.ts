import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/static': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  base: '/static/',
  build: {
    outDir: resolve(__dirname, '..', 'static'),
    emptyOutDir: true,
    assetsDir: 'assets',
    rollupOptions: {
      output: {
        // vendor 拆分：框架代码独立 chunk（带 hash 永久缓存），
        // 业务代码更新时框架 chunk 命中缓存，二次部署加载量最小化
        manualChunks: {
          vendor: ['vue', 'vue-router', 'pinia'],
        },
      },
    },
  },
})
