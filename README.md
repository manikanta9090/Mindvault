# MindVault

MindVault is a personal knowledge application for saving notes and URLs, indexing them
semantically, and asking questions with source citations.

> **Current status: Milestone 4, Phase 4.5A.** Backend ingestion, automatic chunking,
> embeddings, ChromaDB indexing, semantic retrieval, Groq-compatible RAG, and
> `POST /query` are implemented. Mocked end-to-end verification passes. **Live Groq
> verification was not performed** because no real API key was available in this
> environment.

## Technology stack

| Area | Technologies |
| --- | --- |
| Frontend | React, TypeScript, Vite, Tailwind CSS |
| Backend | FastAPI, Pydantic, SQLAlchemy, SQLite |
| Retrieval | ChromaDB persistent client, cosine distance, all-MiniLM-L6-v2 embeddings |
| LLM | Groq OpenAI-compatible chat completions via `httpx2` |
| Testing | Pytest with offline fake embedders and fake LLM providers |

## Architecture and RAG workflow

```text
POST /ingest
    -> validate payload / fetch URL
    -> extract readable text
    -> KnowledgeItem row in SQLite (source of truth)

automatic indexing in a separate transaction
    -> tokenizer-aware chunking
    -> all-MiniLM-L6-v2 embeddings (384 dimensions)
    -> stable ChromaDB vector IDs
    -> mark SQLite chunk rows INDEXED only after successful upsert

POST /query
    -> embed the question
    -> ChromaDB nearest-neighbour search
    -> validate vectors against SQLite (status, hash, model, dimension, metadata)
    -> build bounded context with [1], [2], ... citations
    -> call the configured LLM provider with grounding instructions
    -> remove invalid citations
    -> return answer + source mapping
```

SQLite remains authoritative. The item is committed before indexing starts, so an
indexing failure never deletes successfully ingested content. ChromaDB results whose
SQL chunk or item is missing, stale, or not `INDEXED` are discarded before they can
reach the prompt. `POST /ingest` reports `indexing_status` separately from the item's
`status`.

## Project structure

```text
MindVault/
├── frontend/                    # Vite UI (unchanged by Phase 4.4)
├── backend/
│   ├── app/
│   │   ├── api/routes/          # health, ingest, items, query
│   │   ├── core/                # config, database, logging, errors, middleware
│   │   ├── models/              # KnowledgeItem and KnowledgeChunk ORM models
│   │   ├── schemas/             # Pydantic request/response schemas
│   │   ├── services/            # chunking, embeddings, indexing, retrieval, context, rag, llm
│   │   ├── workers/             # reserved; no background queue is configured
│   │   └── main.py              # application factory and lifespan
│   ├── tests/
│   ├── pytest.ini
│   └── requirements.txt
├── storage/                     # generated SQLite and ChromaDB files (gitignored)
├── docs/
├── .env.example
└── README.md
```

## Installation and startup

Prerequisites: Python 3.14+, Node.js 22+ with npm 10+.

From the repository root in PowerShell:

```powershell
Copy-Item .env.example .env
Copy-Item frontend\.env.example frontend\.env

python -m venv backend\.venv
.\backend\.venv\Scripts\python.exe -m pip install --upgrade pip
.\backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt

cd frontend
npm install
cd ..
```

If `python` resolves to the Microsoft Store stub, use `py -3.14` instead.

Start the backend:

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The API listens at `http://localhost:8000`. Documentation is available at
`http://localhost:8000/docs`.

Start the frontend separately:

```powershell
cd frontend
npm run dev
```

The UI uses `http://localhost:5173` and `VITE_API_BASE_URL`.

## Environment variables

Copy `.env.example` to `.env`; never commit `.env` or a real Groq key.

