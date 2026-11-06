import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { defineConfig, type PlaywrightTestConfig } from "@playwright/test";

type WebServer = Exclude<PlaywrightTestConfig["webServer"], undefined | unknown[]>;

// The E2E run starts its own backend(s) and Vite server(s) on dedicated ports, with a throwaway
// SQLite file, so it never touches backend/data/ or a dev server you have running.
const python = process.env.E2E_PYTHON ?? path.resolve(import.meta.dirname, "../backend/.venv/bin/python");
const backendDir = path.resolve(import.meta.dirname, "../backend");
const tmp = mkdtempSync(path.join(tmpdir(), "cma-e2e-"));

function stack(name: string, backendPort: number, vitePort: number, injectFailureFor: string): WebServer[] {
  return [
    {
      command: `${python} -m uvicorn app.main:app --port ${backendPort}`,
      cwd: backendDir,
      url: `http://localhost:${backendPort}/api/health`,
      reuseExistingServer: false,
      env: {
        LLM_PROVIDER: "fake",
        DATABASE_PATH: path.join(tmp, `${name}.db`),
        INJECT_INTERVIEW_FAILURE_FOR: injectFailureFor,
        LOG_LEVEL: "WARNING",
      },
    },
    {
      command: `npx vite --port ${vitePort} --strictPort`,
      url: `http://localhost:${vitePort}`,
      reuseExistingServer: false,
      env: { VITE_API_PROXY: `http://localhost:${backendPort}` },
    },
  ];
}

export default defineConfig({
  testDir: "./e2e",
  workers: 1,
  reporter: [["list"], ["html", { open: "never" }]],
  use: { screenshot: "only-on-failure", trace: "retain-on-failure" },
  projects: [
    // Normal backend: the happy path.
    { name: "workflow", testMatch: "workflow.spec.ts", use: { baseURL: "http://localhost:5174" } },
    // Backend started with the failure injected for cand_priya.
    { name: "injected-failure", testMatch: "failure.spec.ts", use: { baseURL: "http://localhost:5175" } },
  ],
  webServer: [...stack("workflow", 8100, 5174, ""), ...stack("failure", 8101, 5175, "cand_priya")],
});
