# @luzia/nexo-sdk

This is the checked-in SDK package used by the public examples and docs in this
repo.

Treat this directory as the canonical package for the `luzia-nexo-api` lane and
keep downstream consumer mirrors aligned when the shared hosted-app contract
changes.

## Usage

Apps in this repo can import from the package:

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
