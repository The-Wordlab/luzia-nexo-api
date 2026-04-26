# Partner Identity Bridge Example PRD

**Status:** Shaping
**Updated:** 2026-04-26

## Problem

Partners that run their own auth systems (phone/WhatsApp OTP, custom SSO,
magic links, etc.) need a way to link their users into the Nexo identity graph
so those users can access Nexo-powered features - chat, profile, apps,
personalization - without a second login.

Nexo already has the substrate:

- `ExternalRuntime` registration for partner systems
- `ExternalAccountLink` (phone + external_user_id mapped to Nexo user)
- `LinkSession` (short-lived verification session with status tracking)
- HMAC-SHA256 webhook signing (`X-Timestamp` + `X-Signature` headers)
- Auth handoff exchange proven by WC2026

But there is no reference implementation a partner can follow. A partner with
WhatsApp-based login cannot see how to link their verified phone identity into
Nexo and get a usable token back.

## Proposal

Build a **Partner Identity Bridge** reference example in `luzia-nexo-api` that
demonstrates how an external system with its own auth links identities into
Nexo. The example is generic - not tied to any specific partner brand.

The example is a TypeScript/Express backend (same stack as `worldcup-server`)
that shows the complete flow: phone collection, mock OTP verification, signed
Nexo API calls, token management, and error handling.

## Security model

Every request between the partner backend and Nexo is authenticated and
integrity-checked. No secrets touch the browser.

### Server-to-server auth

All partner-to-Nexo API calls use the same HMAC signing scheme as webhook
dispatch:

| Header | Value |
|--------|-------|
| `X-App-Id` | The partner's Nexo app UUID |
| `X-App-Secret` | The partner's `webhook_secret` (verified against bcrypt hash on Nexo side) |
| `X-Timestamp` | Unix timestamp (integer seconds) |
| `X-Signature` | `sha256={HMAC-SHA256(webhook_secret, "{timestamp}.{raw_body}")}` |

Nexo validates:
1. `X-App-Id` resolves to a real app
2. `X-App-Secret` matches the app's stored `webhook_secret` (bcrypt verify)
3. `X-Timestamp` is within a 5-minute drift window (replay protection)
4. `X-Signature` matches the HMAC of the timestamp + request body

This is the same signing contract Nexo already uses for outbound webhook
delivery (`backend/app/services/webhook_signing.py`), now applied in reverse
for inbound partner calls.

### Token scoping

The access token returned by `link-start` is a standard Nexo JWT scoped to the
linked user. The partner backend stores this token server-side and proxies Nexo
API calls - the token never reaches the end-user's browser.

### Phone verification ownership

Nexo never sends OTPs. The partner owns the entire phone verification flow
(WhatsApp, SMS, or any other channel). Nexo trusts the partner's assertion that
the phone is verified, backed by the HMAC-signed request proving the call came
from the registered partner backend.

## Flow

```
User                Partner frontend        Partner backend              Nexo
----                ----------------        ---------------              ----

1. Opens app
2. Enters phone     POST /auth/request-code
                                            3. Sends OTP via
                                               WhatsApp/SMS
4. Enters OTP       POST /auth/verify-code
                                            5. Verifies OTP
                                            6. Has: phone_e164
                                               + partner_user_id

                                            7. POST /api/identity-bridge/link-start
                                               (signed: X-App-Id, X-App-Secret,
                                                X-Timestamp, X-Signature)
                                               body: { phone_e164, external_user_id,
                                                       provider, metadata }

                                                                        8. Lookup phone in
                                                                           ExternalAccountLink

                                            9a. status=linked           <-- already linked
                                                nexo_user_id, token

                                            9b. status=new              <-- auto-provisioned
                                                nexo_user_id, token

                                            9c. status=confirm_required <-- phone known to
                                                hint: "m***@gmail.com"     another Nexo account

                                            (if 9c) show user the hint
10. Confirms merge  POST /auth/confirm-link
                                            11. POST /api/identity-bridge/link-confirm
                                                (signed)

                                            12. status=linked
                                                nexo_user_id, token

                                            13. Store nexo_user_id +
                                                token server-side
14. Logged in,
    Nexo features
    available
```

## API contract (Nexo side)

### `POST /api/identity-bridge/link-start`

Partner calls this after verifying the user's phone.

**Auth:** `X-App-Id` + `X-App-Secret` + `X-Timestamp` + `X-Signature`

**Request:**
```json
{
  "phone_e164": "+34612345678",
  "external_user_id": "partner-uid-abc123",
  "metadata": {
    "display_name": "Maria",
    "locale": "es"
  }
}
```

**Response - new user (auto-provisioned):**
```json
{
  "link_session_id": "uuid",
  "link_status": "new",
  "nexo_user_id": "uuid",
  "access_token": "eyJ...",
  "token_expires_in": 3600
}
```

**Response - already linked:**
```json
{
  "link_session_id": "uuid",
  "link_status": "linked",
  "nexo_user_id": "uuid",
  "access_token": "eyJ...",
  "token_expires_in": 3600
}
```

