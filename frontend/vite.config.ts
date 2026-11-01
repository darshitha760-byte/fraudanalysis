import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  return {
    plugins: [react()],
    build: { rollupOptions: { output: { manualChunks: { charts: ["recharts"] } } } },
    server: {
      host: "127.0.0.1",
      port: 5173,
      strictPort: true,
      proxy: {
        "/backend": {
          target: env.API_PROXY_TARGET || "http://127.0.0.1:8001",
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/backend/, ""),
          headers: { "X-Forwarded-Prefix": "/backend" },
          timeout: 360000,
          proxyTimeout: 360000,
        },
      },
    },
  };
});
