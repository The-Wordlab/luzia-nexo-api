# Luzia Nexo API Docs

Fast partner integration docs.

## Integration at a glance

```mermaid
flowchart LR
    Partner[Partner Backend]

    subgraph Nexo[Nexo]
      Threads[Threads]
      Characters[Characters]
      Tools[Tools]
      Messages[Messages]
    end

    Threads --> Characters
    Threads --> Tools
    Threads --> Messages

    Partner -->|GET /apps/:app_id/threads| Threads
    Partner -->|GET /apps/:app_id/threads/:thread_id/messages| Messages
    Partner -->|POST /apps/:app_id/threads| Threads
    Partner -->|POST /apps/:app_id/threads/:thread_id/messages| Messages
    Partner -->|POST /apps/:app_id/threads/:thread_id/messages/assistant| Messages
```

## Start here

1. **Onboarding (5 minutes)**: [Onboarding](onboarding.md)
2. **Quickstart (hosted or self-deploy)**: [Quickstart](quickstart.md)
3. **Code examples**: [Examples](examples.md)

## Live hosted services

- Demo receiver: [nexo-demo-receiver](https://nexo-demo-receiver-v3me5awkta-ew.a.run.app)
- Hosted Python examples: [nexo-examples-py](https://nexo-examples-py-v3me5awkta-ew.a.run.app)
- Hosted TypeScript examples: [nexo-examples-ts](https://nexo-examples-ts-v3me5awkta-ew.a.run.app)

## API secret and support

- Partner portal: [nexo.luzia.com/partners](https://nexo.luzia.com/partners)
- Support: [mmm@luzia.com](mailto:mmm@luzia.com) (Mark MacMahon)

## What these docs cover

- How to use hosted examples immediately
- How to deploy your own copy on GCP
- Direct links to Python, TypeScript, and cURL examples

## Source repository

- [github.com/The-Wordlab/luzia-nexo-api](https://github.com/The-Wordlab/luzia-nexo-api)