**Response - phone known to existing Nexo user, needs confirmation:**
```json
{
  "link_session_id": "uuid",
  "link_status": "confirm_required",
  "existing_user_hint": "m***@gmail.com"
}
```

### `POST /api/identity-bridge/link-confirm`

Partner confirms the merge after showing the user the masked hint.

**Auth:** `X-App-Id` + `X-App-Secret` + `X-Timestamp` + `X-Signature`

**Request:**
```json
{
  "link_session_id": "uuid",
  "confirmed": true
}
```

**Response:**
```json
{
  "link_status": "linked",
  "nexo_user_id": "uuid",
  "access_token": "eyJ...",
  "token_expires_in": 3600
}
```

### `POST /api/identity-bridge/token-refresh`

Partner requests a fresh token for an already-linked user.

**Auth:** `X-App-Id` + `X-App-Secret` + `X-Timestamp` + `X-Signature`

**Request:**
```json
{
  "external_user_id": "partner-uid-abc123"
}
```

**Response:**
```json
{
  "nexo_user_id": "uuid",
  "access_token": "eyJ...",
  "token_expires_in": 3600
}
```

### `GET /api/identity-bridge/link-status?external_user_id=X`

Check the current link status for a partner user.

**Auth:** `X-App-Id` + `X-App-Secret` + `X-Timestamp` + `X-Signature`

**Response:**
```json
{
  "linked": true,
  "nexo_user_id": "uuid",
  "phone_e164": "+34612345678",
  "linked_at": "2026-04-26T12:00:00Z"
}
```

### Error responses

| Status | Detail key | When |
|--------|-----------|------|
| 401 | `ERROR_INVALID_APP_SECRET` | Bad secret or signature |
| 400 | `ERROR_INVALID_PHONE` | Phone not in E.164 format |
| 400 | `ERROR_MISSING_EXTERNAL_USER_ID` | No external_user_id provided |
| 404 | `ERROR_LINK_SESSION_NOT_FOUND` | Invalid or expired link_session_id |
| 409 | `ERROR_LINK_SESSION_EXPIRED` | Session TTL exceeded |
| 409 | `ERROR_ALREADY_LINKED_DIFFERENT_USER` | external_user_id already linked to a different phone |

## Example implementation (TypeScript, in luzia-nexo-api)

### Stack

Same as `worldcup-server`: Express + TypeScript, vitest for tests, no
framework beyond what the reference example needs.

### File structure

```
examples/identity-bridge/
  src/
    index.ts              # Express app entry
    config.ts             # Env config (NEXO_API_URL, APP_ID, WEBHOOK_SECRET)
    nexo-client.ts        # Typed Nexo identity bridge API client with signing
    routes/
      auth.ts             # Phone login routes (request-code, verify-code, confirm-link)
      status.ts           # Health + link status check
    lib/
      signing.ts          # HMAC-SHA256 request signing (mirrors webhook_signing.py)
      phone.ts            # E.164 validation + country code helpers
      otp-store.ts        # In-memory mock OTP store (TTL, max attempts)
    views/
      login.html          # Phone input form (country picker + number)
      verify.html         # 6-digit OTP entry
      linked.html         # Success: shows linked identity + what Nexo features are available
  tests/
    signing.test.ts       # HMAC signing matches Nexo's Python implementation
    auth-flow.test.ts     # Full link flow: request -> verify -> link-start -> linked
    phone.test.ts         # E.164 validation edge cases
  package.json
  tsconfig.json
  Dockerfile
  README.md               # Full setup guide, architecture diagram, security notes
  .env.example
```

### Key modules

**`nexo-client.ts`** - Typed client for the identity bridge endpoints:
```typescript
import { signRequest } from "./lib/signing";

export class NexoIdentityBridgeClient {
  constructor(
    private apiUrl: string,
    private appId: string,
    private webhookSecret: string,
  ) {}

  async linkStart(phone_e164: string, external_user_id: string, metadata?: Record<string, string>) {
    return this.signedPost("/api/identity-bridge/link-start", {
      phone_e164, external_user_id, metadata,
    });
  }

  async linkConfirm(link_session_id: string) { ... }
  async tokenRefresh(external_user_id: string) { ... }
  async linkStatus(external_user_id: string) { ... }

  private async signedPost(path: string, body: unknown) {
    const rawBody = JSON.stringify(body);
    const { timestamp, signature } = signRequest(this.webhookSecret, rawBody);
    const resp = await fetch(`${this.apiUrl}${path}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-App-Id": this.appId,
        "X-App-Secret": this.webhookSecret,
        "X-Timestamp": String(timestamp),
        "X-Signature": signature,
      },
      body: rawBody,
    });
    // ... error handling
  }
}
```

**`lib/signing.ts`** - HMAC-SHA256 matching Nexo's Python implementation:
```typescript
import { createHmac } from "crypto";

