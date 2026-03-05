# IAM and Isolation Strategy

Use a dedicated GCP project for demo receiver only.

## Service account

Create one runtime service account:

- `nexo-examples-runtime@<project>.iam.gserviceaccount.com`

Permissions:

- `roles/datastore.user` (if Firestore backend is enabled later)
- `roles/logging.logWriter`

## Invocation

Two valid modes:

1. Public demo URL (quick demos)
   - Grant `roles/run.invoker` to `allUsers`
   - Use strict demo key entropy and rate limits

2. Private service-to-service (preferred)
   - No public invoker
   - Dashboard backend proxies requests with signed identity

## Separation guardrails

- No shared service accounts with production.
- No shared state stores with production.
- Keep secrets in this project only.
