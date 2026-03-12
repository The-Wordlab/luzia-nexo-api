# A2A Profile For Nexo Examples

Status: execution baseline
Updated: 2026-03-12

This profile defines the single contract shape every webhook example must follow.

## Response envelope

Required:
- `schema_version`
- lifecycle via `status` or `task.status`
- at least one output channel: `content_parts`, `cards`, `actions`, or `artifacts`

A2A-aligned optional fields:
- `task`
- `capability`
- `artifacts`
- structured `error`

## Task lifecycle

Allowed values:
- `queued`
- `in_progress`
- `requires_input`
- `completed`
- `failed`
- `canceled`

Semantics:
- `failed`/`canceled` map to error lifecycle
- all others map to completed/in-progress lifecycle

## Capability publication

Each example should publish capability metadata at:
- `/.well-known/agent.json`

Each capability item should include:
- `name` (required)
- `description` (recommended)
- `input_schema` / `output_schema` (recommended)
- `supports_streaming` (recommended)
- `supports_cancellation` (recommended)

## Stream events

Preferred taxonomy:
- `task.started`
- `task.delta`
- `task.artifact`
- `task.state`
- `task.completed`
- `task.failed`

Compatibility:
- Nexo normalizes `task.delta` to token delta behavior.
- Unknown `task.*` events are forwarded to clients.

## Conformance requirement

Every example should pass the same checks:
1. valid sync envelope
2. valid stream terminal behavior
3. artifact-only completion accepted
4. failed task lifecycle resolves to error
5. capability metadata published and parseable
