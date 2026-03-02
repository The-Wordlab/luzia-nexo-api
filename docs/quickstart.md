# Quickstart

## 1) Implement your webhook

Create a webhook endpoint in your own backend and return a JSON response:

```json
{
  "text": "Your assistant response"
}
```

## 2) Configure your app secret and webhook URL

1. Go to [nexo.luzia.com/partners](https://nexo.luzia.com/partners)
2. Create or open your app
3. Set your webhook URL and secret
4. Verify requests on your backend

## 3) Support both response modes

- Traditional JSON response
- SSE streaming response (`text/event-stream`)

## Optional: reference hosted examples

These are sample implementations only:
- Python: [nexo-examples-py](https://nexo-examples-py-v3me5awkta-ew.a.run.app)
- TypeScript: [nexo-examples-ts](https://nexo-examples-ts-v3me5awkta-ew.a.run.app)

## Next

- [API Reference](partner-api-reference.md)
