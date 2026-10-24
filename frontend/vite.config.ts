import { fileURLToPath, URL } from 'node:url'

import { defineConfig, type ViteDevServer } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    vueDevTools(),
    {
      name: 'public-api-boundary',
      configureServer(server: ViteDevServer) {
        server.middlewares.use((req, res, next) => {
          const path = req.url || '';
          if (path.startsWith('/api/') && !path.startsWith('/api/planning/v1/') && !path.startsWith('/api/participation/rounds/')) {
            res.statusCode = 404;
            res.end();
            return;
          }
          next();
        });
      },
    },
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    host: '127.0.0.1',
    strictPort: true,
    proxy: {
      '/api/planning/v1/': { target: 'http://127.0.0.1:18080', rewrite: path => path.replace(/^\/api\/planning/, '') },
      '/api/participation/rounds/': { target: 'http://127.0.0.1:13002', rewrite: path => path.replace(/^\/api\/participation/, '') },
    },
  },
})
