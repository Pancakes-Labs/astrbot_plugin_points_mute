"""向后兼容转发模块。"""

from .core.storage.points_repository import PointsRepository as DataManager
from .core.storage.sqlite_db import SqliteDatabase

__all__ = ["DataManager", "SqliteDatabase"]
