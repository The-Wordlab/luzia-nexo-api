# WIP

**Updated:** 2026-05-08

## Status

Public example inventory is lean and explicit. The repo treats webhook apps,
hosted reference APIs, integration utilities, and the checked-in app SDK mirror
as separate public surfaces.

## Current state

- One unified app model framing in README and docs/index.md
- Auth bridge doc updated with hosted profile/logout follow-through and the
  signed app-header exchange contract (`/api/apps/structured/apps/{connected_app_id}/auth-handoffs/exchange`)
- Public inventory now centers:
  - webhook app examples (`minimal`, `structured`, `advanced`, `food-ordering`, `openclaw-bridge`)
  - hosted reference APIs (`hosted/python`, `hosted/typescript`)
  - integration utilities (`identity-bridge`, `partner-api/proactive`)
- SDK mirror (`sdk/nexo-sdk`) synced from
  `../luzia-nexo-apps/apps/nexo-sdk`
  - treat `luzia-nexo-apps` as the only source of truth for hosted app SDK
    transport and site-config changes
  - current mirror tracks the canonical A2A transport, message-shaped webhook
    payload, session-context helpers, hosted-session-first first-party auth
    with direct-API fallback for standalone CDN entry,
    `Agent*` browser surface, and `App*` server naming
  - the shared SDK surface no longer ships `Companion*` or `MicroApp*`
    compatibility naming
  - do not hand-edit the mirror here; resync it when the source SDK changes
- External-runtime public docs now use `agent` / `app agent` naming for
  app-specific intelligence instead of older legacy terminology
- Identity Bridge positioning now follows the slug-scoped hosted utility model:
  the partner-owned auth layer should hand off into `/apps/{slug}/auth`,
  `/apps/{slug}/profile`, and `/apps/{slug}/onboarding` rather than living as a
  separate long-term account UX
- Signing contract unchanged (X-App-Id + X-App-Secret + HMAC)
- A2A example compliance tests now use canonical agent-card naming
- Provisioning endpoint (`POST /api/apps/structured/provision`) documented
- MCP provision_app tool documented
- Knowledge Packs developer guide shipped

## Next

- Keep the public example inventory lean and accurate as examples evolve
- Keep the checked-in SDK mirror synced from `../luzia-nexo-apps/apps/nexo-sdk`
  whenever hosted app transport, auth/profile/onboarding URLs, or site-config
  behavior changes
- Decide whether lightweight public app-shell consumers should live under
  `examples/apps/` on top of the mirrored SDK
- Shape the first partner-facing identity-bridge example around the
  `luziaclaw` login/session model so the example demonstrates partner auth
  handing off cleanly into Nexo-hosted app utility pages
- Decide whether the next public serverless app example should be a thin
  food-ordering app shell on the mirrored SDK
- Update remaining doc pages for unified model framing where still needed
- Add "Getting Started: Create Your First App" guide showing one-call
  provisioning
- Clean legacy mid-file imports in examples/scripts incrementally now that a
  diff-aware import-placement guard is in place for new Python and JS/TS
  changes; keep only explicit documented exceptions
