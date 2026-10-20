import react from '@vitejs/plugin-react'
import { configDefaults, defineConfig } from 'vitest/config'
import { fileURLToPath, URL } from 'node:url'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  test: {
    exclude: [...configDefaults.exclude, 'e2e/**'],
    testTimeout: 15_000,
    hookTimeout: 15_000,
  },
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8011',
    },
  },
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
})
