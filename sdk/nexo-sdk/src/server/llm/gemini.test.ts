import { afterEach, describe, expect, it, vi } from "vitest";

// Mock @google/genai so the dynamic import in gemini.ts doesn't fail
// in test environments where the peer dependency isn't installed.
vi.mock("@google/genai", () => ({
  GoogleGenAI: vi.fn(),
}));

import {
  buildGeminiGenerateRequest,
  buildGoogleGenAIOptions,
  GeminiLLMClient,
} from "./gemini";
import type { LLMGenerateOptions, LLMMessage } from "./types";

const originalEnv = { ...process.env };

afterEach(() => {
  process.env = { ...originalEnv };
});

describe("buildGoogleGenAIOptions", () => {
  it("uses Vertex AI ADC by default", () => {
    expect(
      buildGoogleGenAIOptions({
        authMode: "vertex_adc",
        project: "luzia-nexo-api-examples",
        location: "europe-west1",
      }),
    ).toEqual({
      vertexai: true,
      project: "luzia-nexo-api-examples",
      location: "europe-west1",
      apiVersion: "v1",
    });
  });

  it("fills safe default Vertex project and region when callers omit them", () => {
    delete process.env.GOOGLE_CLOUD_PROJECT;
    delete process.env.GCLOUD_PROJECT;
    delete process.env.GOOGLE_CLOUD_LOCATION;
    delete process.env.VERTEX_LOCATION;

    expect(
      buildGoogleGenAIOptions({
        authMode: "vertex_adc",
      }),
    ).toEqual({
      vertexai: true,
      project: "luzia-nexo-api-examples",
      location: "europe-west1",
      apiVersion: "v1",
    });
  });

  it("prefers explicit environment defaults for Vertex project and region", () => {
    process.env.GCLOUD_PROJECT = "env-project";
    process.env.VERTEX_LOCATION = "us-central1";

    expect(
      buildGoogleGenAIOptions({
        authMode: "vertex_adc",
      }),
    ).toEqual({
      vertexai: true,
      project: "env-project",
      location: "us-central1",
      apiVersion: "v1",
    });
  });

  it("supports a direct Vertex AI API key override", () => {
    expect(
      buildGoogleGenAIOptions({
        authMode: "vertex_api_key",
        apiKey: "vertex-key",
        project: "luzia-nexo-api-examples",
        location: "europe-west1",
      }),
    ).toEqual({
      vertexai: true,
      project: "luzia-nexo-api-examples",
      location: "europe-west1",
      apiKey: "vertex-key",
      apiVersion: "v1",
    });
  });

  it("supports the Gemini Developer API key mode", () => {
    expect(
      buildGoogleGenAIOptions({
        authMode: "developer_api_key",
        apiKey: "developer-key",
        project: "ignored-project",
        location: "ignored-location",
      }),
    ).toEqual({
      apiKey: "developer-key",
      apiVersion: "v1beta",
    });
  });

  it("fails fast when an API-key mode has no key configured", () => {
    expect(() =>
      buildGoogleGenAIOptions({
        authMode: "developer_api_key",
        apiKey: "",
        project: "luzia-nexo-api-examples",
        location: "europe-west1",
      }),
    ).toThrow("GEMINI_API_KEY is required");
  });
});

describe("buildGeminiGenerateRequest", () => {
  it("converts the generic loop message format into a Gemini request", () => {
    const messages: LLMMessage[] = [
      { role: "system", content: "Answer like a concise pundit." },
      { role: "system", content: "Stay grounded in the available facts." },
      { role: "user", content: "How do you see Mexico vs South Africa?" },
      { role: "assistant", content: "I need one tool lookup first." },
      { role: "tool", name: "get_match_context", content: '{"match_id":"m1"}' },
    ];
    const options: LLMGenerateOptions = {
      temperature: 0.4,
      responseMimeType: "application/json",
    };

    expect(
      buildGeminiGenerateRequest("gemini/gemini-2.5-flash", messages, options),
    ).toEqual({
      model: "gemini-2.5-flash",
      contents: [
        {
          role: "user",
          parts: [{ text: "How do you see Mexico vs South Africa?" }],
        },
        {
          role: "model",
          parts: [{ text: "I need one tool lookup first." }],
        },
        {
          role: "user",
          parts: [{ text: 'Tool get_match_context result:\n{"match_id":"m1"}' }],
        },
      ],
      config: {
        systemInstruction:
          "Answer like a concise pundit.\n\nStay grounded in the available facts.",
        temperature: 0.4,
        responseMimeType: "application/json",
      },
    });
  });
});

describe("GeminiLLMClient", () => {
  it("uses the configured auth seam and returns generated text", async () => {
    const generateContent = vi.fn().mockResolvedValue({
      text: "Mexico looks safer, but it should stay close.",
    });
    const clientFactory = vi.fn().mockReturnValue({
      models: { generateContent },
    });

    const client = new GeminiLLMClient({
      model: "gemini/gemini-2.5-flash",
      authMode: "vertex_adc",
      project: "luzia-nexo-api-examples",
      location: "europe-west1",
      clientFactory,
    });

    const result = await client.generate([
      { role: "system", content: "Answer in one sentence." },
      { role: "user", content: "Who looks stronger in Mexico vs South Africa?" },
    ]);

    expect(client.authMode).toBe("vertex_adc");
    expect(clientFactory).toHaveBeenCalledWith({
      vertexai: true,
      project: "luzia-nexo-api-examples",
      location: "europe-west1",
      apiVersion: "v1",
    });
    expect(generateContent).toHaveBeenCalledWith({
      model: "gemini-2.5-flash",
      contents: [
        {
          role: "user",
          parts: [{ text: "Who looks stronger in Mexico vs South Africa?" }],
        },
      ],
      config: {
        systemInstruction: "Answer in one sentence.",
        temperature: 0.2,
        responseMimeType: "application/json",
      },
    });
    expect(result).toBe("Mexico looks safer, but it should stay close.");
  });
});
