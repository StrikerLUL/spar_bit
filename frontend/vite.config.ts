import react from "@vitejs/plugin-react";
import path from "node:path";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  server: {
    port: 5173,
    proxy: {
      // Im Dev-Modus direkt aufs Backend, damit Cookies und SSE funktionieren.
      // 127.0.0.1 statt localhost: run.py und der Browser-Test starten das
      // Backend nur auf IPv4, "localhost" kann aber zuerst ::1 sein.
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true, ws: true },
    },
  },
  build: { outDir: "dist", sourcemap: false, chunkSizeWarningLimit: 900 },
});
