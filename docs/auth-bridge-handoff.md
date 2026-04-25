# External App Auth Bridge (Phase 1 Internal)

This page documents the Nexo-owned login and handoff pattern for
externally hosted apps.

It is **not** a broadly shipped public API contract yet. The current state is:

- the phase-1 internal Luzia-owned slice is now real in `luzia-nexo`
- the public builder posture is still conservative and non-self-serve

The goal of this page is to explain the integration model so builders and
internal teams do not invent one-off app login flows while the platform work
is landing.

## Availability

Phase 1 is intentionally conservative:

- Luzia org-owned apps only
- not a generic partner-integration feature yet

This page explains the intended model, but partner builders should not assume
the capability is self-serve or broadly enabled in the first release.

## Current proving slice

One adjacent runtime slice has already been real in Nexo:

- browser-facing Ask Expert turns can already enter Nexo first from a
  Personalized App surface
- Nexo resolves an **approved linked Connected App** companion through
  initiative metadata plus `linked_app_ids`
- Nexo restores the same companion thread from its own thread/message store

That proves the runtime half of the external-app shape:

`browser -> Nexo -> linked Connected App companion`

And the next auth-bridge slice is now also real for the phase-1 internal path:

- `POST /api/micro-apps/{app_id}/auth-handoffs`
- `POST /api/apps/{connected_app_id}/auth-handoffs/exchange`
- Nexo auth pages preserve bridge state and continue automatically after
  login/register
- if browser web does not provide a `device_key`, Nexo now synthesizes and
  persists a stable web-scoped key on the Nexo domain

The remaining work is the first full proving flow:

- user-facing hosted login entry in the proving app
  - now wired in WC2026 through `/auth/apps/start`
  - hosted app public config now treats `auth_base_url` as an explicit part of
    the contract instead of guessing the auth origin from the API host
- guest-adoption continuity
- Ask Expert thread continuity across guest -> login
- broader operator posture and later partner availability

## What problem this solves

Some apps want to:

- host their own web frontend
- let Nexo handle Google login, registration, and identity scaffolding
- return control to the app without sharing cookies across domains

Examples:

- a hosted WC2026 predictor frontend
- future app families that want a branded surface but still rely on Nexo for
  auth and canonical app state

## Product direction

Nexo should act as the **auth bridge** for externally hosted apps.

That means:

1. the user starts from the hosted app
2. the app sends the user to a Nexo-owned login page
3. Nexo handles login, registration, linking, and required account setup
4. Nexo redirects back to the app backend with a short-lived one-time code
5. the app backend exchanges that code with Nexo and creates its own session

This keeps:

- Nexo as the identity and bootstrap layer
- the hosted app as the UI layer
- the app backend as the place where the app cookie/session is created
- room for a later thin compatibility layer that can forward selected client
  auth/chat calls to Nexo without creating a second runtime or second thread
  store

Important rule:

- **login is not always the same as app access**
- for open/default Luzia-owned apps, the bridge may create the app-access edge
  during callback
- for gated apps, such as invite-only or code-required entry, the bridge may
  authenticate the user first and return an access state that still requires
  invite completion or approval
- for gated apps, the bridge should still create or preserve a canonical
  `pending` membership edge so the user is captured in the app's waiting-list
  path instead of being blocked anonymously

## Why not shared cookies or iframe auth

The planned contract is:

- top-level redirect or popup
- one-time handoff code
- backend callback exchange

It is **not**:

- shared cookies across unrelated domains
- long-lived tokens in query params
- iframe-first login

This avoids fragile browser storage behavior and keeps the security boundary
clean.

## Web flow

### 1. Start on the hosted app

The hosted app sends the browser to a Nexo-owned auth page with:

- `app_id`
- allowlisted callback URL
- opaque `state`
- a stable `device_key` when already available
- optional in-app resume path (`next`)

### 2. Nexo handles auth

Nexo performs:

- Google or password login
- registration if needed
- required account scaffolding
- app entry-policy evaluation
- app access setup when policy allows it

The external app does not need to implement Google OAuth directly for this
flow.

For browser web, if the hosted app does not already have a stable
installation-scoped `device_key`, Nexo can synthesize and persist a stable
web-scoped key during bridge start instead of requiring the caller to invent
one first.

### 3. Nexo redirects to the app backend

After auth, Nexo redirects to an app backend callback such as:

```text
GET /auth/nexo/callback?code=<one-time-code>&state=<state>
```

The callback should be a backend route, not a browser-only page.

### 4. App backend exchanges with Nexo

The app backend exchanges the one-time code with Nexo and sets its own app
session.

