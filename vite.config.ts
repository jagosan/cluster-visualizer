import { defineConfig } from 'vite';

// SPEC-00: Cluster Visualizer — Vite + TypeScript + Three.js WebGL client.
// Static GLB assets live in public/assets (copied verbatim to dist on build).
export default defineConfig({
  base: './',
  publicDir: 'public',
  server: {
    host: '0.0.0.0',
    port: 5180,
    strictPort: true,
    allowedHosts: true,
    proxy: {
      '/clusters/vanilla': {
        target: 'http://35.193.124.181:5180',
        changeOrigin: true,
      },
      '/clusters/kuberay': {
        target: 'http://35.193.124.181:5180',
        changeOrigin: true,
      },
      '/api/v1': {
        target: 'http://35.193.124.181:5180/clusters/kuberay',
        changeOrigin: true,
      },
    },
  },
  preview: {
    host: '0.0.0.0',
    port: 5180,
    strictPort: true,
    allowedHosts: true,
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
