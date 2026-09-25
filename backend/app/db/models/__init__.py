"""ORM models.

Importing this package registers every table on ``Base.metadata``, which is what
Alembic and the test fixtures rely on.
"""

from app.db.models.areas import Area
from app.db.models.daily import DailyHabitEntry
from app.db.models.daily_state import DailyState
from app.db.models.habits import Habit, HabitVersion
from app.db.models.insights import InsightSnapshot
from app.db.models.system import AppMetadata

__all__ = ["AppMetadata", "Area", "DailyHabitEntry", "DailyState", "Habit", "HabitVersion",
           "InsightSnapshot"]
