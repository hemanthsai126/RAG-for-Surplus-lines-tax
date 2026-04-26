import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "VITE_");
  const apiPort = (env.VITE_API_PORT || "8001").trim();
  return {
    plugins: [react(), tailwindcss()],
    build: {
      // Avoid clashing with legacy FastAPI static mount at `/assets/`
      assetsDir: "spa-assets",
    },
    server: {
      port: 5173,
      proxy: {
        "/api": `http://127.0.0.1:${apiPort}`,
      },
    },
  };
});
