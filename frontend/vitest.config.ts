import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      // __dirname 在 ESM 下已废弃（Vite 8 会告警），改用 import.meta.url
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  test: {
    environment: 'happy-dom',
    globals: true,
    exclude: ['tests/**/*.spec.ts', 'e2e/**', 'node_modules/**'],
  },
})
