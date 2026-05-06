/**
 * Stub for @google/genai peer dependency.
 *
 * Used by vitest so the SDK tests can run without @google/genai installed.
 * The real package is a peer dependency provided by consuming apps.
 */
export class GoogleGenAI {
  constructor(_opts: Record<string, unknown>) {}
  models = {
    async generateContent() {
      throw new Error("GoogleGenAI stub - not for real use");
    },
  };
}
