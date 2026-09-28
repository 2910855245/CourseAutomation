import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:17017',
        changeOrigin: true,
      },
      '/static': {
        target: 'http://127.0.0.1:17017',
        changeOrigin: true,
      },
    },
  },
  base: '/static/',
  build: {
    outDir: fileURLToPath(new URL('../static', import.meta.url)),
    emptyOutDir: true,
    assetsDir: 'assets',
    rollupOptions: {
      output: {
        // vendor 拆分：框架代码独立 chunk（带 hash 永久缓存），
        // 业务代码更新时框架 chunk 命中缓存，二次部署加载量最小化。
        // 注意：Vite 8（rolldown）要求 manualChunks 为函数，不支持对象写法。
        manualChunks(id: string) {
          if (!id.includes('node_modules')) return
          if (/[\\/]node_modules[\\/](vue|vue-router|pinia|@vue)[\\/]/.test(id)) {
            return 'vendor-vue'
          }
          // Phase 3 引入 Naive UI / ECharts 后，在此追加 vendor-naive / vendor-echarts
        },
      },
    },
  },
})