| Variable | Default | Purpose |
| --- | --- | --- |
| `MINDVAULT_APPLICATION` | `MindVault` | Application label |
| `MINDVAULT_VERSION` | `1.0.0` | Reported API version |
| `MINDVAULT_ENVIRONMENT` | `development` | Environment label in structured logs |
| `MINDVAULT_LOG_LEVEL` | `INFO` | Log level (`DEBUG`–`CRITICAL`) |
| `MINDVAULT_CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Comma-separated CORS origins |
| `MINDVAULT_DOCS_ENABLED` | `true` | Enables `/docs`, `/redoc`, `/openapi.json` |
| `MINDVAULT_DATABASE_URL` | `sqlite:///./storage/mindvault.db` | SQLAlchemy URL; relative SQLite paths resolve from repo root |
| `MINDVAULT_FETCH_TIMEOUT_SECONDS` | `10.0` | URL fetch timeout |
| `MINDVAULT_FETCH_MAX_BYTES` | `2000000` | Maximum fetched HTML body size |
| `MINDVAULT_FETCH_MAX_REDIRECTS` | `3` | Maximum manual redirect hops |
| `MINDVAULT_CHUNK_SIZE_TOKENS` | `256` | Total tokenizer budget including special tokens |
| `MINDVAULT_CHUNK_OVERLAP_TOKENS` | `60` | Token overlap between adjacent chunks |
| `MINDVAULT_CHROMA_PATH` | `./storage/chroma` | Persistent ChromaDB directory |
| `MINDVAULT_CHROMA_COLLECTION` | `mindvault_chunks` | Chroma collection name |
| `MINDVAULT_RETRIEVAL_TOP_K` | `8` | Candidate chunks passed to RAG |
| `MINDVAULT_LLM_PROVIDER` | `groq` | Only implemented provider |
| `MINDVAULT_GROQ_API_KEY` | unset | Required only by `POST /query` when context exists |
| `MINDVAULT_LLM_MODEL` | `openai/gpt-oss-20b` | Groq model ID; verified 2026-11-20 and configurable |
| `MINDVAULT_LLM_TIMEOUT` | `30` | Provider request timeout in seconds |
| `MINDVAULT_LLM_CONTEXT_MAX_CHARS` | `12000` | Character budget for the constructed context |
| `VITE_API_BASE_URL` | `http://localhost:8000` | Backend URL used by the frontend |

The application starts, ingests, lists, and reports health **without** a Groq key.
A missing key produces a `503` response only from `/query`.

## API endpoints and examples

### `GET /health`

```json
{"status": "ok"}
```

### `POST /ingest` — note

```json
{
  "title": "Node.js runtime",
  "content": "Node.js is a JavaScript runtime.",
  "source_type": "NOTE"
}
```

The `201` response contains the saved item plus an independent indexing outcome:

```json
{
  "id": 23,
  "title": "Node.js runtime",
  "content": "Node.js is a JavaScript runtime.",
  "source_type": "NOTE",
  "source_url": null,
  "status": "COMPLETED",
  "created_at": "2026-11-20T12:00:00Z",
  "updated_at": "2026-11-20T12:00:00Z",
  "indexing_status": "indexed",
  "indexed_chunk_count": 1,
  "indexing_error_code": null
}
```

`indexing_status` is `indexed`, `failed`, or `unavailable`. A failed or unavailable
index still returns `201` because the item was saved; `indexing_error_code` carries a
stable code such as `embedding_failed`, `vector_store_failed`, or
`vector_store_unavailable`.

### `POST /ingest` — URL

```json
{
  "title": null,
  "content": "",
  "source_type": "URL",
  "source_url": "https://example.com/node"
}
```

Content supplied by the client is ignored for `URL` items; readable text is fetched
and extracted server-side.

### `GET /items`

Returns a newest-first page with `total`, `limit`, `offset`, and optional filters
`source_type` and `status`.

### `POST /query`

```json
{
  "question": "What did I save about Node.js?"
}
```

Successful response:

```json
{
  "answer": "Node.js is a JavaScript runtime [1].",
  "sources": [
    {
      "item_id": 23,
      "title": "Node.js runtime",
      "source_type": "NOTE",
      "source_url": null,
      "snippet": "Node.js is a JavaScript runtime.",
      "citation_id": "[1]"
    }
  ]
}
```

