# External Runtime Integration

Connect an external runtime (AI assistant, companion service, background worker)
to Nexo so it can act on behalf of users, sync data, and surface capabilities
through the Nexo ecosystem.

This guide covers the full integration flow:

1. [Authentication](#authentication) - developer keys and machine auth
2. [Account linking](#account-linking) - connect external user identities
3. [Capability sync](#capability-sync) - register what your runtime can do
4. [Context summaries](#context-summaries) - push typed user context into Nexo
5. [Context bundles](#context-bundles) - pull unified context for LLM grounding
6. [Knowledge Pack sync](#knowledge-pack-sync) - keep reference data fresh
7. [Worker/job topology](#workerjob-topology) - scheduled sync patterns
8. [Companion services](#companion-services) - app-specific intelligence

## Prerequisites

- A Nexo developer key (`nexo_uak_...`). See [Developer Auth](developer-auth.md).
- An external runtime registered by a Nexo admin.
- A Nexo app (Connected App or Personalized App) to attach data to.

## Authentication

External runtimes authenticate with Nexo using **developer key exchange**.

### For interactive tools (MCP, CLI, scripts)

Pass the key directly as an `X-Api-Key` header:

```bash
curl "${NEXO_BASE_URL}/api/capabilities/manifest" \
  -H "X-Api-Key: nexo_uak_..."
```

### For background workers and scheduled jobs

Exchange the developer key for a short-lived JWT, then use Bearer auth:

```bash
# Step 1: Exchange key for JWT
TOKEN=$(curl -s -X POST "${NEXO_BASE_URL}/api/auth/key-exchange" \
  -H "Content-Type: application/json" \
  -d '{"api_key": "nexo_uak_..."}' | jq -r '.access_token')

# Step 2: Use JWT for all subsequent calls
curl "${NEXO_BASE_URL}/api/external-sync/capabilities" \
  -X PUT \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '...'
```

The JWT expires after 1 hour. Workers should exchange once at job start and
reuse the token for the duration of the job run.

### TypeScript example (from a Cloud Run Job)

```typescript
import { NexoClient } from "./nexo/client";

const nexo = new NexoClient({
  apiUrl: process.env.NEXO_API_URL,
});
await nexo.authenticate(process.env.NEXO_DEVELOPER_KEY);

// All subsequent calls use the exchanged Bearer token
await nexo.upsertRecord(packId, datasetId, "record-key", { ... });
```

### Machine auth model (v1)

The current production model uses **user-scoped developer keys** for worker
authentication. Each worker runs as a specific developer identity.

- Store `NEXO_DEVELOPER_KEY` in GCP Secret Manager (not in GitHub Secrets).
- Inject via `--set-secrets` in Cloud Run Job definitions.
- The key identifies the developer; Nexo scopes data access to that user's
  permissions.

Service-account-level auth (where the job identity is the credential rather
than a user key) is a future evolution. The developer-key model is sufficient
for v1 and is already proven in production.

## Account linking

Account linking connects an external user identity (e.g. a phone number on a
chat platform) to a Nexo user. This lets external runtimes sync user-scoped
data.

### Flow

```
1. GET  /api/account-linking/runtimes        -> discover available runtimes
2. POST /api/account-linking/links/initiate  -> start a link session
3. POST /api/account-linking/links/verify    -> complete with verification code
4. GET  /api/account-linking/links           -> list linked accounts
5. DELETE /api/account-linking/links/{id}    -> unlink
```

### Step 1: List runtimes

```bash
curl "${NEXO_BASE_URL}/api/account-linking/runtimes" \
  -H "Authorization: Bearer ${TOKEN}"
```

Response:

```json
[
  {
    "id": "uuid",
    "key": "my-runtime",
    "name": "My AI Assistant",
    "webhook_base_url": "https://my-runtime.example.com",
    "is_active": true,
    "config_json": {},
    "created_at": "2026-04-20T12:00:00Z"
  }
]
```

### Step 2: Initiate a link

```bash
curl -X POST "${NEXO_BASE_URL}/api/account-linking/links/initiate" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "runtime_key": "my-runtime",
    "phone_e164": "+34600123456"
  }'
```

Response (HTTP 202):

```json
{
  "session_id": "uuid",
  "status": "pending_code_request",
  "expires_at": "2026-04-20T12:15:00Z",
  "masked_phone": "+34***456"
}
```

### Step 3: Verify

The user receives a verification code through the external runtime's channel.
Submit it to complete the link:

```bash
curl -X POST "${NEXO_BASE_URL}/api/account-linking/links/verify" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "uuid-from-step-2",
    "code": "123456"
  }'
```

Response:

```json
{
  "link_id": "uuid",
  "status": "linked",
  "external_user_id": "ext-user-123",
  "runtime_key": "my-runtime"
}
```

### Unlink

```bash
curl -X DELETE "${NEXO_BASE_URL}/api/account-linking/links/${LINK_ID}" \
  -H "Authorization: Bearer ${TOKEN}"
```

## Capability sync

Register what your runtime can do. Capabilities appear in the
[Capability Manifest](capability-discovery.md) and in user context bundles.

```bash
curl -X PUT "${NEXO_BASE_URL}/api/external-sync/capabilities" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "runtime_key": "wc2026-predictor",
    "capability_key": "predictions",
    "name": "Match Predictions",
    "description": "Predict World Cup 2026 match outcomes",
    "category": "sports",
    "metadata_json": {},
    "is_active": true
  }'
```

Response:

```json
{
  "id": "uuid",
  "capability_key": "predictions",
  "name": "Match Predictions",
  "created": true
}
```

**Upsert behavior:** The endpoint uses `runtime_key` + `capability_key` as the
unique key. Calling again with the same keys updates the existing entry.

Run capability sync as part of your recurring sync job so the manifest stays
current as your runtime evolves.

## Context summaries

Push typed, user-scoped context summaries into Nexo. These appear in context
bundles alongside profile facts and app data.

```bash
curl -X PUT "${NEXO_BASE_URL}/api/external-sync/context-summaries" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "runtime_key": "wc2026-predictor",
    "summary_type": "activity",
    "summary_key": "recent-predictions",
    "title": "Recent Predictions",
    "content_text": "User predicted 3 matches this week, 2 correct.",
    "content_json": {"correct": 2, "total": 3},
    "confidence": 0.95,
    "effective_at": "2026-06-01T00:00:00Z",
    "expires_at": "2026-06-08T00:00:00Z"
  }'
```

Response:

```json
{
  "id": "uuid",
  "summary_key": "recent-predictions",
  "created": true
}
```

**Upsert behavior:** The endpoint uses `runtime_key` + `user_id` + `summary_key`
as the unique key. The `user_id` is resolved from the authenticated token.

**Fields:**

| Field | Required | Description |
|---|---|---|
| `runtime_key` | Yes | The registered runtime's key |
| `summary_type` | Yes | Category: `"activity"`, `"preference"`, `"status"`, etc. (max 64 chars) |
| `summary_key` | Yes | Unique key within this runtime + user (max 128 chars) |
| `title` | No | Human-readable title (max 255 chars) |
| `content_text` | No | Text content for LLM grounding |
| `content_json` | No | Structured data (default: `{}`) |
| `confidence` | No | Confidence score 0.0-1.0 |
| `effective_at` | No | When this summary became valid |
| `expires_at` | No | When this summary should be considered stale |

## Context bundles

Pull a unified, ranked projection of all user context - profile, apps,
capabilities, and external runtime data - in one call.

### JSON format

```bash
curl -X POST "${NEXO_BASE_URL}/api/context/bundle" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "include_profile": true,
    "include_apps": true,
    "include_capabilities": true,
    "max_items": 50
  }'
```

Response:

```json
{
  "version": "2026-04",
  "generated_at": "2026-04-25T10:00:00Z",
  "user_id": "uuid",
  "items": [
    {
      "source": "capability",
      "key": "predictions",
      "type": "capability",
      "content": "Match Predictions - Predict World Cup 2026 match outcomes",
      "confidence": 1.0,
      "timestamp": null
    },
    {
      "source": "external_runtime",
      "key": "recent-predictions",
      "type": "summary",
      "content": "User predicted 3 matches this week, 2 correct.",
      "confidence": 0.95,
      "timestamp": "2026-06-01T00:00:00Z"
    },
    {
      "source": "profile",
      "key": "language",
      "type": "fact",
      "content": "Preferred language: Spanish",
      "confidence": 1.0,
      "timestamp": null
    }
  ],
  "total_tokens_estimate": 342
}
```

### Markdown format

```bash
curl "${NEXO_BASE_URL}/api/context/bundle.md" \
  -H "Authorization: Bearer ${TOKEN}"
```

Returns a plain-text markdown document suitable for injecting directly into an
LLM system prompt.

### Item sources

Items are drawn from four sources, in priority order:

1. **capability** - app capabilities from the manifest
2. **profile** - user facts and preferences
3. **app** - personalized app summaries
4. **external_runtime** - capabilities and typed summaries from linked runtimes

The builder ranks items by source priority and caps at `max_items`. The
`total_tokens_estimate` field helps budget context window usage.

## Knowledge Pack sync

For reference data that your runtime maintains (product catalogs, match
fixtures, team rosters), use [Knowledge Packs](knowledge-packs.md).

### Sync workflow

```
1. Register a source:  POST /api/knowledge-packs/{pack_id}/sources
2. Start sync:         PATCH .../sources/{source_id}/sync  {"sync_status": "syncing"}
3. Bulk import:        POST .../datasets/{dataset_id}/records/bulk
4. Complete sync:      PATCH .../sources/{source_id}/sync  {"sync_status": "synced", "content_hash": "..."}
5. Run projections:    POST /api/projections/apps/{app_id}/definitions/{def_id}/run
```

On error, set `sync_status` to `"error"` with a `last_error` message.

### Source status lifecycle

```
pending -> syncing -> synced
                   -> error -> syncing (retry)
```

Track `content_hash` and `version_tag` to detect whether new data actually
changed and avoid unnecessary projection reruns.

### Example: seeding reference data (TypeScript)

```typescript
const nexo = new NexoClient();
await nexo.authenticate();

// Find the Knowledge Pack for your app
const packs = await nexo.listKnowledgePacks(appId);
const pack = packs[0];

// Upsert records by key (idempotent)
for (const team of teams) {
  await nexo.upsertRecord(
    pack.id,
    "teams",          // dataset key
    `team-${team.code}`,
    {
      name: team.name,
      code: team.code,
      group: team.group,
    },
    `${team.name} ${team.code}`,  // search_text for future retrieval
  );
}
```

See [Knowledge Packs](knowledge-packs.md) for the full API reference including
projections, bulk imports, and MCP inspection tools.

## Worker/job topology

For data that needs to stay fresh (match scores, stock prices, weather), run a
background sync job on a schedule.

### Recommended architecture

```
Cloud Scheduler (cron)
  -> Cloud Run Job (your sync code)
    -> Nexo API (Knowledge Packs, capability sync, context summaries)
    -> External provider (football-data.org, RSS feeds, etc.)
```

### Job types

| Job | Purpose | Schedule |
|---|---|---|
| **Seed** | One-time bootstrap of reference data | Manual / on deploy |
| **Sync** | Recurring provider fetch + Nexo upsert | Every 15 min (active) / daily (idle) |
| **Recompute** | Deterministic derived outputs | After sync completes |

### Job implementation pattern

Each job follows the same structure:

```typescript
async function main() {
  // 1. Authenticate with Nexo
  const nexo = new NexoClient({
    apiUrl: process.env.NEXO_API_URL,
  });
  await nexo.authenticate(process.env.NEXO_DEVELOPER_KEY);

  // 2. Fetch from external provider (if applicable)
  const data = await fetchFromProvider();

  // 3. Upsert into Nexo Knowledge Packs
  for (const record of data) {
    await nexo.upsertRecord(packId, datasetId, record.key, record.data);
  }

  // 4. Sync capability metadata
  await nexo.syncCapability(runtimeKey, "my-capability", "My Capability", "...");

  // 5. Exit cleanly (Cloud Run Job semantics)
  console.log("Sync complete.");
}

main().catch((err) => {
  console.error("Job failed:", err);
  process.exit(1);
});
```

### Deployment model

Use a single Docker image for both the HTTP service and background jobs.
Override the entrypoint per job:

```yaml
# Cloud Run service (HTTP)
gcloud run deploy my-service --image $IMAGE

# Cloud Run job (sync)
gcloud run jobs update my-sync-job \
  --image $IMAGE \
  --command "node" \
  --args "dist/jobs/sync-reference-data.js" \
  --set-secrets "NEXO_DEVELOPER_KEY=nexo-developer-key:latest"
```

### Credentials

- Store `NEXO_DEVELOPER_KEY` in **GCP Secret Manager**, not GitHub Secrets.
- Inject secrets into Cloud Run Jobs via `--set-secrets`.
- Store provider API keys (`FOOTBALL_DATA_API_KEY`, etc.) in the same Secret
  Manager project.
- GitHub repository variables hold workflow config (WIF provider, service
  accounts, project/region). GitHub Secrets hold only the minimum needed for
  CI/CD auth (typically nothing, when using Workload Identity Federation).

### Error handling

- Set source status to `"error"` with `last_error` on failure.
- Exit with non-zero code so Cloud Scheduler records the failure.
- Use content hashing to skip no-op syncs.
- Log structured output for Cloud Logging.

## Companion services

Some apps need domain-specific intelligence beyond what Nexo provides natively
(prediction suggestions, expert Q&A, provider-specific analysis).

### Design rules

Companion services follow the same partner-integration shape as all
runtime-backed apps:

- **Thin and stateless** - all persistent state lives in Nexo (app tables,
  Knowledge Packs)
- **App-secret authenticated** - use `X-App-Secret` for webhook/companion calls
- **Nexo as the substrate** - predictions, competitions, reference data, and
  user state all live in Nexo
- **No separate backend family** - even chat-like "Ask Expert" features should
  be a companion endpoint, not a standalone backend

### Ask Expert / chat-like companions

An "Ask Expert" feature (AI-powered Q&A about your domain) is a companion
capability, not a separate system:

```
User question -> Nexo webhook dispatch -> Companion service
  -> Reads Knowledge Pack data for grounding
  -> Calls LLM with domain context
  -> Returns response via standard webhook envelope
```

Before building a custom retrieval stack, prove how far live-updated Knowledge
Packs can go for RAG-like grounding. Knowledge Pack records include
`search_text` and `markdown_projection` fields designed for this purpose.

### Example companion endpoints

```
GET  /matches/:id/suggestions  - AI prediction suggestions
GET  /matches/:id/questions    - Contextual prompt chips
POST /ask-expert               - Domain-expert Q&A
```

These are optional thin endpoints. The core app loop (CRUD, reference data,
derived outputs) always runs through Nexo directly.

## End-to-end integration flow

Putting it all together, here is the full lifecycle for an external runtime:

```
1. Register runtime         (admin: POST /api/account-linking/runtimes)
2. Link user accounts       (user: initiate -> verify)
3. Sync capabilities        (worker: PUT /api/external-sync/capabilities)
4. Push context summaries   (worker: PUT /api/external-sync/context-summaries)
5. Seed Knowledge Packs     (job: bulk upsert into datasets)
6. Schedule recurring sync  (Cloud Scheduler -> Cloud Run Job)
7. Pull context bundles     (runtime: POST /api/context/bundle)
8. Discover capabilities    (runtime: GET /api/capabilities/manifest)
```

Steps 3-6 run in your background worker. Steps 7-8 run in your interactive
runtime at query time.

## Reference implementation

The [WC2026 Predictor](https://github.com/The-Wordlab/worldcup-server) is the
canonical reference implementation. It demonstrates:

- `src/nexo/client.ts` - TypeScript Nexo client with key-exchange auth
- `src/jobs/seed-to-nexo.ts` - Bootstrap job that seeds Knowledge Packs
- `src/jobs/sync-reference-data.ts` - Recurring-sync foundation: capability
  registration is wired, provider fetch still needs implementation
- `src/jobs/recompute-standings.ts` - Deterministic derived output computation
- `.github/workflows/deploy.yml` - Cloud Run service + jobs deploy/update
  workflow foundation
- `docs/custom-service-seam.md` - Companion service design

## Related docs

- [Developer Auth](developer-auth.md) - get and use a developer key
- [Capability Discovery](capability-discovery.md) - the capability manifest
- [Knowledge Packs](knowledge-packs.md) - reference data management
- [API Reference](partner-api-reference.md) - full endpoint reference
- [Live Streaming Architecture](design-live-streaming.md) - push event patterns
