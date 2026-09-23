/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

const DEFAULT_API_TARGET = 'http://127.0.0.1:8000'

export default defineConfig(() => {
  // The dev server proxies /api to FastAPI so the browser only ever talks to one
  // origin (no CORS round-trip) and components can use relative URLs.
  const apiTarget = process.env.VITE_API_PROXY_TARGET ?? DEFAULT_API_TARGET

  return {
    plugins: [react()],
    server: {
      port: 5173,
      // Not strict on purpose: if another Vite project already holds 5173 the
      // dev server moves to the next free port instead of failing. The /api
      // proxy below is what the app needs, and it is port-independent.
      strictPort: false,
      proxy: {
        '/api': { target: apiTarget, changeOrigin: true },
      },
    },
    build: {
      outDir: 'dist',
      sourcemap: true,
    },
    test: {
      environment: 'jsdom',
      setupFiles: ['src/test/setup.ts'],
      include: ['src/**/*.test.{ts,tsx}'],
      restoreMocks: true,
    },
  }
})
