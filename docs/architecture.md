# RESOLVE — Architecture

Mermaid diagrams of the system, checked against the code (PLAN §11.6).

## Case flow (multi-agent graph)

```mermaid
flowchart TD
    U[Complaint narrative] --> MASK[Intake: PII mask\nsecurity/pii.py]
    MASK --> R[Router agent\nno tools\nagent/router.py]
    R -->|confidence < τ| AB[Abstain / escalate]
    R -->|confidence ≥ τ| FAN{Fan-out}
    FAN --> REG[Regulation agent\npoint-in-time search\nretrieval/search.py]
    FAN --> ACC[Account agent\nRLS tools\nmcp_server/tools.py]
    REG --> EV[(Evidence reducer)]
    ACC --> EV
    EV --> D[Drafter\nLetter + citations\nagent/graph_multi.py]
    D --> V[Citation + output guardrails\neval/metrics/citations.py\nsecurity/guardrails.py]
    V --> HIL[Human review\ninterrupt / resume]
    HIL --> AUD[(Audit log\nhash chain)]
    AB --> AUD
```

## Retrieval (point-in-time hybrid)

```mermaid
flowchart LR
    Q[legal_question] --> RW[rewrite.py\nSearchIntent]
    RW --> DQ[Gemini dense embed] --> QD[(Qdrant: dense)]
    RW --> SQ[BM25 sparse encode] --> QS[(Qdrant: bm25/IDF)]
    QD --> RRF[RRF fusion\nsearch.py]
    QS --> RRF
    RRF --> PIT[PIT filter\nvalid_from ≤ as_of < valid_to]
    PIT --> RR[rerank + parent-child\nrerank.py]
    RR --> OUT[top-k evidence]
```

## Data + eval pipeline

```mermaid
flowchart TD
    CFPB[CFPB API] --> ING[cfpb_ingest.py] --> PARQ[(complaints.parquet)]
    ECFR[eCFR API] --> EING[ecfr_ingest.py] --> REGJ[(regulations.jsonl)]
    PARQ --> PG[(Postgres: complaints)]
    SYN[synth_accounts.py] --> PG
    REGJ --> CHK[chunking.py] --> IDX[index.py] --> QDR[(Qdrant)]
    PARQ --> GOLD[golden sets\neval/golden/*.jsonl]
    GOLD --> GATE[eval gate\neval/runners/gate.py] --> SUM[summary.md + CI]
```

## Trust boundaries (security)

```mermaid
flowchart LR
    subgraph Untrusted
      N[Complaint narrative]
    end
    subgraph Agent
      RT[Router: reads narrative, NO tools]
      AG[Account agent: tools, never sees narrative]
    end
    subgraph Data
      DB[(Postgres + RLS)]
    end
    N --> RT
    RT -->|route only| AG
    AG -->|scoped JWT + RLS| DB
```

Rendered on GitHub automatically. Node labels name the implementing module.
