import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'
import path from 'node:path'

const harness = (name: string) => path.resolve(__dirname, 'e05-harness', name)
export default defineConfig({
  define: { 'import.meta.env.VITE_E05_HARNESS': JSON.stringify('true') },
  plugins: [
    {
      name: 'e05-no-remote-fonts', enforce: 'pre',
      transform(code, id) {
        if (id.split('?')[0].endsWith('/src/app/styles.css')) {
          return code.replace(/^@import url\([^\n]+\);\s*/gm, '')
        }
      },
    },
    react(), tailwindcss(),
  ],
  resolve: { alias: [
    { find: /^@\/features\/coach\/audio\/local-audio-runtime$/, replacement: harness('runtime.ts') },
    { find: /^\.\.\/audio\/local-audio-runtime$/, replacement: harness('runtime.ts') },
    { find: /^@\/stores\/(app|hardware|runtime|stage4)-store$/, replacement: harness('stores.ts') },
    { find: '@', replacement: path.resolve(__dirname, 'src') },
  ] },
  // No API/media proxy, HMR sockets, production bootstrap, or backend process.
  server: { host: '127.0.0.1', port: 5179, strictPort: true, hmr: false },
})