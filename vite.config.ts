import { defineConfig } from 'vite';

// SPEC-00: Cluster Visualizer — Vite + TypeScript + Three.js WebGL client.
// Static GLB assets live in public/assets (copied verbatim to dist on build).
export default defineConfig({
  base: './',
  publicDir: 'public',
  server: {
    port: 5173,
    strictPort: false,
  },
  build: {
    target: 'es2022',
    outDir: 'dist',
    sourcemap: true,
    rollupOptions: {
      output: {
        manualChunks: {
          three: ['three'],
        },
      },
    },
  },
});
