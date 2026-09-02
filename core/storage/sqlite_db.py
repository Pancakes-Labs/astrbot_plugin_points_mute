"""SQLite 数据库底层连接与初始化模块。"""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

from astrbot.api import logger

try:
    from astrbot.core.utils.astrbot_path import get_astrbot_data_path
except ImportError:

    def get_astrbot_data_path() -> Path:
        return Path("data")


class SqliteDatabase:
    """SQLite 数据库底层管理器。"""

    def __init__(self, plugin_name: str = "astrbot_plugin_points_mute"):
        self.plugin_name = plugin_name
        self._lock = asyncio.Lock()
        base_path = Path(get_astrbot_data_path())
        self._data_dir = base_path / "plugin_data" / self.plugin_name
        self._db_file = self._data_dir / "points.db"
        self._initialized = False

    async def initialize(self) -> None:
        """异步初始化数据库与建表。"""
        async with self._lock:
            if self._initialized:
                return
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._init_db_sync)
            self._initialized = True
            logger.info(f"[积分禁言] SQLite 数据库初始化成功：{self._db_file}")

    def get_connection(self) -> sqlite3.Connection:
        """获取 SQLite 连接并配置 row_factory。"""
        self._data_dir.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._db_file, timeout=20.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db_sync(self) -> None:
        """执行建表与索引脚本。"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # 1. 用户积分主表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_points (
                    group_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    nickname TEXT NOT NULL DEFAULT '',
                    points INTEGER NOT NULL DEFAULT 0,
                    shields INTEGER NOT NULL DEFAULT 0,
                    total_checkin_count INTEGER NOT NULL DEFAULT 0,
                    continuous_checkin_days INTEGER NOT NULL DEFAULT 0,
                    last_checkin_date TEXT NOT NULL DEFAULT '',
                    last_checkin_timestamp INTEGER NOT NULL DEFAULT 0,
                    today_luck TEXT NOT NULL DEFAULT '',
                    today_luck_desc TEXT NOT NULL DEFAULT '',
                    mute_count_done INTEGER NOT NULL DEFAULT 0,
                    mute_count_received INTEGER NOT NULL DEFAULT 0,
                    total_points_earned INTEGER NOT NULL DEFAULT 0,
                    total_points_spent INTEGER NOT NULL DEFAULT 0,
                    updated_at INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (group_id, user_id)
                )
            """)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_user_points_points ON user_points (group_id, points DESC)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_user_points_streak ON user_points (group_id, continuous_checkin_days DESC)"
            )

            # 2. 每日群签到顺位表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS daily_group_checkin (
                    group_id TEXT NOT NULL,
                    checkin_date TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    rank_num INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    PRIMARY KEY (group_id, checkin_date, user_id)
                )
            """)

            # 3. 每日禁言上限统计表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS daily_mute_stats (
                    stat_date TEXT NOT NULL,
                    group_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    mute_done_count INTEGER NOT NULL DEFAULT 0,
                    muted_count INTEGER NOT NULL DEFAULT 0,
                    muted_duration INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (stat_date, group_id, user_id)
                )
            """)

            # 4. 全群每日总禁言次数表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS group_daily_mute_total (
                    stat_date TEXT NOT NULL,
                    group_id TEXT NOT NULL,
                    total_count INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (stat_date, group_id)
                )
            """)
            conn.commit()
