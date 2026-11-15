import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The dev server proxies every `/api/*` request (including `/api/docs`) to the
// FastAPI backend on port 8000, so the app can always use relative URLs and the
// production build behaves identically when FastAPI serves `dist/` at `/`.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  preview: {
    port: 4173,
    // `vite preview` does not inherit `server.proxy`, so configure it here too.
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
