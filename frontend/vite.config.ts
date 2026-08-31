import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  return {
    base: env.VITE_BASE_PATH || "/",
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        "/api": {
          target: env.VITE_API_ORIGIN || "http://127.0.0.1:8000",
          changeOrigin: true,
        },
        "/health": {
          target: env.VITE_API_ORIGIN || "http://127.0.0.1:8000",
          changeOrigin: true,
        },
      },
    },
  };
});
