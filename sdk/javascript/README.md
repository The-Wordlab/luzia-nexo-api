# @nexo/partner-sdk

TypeScript SDK for integrating with the Nexo Partner API. Provides webhook signature verification and a proactive messaging client.

## Install

```bash
npm install @nexo/partner-sdk
```

## Quick Start

### Webhook Verification

Verify incoming webhook requests from Nexo to ensure authenticity:

```ts
import { verifyWebhookSignature, parseWebhookPayload } from "@nexo/partner-sdk";

// Express middleware example
app.post("/webhook", (req, res) => {
  const rawBody = req.body; // must be the raw string, not parsed JSON
  const signature = req.headers["x-signature"] as string;
  const timestamp = req.headers["x-timestamp"] as string;

  if (!verifyWebhookSignature(rawBody, signature, timestamp, process.env.WEBHOOK_SECRET!)) {
    return res.status(401).json({ error: "Invalid signature" });
  }

  const payload = parseWebhookPayload(rawBody);
  console.log(`Received message: ${payload.message.content}`);

  res.json({
    schema_version: "2026-03",
    status: "completed",
    content_parts: [{ type: "text", text: `Echo: ${payload.message.content}` }],
  });
});
```

### Fastify Middleware Example

```ts
import Fastify from "fastify";
import { verifyWebhookSignature, parseWebhookPayload } from "@nexo/partner-sdk";

const app = Fastify({ logger: true });

// Use addContentTypeParser to get raw body
app.addContentTypeParser("application/json", { parseAs: "string" }, (req, body, done) => {
  done(null, body);
});

app.post("/webhook", async (request, reply) => {
  const rawBody = request.body as string;
  const signature = request.headers["x-signature"] as string;
  const timestamp = request.headers["x-timestamp"] as string;

  if (!verifyWebhookSignature(rawBody, signature, timestamp, process.env.WEBHOOK_SECRET!)) {
    return reply.status(401).send({ error: "Invalid signature" });
  }

  const payload = parseWebhookPayload(rawBody);
  return {
    schema_version: "2026-03",
    status: "completed",
    content_parts: [{ type: "text", text: `Echo: ${payload.message.content}` }],
  };
});
```

### Proactive Messaging

Send messages to subscribers outside of the normal conversational flow:

```ts
import { NexoClient } from "@nexo/partner-sdk";

const client = new NexoClient({
  apiKey: process.env.APP_SECRET!,
  baseUrl: "https://your-nexo-instance.com",
});

// Send a shipping notification
const message = await client.sendMessage(
  "your-app-id",
  "thread-id",
  "Your order #12345 has shipped! Track it at https://tracking.example.com/12345",
);
console.log(`Sent message ${message.id}`);

// Get thread details
const thread = await client.getThread("your-app-id", "thread-id");

// List subscribers
const subscribers = await client.listSubscribers("your-app-id");

// List threads for a subscriber
const threads = await client.listSubscriberThreads("your-app-id", "subscriber-id");
```

### Error Handling

```ts
import { NexoClient, NexoApiError } from "@nexo/partner-sdk";

const client = new NexoClient({
  apiKey: process.env.APP_SECRET!,
  baseUrl: "https://your-nexo-instance.com",
});

try {
  await client.sendMessage("app-id", "thread-id", "Hello!");
} catch (error) {
  if (error instanceof NexoApiError) {
    console.error(`API error ${error.status}: ${error.message}`);
    console.error("Response body:", error.body);
  } else {
    console.error("Unexpected error:", error);
  }
}
```

## Webhook Signature Algorithm

Nexo signs webhook requests using HMAC-SHA256:

1. Build the signed payload: `{timestamp}.{raw_body}`
2. Compute HMAC-SHA256 using your webhook secret as the key
3. The signature header value is `sha256={hex_digest}`

Headers sent with each signed request:
- `X-Timestamp` - Unix timestamp (seconds) when the request was signed
- `X-Signature` - The HMAC-SHA256 signature (`sha256=...`)

## Type Reference

The SDK exports these types:

| Type | Description |
|------|-------------|
| `WebhookPayload` | Webhook request payload (event: `message_received`) |
| `WebhookResponse` | Rich webhook response envelope |
| `Message` | Message as returned by the API |
| `MessageResponse` | Response from sending a proactive message |
| `Thread` | Thread object |
| `Subscriber` | Subscriber object |
| `NexoClientOptions` | Options for constructing a `NexoClient` |
| `NexoApiError` | Error class with `status`, `statusText`, and `body` |

## Development

```bash
# Install dependencies
pnpm install

# Run tests
pnpm test

# Type check
npx tsc --noEmit

# Build
pnpm run build
```
