"""SQL for people, embeddings, sessions, results and liveness events."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime

import numpy as np
import psycopg

from app.core.errors import AppError, ErrorCode
from app.db.database import Database


@dataclass(frozen=True)
class EmbeddingMeta:
    model_name: str
    model_version: str
    embedding_dimension: int
    preprocessing_version: str


class PeopleRepository:
    def __init__(self, db: Database):
        self.db = db

    def create(self, name: str, external_id: str | None, status: str = "PENDING") -> dict:
        with self.db.connect() as c:
            try:
                return c.execute(
                    "INSERT INTO people(name, external_id, status) VALUES (%s, %s, %s) RETURNING *",
                    (name, external_id, status)).fetchone()
            except psycopg.errors.UniqueViolation as e:
                raise AppError(ErrorCode.INVALID_REQUEST, "external_id already exists", 409) from e

    def get(self, person_id: uuid.UUID) -> dict | None:
        with self.db.connect() as c:
            return c.execute(
                "SELECT p.*, (SELECT count(*) FROM face_embeddings e WHERE e.person_id = p.id) AS embedding_count "
                "FROM people p WHERE p.id = %s", (person_id,)).fetchone()

    def set_status(self, person_id: uuid.UUID, status: str) -> None:
        with self.db.connect() as c:
            c.execute("UPDATE people SET status = %s, updated_at = now() WHERE id = %s", (status, person_id))

    def delete(self, person_id: uuid.UUID) -> bool:
        with self.db.connect() as c:
            return c.execute("DELETE FROM people WHERE id = %s", (person_id,)).rowcount > 0


class SessionRepository:
    def __init__(self, db: Database):
        self.db = db

    def create(self, session_id: uuid.UUID, session_type: str, challenge: dict, expires_at: datetime,
               person_id: uuid.UUID | None = None) -> None:
        with self.db.connect() as c:
            c.execute("INSERT INTO recognition_sessions(session_id, session_type, person_id, status, challenge, "
                      "expires_at) VALUES (%s, %s, %s, 'CREATED', %s, %s)",
                      (session_id, session_type, person_id, json.dumps(challenge), expires_at))

    def update_status(self, session_id: uuid.UUID, status: str, failure_code: str | None = None,
                      challenge: dict | None = None) -> None:
        with self.db.connect() as c:
            c.execute("UPDATE recognition_sessions SET status = %s, failure_code = COALESCE(%s, failure_code), "
                      "challenge = COALESCE(%s, challenge) WHERE session_id = %s",
                      (status, failure_code, json.dumps(challenge) if challenge else None, session_id))

    def mark_completed(self, session_id: uuid.UUID) -> bool:
        """Atomically set completed_at once. False if it was already completed (duplicate)."""
        with self.db.connect() as c:
            return c.execute("UPDATE recognition_sessions SET completed_at = now() "
                             "WHERE session_id = %s AND completed_at IS NULL", (session_id,)).rowcount == 1

    def get(self, session_id: uuid.UUID) -> dict | None:
        with self.db.connect() as c:
            return c.execute("SELECT * FROM recognition_sessions WHERE session_id = %s", (session_id,)).fetchone()

    def add_liveness_event(self, session_id: uuid.UUID, frame_number: int, score: float, is_live: bool,
                           stage: str) -> None:
        with self.db.connect() as c:
            c.execute("INSERT INTO liveness_events(session_id, frame_number, score, prediction, stage) "
                      "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (session_id, frame_number) DO NOTHING",
                      (session_id, frame_number, score, "LIVE" if is_live else "SPOOF", stage))

    def liveness_events(self, session_id: uuid.UUID) -> list[dict]:
        with self.db.connect() as c:
            return c.execute("SELECT frame_number, score, prediction, stage, created_at FROM liveness_events "
                             "WHERE session_id = %s ORDER BY frame_number", (session_id,)).fetchall()

    def add_result(self, session_id: uuid.UUID, result: str, person_id: uuid.UUID | None = None,
                   similarity: float | None = None, liveness: float | None = None, threshold: float | None = None,
                   model_name: str | None = None, model_version: str | None = None) -> None:
        with self.db.connect() as c:
            c.execute("INSERT INTO recognition_results(session_id, person_id, similarity_score, liveness_score, "
                      "threshold, model_name, model_version, result) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                      "ON CONFLICT (session_id) DO NOTHING",
                      (session_id, person_id, similarity, liveness, threshold, model_name, model_version, result))

    def get_result(self, session_id: uuid.UUID) -> dict | None:
        with self.db.connect() as c:
            return c.execute("SELECT * FROM recognition_results WHERE session_id = %s", (session_id,)).fetchone()


class VectorSearchService:
    """Nearest-neighbour search on face_embeddings with cosine distance (pgvector `<=>`).

    Only embeddings with the same model_name, model_version and dimension are ever compared.
    Exact (sequential) search: fine for a research gallery of hundreds of people; an HNSW
    index needs a fixed-dimension column and can be added once a single model is final.
    """

    def __init__(self, db: Database):
        self.db = db

    def insert(self, person_id: uuid.UUID, embedding: np.ndarray, meta: EmbeddingMeta,
               pose: str | None = None, quality_score: float | None = None) -> uuid.UUID:
        emb = np.asarray(embedding, dtype=np.float32)
        if emb.ndim != 1 or emb.shape[0] != meta.embedding_dimension or not np.isfinite(emb).all():
            raise AppError(ErrorCode.INVALID_REQUEST, "Embedding does not match its declared dimension")
        with self.db.connect() as c:
            return c.execute(
                "INSERT INTO face_embeddings(person_id, embedding, model_name, model_version, embedding_dimension, "
                "preprocessing_version, pose, quality_score) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (person_id, emb, meta.model_name, meta.model_version, meta.embedding_dimension,
                 meta.preprocessing_version, pose, quality_score)).fetchone()["id"]

    def search(self, embedding: np.ndarray, meta: EmbeddingMeta, top_k: int = 5,
               only_active: bool = True) -> list[dict]:
        """Return up to top_k PEOPLE (best embedding per person), highest similarity first.

        similarity = 1 - cosine_distance = cosine similarity.
        """
        emb = np.asarray(embedding, dtype=np.float32)
        if emb.shape != (meta.embedding_dimension,):
            raise AppError(ErrorCode.INVALID_REQUEST, "Query embedding dimension mismatch")
        status_filter = "AND p.status = 'ACTIVE'" if only_active else ""
        sql = f"""
            SELECT person_id, name, external_id, max(similarity) AS similarity, count(*) AS matched_embeddings
            FROM (
                SELECT e.person_id, p.name, p.external_id,
                       1 - (e.embedding::vector({meta.embedding_dimension}) <=> %(q)s) AS similarity
                FROM face_embeddings e JOIN people p ON p.id = e.person_id
                WHERE e.model_name = %(m)s AND e.model_version = %(v)s
                  AND e.embedding_dimension = %(d)s AND e.preprocessing_version = %(pv)s {status_filter}
            ) s
            GROUP BY person_id, name, external_id
            ORDER BY similarity DESC
            LIMIT %(k)s
        """
        with self.db.connect() as c:
            rows = c.execute(sql, {"q": emb, "m": meta.model_name, "v": meta.model_version,
                                   "d": meta.embedding_dimension, "pv": meta.preprocessing_version,
                                   "k": top_k}).fetchall()
        return [{**r, "similarity": float(r["similarity"])} for r in rows]

    def count(self, meta: EmbeddingMeta | None = None) -> int:
        with self.db.connect() as c:
            if meta is None:
                return c.execute("SELECT count(*) AS n FROM face_embeddings").fetchone()["n"]
            return c.execute("SELECT count(*) AS n FROM face_embeddings WHERE model_name = %s AND model_version = %s",
                             (meta.model_name, meta.model_version)).fetchone()["n"]
