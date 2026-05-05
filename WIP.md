# WIP

**Updated:** 2026-05-05

## Status

Docs and examples reframed for the unified app model. README and
docs/index.md now describe one app model with optional webhook instead
of two developer lanes. Remaining doc pages (~40) still reference old
framing and will be updated incrementally.

## Current state

- One unified app model framing in README and docs/index.md
- Auth bridge doc updated with hosted profile/logout follow-through and the
  signed app-header exchange contract (`/api/apps/structured/apps/{connected_app_id}/auth-handoffs/exchange`)
- All webhook examples are app-type agnostic (no code changes needed)
- Signing contract unchanged (X-App-Id + X-App-Secret + HMAC)
- A2A example compliance tests now use canonical agent-card naming
- RAG examples (news, sports, travel) deployed and healthy on Cloud Run
- Provisioning endpoint (`POST /api/apps/structured/provision`) documented
- MCP provision_app tool documented
- Knowledge Packs developer guide shipped

## Next

- Update remaining ~40 doc pages for unified model framing (incremental)
- Add "Getting Started: Create Your First App" guide showing one-call
  provisioning
- Keep auth bridge doc truthful (phase-1 internal, not broad partner API)
- Keep operational RAG services healthy
- Clean legacy mid-file imports in examples/scripts incrementally now that a
  diff-aware import-placement guard is in place for new Python and JS/TS
  changes; keep only explicit documented exceptions
