# Milestone 2, Phase 1 — Database Foundation

## Scope

SQLite and SQLAlchemy are wired into the application as a foundation only. No ORM models,
ingestion, or AI functionality is included.

## Configuration

`Settings.database_url` is read from `MINDVAULT_DATABASE_URL` and defaults to
`sqlite:///./storage/mindvault.db`. Because the backend may be started from either the repository
root or `backend/`, relative SQLite paths are resolved against the repository root in
`app/core/config.py`. Absolute paths and `sqlite:///:memory:` URLs are left unchanged.

## Lifecycle

- `create_database(url)` builds one `Engine` and one `sessionmaker` per application instance.
- SQLite connections use `check_same_thread=False` and enable `PRAGMA foreign_keys=ON`.
- The engine uses `pool_pre_ping=True`; in-memory SQLite uses `StaticPool`.
- `app.state.database` holds the engine/factory created from the app's settings.
- `get_db` opens a session per request and closes it in a `finally` block.
- `init_db()` is called explicitly from the FastAPI lifespan. It creates the database parent
  directory, opens a connection, and calls `Base.metadata.create_all()`. With no models registered
  yet, no tables are created.
- The engine pool is disposed when the application shuts down.

## Testing

Database tests use `tmp_path` SQLite files. The existing health-test fixture was updated so the
test application also uses a temporary database, ensuring the development database is never
modified by tests.
