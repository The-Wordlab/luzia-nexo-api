# World Cup Migration Note

## Purpose

Record the intended boundary between this examples repo and the real World Cup
product lane.

## Direction

World Cup-specific product/runtime work should consolidate into:

- `worldcup-server`

That repo should own:

- product and system planning
- live football/provider integration
- app-specific chat and Ask Expert behavior
- internal web harness and app-local backoffice
- Nexo integration for the World Cup app

## What stays here

`luzia-nexo-api` should keep only reusable generic partner-integration ideas,
for example:

- webhook contract patterns
- streaming response patterns
- worker/job split
- generic live-ingest structures
- deployment/devex documentation

## What should move out conceptually

These should no longer be treated as active long-term example lanes in this
repo:

- World Cup-specific football product architecture
- football-only live intelligence as a flagship example
- the idea that `football-live` is the canonical place to understand the World
  Cup product direction

## Practical implication

The end state is:
- no active public docs/catalog references to `football-live`
- World Cup-specific code and GCP deployment shape live in `worldcup-server`
- this repo keeps only generic developer-experience patterns

Operational cleanup still required:
- undeploy the old football-live GCP service and related scheduler/worker
  resources
- remove football-live from active seed/demo/showcase paths
- remove old staging/production app records that still surface the demo lane
