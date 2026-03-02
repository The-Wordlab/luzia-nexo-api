# Migration From luzia-nexo/examples

## Goals

1. Remove Replit-specific and local artifact noise.
2. Consolidate redundant webhook tiers.
3. Preserve clear learning progression.

## Initial mapping

| Source in luzia-nexo | Destination in luzia-nexo-api | Action |
|---|---|---|
| `examples/partner-api/python/webhook_server.py` | `examples/webhook/minimal/python/` | migrate |
| `examples/partner-api/typescript/webhook-server.mjs` | `examples/webhook/minimal/typescript/` | migrate |
| `examples/hello-world`, `webhook-basics`, `intermediate` | `examples/webhook/{minimal,structured}/python` | consolidate |
| `examples/advanced` | `examples/webhook/advanced/python` | consolidate |
| `examples/partner-sdk` | `sdk/javascript/` | migrate |
| `.replit`, `replit.nix`, `.venv`, `__pycache__`, `.pytest_cache` | n/a | delete |

## Cutover phases

1. Bootstrap new repo and minimal examples.
2. Publish migration pointers in old repo docs.
3. Migrate structured and advanced tiers.
4. Deprecate old examples tree after one release cycle.
