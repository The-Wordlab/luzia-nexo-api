# Internal Apps

This page is intentionally short because **Internal Apps are owned by `luzia-nexo`, not by the public `luzia-nexo-api` contract surface**.

Use this distinction:

- **Partner Integrations**: external webhook-backed apps documented in this repo
- **Personalized Apps**: first-party structured apps exposed here through the headless REST and MCP lanes
- **Internal Apps**: Nexo-only implementation pattern for first-party in-process capabilities such as the Builder

If you need the implementation details for Internal Apps, use the `luzia-nexo` docs:

- `docs/guides/internal-architecture.md`
- `docs/guides/micro-apps.md`

Internal Apps are not the normal external/customer integration path and should not be treated as a third public lane alongside Partner Integrations and Personalized Apps.
