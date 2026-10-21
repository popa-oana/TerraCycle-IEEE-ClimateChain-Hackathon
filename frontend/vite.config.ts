import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');

  // The verified proof document is served read-only by scripts/serve_demo.py.
  // The dev and preview servers proxy /api/proof to it, so the browser always
  // talks to its own origin and no CORS change is needed.
  const proofServer = env.PROOF_SERVER_ORIGIN || 'http://127.0.0.1:8090';
  const proofProxy = {
    '/api/proof': {
      target: proofServer,
      changeOrigin: true,
    },
  };

  return {
    plugins: [react(), tailwindcss()],
    server: {
      proxy: proofProxy,
    },
    preview: {
      proxy: proofProxy,
    },
  };
});
