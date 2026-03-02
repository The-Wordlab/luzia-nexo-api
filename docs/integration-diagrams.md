# Integration Diagrams

These diagrams show how partners integrate with hosted examples and the demo receiver.

## 1) End-to-end webhook flow

```mermaid
sequenceDiagram
    autonumber
    participant Partner as Partner System
    participant Nexo as Nexo Platform
    participant ExPy as Hosted Example (Python)
    participant ExTs as Hosted Example (TypeScript)

    Partner->>Nexo: Configure app webhook URL + shared secret
    Nexo->>ExPy: POST /webhook/minimal (X-App-Secret)
    ExPy-->>Nexo: 200 OK + example response

    Nexo->>ExTs: POST /webhook/structured (X-App-Secret)
    ExTs-->>Nexo: 200 OK + example response
```

## 2) Hosted services topology

```mermaid
flowchart LR
    subgraph GCP[Google Cloud Project]
        AR[Artifact Registry\nnexo-examples]
        CR1[Cloud Run\nnexo-examples-py]
        CR2[Cloud Run\nnexo-examples-ts]
        CR3[Cloud Run\nnexo-demo-receiver]
    end

    GH[GitHub Repository\nluzia-nexo-api] --> AR
    AR --> CR1
    AR --> CR2
    AR --> CR3

    Nexo[Nexo Dashboard / Runtime] --> CR1
    Nexo --> CR2
    Nexo --> CR3
```

## 3) Demo receiver capture flow

```mermaid
flowchart TD
    Nexo[Nexo webhook dispatch] --> Validate{Valid secret?}
    Validate -- No --> Reject[401/403 reject]
    Validate -- Yes --> Redact[Apply redaction rules]
    Redact --> Store[Store recent events by demo_key]
    Store --> TTL[Auto-expire by TTL]
    Store --> API[GET /events?demo_key=...]
    API --> Dashboard[Dashboard demo viewer]
```

## 4) Health and discovery endpoints

```mermaid
flowchart LR
    Dev[Developer] --> Root[GET /]
    Dev --> Info[GET /info]
    Dev --> Health[GET /health]

    Root --> HTML[HTML by default]
    Info --> JSONQ[JSON via ?format=json]
    Health --> OK[Service health status]
```
