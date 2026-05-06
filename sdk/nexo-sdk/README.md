# @luzia/nexo-sdk - Mirror

This is a downstream mirror of the Nexo SDK from
`luzia-nexo-apps/apps/nexo-sdk`.

**Do not edit files in this directory.** All changes must be made in the source
repo and synced here via the sync script.

## Source of truth

`luzia-nexo-apps/apps/nexo-sdk/src/` is the authoritative source.

## Sync

From the `luzia-nexo-api` repo root:

```bash
./scripts/sync-nexo-sdk.sh
```

This copies the source TypeScript files from the sibling repo. The mirror is
intentionally checked in so consumers can use it without needing the source
repo.

Re-run this sync any time the source SDK changes before publishing public app
examples from this repo.

## Usage

Apps in this repo can import from the mirror:

```typescript
import { NexoAppShell } from "@luzia/nexo-sdk/react";
import type { AgentChatOptions } from "@luzia/nexo-sdk/react";
```

Or via the `file:` dependency in package.json:

```json
{
  "dependencies": {
    "@luzia/nexo-sdk": "file:../../sdk/nexo-sdk"
  }
}
```
