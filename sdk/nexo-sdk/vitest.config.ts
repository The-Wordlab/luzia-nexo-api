import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    alias: {
      // @google/genai is a peer dependency of consuming apps.
      // Stub it so Vitest can resolve the import without the package installed.
      "@google/genai": new URL("./src/server/llm/__mocks__/google-genai.ts", import.meta.url).pathname,
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
  },
});
