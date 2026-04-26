# Nexo Partner Identity Bridge - Example

A reference implementation showing how a partner with phone-based authentication
(e.g. WhatsApp OTP) links their users into Nexo. The partner server authenticates
the user locally, then calls Nexo's Identity Bridge API with HMAC-signed requests
to create or retrieve a Nexo identity for that phone number.

## Architecture

```
Browser                Partner Server (:4100)              Nexo API (:8000)
  |                          |                                  |
  |  GET /auth/login         |                                  |
  |------------------------->|                                  |
  |  <phone input form>      |                                  |
  |<-------------------------|                                  |
  |                          |                                  |
  |  POST /auth/request-code |                                  |
  |  phone=+34612345678      |                                  |
  |------------------------->|                                  |
  |  validate E.164          |                                  |
  |  create OTP (demo: fixed)|                                  |
  |  <OTP entry form>        |                                  |
  |<-------------------------|                                  |
  |                          |                                  |
  |  POST /auth/verify-code  |                                  |
  |  phone=...&code=123456   |                                  |
  |------------------------->|                                  |
  |  verify OTP              |                                  |
  |                          |  POST /api/identity-bridge/      |
  |                          |       link-start                 |
  |                          |  X-App-Id: <uuid>                |
  |                          |  X-App-Secret: <secret>          |
  |                          |  X-Timestamp: <unix_ts>          |
  |                          |  X-Signature: sha256=<hmac>      |
  |                          |  {phone_e164, external_user_id}  |
  |                          |--------------------------------->|
  |                          |  {link_status, nexo_user_id,     |
  |                          |   access_token}                  |
  |                          |<---------------------------------|
  |  <success page>          |                                  |
  |<-------------------------|                                  |
```

## Security model

- **HMAC-SHA256 request signing** - every request to Nexo includes an
  `X-Signature` header computed as `sha256=HMAC(secret, "{timestamp}.{body}")`.
  This matches the signing scheme in Nexo's `webhook_signing.py`.
- **No secrets in the browser** - the partner server holds the webhook secret
  and makes all Nexo API calls server-side.
- **Server-side token management** - the Nexo access token is received and
  stored server-side. The browser never sees raw tokens (in this demo they are
  shown truncated for illustration).
- **Replay protection** - the timestamp in the signed payload allows Nexo to
  reject requests outside a tolerance window.

## Prerequisites

- A running Nexo instance (default: `http://localhost:8000`)
- A Nexo app with a `webhook_secret` configured
- Node.js 22+

## Quick start

```bash
cd examples/identity-bridge
cp .env.example .env
# Edit .env with your Nexo app ID and webhook secret

pnpm install
pnpm dev

# Open http://localhost:4100/auth/login
```

## How it works

1. **Phone entry** - the user enters their phone number in E.164 format
   (e.g. `+34612345678`).

2. **OTP verification** - in this demo the code is always `123456`. A real
   partner would send an SMS or WhatsApp message via their existing OTP flow.

3. **Identity linking** - after successful OTP verification, the partner server
   calls Nexo's `POST /api/identity-bridge/link-start` with:
   - `phone_e164` - the verified phone number
   - `external_user_id` - the partner's internal user ID for this phone
   - `metadata` - optional display name, locale, etc.

4. **Response handling** - Nexo returns one of:
   - `link_status: "new"` - a new Nexo user was created and linked
   - `link_status: "linked"` - this phone was already linked, returning
     existing credentials
   - `link_status: "confirm_required"` - the phone is linked to a different
     Nexo account; user confirmation needed (via `link-confirm`)

5. **Token usage** - the partner stores the `access_token` and `nexo_user_id`
   server-side, using them for subsequent Nexo API calls on behalf of this user.

## API reference

All requests require these headers:

| Header | Value |
|--------|-------|
| `X-App-Id` | Partner's Nexo app UUID |
| `X-App-Secret` | Partner's webhook secret |
| `X-Timestamp` | Unix timestamp (integer seconds) |
| `X-Signature` | `sha256={HMAC-SHA256(secret, "{timestamp}.{body}")}` |

### POST /api/identity-bridge/link-start

