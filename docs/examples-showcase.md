# Examples Showcase

This page summarizes the example surfaces that are currently maintained in this
repository.

Use it as a quick guide for choosing the right starting point.

## Webhook app examples

These are the main app-shaped examples for external builders.

| Example | Use it when you need | Source |
|---|---|---|
| Minimal | the smallest valid webhook in Python or TypeScript | `examples/webhook/minimal` |
| Structured | a richer response envelope with locale-aware hints and cards | `examples/webhook/structured/python` |
| Advanced | retries, idempotency, and action-routing patterns | `examples/webhook/advanced/python` |
| Food Ordering | a multi-step conversational commerce workflow | `examples/webhook/food-ordering/python` |
| OpenClaw Bridge | an adapter from Nexo webhook requests to OpenClaw `/v1/responses` | `examples/webhook/openclaw-bridge/typescript` |

## Hosted reference APIs

These are small reference HTTP services for capability and contract testing.

| Example | Purpose | Source |
|---|---|---|
| Hosted Python API | minimal authenticated reference API in Python | `examples/hosted/python` |
| Hosted TypeScript API | minimal authenticated reference API in TypeScript | `examples/hosted/typescript` |

## Integration utilities

These are supporting examples for app-adjacent platform seams.

| Example | Purpose | Source |
|---|---|---|
| Identity Bridge | partner-owned auth that links into Nexo and then hands off into Nexo-hosted app auth/profile/onboarding | `examples/identity-bridge` |
| Proactive Partner API scripts | push events or messages into Nexo threads from bash, Python, or TypeScript | `examples/partner-api/proactive` |

## How to choose

Start here:

1. clone `webhook/minimal` if you only need the contract shape
2. move to `webhook/structured` or `webhook/advanced` when you need richer UX or stronger delivery handling
3. use `webhook/food-ordering` when you want a fuller conversational app pattern
4. use `openclaw-bridge` when your runtime already speaks OpenClaw
5. use `identity-bridge` when login starts outside Nexo but the app should still converge on Nexo-hosted app auth/profile/onboarding

## Local verification

From the repo root:

```bash
make test-examples
make test-hosted-examples
make docs-build
```

For deploy guidance, see [Hosting](hosting.md) and [GCP Deploy Playbook](gcp-deploy-playbook.md).
