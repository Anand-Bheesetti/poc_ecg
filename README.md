```mermaid
flowchart TD
    A[Start] --> B[Fetch Commits]
    B --> C[Generate Diff]
    C --> D{Contains Secrets?}
    D -->|Yes| E[Redact Secrets]
    D -->|No| F[Continue]
    E --> F
    F --> G[Complete]
```
