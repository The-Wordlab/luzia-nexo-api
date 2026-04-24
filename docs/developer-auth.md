# Developer Authentication

One credential for all Nexo developer tooling.

## Get a developer key

1. Open the Nexo dashboard - Profile - Developer Access
2. Create a key
3. Copy the `nexo_uak_...` value

Dashboard URLs:

- Local: `http://localhost:3000/dashboard/profile`
- Staging: `https://staging.nexo.luzia.com/dashboard/profile`
- Production: `https://nexo.luzia.com/dashboard/profile`

## Store the key

Add to your `.env` (gitignored):

```bash
NEXO_DEVELOPER_KEY=nexo_uak_...
```

For multi-environment workflows, use environment-specific aliases:

```bash
DEV_KEY_LOCAL=nexo_uak_...
DEV_KEY_STAGE=nexo_uak_...
DEV_KEY_PROD=nexo_uak_...
```

## Use with MCP

Pass the key directly as an `X-Api-Key` header. No exchange step needed.

```bash
claude mcp add --scope project --transport http nexo-mcp \
  "${NEXO_BASE_URL}/mcp" \
  -H "X-Api-Key: ${NEXO_DEVELOPER_KEY}"
```

MCP base URLs:

- Local: `http://localhost:8000`
- Staging: `https://nexo-cdn-alb.staging.thewordlab.net`
- Production: `https://luzia-nexo.thewordlab.net`

See [MCP Server](mcp.md) for full MCP documentation.

## Use with the REST API

Exchange the developer key for a short-lived JWT, then use the JWT as a Bearer
token:

```bash
# Exchange key for JWT
curl -X POST "${NEXO_BASE_URL}/api/auth/key-exchange" \
  -H "Content-Type: application/json" \
  -d '{"api_key": "nexo_uak_..."}'

# Response: { "access_token": "eyJ...", "token_type": "bearer", "expires_in": 3600 }

# Use JWT for subsequent calls
curl "${NEXO_BASE_URL}/api/micro-apps/" \
  -H "Authorization: Bearer eyJ..."
```

This is the same pattern used by setup scripts and the `nexo login` CLI.

## Developer key vs app secret

| Credential | Identifies | Used for |
|---|---|---|
| Developer key (`nexo_uak_...`) | A developer/user | MCP, CLI, setup scripts, REST API calls |
| App secret (`X-App-Secret`) | An app | Webhook delivery, HMAC signatures, partner runtime calls |

Do not use app secrets for developer tooling. Do not use developer keys for
runtime webhook authentication.