Error response shape:

```json
{
  "error": {
    "code": "upstream_error",
    "message": "The language model service could not complete the request."
  }
}
```

Common statuses: `200` success, `201` ingestion, `400` unsafe URL, `404/409` invalid
indexing state, `422` validation error, `502` upstream failure, `503` unavailable.

## Chunking strategy

- Tokenizer-aware chunking uses the real MiniLM tokenizer when available.
- `MINDVAULT_CHUNK_SIZE_TOKENS` is the total encoded budget including `[CLS]` and
  `[SEP]`; the default `256` matches all-MiniLM-L6-v2.
- `MINDVAULT_CHUNK_OVERLAP_TOKENS` defaults to `60` and must be smaller than the
  chunk size.
- Chunks are exact ordered source slices with SHA-256 hashes.
- Re-indexing unchanged content does not rewrite SQL rows, regenerate embeddings,
  or create duplicate vectors.

## Vector database choice

ChromaDB is used as a persistent embedded vector store
(`chromadb.PersistentClient`) with cosine distance and a 384-dimensional collection
matching all-MiniLM-L6-v2. Vector IDs are stable:
`knowledge_chunk_{item_id}_{chunk_index}_{content_hash}`.

SQLite stores chunk text, hashes, model metadata, status, and `chroma_id`.
Retrieval validates every Chroma hit against SQLite before use, so orphaned,
pending, failed, or stale vectors never become answer sources.

## Verification

From `backend/`:

```powershell
# Focused ingestion / Phase 4.4 tests
.\.venv\Scripts\python.exe -m pytest tests/test_ingest_auto_indexing.py tests/test_phase44_e2e.py tests/test_phase44_failures.py tests/test_phase44_hardening.py

# Full backend suite
.\.venv\Scripts\python.exe -m pytest

# Bytecode check
.\.venv\Scripts\python.exe -m compileall app
```

Phase 4.4 tests use real SQLite, real ChromaDB, real chunking, and real retrieval,
with deterministic fake embedders and fake LLM providers. They verify pipeline wiring,
metadata/citation integrity, idempotency, and failure recovery. They **do not** verify
live Groq behavior or model answer quality. Set a real `MINDVAULT_GROQ_API_KEY` and run
a manual `/query` check for live integration validation.

## Known limitations and production improvements

- **Automatic indexing is synchronous.** `POST /ingest` waits for chunking, embedding,
  and ChromaDB indexing. This is intentional for Phase 4.5A but adds latency; a
  background worker/queue would be the next production improvement.
- **Failed indexing leaves the item `COMPLETED` with PENDING or no chunks.** Retrieval
  safely ignores the gap and the response reports `indexing_status: "failed"` with a
  stable error code. There is not yet a public retry endpoint or item-level `FAILED`
  state; re-running `index_knowledge_item` is idempotent.
- **Retrieval has no relevance threshold.** Unrelated questions still return the nearest
  neighbours; successful HTTP responses do not prove semantic accuracy.
- **Citation validation checks IDs only.** Removing `[9]` proves the ID was not supplied,
  not that every sentence is supported. The source mapping remains in the response so
  users can inspect the evidence.
- **URL validation is pre-connect.** DNS results are validated before the HTTP request,
  but the client re-resolves the hostname. This is a DNS-rebinding/TOCTOU gap;
  MindVault does not provide complete SSRF protection. A hardened transport should
  pin the validated IP and revalidate redirects.
- **Context is bounded by characters, not model tokens.** Very large metadata or a
  different provider model could still exceed a token limit.
- **Provider failures are not retried.** Timeouts, 401/429, and 5xx responses currently
  map to a generic `502`; production should add status-aware handling, backoff, and an
  output token cap.
- **ChromaDB startup failure is fatal.** There is no degraded read-only mode and no
  migration/validation for an existing incompatible collection.
- **Logging uses structured metadata, but global exception handlers include tracebacks.**
  Third-party exception text should be redacted before production use.
- No authentication, agents, external queues, or distributed infrastructure are included.
