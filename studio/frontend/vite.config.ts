import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // Build output goes to dist/ — served by FastAPI at /studio
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
  // In development, proxy API calls to the running SMN server
  server: {
    port: 5173,
    proxy: {
      "/studio/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  // All routes fall back to index.html for React Router
  base: "/studio/",
});