The server-side credential for this exchange should be the **same existing app
secret** already used for Partner API webhook signing and `X-App-Secret`
authentication.

Do not use a developer key for this runtime flow.

If the app already knows useful external identity anchors, the backend exchange
or immediate follow-on enrichment step should also be able to send:

- `external_runtime_key`
- `external_user_id`
- `phone_e164`

Nexo should associate those values with the resulting canonical user/app link
for future routing, linking, or repair. They are correlation data, not the
credential.

The exchange should also be able to return a truthful access result, for
example:

- access granted immediately for open/default apps
- invite code required
- invite required
- pending approval

## Guest continuity

This planned contract should also cover guest-to-user continuity.

If an app already supports guest usage before login:

- Nexo-native guest flows should use a Nexo-owned adoption path
- apps with guest state in an external or legacy database must provide a
  server-side mapping or migration boundary during exchange

The auth bridge helps by giving one canonical identity boundary and one secure
callback/exchange contract.

It does **not** automatically migrate arbitrary external guest stores by
itself.

If a legacy app can still ship one more version before replacement, forcing the
user through the Nexo auth bridge at "continue chatting" time is a strong
migration lever because the app can capture guest correlation data and pass it
server-to-server during the exchange flow.

The first proving path should go beyond simple login success. A good proof is
an app where conversation continuity matters, such as Ask Expert in WC2026:

- login starts from the hosted app
- Nexo handles auth and callback
- the app resumes on the intended route
- conversation history survives because thread truth is anchored in Nexo-owned
  state
- the browser-facing runtime path should continue to enter through Nexo rather
  than bypassing it with a direct companion webhook call

## Streaming posture

For conversational surfaces, the browser-facing path should eventually call
Nexo first and let Nexo dispatch to companion services server-to-server.

The client-facing stream should keep a small shared core:

- `stream_start`
- `content_delta`
- `done`
- `error`

Nexo-specific additions such as cards, actions, artifacts, and richer content
metadata should remain additive extensions rather than becoming mandatory for
basic client rendering.

Nexo should forward text deltas immediately as they arrive from the companion
service. Do not buffer the full response before streaming text to the client.

## Future compatibility layer

A later compatibility layer may preserve an existing client-facing API while
forwarding selected chat or auth calls to Nexo underneath.

If that happens, keep the layer thin:

- no second thread store
- no second message persistence path
- no full-response buffering before SSE forwarding
- no reimplementation of companion orchestration outside Nexo

### 5. Resume the app

After exchange, the app backend:

- sets its own session cookie
- optionally fetches additional bootstrap/profile data from Nexo
- redirects the browser back to the intended page

If access is gated, the callback should still be able to resume the app on a
route that finishes the gate instead of pretending login automatically granted
app access.

## Native / in-app flow

Native should stay distinct at the entry point.

Recommended posture:

- keep the host app's own login/session model
- request a Nexo launch handoff when opening a webview or companion experience
- reuse the same short-lived code and bootstrap concepts

So web and native share the handoff core, but not necessarily the same UX.

## `device_key`

The planned contract preserves `device_key` as a binding key.

Use it for:

- browser-install or device continuity
- binding the handoff to a concrete client
- later thread/app-user correlation where needed

Do **not** treat `device_key` as the credential by itself.

## External identity correlation

Some apps will already know an external user anchor when the callback happens.

Examples:

- a hosted app has its own external account ID
- a phone number has already been verified upstream

The planned contract should let the app backend associate those values with the
Nexo-side entity created during auth.

Recommended posture:

- attach them server-to-server during exchange or follow-on enrichment
- store them as linked correlation data on the Nexo side
- do not use them as standalone browser credentials

## Secret model

The intended model is:

- browser: no secrets
- Nexo auth page: Nexo session only
- app backend: the existing app `webhook_secret`

The same app secret should cover:

- webhook signing and verification
- `X-App-Secret` server-to-server calls
- auth-bridge exchange and secure enrichment

This means the dashboard should present it as one app runtime secret, not as
separate webhook and auth-bridge secrets unless that decision changes later.

## What is already true today

- Nexo already owns Google login and account scaffolding
- externally hosted apps already use Nexo bootstrap and domain-session patterns
- launch/handoff concepts already exist in the Nexo runtime

## What is still planned

The reusable public contract is still being finalized:

- exact auth start URL
- exact exchange endpoint
- exact response payload
- exact callback allowlist model

Until that lands, treat this page as the intended direction, not as a copy-paste
integration reference.

## Related docs

- [External Runtime Integration](external-runtime-integration.md)
- [Partner API Reference](partner-api-reference.md)
- [Micro Apps API](micro-apps-api.md)
- [Capability Discovery](capability-discovery.md)
