import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolveApiProxyTarget } from './viteProxyTarget.js'

export default defineConfig({
  test: {
    environment: 'jsdom',
    globals: true,
  },
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': resolveApiProxyTarget(),
      '/ws': {
        target: resolveApiProxyTarget().replace(/^http/, 'ws'),
        ws: true,
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules/echarts') || id.includes('node_modules/zrender')) {
            return 'echarts'
          }
        },
      },
    },
  },
})
