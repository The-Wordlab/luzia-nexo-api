# Examples

Runnable Nexo integration examples.

Profile context note:
- Webhook payloads include consented profile context (for example `locale`, `language`, `location`, `age`, `date_of_birth`, `gender`, `dietary_preferences`, and preferences/facts).
- Additional attributes are added over time while keeping backward compatibility.
- Build examples and integrations to safely ignore unknown fields.

Folders:
- `webhook/minimal`
- `webhook/structured`
- `webhook/advanced`
- `partner-api/proactive`

Run all example tests from the repo root:

```bash
make test-examples
```
