import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig(() => {
  const apiTarget = process.env.VITE_API_TARGET ?? 'http://127.0.0.1:8011'
  return {
    plugins: [vue()],
    envDir: '..',
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    server: {
      host: '127.0.0.1',
      port: 5174,
      strictPort: true,
      proxy: {
        '/api': apiTarget,
        '/jobs': apiTarget,
        '/processes': apiTarget,
        '/artifacts': apiTarget,
      },
    },
  }
})
