"""Process-wide singletons wired from Settings. Tests replace `container` fields."""
from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings, get_settings
from app.db.database import Database
from app.db.repositories import EmbeddingMeta, PeopleRepository, SessionRepository, VectorSearchService
from app.ml.registry import ModelRegistry, get_registry
from app.services.frame_analyzer import FrameAnalyzer
from app.services.session_engine import SessionEngine


@dataclass
class Container:
    settings: Settings
    db: Database
    registry: ModelRegistry
    people: PeopleRepository
    sessions: SessionRepository
    vectors: VectorSearchService
    engine: SessionEngine


_container: Container | None = None


def build_container(settings: Settings | None = None) -> Container:
    settings = settings or get_settings()
    db = Database.from_settings(settings)
    registry = get_registry()
    rec = registry.embedding.recognizer
    meta = EmbeddingMeta(rec.info.name, rec.info.version, rec.embedding_dimension, registry.alignment.version)
    people, sessions, vectors = PeopleRepository(db), SessionRepository(db), VectorSearchService(db)
    engine = SessionEngine(settings, FrameAnalyzer(registry, settings), sessions, people, vectors, meta)
    return Container(settings, db, registry, people, sessions, vectors, engine)


def get_container() -> Container:
    global _container
    if _container is None:
        _container = build_container()
    return _container


def set_container(c: Container | None) -> None:
    global _container
    _container = c
