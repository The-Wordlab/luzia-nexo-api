# Minimal Webhook - TypeScript/Node

Profile context:
- Today, treat `profile.locale` as the primary stable profile field.
- More consented profile fields will be added to the stable contract in future updates.

Run:

```bash
node webhook-server.mjs
```

Test:

```bash
node --test test-webhook-server.mjs
```

Then point your webhook URL to `http://localhost:8081`.
