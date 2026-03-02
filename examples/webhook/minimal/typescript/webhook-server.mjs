/**
 * Minimal webhook server (Node http only). Implements the sync contract:
 * POST JSON body with webhook payload -> respond with { "reply": "..." }.
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

  const content = data.message?.content ?? "";
  return { status: 200, body: { reply: `Echo: ${content}` } };
}

export function createServer(secretProvider = () => process.env.WEBHOOK_SECRET || "") {
  return http.createServer((req, res) => {
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