export function signRequest(secret: string, rawBody: string, timestamp?: number) {
  const ts = timestamp ?? Math.floor(Date.now() / 1000);
  const signedPayload = `${ts}.${rawBody}`;
  const digest = createHmac("sha256", secret)
    .update(signedPayload)
    .digest("hex");
  return { timestamp: ts, signature: `sha256=${digest}` };
}

export function verifySignature(secret: string, rawBody: string, timestamp: number, signature: string): boolean {
  const { signature: expected } = signRequest(secret, rawBody, timestamp);
  // Constant-time comparison
  return expected.length === signature.length &&
    timingSafeEqual(Buffer.from(expected), Buffer.from(signature));
}
```

**`lib/otp-store.ts`** - Mock OTP for the demo (no real WhatsApp/SMS):
```typescript
// In-memory store. Fixed code "123456" in dev mode.
// Real partner would use Twilio, MessageBird, WhatsApp Business API, etc.
```

### README outline

1. **What this example does** - one paragraph
2. **Architecture diagram** - ASCII sequence diagram showing the full flow
3. **Prerequisites** - running Nexo instance, app registered with webhook_secret
4. **Quick start** - clone, configure .env, run, open browser
5. **Security model** - HMAC signing explained, no secrets in browser, token
   management server-side
6. **How to adapt for production** - replace mock OTP with real provider, add
   rate limiting, add phone validation, add session persistence (Redis/DB
   instead of in-memory)
7. **API reference** - each Nexo endpoint with curl examples
8. **Signing verification** - how to verify the TypeScript signing matches
   Nexo's Python signing (cross-language test)
9. **Troubleshooting** - common errors and fixes

## Implementation plan

### Phase 1: Nexo identity bridge endpoints (in luzia-nexo)

New module at `backend/app/modules/identity_bridge/` with:

1. `router.py` - FastAPI routes for the 4 endpoints
2. `service.py` - Business logic: phone lookup, user provisioning, link
   creation, conflict detection, token issuance
3. `schemas.py` - Pydantic request/response models
4. `auth.py` - HMAC signature verification (reuse webhook_signing.py)

Uses existing models (`ExternalRuntime`, `ExternalAccountLink`, `LinkSession`).
No new tables, no migrations.

Auth: all endpoints verify `X-App-Id` + `X-App-Secret` + `X-Timestamp` +
`X-Signature`. The `X-App-Secret` is verified against the app's bcrypt-hashed
`webhook_secret` (same as event delivery). The `X-Signature` HMAC is verified
against the raw `webhook_secret` (pre-hash) - the partner knows the plaintext
secret, Nexo stores the bcrypt hash for `X-App-Secret` and uses the plaintext
from `signing_secret` column for HMAC verification.

Tests: unit tests for each endpoint + signing verification.

### Phase 2: Example partner backend (in luzia-nexo-api)

TypeScript/Express app at `examples/identity-bridge/` with:

1. Phone login form with country code picker
2. Mock OTP verification (fixed code `123456`)
3. Nexo identity bridge client with HMAC signing
4. Success page showing linked identity
5. Vitest tests for signing + auth flow
6. Dockerfile for deployment
7. Comprehensive README with diagrams and curl examples

### Phase 3: Cross-language signing test

Verify that `lib/signing.ts` produces identical output to
`backend/app/services/webhook_signing.py` for the same inputs. Include a shared
test vector in both repos.

## Open questions

1. **Auto-provision vs gated** - should `link-start` always auto-create a Nexo
   user, or should the partner be able to configure whether unknown phones get
   auto-provisioned vs rejected?
   *Recommendation:* Auto-provision by default. Add an optional
   `auto_provision: false` flag for partners that want to restrict linking to
   existing Nexo users only.

2. **Guest upgrade** - if the user was previously a Nexo guest (e.g., used a
   domain-session), should `link-start` merge the guest state?
   *Recommendation:* Yes, use the existing `migrate_guest_to_user` service.
   Include an optional `guest_token` field in `link-start` for this.

3. **Token lifetime** - what should the default JWT lifetime be?
   *Recommendation:* 1 hour (3600s), matching the auth handoff exchange
   pattern. Partner can refresh via `token-refresh`.

4. **Rate limiting** - should the identity bridge endpoints be rate-limited?
   *Recommendation:* Yes, but not in the POC. Document the recommendation in
   the README and add it when the first real partner integrates.

5. **Multiple phones per user** - should a Nexo user be linkable via multiple
   phone numbers?
   *Recommendation:* Not in Phase 1. One phone per partner link. The
   `ExternalAccountLink` model supports it for future expansion.

## Definition of done

1. Nexo identity bridge endpoints work with existing models (no migrations)
2. All requests are HMAC-signed; timestamp drift and replay are rejected
3. Example TypeScript backend demonstrates phone login + signed bridge calls
4. Cross-language signing test proves TypeScript matches Python output
5. A developer can clone the example, configure `.env`, and see the full flow
   working against a local Nexo instance
6. README documents: architecture, security model, setup, API reference, curl
   examples, production adaptation guide
7. Tests cover: new user linking, existing user linking, conflict resolution,
   bad signature rejection, expired timestamp rejection
