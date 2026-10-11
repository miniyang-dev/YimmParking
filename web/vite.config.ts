import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The backend port is configurable: 8000 is often taken on a dev machine.
const api = process.env.YIMM_API_ORIGIN ?? "http://127.0.0.1:49387";

export default defineConfig({
  plugins: [react()],
  server: {
    // 5173 is taken by the WSL service the Cloudflare tunnel points at.
    port: 5174,
    proxy: { "/api": { target: api, changeOrigin: true } },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
    globals: false,
  },
});
