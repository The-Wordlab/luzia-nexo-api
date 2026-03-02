# Quickstart

## 1) Implement your webhook in your backend

Your webhook should accept Nexo requests and return one of these:

### JSON response

```json
{
  "text": "Your assistant response"
}
```

### SSE response

Use `Content-Type: text/event-stream` and stream `delta` events followed by `done`.

## 2) Configure Nexo

1. Go to [nexo.luzia.com/partners](https://nexo.luzia.com/partners)
2. Create or open your app
3. Set your webhook URL and secret
4. Send a test message and verify logs on your backend

## 3) Validate request handling

Checklist:
- verify `X-App-Id`
- verify timestamp/signature (`X-Timestamp`, `X-Signature`)
- return valid JSON or SSE stream

## Next

- Full contract and examples: [API Reference](partner-api-reference.md)
- Optional hosting/deployment examples: [Hosting (Optional)](hosting.md)
