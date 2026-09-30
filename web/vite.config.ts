/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// NATRA web client. The simulation engine runs in a Web Worker (src/engine/worker.ts),
// so no backend is required for the demo. The optional FastAPI engine is reached via
// VITE_NATRA_SERVER (default http://localhost:8000).
declare const process: { env: Record<string, string | undefined> };
// NATRA_BASE sets the public path, e.g. '/NATRA/' for GitHub Pages project sites.
export default defineConfig({
  base: process.env.NATRA_BASE ?? '/',
  plugins: [react()],
  server: { port: 5173, host: true },
  preview: { port: 4173, host: true },
  worker: { format: 'es' },
  build: { chunkSizeWarningLimit: 2500, sourcemap: false },
  test: { environment: 'node', include: ['src/**/*.test.ts'], testTimeout: 60000 },
});
