import http from "node:http";
import { fileURLToPath } from "node:url";

function json(res, status, body) {
  res.writeHead(status, { "Content-Type": "application/json" });
  res.end(JSON.stringify(body));
}

function html(res, status, body) {
  res.writeHead(status, { "Content-Type": "text/html; charset=utf-8" });
  res.end(body);
}

function infoPayload() {
  return {
    service: "nexo-examples-ts",
    runtime: "typescript",
    description: "Hosted TypeScript webhook and proactive examples.",
    docs_url: "https://the-wordlab.github.io/luzia-nexo-api/",
    auth: {
      shared_secret_env: "EXAMPLES_SHARED_API_SECRET",
      headers: ["X-App-Secret", "Authorization: Bearer <secret>"],
    },
    endpoints: [
      { path: "/health", method: "GET", description: "Service health", auth_required: false },
      { path: "/info", method: "GET", description: "Service endpoint catalog", auth_required: false },
      { path: "/webhook/minimal", method: "POST", description: "Minimal echo webhook", auth_required: true },
      { path: "/partner/proactive/preview", method: "POST", description: "Proactive message contract preview", auth_required: true },
    ],
  };
}

function infoHtml(info) {
  const rows = info.endpoints
    .map(
      (e) =>
        `<tr><td><code>${e.method}</code></td><td><code>${e.path}</code></td><td>${e.description}</td><td>${e.auth_required ? "yes" : "no"}</td></tr>`,
    )
    .join("");

  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>${info.service} - endpoint catalog</title>
    <style>
      body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 24px; color: #1f2937; }
      h1 { margin-bottom: 4px; }
      p { margin-top: 0; color: #4b5563; }
      table { width: 100%; border-collapse: collapse; margin-top: 16px; }
      th, td { border: 1px solid #e5e7eb; padding: 10px; text-align: left; font-size: 14px; }
      th { background: #f9fafb; }
      code { background: #f3f4f6; padding: 2px 5px; border-radius: 4px; }
      .hint { margin-top: 16px; font-size: 13px; color: #6b7280; }
    </style>
  </head>
  <body>
    <h1>${info.service}</h1>
    <p>${info.description}</p>
    <p><a href="${info.docs_url}" target="_blank" rel="noopener noreferrer">Integration guide and setup instructions</a></p>
    <table>
      <thead><tr><th>Method</th><th>Path</th><th>Description</th><th>Auth</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
    <p class="hint">For JSON output, request <code>/info?format=json</code> or send <code>Accept: application/json</code>.</p>
  </body>
</html>`;
}

function wantsJson(format, acceptHeader = "") {
  if (format === "json") return true;
  return acceptHeader.includes("application/json") && !acceptHeader.includes("text/html");
}

export function isAuthorized(headers, expectedSecret) {
  if (!expectedSecret) return false;
  const appSecret = (headers["x-app-secret"] ?? "").toString();
  if (appSecret && appSecret === expectedSecret) return true;

  const auth = (headers.authorization ?? "").toString();
  if (auth.startsWith("Bearer ")) {
    return auth.slice("Bearer ".length).trim() === expectedSecret;
  }
  return false;
}

export function processRequest(method, url, headers, rawBody, expectedSecret) {
  const parsed = new URL(url, "http://localhost");
  const path = parsed.pathname;
  const format = parsed.searchParams.get("format");
  const accept = (headers.accept ?? "").toString();

  if (method === "GET" && (path === "/" || path === "/info")) {
    const info = infoPayload();
    if (wantsJson(format, accept)) {
      return { status: 200, body: info, contentType: "application/json" };
    }
    return { status: 200, body: infoHtml(info), contentType: "text/html; charset=utf-8" };
  }

  if (method === "GET" && path === "/health") {
    return {
      status: 200,
      body: {
        status: "ok",
        service: "nexo-examples-ts",
        runtime: "typescript",
      },
      contentType: "application/json",
    };
  }

  if (!isAuthorized(headers, expectedSecret)) {
    return { status: 401, body: { error: "Unauthorized" } };
  }

  if (method === "POST" && path === "/webhook/minimal") {
    let payload = {};
    try {
      payload = JSON.parse(rawBody || "{}");
    } catch {
      return { status: 400, body: { error: "Invalid JSON" } };
    }
    const content = payload?.message?.content ?? "";
    return { status: 200, body: { reply: `Echo: ${content}`.trim() }, contentType: "application/json" };
  }

  if (method === "POST" && path === "/partner/proactive/preview") {
    return {
      status: 200,
      body: {
        message: {
          role: "assistant",
          content: "Your order is arriving in 15 minutes.",
        },
        headers: {
          "X-App-Id": "<app-id>",
          "X-App-Secret": "<shared-secret>",
        },
      },
      contentType: "application/json",
    };
  }

  return { status: 404, body: { error: "Not found" }, contentType: "application/json" };
}

export function createServer(secretProvider = () => process.env.EXAMPLES_SHARED_API_SECRET || "") {
  return http.createServer((req, res) => {
    const chunks = [];
    req.on("data", (chunk) => chunks.push(chunk));
    req.on("end", () => {
      const rawBody = Buffer.concat(chunks).toString("utf8");
      const result = processRequest(
        req.method || "GET",
        req.url || "/",
        req.headers,
        rawBody,
        secretProvider(),
      );
      if (result.contentType && result.contentType.includes("text/html")) {
        html(res, result.status, result.body);
        return;
      }
      json(res, result.status, result.body);
    });
  });
}

function startServer() {
  const port = Number(process.env.PORT || 8080);
  const server = createServer();
  server.listen(port, () => {
    console.log(`nexo-examples-ts listening on :${port}`);
  });
}

const isMain = process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1];
if (isMain) {
  startServer();
}
