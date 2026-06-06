import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { viteSingleFile } from 'vite-plugin-singlefile'

// Build output: ../html/index.html → postbuild renames to standalone.html
export default defineConfig({
  plugins: [react(), viteSingleFile()],
  build: {
    outDir: '../html',
    emptyOutDir: false,
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
