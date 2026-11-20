"""Persistence models.

Importing this package registers every ORM model with ``Base.metadata`` so that
``init_db()`` can create all tables. Model modules must be listed here; no
tables are created at import time.
"""

from app.models.knowledge_chunk import ChunkStatus, KnowledgeChunk
from app.models.knowledge_item import ItemStatus, KnowledgeItem, SourceType

__all__ = [
    "ChunkStatus",
    "KnowledgeChunk",
    "ItemStatus",
    "KnowledgeItem",
    "SourceType",
]
