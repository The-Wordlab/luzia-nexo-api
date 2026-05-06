/**
 * Gemini/Vertex AI LLM provider.
 *
 * Implements LLMClient for Google's Gemini models via @google/genai.
 * Supports three auth modes:
 * - developer_api_key: direct API key
 * - vertex_api_key: Vertex AI with API key
 * - vertex_adc: Vertex AI with Application Default Credentials
 */

import type { LLMClient, LLMGenerateOptions, LLMMessage } from "./types";

/** Auth mode for Gemini/Vertex AI. */
export type GeminiAuthMode = "developer_api_key" | "vertex_api_key" | "vertex_adc";

export interface GeminiClientOptions {
  model: string;
  apiKey?: string;
  authMode?: GeminiAuthMode;
  project?: string;
  location?: string;
  clientFactory?: GeminiTransportFactory;
}

interface GeminiPart {
  text?: string;
}

interface GeminiContent {
  role: "user" | "model";
  parts: GeminiPart[];
}

interface GeminiTransport {
  models: {
    generateContent(
      request: GeminiGenerateContentParameters,
    ): Promise<{ text?: string | undefined }>;
  };
}

interface GeminiGenerateContentConfig {
  systemInstruction?: string;
  temperature?: number;
  responseMimeType?: "application/json" | "text/plain";
}

interface GeminiGenerateContentParameters {
  model: string;
  contents: GeminiContent[];
  config: GeminiGenerateContentConfig;
}

interface GoogleGenAIOptions {
  apiKey?: string;
  vertexai?: boolean;
  project?: string;
  location?: string;
  apiVersion?: string;
}

type GeminiTransportFactory = (options: GoogleGenAIOptions) => GeminiTransport;

const DEFAULT_VERTEX_PROJECT = "luzia-nexo-api-examples";
const DEFAULT_VERTEX_LOCATION = "europe-west1";

function stripModelPrefix(model: string): string {
  return model.replace(/^gemini\//u, "");
}

function toGeminiRole(message: LLMMessage): GeminiContent["role"] {
  return message.role === "assistant" ? "model" : "user";
}

function toGeminiText(message: LLMMessage): string {
  if (message.role === "tool") {
    return `Tool ${message.name || "tool"} result:\n${message.content}`;
  }
  return message.content;
}

function requireApiKey(apiKey: string, authMode: GeminiAuthMode): string {
  if (!apiKey) {
    throw new Error(
      `GEMINI_API_KEY is required when ASK_EXPERT_AUTH_MODE=${authMode}`,
    );
  }

  return apiKey;
}

function resolveVertexProject(project?: string): string {
  return (
    project ||
    process.env.GOOGLE_CLOUD_PROJECT ||
    process.env.GCLOUD_PROJECT ||
    DEFAULT_VERTEX_PROJECT
  );
}

function resolveVertexLocation(location?: string): string {
  return (
    location ||
    process.env.GOOGLE_CLOUD_LOCATION ||
    process.env.VERTEX_LOCATION ||
    DEFAULT_VERTEX_LOCATION
  );
}

export function buildGoogleGenAIOptions({
  apiKey = "",
  authMode = "vertex_adc",
  project,
  location,
}: Omit<GeminiClientOptions, "model" | "clientFactory"> = {}): GoogleGenAIOptions {
  if (authMode === "developer_api_key") {
    return {
      apiKey: requireApiKey(apiKey, authMode),
      apiVersion: "v1beta",
    };
  }

  const resolvedProject = resolveVertexProject(project);
  const resolvedLocation = resolveVertexLocation(location);

  if (authMode === "vertex_api_key") {
    return {
      vertexai: true,
      project: resolvedProject,
      location: resolvedLocation,
      apiKey: requireApiKey(apiKey, authMode),
      apiVersion: "v1",
    };
  }

  return {
    vertexai: true,
    project: resolvedProject,
    location: resolvedLocation,
    apiVersion: "v1",
  };
}

function collapseMessages(messages: LLMMessage[]): {
  systemInstruction: string;
  contents: GeminiContent[];
} {
  const systemInstruction = messages
    .filter((message) => message.role === "system")
    .map((message) => message.content.trim())
    .filter(Boolean)
    .join("\n\n");

  const contents: GeminiContent[] = [];
  for (const message of messages) {
    if (message.role === "system") continue;
    const role = toGeminiRole(message);
    const text = toGeminiText(message).trim();
    if (!text) continue;

    const previous = contents.at(-1);
    if (previous && previous.role === role) {
      previous.parts.push({ text });
      continue;
    }

    contents.push({
      role,
      parts: [{ text }],
    });
  }

  return { systemInstruction, contents };
}

export function buildGeminiGenerateRequest(
  model: string,
  messages: LLMMessage[],
  options: LLMGenerateOptions = {},
): GeminiGenerateContentParameters {
  const { systemInstruction, contents } = collapseMessages(messages);
  if (contents.length === 0) {
    throw new Error("Gemini request requires at least one non-system message");
  }

  return {
    model: stripModelPrefix(model),
    contents,
    config: {
      systemInstruction: systemInstruction || undefined,
      temperature: options.temperature ?? 0.2,
      responseMimeType: options.responseMimeType ?? "application/json",
    },
  };
}

function createDefaultTransport(options: GoogleGenAIOptions): GeminiTransport {
  let clientPromise: Promise<GeminiTransport> | null = null;

  return {
    models: {
      async generateContent(request: GeminiGenerateContentParameters) {
        if (!clientPromise) {
          clientPromise = import("@google/genai").then(
            ({
              GoogleGenAI,
            }: {
              GoogleGenAI: new (
                opts: GoogleGenAIOptions,
              ) => GeminiTransport;
            }) => new GoogleGenAI(options),
          );
        }

        const client = await clientPromise;
        return client.models.generateContent(request);
      },
    },
  };
}

export class GeminiLLMClient implements LLMClient {
  readonly model: string;
  readonly authMode: GeminiAuthMode;
  private readonly client: GeminiTransport;

  constructor({
    model,
    apiKey = "",
    authMode = "vertex_adc",
    project,
    location,
    clientFactory = createDefaultTransport,
  }: GeminiClientOptions) {
    this.model = model;
    this.authMode = authMode;
    this.client = clientFactory(
      buildGoogleGenAIOptions({ apiKey, authMode, project, location }),
    );
  }

  async generate(
    messages: LLMMessage[],
    options: LLMGenerateOptions = {},
  ): Promise<string> {
    const response = await this.client.models.generateContent(
      buildGeminiGenerateRequest(this.model, messages, options),
    );
    const text = response.text?.trim();

    if (!text) {
      throw new Error("LLM returned empty response");
    }

    return text;
  }
}

/**
 * Create a Gemini LLM client.
 */
export function createGeminiClient(options: GeminiClientOptions): LLMClient {
  return new GeminiLLMClient(options);
}
