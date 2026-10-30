import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/run': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/run_sse': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/apps': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/ui': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/preview': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
});
