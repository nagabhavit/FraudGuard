/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
    // 'forks' (Vitest's default) needs to spawn child processes, which some
    // sandboxed/CI environments block; 'threads' runs in-process instead.
    pool: 'threads',
  },
})
