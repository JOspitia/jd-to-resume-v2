import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from "path"
import { fileURLToPath } from "node:url"

// Resolve the directory of this config file using ESM-native helpers.
// `__dirname` is `undefined` under Vite 8's native configLoader and falls back
// to the CommonJS shim only on older loaders, so we explicitly compute it.
const __dirname = path.dirname(fileURLToPath(import.meta.url))

// https://vite.dev/config/
export default defineConfig({
  // Pin both port and host so a busy 5173 doesn't auto-bump to 5174, which
  // breaks HMR's WebSocket URL injection (the symptom was the React refresh
  // runtime failing to register → entire app failing to mount).
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
  },
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
})
