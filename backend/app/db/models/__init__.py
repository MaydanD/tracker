"""ORM models.

Importing this package registers every table on ``Base.metadata``, which is what
Alembic and the test fixtures rely on. Stage 1 models no product entities yet.
"""

from app.db.models.system import AppMetadata

__all__ = ["AppMetadata"]
