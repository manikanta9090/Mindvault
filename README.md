# MindVault

MindVault is a personal AI-powered knowledge management application. The long-term product lets
people save text notes and URLs, search their knowledge semantically, and ask questions answered
with source citations.

> **Current status: Milestone 1 — Project Foundation.** Only the application shell, backend
> health endpoint, configuration, and tests are implemented. Product features are not built yet.

## Technology stack

| Area | Technologies |
| --- | --- |
| Frontend | React, TypeScript, Vite, Tailwind CSS |
| Backend | Python, FastAPI, Pydantic, SQLAlchemy |
| Testing | Pytest (backend), Vite production build (frontend) |

SQLAlchemy is installed as part of the milestone stack but no database models or tables are
defined yet.

## Project structure

```text
MindVault/
├── frontend/
│   ├── src/
│   │   ├── services/api.ts    # Backend API client
│   │   ├── App.tsx            # Landing/dashboard shell
│   │   ├── index.css          # Tailwind entry point
│   │   └── main.tsx
│   ├── .env.example
│   ├── package.json
│   └── vite.config.ts
├── backend/
│   ├── app/
│   │   ├── api/               # Routers and route handlers
│   │   ├── core/              # Config, logging, errors, middleware
│   │   ├── models/            # Empty until database milestone
│   │   ├── schemas/           # Pydantic request/response models
│   │   ├── services/          # Empty until later milestones
│   │   ├── workers/           # Empty until later milestones
│   │   └── main.py            # Application factory + ASGI app
│   ├── tests/
│   ├── pytest.ini
│   └── requirements.txt
├── storage/                   # Reserved for generated files (gitignored)
├── docs/                      # Milestone notes
├── .env.example
├── .gitignore
└── README.md
```

## Windows PowerShell setup

Prerequisites: Python 3.14+ and Node.js 22+ with npm 10+.

From the repository root:

```powershell
# 1. Create local environment files (never commit the copies)
Copy-Item .env.example .env
Copy-Item frontend\.env.example frontend\.env

# 2. Create the backend virtual environment and install pinned packages
python -m venv backend\.venv
.\backend\.venv\Scripts\python.exe -m pip install --upgrade pip
.\backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt

# 3. Install frontend packages
cd frontend
npm install
cd ..
```

If `python` resolves to the Microsoft Store stub, use `py -3.14` instead in the commands above.

## Run the backend

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The API listens at `http://localhost:8000`. Health check: `GET /health`.

## Run the frontend

In a second PowerShell window, from the repository root:

```powershell
cd frontend
npm run dev
```

Open `http://localhost:5173`. The page calls `GET /health` and shows whether the backend is
connected. The API base URL defaults to `http://localhost:8000` and can be changed in
`frontend/.env`.

## Run tests and checks

```powershell
# Backend tests
cd backend
.\.venv\Scripts\python.exe -m pytest

# Frontend production build (type-check + bundle)
cd ..\frontend
npm run build
```

## Local API documentation

- Swagger UI: <http://localhost:8000/docs>
- OpenAPI schema: <http://localhost:8000/openapi.json>
- Health endpoint: <http://localhost:8000/health>

## Environment variables

Copy `.env.example` to `.env` (root) and `frontend/.env.example` to `frontend/.env`. `.env` files
are gitignored; only the examples are tracked.

| Variable | Default | Purpose |
| --- | --- | --- |
| `MINDVAULT_APPLICATION` | `MindVault` | Application name in settings |
| `MINDVAULT_VERSION` | `1.0.0` | Reported API version |
| `MINDVAULT_ENVIRONMENT` | `development` | Environment label in structured logs |
| `MINDVAULT_LOG_LEVEL` | `INFO` | Root log level |
| `MINDVAULT_CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Comma-separated allowed CORS origins |
| `MINDVAULT_DOCS_ENABLED` | `true` | Enables `/docs`, `/redoc`, and `/openapi.json` |
| `VITE_API_BASE_URL` | `http://localhost:8000` | Backend base URL used by the frontend |

No API endpoint returns environment variables or secrets.

## Milestone 1 scope

Implemented: modular FastAPI app, `GET /health`, CORS, environment configuration, structured
logging, error handling, Swagger documentation, landing page, backend connection status, and
health tests.

Deferred to later milestones: database tables and migrations, ChromaDB, embeddings, OpenAI, RAG,
URL extraction, background ingestion, authentication, Docker, and Kubernetes.

See `docs/milestone-1.md` for design notes.
