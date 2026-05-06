declare module "@google/genai" {
  export interface GoogleGenAIOptions {
    apiKey?: string;
    vertexai?: boolean;
    project?: string;
    location?: string;
    apiVersion?: string;
  }

  export interface GoogleGenAIResponse {
    text?: string | undefined;
  }

  export class GoogleGenAI {
    constructor(options: GoogleGenAIOptions);
    models: {
      generateContent(request: unknown): Promise<GoogleGenAIResponse>;
    };
  }
}
