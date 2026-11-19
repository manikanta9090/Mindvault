"""Persistence models.

Importing this package registers every ORM model with ``Base.metadata`` so that
``init_db()`` can create all tables. Model modules must be listed here; no
tables are created at import time.
"""

from app.models.knowledge_item import ItemStatus, KnowledgeItem, SourceType

__all__ = ["ItemStatus", "KnowledgeItem", "SourceType"]
