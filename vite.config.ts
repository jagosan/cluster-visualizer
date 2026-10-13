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
        target: 'http://127.0.0.1:8081',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/clusters\/vanilla/, ''),
      },
      '/clusters/cv-kuberay-kueue': {
        target: 'http://127.0.0.1:8082',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/clusters\/cv-kuberay-kueue/, ''),
      },
      '/clusters/cv-kuberay': {
        target: 'http://127.0.0.1:8081',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/clusters\/cv-kuberay/, ''),
      },
      '/clusters/kuberay': {
        target: 'http://127.0.0.1:8082',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/clusters\/kuberay/, ''),
      },
      '/api/v1': {
        target: 'http://127.0.0.1:8082',
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
