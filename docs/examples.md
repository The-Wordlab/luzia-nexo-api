# Examples

Use the examples folder as the single source of runnable integrations.

Main folder:
- [github.com/The-Wordlab/luzia-nexo-api/tree/main/examples](https://github.com/The-Wordlab/luzia-nexo-api/tree/main/examples)

## Minimal webhook snippet (Python)

```python
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class Payload(BaseModel):
    message: dict | None = None

@app.post("/webhook")
def webhook(payload: Payload):
    content = (payload.message or {}).get("content", "")
    return {"text": f"Echo: {content}"}
```

## Minimal webhook snippet (TypeScript)

```ts
import express from "express";

const app = express();
app.use(express.json());

app.post("/webhook", (req, res) => {
  const content = req.body?.message?.content ?? "";
  res.json({ text: `Echo: ${content}` });
});
```

## Hosted examples

- Python: [nexo-examples-py](https://nexo-examples-py-v3me5awkta-ew.a.run.app/)
- TypeScript: [nexo-examples-ts](https://nexo-examples-ts-v3me5awkta-ew.a.run.app/)

Protected endpoints require `X-App-Secret` or `Authorization: Bearer`.
