# Knowledge Packs

Knowledge Packs let you attach reference data to Personalized Apps and compute
derived outputs like standings, leaderboards, and group aggregations.

## When to use Knowledge Packs

Use Knowledge Packs when your app needs:

- **Reference datasets** that don't change with every user action (product
  catalogs, menu items, employee directories, pricing tiers)
- **Derived outputs** computed deterministically from reference + operational data
  (standings tables, leaderboard rankings, group counts)
- **Sync tracking** so you know when reference data was last updated and whether
  the import succeeded

Don't use Knowledge Packs for:

- User-entered operational state (use Personalized Apps tables instead)
- Real-time data that changes every second
- Document search / RAG (not yet supported in this phase)

## Concepts

### Packs

A Knowledge Pack is a named container of reference data attached to an app.

- **Owner scope:** currently `app` only (the pack belongs to a specific app)
- **Pack types:** `structured`, `document`, `hybrid` (only `structured` is
  fully implemented in phase one)
- **Key:** unique per owner, used for idempotent identification

### Datasets

Each pack contains one or more datasets - logical collections like "products",
"categories", or "pricing_tiers".

### Records

Each dataset contains records identified by `record_key`. Records hold
structured data in `data_json` and optional `markdown_projection` for
text rendering.

### Sources

Sources track where the data comes from and whether it's up to date.

- **Source types:** `manual`, `static`, `api_polled`
- **Sync status:** `pending` → `syncing` → `synced` (or `error`)
- **Metadata:** content hash, version tag, last error, timestamps

### Projections

Projections compute derived outputs from dataset records.

- **Built-in types:** `standings`, `leaderboard`, `group_counts`
- **Source dataset:** where the projection reads input records
- **Output dataset:** where materialized results are written
- **Replace-all semantics:** each run replaces all output records (no stale rows)

## REST API

### Create a pack

```bash
curl -X POST "${NEXO_BASE_URL}/api/knowledge-packs" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "key": "product-catalog",
    "title": "Product Catalog",
    "owner_type": "app",
    "owner_id": "YOUR_APP_ID",
    "pack_type": "structured"
  }'
```

### Create a dataset

```bash
curl -X POST "${NEXO_BASE_URL}/api/knowledge-packs/${PACK_ID}/datasets" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "key": "products",
    "title": "Products"
  }'
```

### Upsert records (single)

```bash
curl -X PUT "${NEXO_BASE_URL}/api/knowledge-packs/${PACK_ID}/datasets/${DATASET_ID}/records" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "record_key": "prod-001",
    "data_json": {
      "name": "Wireless Headphones",
      "category": "electronics",
      "price": 79.99,
      "in_stock": true
    }
  }'
```

Records are upserted by `record_key` - calling with the same key updates
the existing record (merging `data_json` fields).

### Bulk import

```bash
curl -X POST "${NEXO_BASE_URL}/api/knowledge-packs/${PACK_ID}/datasets/${DATASET_ID}/records/bulk" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '[
    {"record_key": "prod-001", "data_json": {"name": "Wireless Headphones", "price": 79.99}},
    {"record_key": "prod-002", "data_json": {"name": "USB-C Cable", "price": 12.99}},
    {"record_key": "prod-003", "data_json": {"name": "Laptop Stand", "price": 45.00}}
  ]'
```

Response: `{"created": 3, "updated": 0, "total": 3}`

### Create a projection

```bash
curl -X POST "${NEXO_BASE_URL}/api/projections/apps/${APP_ID}/definitions" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "key": "price-ranking",
    "title": "Products by Price",
    "projection_type": "standings",
    "config_json": {"sort_key": "price", "descending": true},
    "source_dataset_id": "PRODUCTS_DATASET_ID",
    "output_dataset_id": "RANKED_DATASET_ID"
  }'
```

### Run a projection

```bash
curl -X POST "${NEXO_BASE_URL}/api/projections/apps/${APP_ID}/definitions/${DEF_ID}/run" \
  -H "Authorization: Bearer ${TOKEN}"
```

Response includes run status, timing, and record counts:

```json
{
  "id": "...",
  "status": "completed",
  "input_record_count": 4,
  "output_record_count": 4,
  "duration_ms": 12
}
```

## MCP inspection

Use the Knowledge Packs MCP tools for inspection and projection execution:

```
# List packs for an app
knowledge_packs__list_packs(app_id="...")

# Check dataset record counts
knowledge_packs__list_datasets(pack_id="...")

# Monitor sync health
knowledge_packs__list_sources(pack_id="...")

# Run a projection
knowledge_packs__run_projection(app_id="...", definition_id="...")

# Check run history
knowledge_packs__list_projection_runs(definition_id="...")
```

## Projection types

### standings

Rank records by a sort key with optional tiebreakers.

```json
{
  "projection_type": "standings",
  "config_json": {
    "sort_key": "points",
    "tiebreaker_keys": ["gd", "gf"],
    "descending": true
  }
}
```

Output records include a `rank` field.

### leaderboard

Top-N scored entries.

```json
{
  "projection_type": "leaderboard",
  "config_json": {
    "score_key": "total",
    "name_key": "name",
    "limit": 10
  }
}
```

### group_counts

Count records by a grouping field.

```json
{
  "projection_type": "group_counts",
  "config_json": {
    "group_key": "status"
  }
}
```

## Sync workflow

For apps with external reference data:

1. Create a source: `POST /api/knowledge-packs/{id}/sources`
2. Start sync: `PATCH .../sources/{id}/sync` with `{"sync_status": "syncing"}`
3. Import records via bulk endpoint
4. Complete sync: `PATCH .../sources/{id}/sync` with `{"sync_status": "synced", "content_hash": "..."}`
5. Run projections to materialize derived outputs

On error: `PATCH .../sources/{id}/sync` with `{"sync_status": "error", "last_error": "..."}`

## Ownership model

- **Nexo** provides the runtime: storage, projections, MCP inspection, admin UI
- **Your app repo** provides domain-specific transforms and sync scripts
- Do not add domain-specific projection logic to Nexo - keep it in your sync scripts

## Admin dashboard

Superusers can inspect Knowledge Packs health at:
`/dashboard/admin/knowledge-packs`

This shows pack status, source sync health, and projection definitions across all apps.
