# Hosted App Auth, Profile, and Onboarding

Use this pattern when an app keeps its own frontend or partner-owned first-step
login, but wants Nexo to own the canonical app-auth continuation, profile
surface, and onboarding flow.

The goal is simple:

1. the user starts from the app
2. the app enters Nexo through an app-scoped hosted route
3. Nexo handles login, profile, and onboarding in app context
4. Nexo returns the user to the app

This keeps identity, onboarding state, and profile behavior consistent across
Nexo apps while still allowing partner-specific login and session models.

## Hosted route family

Nexo's app-scoped hosted utility routes are:

- `/apps/{slug}/auth`
- `/apps/{slug}/auth/continue`
- `/apps/{slug}/profile`
- `/apps/{slug}/onboarding`

Use the app slug so Nexo can:

- keep the user in the correct app context
- prioritize the published CDN-hosted app URL by default
- validate return navigation safely
- render app-specific copy or branding where needed

## When to use this pattern

Use the hosted route family when:

- the app is hosted outside the main Nexo frontend
- the app wants Nexo-owned login continuation
- the app wants a canonical hosted profile page
- the app wants a canonical hosted onboarding flow
- the app should return to a specific in-app route after auth or setup

Examples:

- a published app shell served from the Nexo CDN
- a partner-owned frontend that needs a Nexo-owned profile/onboarding step
- a partner app such as `luziaclaw` that keeps a first-step login UX but should
  hand off into Nexo for app-scoped auth continuity

## Integration model

There are two common entry shapes.

### 1. Nexo-first app auth

The app sends the browser directly to:

```text
/apps/{slug}/auth?return_to=/target/path
```

Nexo handles login or registration, then continues to the app in the same app
context.

### 2. Partner-owned first-step auth + Nexo handoff

The partner authenticates the user first, then links or resolves the Nexo user
server-to-server. After that, the browser should still enter the Nexo hosted
app flow through the same slug-scoped route family.

That means the identity bridge is the server-side handoff, not a replacement
for Nexo's hosted app auth/profile/onboarding surfaces.

## Return navigation

The app should pass a relative in-app path such as:

```text
/apps/{slug}/auth?return_to=/competitions?invite_code=ABC123
```

Nexo should treat the slug as the app context and the `return_to` path as the
resume location inside that app context.

Recommended behavior:

- prefer the published CDN app URL when available
- allow additional app-owned return origins only when explicitly configured
- keep `return_to` relative rather than passing arbitrary absolute URLs from
  the browser

## Hosted profile and onboarding

`/apps/{slug}/profile` and `/apps/{slug}/onboarding` use the same underlying
user truth as login.

That means:

- profile is not a separate account system
- onboarding is not app-local one-off logic
- profile can include a clean CTA into onboarding when setup is incomplete
- onboarding completion can return the user to the app route they came from

This is the preferred way to keep profile and onboarding consistent across
first-party and partner-integrated apps.

## Session exchange posture

If the app backend needs a server-side session after Nexo auth continuation,
the exchange should use the app's server credential boundary, not a developer
key.

Use app credentials and signed server-to-server exchange flows for runtime
session creation. Developer keys are for tooling, MCP, and operator scripts,
not app runtime auth.

## Guest continuity

If the app supports guest usage before login:

- preserve guest continuity through the auth handoff
- return the user to the same app route after auth
- keep profile/onboarding in the same app context

Nexo should own the canonical user/app identity state. External guest stores
can still exist, but they should reconcile to the same Nexo user/app link once
the user authenticates.

## What this page does not cover

This page does not define:

- partner-owned OTP mechanics
- provider-specific OAuth implementations
- app-local session cookie design

Those can vary by app. The stable part is the Nexo-hosted app-scoped route
family and the expectation that profile/onboarding stay on the Nexo side once
the app enters that flow.
