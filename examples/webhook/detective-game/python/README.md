# Sky Diamond Webhook

Stateful webhook game for a single mystery: `Sky Diamond`.

This example supports both webhook response modes used across the repository:

- traditional JSON response
- SSE streaming response when `Accept: text/event-stream` is present

## Game loop

1. The webhook introduces the case
2. User opens it with `begin case`
3. User investigates locations, unlocks deeper story beats, or pressures suspects
4. The webhook persists clue state, act progression, and revelations by `thread.id`
5. User accuses a suspect once enough evidence and key reveals are collected

## Commands

- `begin case`
- `inspect the glass dome`
- `inspect the moon balcony`
- `question iris bell`
- `check the lens room`
- `review clues`
- `accuse bruno vale`
- `restart`

Run locally:

```bash
pip install -r requirements.txt
export DETECTIVE_GAME_DSN=postgresql://postgres:postgres@localhost:5432/nexo_games
uvicorn app:app --reload --port 8105
```

Optional environment variables:

- `DETECTIVE_GAME_DSN` for the Postgres / Cloud SQL connection string
- `DATABASE_URL`, `POSTGRES_DSN`, or `PGVECTOR_DSN` as alternative DSN env names
- `WEBHOOK_SECRET` to enable signed webhook verification

Locale behavior:

- Reads `profile.locale` or `profile.language`
- Localizes case-entry and system text for supported languages where practical
- Continues to accept normal typed chat alongside `metadata.prompt_suggestions`

## Authoring model

The case now lives as JSON in `adventures/sky_diamond.json`.

- `title`, `aliases`, `hook`, `objective`, `setting`, `tone`
- `briefing` and `start_text`
- `initial_act`, optional `act_titles`, and optional `act_objectives`
- `clue_labels`
- optional `flag_labels`
- `moves`
  Each move can define `label`, `visit`, `clue`, `aliases`, `text`, `repeat_text`, `min_clues`, `requires_flags`, and `unlocks`
- `suspects` and optional `suspect_updates`
- `culprit`, `accusation_threshold`, optional `accusation_requires_flags`, and `solve_text`

The runtime validates this file at startup, so missing clues or broken unlock references fail early instead of surfacing as mid-game errors.

`Sky Diamond` uses the richer format:

- Act I gathers surface clues
- Act II unlocks `Reconstruct the blackout` and `Replay the blue burst`
- Act III opens the extraction route and confrontation
- the accusation only becomes available once the case has enough evidence and the decisive reveals have been triggered

## Cloud Run deployment

This example now includes a `cloudbuild.yaml` following the same build-push-deploy pattern used by the other durable webhook examples in this repository.

It expects:

- `WEBHOOK_SECRET` in Secret Manager
- `NEXO_PGVECTOR_DSN` in Secret Manager
- Cloud SQL instance access via `--add-cloudsql-instances`
