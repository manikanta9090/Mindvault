# Milestone 1 — Project Foundation

## Goal

Establish a runnable, testable foundation for MindVault without implementing product features
that belong to later milestones.

## Included

- React + TypeScript + Vite frontend with Tailwind CSS via `@tailwindcss/vite`.
- A landing/dashboard shell with branding, tagline, and a live backend connection indicator.
- A reusable frontend API client (`frontend/src/services/api.ts`) calling `GET /health`.
- FastAPI backend with separate configuration, logging, middleware, error handling, routes, and
  schemas packages.
- `GET /health` returning a fixed health payload.
- Environment-driven settings, CORS, Swagger UI, structured JSON logs, and consistent error
  responses.
- Pytest coverage for the health endpoint and its OpenAPI registration.

## Design notes

- `Settings.from_env()` reads `MINDVAULT_*` variables; the cached instance is injected through
  FastAPI dependencies. The settings object is never returned by an endpoint.
- No secret-bearing settings exist yet. `.env` files are ignored and only `.env.example` files
  are tracked.
- Error responses use the shape `{"error": {"code": ..., "message": ..., "details": ...}}` and
  never include stack traces or submitted values.
- Logs are single-line JSON records written to stdout, including HTTP method, path, status, and
  duration.

## Explicitly deferred

Database tables/migrations, ChromaDB, embeddings, OpenAI, RAG, URL extraction, background
ingestion, authentication, Docker, and Kubernetes.