```bash
BODY='{"phone_e164":"+34612345678","external_user_id":"partner-34612345678","metadata":{"display_name":"User 5678","locale":"en"}}'
TS=$(date +%s)
SIG=$(echo -n "${TS}.${BODY}" | openssl dgst -sha256 -hmac "$NEXO_WEBHOOK_SECRET" | awk '{print $2}')

curl -X POST http://localhost:8000/api/identity-bridge/link-start \
  -H "Content-Type: application/json" \
  -H "X-App-Id: $NEXO_APP_ID" \
  -H "X-App-Secret: $NEXO_WEBHOOK_SECRET" \
  -H "X-Timestamp: $TS" \
  -H "X-Signature: sha256=$SIG" \
  -d "$BODY"
```

### POST /api/identity-bridge/link-confirm

```bash
BODY='{"link_session_id":"<session-id>","confirmed":true}'
TS=$(date +%s)
SIG=$(echo -n "${TS}.${BODY}" | openssl dgst -sha256 -hmac "$NEXO_WEBHOOK_SECRET" | awk '{print $2}')

curl -X POST http://localhost:8000/api/identity-bridge/link-confirm \
  -H "Content-Type: application/json" \
  -H "X-App-Id: $NEXO_APP_ID" \
  -H "X-App-Secret: $NEXO_WEBHOOK_SECRET" \
  -H "X-Timestamp: $TS" \
  -H "X-Signature: sha256=$SIG" \
  -d "$BODY"
```

### POST /api/identity-bridge/token-refresh

```bash
BODY='{"external_user_id":"partner-34612345678"}'
TS=$(date +%s)
SIG=$(echo -n "${TS}.${BODY}" | openssl dgst -sha256 -hmac "$NEXO_WEBHOOK_SECRET" | awk '{print $2}')

curl -X POST http://localhost:8000/api/identity-bridge/token-refresh \
  -H "Content-Type: application/json" \
  -H "X-App-Id: $NEXO_APP_ID" \
  -H "X-App-Secret: $NEXO_WEBHOOK_SECRET" \
  -H "X-Timestamp: $TS" \
  -H "X-Signature: sha256=$SIG" \
  -d "$BODY"
```

### GET /api/identity-bridge/link-status

```bash
TS=$(date +%s)
SIG=$(echo -n "${TS}." | openssl dgst -sha256 -hmac "$NEXO_WEBHOOK_SECRET" | awk '{print $2}')

curl http://localhost:8000/api/identity-bridge/link-status?external_user_id=partner-34612345678 \
  -H "X-App-Id: $NEXO_APP_ID" \
  -H "X-App-Secret: $NEXO_WEBHOOK_SECRET" \
  -H "X-Timestamp: $TS" \
  -H "X-Signature: sha256=$SIG"
```

## Adapting for production

This example uses simplified implementations for clarity. For production:

| Demo shortcut | Production replacement |
|---------------|----------------------|
| Fixed OTP code (`123456`) | Real SMS/WhatsApp OTP via Twilio, Vonage, or similar |
| In-memory OTP store | Redis or database-backed store with TTL |
| No session management | Express sessions or JWT-based session with httpOnly cookies |
| No rate limiting | Rate limit OTP requests per phone and per IP |
| Server-side template rendering | Your existing frontend framework |
| No persistent token storage | Store `nexo_user_id` and `access_token` in your user database |
| Console logging | Structured logging (pino, winston) |

## Cross-language signing verification

The HMAC signing in `src/lib/signing.ts` must produce identical output to
Nexo's Python `webhook_signing.py`. To verify:

```python
# Python
import hmac, hashlib
secret = "nexo-test-secret"
payload = '1700000000.{"test":true}'
digest = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
print(f"sha256={digest}")
```

```typescript
// TypeScript
import { signRequest } from "./src/lib/signing";
const { signature } = signRequest("nexo-test-secret", '{"test":true}', 1700000000);
console.log(signature);
```

Both must produce the same `sha256=...` string. The test suite includes a
cross-language test vector that logs the TypeScript output for comparison.

## Running tests

```bash
pnpm test        # run once
pnpm test:watch  # watch mode
```

## Building and running with Docker

```bash
docker build -t nexo-identity-bridge-example .
docker run -p 4100:4100 \
  -e NEXO_API_URL=http://host.docker.internal:8000 \
  -e NEXO_APP_ID=<your-app-uuid> \
  -e NEXO_WEBHOOK_SECRET=<your-webhook-secret> \
  nexo-identity-bridge-example
```
