/**
 * Minimal webhook server (Node http only). Implements the sync contract:
 * POST JSON body with webhook payload -> respond with rich content envelope.
 * Port 8081 to avoid conflict with main app (3000, 8000).
 */
import http from "node:http";
import crypto from "node:crypto";
import { fileURLToPath } from "node:url";

const PORT = parseInt(process.env.PORT || "8081", 10);

export function verifySignature(secret, rawBody, timestamp, signature) {
  if (!secret || !timestamp || !signature) return true;
  try {
    const signed = `${timestamp}.${rawBody}`;
    const expected =
      "sha256=" +
      crypto.createHmac("sha256", secret).update(signed).digest("hex");
    const a = Buffer.from(signature, "utf8");
    const b = Buffer.from(expected, "utf8");
    return a.length === b.length && crypto.timingSafeEqual(a, b);
  } catch {
    return false;
  }
}

export function processWebhook(raw, headers = {}, secret = "") {
  const ts = (headers["x-timestamp"] ?? "").toString();
  const sig = (headers["x-signature"] ?? "").toString();

  if (secret && !verifySignature(secret, raw, ts, sig)) {
    return { status: 401, body: null };
  }

  let data;
  try {
    data = JSON.parse(raw);
  } catch {
    return { status: 400, body: { error: "Invalid JSON" } };
  }

  // A2A shape: text in message.parts, profile in message.metadata
  const message = data.message ?? {};
  const metadata = message.metadata ?? {};

  // Extract text: try A2A parts first, fall back to legacy content
  let content = "";
  if (Array.isArray(message.parts)) {
    for (const part of message.parts) {
      if (part?.type === "text" && typeof part?.text === "string") {
        content = part.text;
        break;
      }
    }
  }
  if (!content) {
    content = message.content ?? "";
  }

  // Extract profile: A2A metadata.profile or legacy top-level profile
  const profile = metadata.profile ?? data.profile ?? {};
  const displayName = profile.display_name ?? profile.name ?? null;
  const locale = metadata.locale ?? profile.locale ?? profile.language ?? null;
  const dietary = profile.dietary_preferences ?? null;

  let text = displayName ? `${displayName}, you said: ${content}` : `Echo: ${content}`;
  const hints = [];
  if (locale) hints.push(`locale=${locale}`);
  if (dietary) hints.push(`dietary=${dietary}`);
  if (hints.length > 0) text = `${text} (${hints.join(", ")})`;
  const promptSuggestions = [
    "Help me plan dinner",
    "Track my order status",
    "Show options under $20",
  ];

  return {
    status: 200,
    body: {
      schema_version: "2026-03",
      status: "completed",
      content_parts: [{ type: "text", text }],
      metadata: { prompt_suggestions: promptSuggestions },
    },
  };
}

export function createServer(secretProvider = () => process.env.WEBHOOK_SECRET || "") {
  return http.createServer((req, res) => {
    if (req.method === "GET" && req.url === "/") {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(
        JSON.stringify({
          service: "webhook-minimal-typescript",
          description: "Minimal Nexo webhook example with optional HMAC verification.",
          routes: [
            {
              path: "/",
              method: "POST",
              description: "Receive Nexo webhook payload and return response envelope.",
              auth: "Optional WEBHOOK_SECRET (X-Timestamp + X-Signature)",
            },
          ],
          schema_version: "2026-03",
        }),
      );
      return;
    }

    if (req.method !== "POST") {
      res.writeHead(405);
      res.end();
      return;
    }

    const chunks = [];
    req.on("data", (chunk) => chunks.push(chunk));
    req.on("end", () => {
      const raw = Buffer.concat(chunks).toString("utf8");
      const result = processWebhook(raw, req.headers, secretProvider());

      if (result.status === 401) {
        res.writeHead(401);
        res.end();
        return;
      }

      if (result.status === 400) {
        res.writeHead(400, { "Content-Type": "application/json" });
        res.end(JSON.stringify(result.body));
        return;
      }

      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify(result.body));
    });
  });
}

function startServer() {
  const server = createServer();
  server.listen(PORT, "0.0.0.0", () => {
    console.log(`Webhook listening on http://0.0.0.0:${PORT}`);
  });
}

const isMain = process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1];
if (isMain) {
  startServer();
}
