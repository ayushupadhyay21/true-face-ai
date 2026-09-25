# Database

PostgreSQL 18 (local Windows service `postgresql-x64-18`, port 5432) with the pgvector extension v0.8.6. The schema is in `database/migrations/001_initial_schema.sql`. Migrations are recorded in `schema_migrations` and applied by `scripts/setup_database.py` (or `app.db.database.apply_migrations`).

## One-time setup

pgvector is not bundled with the EDB Windows installer. It is built from source with MSVC (official method), which needs Visual Studio Build Tools 2022; they are installed on the audit machine.

1. Install pgvector from an **elevated** PowerShell:

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\install_pgvector.ps1
   ```

2. Copy `.env.example` to `.env` and set `POSTGRES_PASSWORD` to a new password for the application role.
3. Create the role and database, enable pgvector, and apply the migrations. This prompts once for the `postgres` superuser password and does not store it:

   ```powershell
   .venv\Scripts\python.exe scripts\setup_database.py
   ```

4. Verify: `GET http://localhost:8000/health` returns `database_ok: true`.

`setup_database.py` also creates `<POSTGRES_DB>_test`. The pytest database tests run **only** against that test database: they truncate every table before each test. `conftest.py` refuses to truncate any database whose name does not end in `_test`. Enrolled people in the real database are never touched by tests.

## Tables

| Table | Purpose | Key constraints |
|---|---|---|
| `people` | Enrolled identities | `status IN (ACTIVE, PENDING, DISABLED)`; `external_id` UNIQUE. Only `ACTIVE` people are searched. |
| `face_embeddings` | One row per stored sample | FK `person_id` → people **ON DELETE CASCADE**. `embedding vector` (no fixed dimension), `CHECK vector_dims(embedding) = embedding_dimension`. Also stores `model_name`, `model_version`, `preprocessing_version`, `pose`, `quality_score`. |
| `recognition_sessions` | One row per enrollment or recognition attempt | `session_id` UNIQUE; status CHECK (CREATED, IN_PROGRESS, PASSED, FAILED, EXPIRED); `challenge` JSONB (challenge_id, expected_actions, current_action, created_at, expires_at); `completed_at` set once |
| `recognition_results` | Final decision per session | `session_id` UNIQUE FK → sessions CASCADE; `person_id` FK SET NULL; `result` CHECK (KNOWN, UNKNOWN, LIVENESS_FAILED, CHALLENGE_FAILED, MULTIPLE_FACES, EXPIRED, ENROLLED); stores the similarity, liveness score, threshold and model |
| `liveness_events` | Per-frame passive PAD score | FK session CASCADE; UNIQUE (session_id, frame_number); `score BETWEEN 0 AND 1` |

Indexes: embeddings by person and by (model_name, model_version); sessions by status; results by person; events by session.

## Vector search

`VectorSearchService.search` does the following:

1. Casts each embedding to `vector(dim)`.
2. Computes cosine similarity `1 - (embedding <=> query)`.
3. Filters on the exact model name, version, dimension and preprocessing version, and on people with `status = 'ACTIVE'`.
4. Groups by person (best embedding per person) and returns the top k.

The search is exact (sequential scan), which is fine for a research gallery. An HNSW index needs a fixed-dimension column; add one once a single model is final, for example `CREATE INDEX ON face_embeddings USING hnsw ((embedding::vector(512)) vector_cosine_ops)` together with a matching expression in the query.

## Privacy

No images are stored, only embeddings plus metadata. Deleting a person cascades to their embeddings. Recognition results keep the row but set `person_id` to NULL.
