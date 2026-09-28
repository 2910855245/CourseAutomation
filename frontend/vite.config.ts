import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import Components from 'unplugin-vue-components/vite'
import { NaiveUiResolver } from 'unplugin-vue-components/resolvers'
import { fileURLToPath, URL } from 'node:url'

// Naive UI 及其运行时依赖独立成块：它体积大且几乎不随业务改动，
// 单独 chunk 后可长期命中浏览器缓存。
const NAIVE_DEPS =
  /[\\/]node_modules[\\/](naive-ui|vueuc|css-render|@css-render|seemly|treemate|vooks|vdirs|evtd|date-fns|@juggle)[\\/]/

export default defineConfig({
  plugins: [
    vue(),
    // 只让 resolver 负责 n-* 组件：dirs 置空，自有组件保持显式 import
    // （否则 1800 行的 YpayTab 之类会被隐式注册，体积与可读性都变差）。
    Components({
      dirs: [],
      resolvers: [NaiveUiResolver()],
      // dts 产物提交进 git：build 脚本第一段是 `vue-tsc --noEmit`，
      // 首次 clone 时若 dts 不存在，类型检查会直接失败。
      dts: 'src/types/components.d.ts',
    }),
  ],
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
          if (NAIVE_DEPS.test(id)) return 'vendor-naive'
        },
      },
    },
  },
})
