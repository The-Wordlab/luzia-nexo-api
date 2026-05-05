# @luzia/nexo-sdk - Mirror

This is a downstream mirror of the Nexo SDK from `luzia-nexo/apps/nexo-sdk`.

**Do not edit files in this directory.** All changes must be made in the source
repo and synced here via the sync script.

## Source of truth

`luzia-nexo/apps/nexo-sdk/src/` is the authoritative source.

## Sync

From the `luzia-nexo-api` repo root:

```bash
./scripts/sync-nexo-sdk.sh
```

This copies the source TypeScript files from the sibling repo. The mirror is
intentionally checked in so consumers can use it without needing the source
repo.

## Usage

Apps in this repo can import from the mirror:

```typescript
import { useCompanionChat } from "../sdk/nexo-sdk/src/useCompanionChat";
import type { ChatMessage } from "../sdk/nexo-sdk/src/chat-types";
```

Or via the `file:` dependency in package.json:

```json
{
  "dependencies": {
    "@luzia/nexo-sdk": "file:../../sdk/nexo-sdk"
  }
}
```
