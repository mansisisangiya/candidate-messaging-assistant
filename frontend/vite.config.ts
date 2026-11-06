/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => ({
  plugins: [react()],
  server: {
    port: 5173,
    // Dev-only: forward /api calls to the FastAPI backend. VITE_API_PROXY lets the E2E
    // tests point at their own backend without touching the default port 8000.
    proxy: { "/api": loadEnv(mode, ".", "").VITE_API_PROXY ?? "http://localhost:8000" },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/setupTests.ts"],
    include: ["src/**/*.test.{ts,tsx}"], // keeps Vitest away from the Playwright specs in e2e/
  },
}));
