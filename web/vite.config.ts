import { defineConfig } from 'vite';

const api = process.env.KEYSTONE_DEV_API || 'http://127.0.0.1:8765';
if (!/^http:\/\/127\.0\.0\.1:[0-9]{4,5}$/.test(api)) throw new Error('Development API must use local loopback.');
export default defineConfig({
  server: { host: '127.0.0.1', proxy: { '/api': { target: api, changeOrigin: false } } },
  build: { outDir: 'dist', emptyOutDir: true },
});
