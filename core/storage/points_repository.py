"""积分与用户数据仓储模块。"""

from __future__ import annotations

import asyncio
import math
import time
from datetime import datetime, timedelta
from typing import Any

from .sqlite_db import SqliteDatabase


class PointsRepository:
    """负责处理用户积分、签到记录、上限统计和数据查询的仓储层。"""

    def __init__(self, db: SqliteDatabase):
        self.db = db

    def resolve_group_key(
        self, group_id: str | None, config: dict[str, Any] | None = None
    ) -> str:
        """根据隔离模式解析 group_key。"""
        if config and config.get("points_isolation_mode") == "global_shared":
            return "_global_"
        gid = str(group_id or "").strip()
        return gid if gid else "_global_"

    def get_current_business_date(self, reset_hour: int = 0) -> str:
        now = datetime.now()
        if now.hour < reset_hour:
            adjusted = now - timedelta(days=1)
        else:
            adjusted = now
        return adjusted.strftime("%Y-%m-%d")

    def get_previous_business_date(self, reset_hour: int = 0) -> str:
        now = datetime.now()
        if now.hour < reset_hour:
            adjusted = now - timedelta(days=2)
        else:
            adjusted = now - timedelta(days=1)
        return adjusted.strftime("%Y-%m-%d")

    # ================= 基础积分查询与更新 =================

    async def get_user_points(
        self,
        user_id: str,
        group_id: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> int:
        gkey = self.resolve_group_key(group_id, config)
        uid = str(user_id).strip()
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._get_points_sync, gkey, uid)

    def _get_points_sync(self, group_key: str, user_id: str) -> int:
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT points FROM user_points WHERE group_id = ? AND user_id = ?",
                (group_key, user_id),
            )
            row = cursor.fetchone()
            return int(row["points"]) if row else 0

    async def get_user_info(
        self,
        user_id: str,
        group_id: str | None = None,
        nickname: str = "",
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        gkey = self.resolve_group_key(group_id, config)
        uid = str(user_id).strip()
        init_pts = int(config.get("initial_points", 0)) if config else 0
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._get_user_info_sync, gkey, uid, nickname, init_pts
        )

    def _get_user_info_sync(
        self, group_key: str, user_id: str, nickname: str, init_pts: int
    ) -> dict[str, Any]:
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM user_points WHERE group_id = ? AND user_id = ?",
                (group_key, user_id),
            )
            row = cursor.fetchone()
            if row:
                data = dict(row)
                if nickname and data.get("nickname") != nickname:
                    cursor.execute(
                        "UPDATE user_points SET nickname = ?, updated_at = ? WHERE group_id = ? AND user_id = ?",
                        (nickname, int(time.time()), group_key, user_id),
                    )
                    conn.commit()
                    data["nickname"] = nickname
                return data

            name = nickname or f"用户_{user_id[-4:] if len(user_id) >= 4 else user_id}"
            now_ts = int(time.time())
            cursor.execute(
                """
                INSERT INTO user_points (
                    group_id, user_id, nickname, points, shields,
                    total_checkin_count, continuous_checkin_days, last_checkin_date,
                    last_checkin_timestamp, today_luck, today_luck_desc,
                    mute_count_done, mute_count_received, total_points_earned,
                    total_points_spent, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    group_key,
                    user_id,
                    name,
                    init_pts,
                    0,
                    0,
                    0,
                    "",
                    0,
                    "",
                    "",
                    0,
                    0,
                    init_pts,
                    0,
                    now_ts,
                ),
            )
            conn.commit()
            return {
                "group_id": group_key,
                "user_id": user_id,
                "nickname": name,
                "points": init_pts,
                "shields": 0,
                "total_checkin_count": 0,
                "continuous_checkin_days": 0,
                "last_checkin_date": "",
                "last_checkin_timestamp": 0,
                "today_luck": "",
                "today_luck_desc": "",
                "mute_count_done": 0,
                "mute_count_received": 0,
                "total_points_earned": init_pts,
                "total_points_spent": 0,
                "updated_at": now_ts,
            }

    async def add_points(
        self,
        user_id: str,
        amount: int,
        group_id: str | None = None,
        nickname: str = "",
        config: dict[str, Any] | None = None,
    ) -> int:
        if amount <= 0:
            return await self.get_user_points(user_id, group_id, config)
        gkey = self.resolve_group_key(group_id, config)
        uid = str(user_id).strip()
        init_pts = int(config.get("initial_points", 0)) if config else 0
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._add_points_sync, gkey, uid, amount, nickname, init_pts
        )

    def _add_points_sync(
        self, group_key: str, user_id: str, amount: int, nickname: str, init_pts: int
    ) -> int:
        self._get_user_info_sync(group_key, user_id, nickname, init_pts)
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE user_points
                SET points = points + ?,
                    total_points_earned = total_points_earned + ?,
                    updated_at = ?
                WHERE group_id = ? AND user_id = ?
            """,
                (amount, amount, int(time.time()), group_key, user_id),
            )
            conn.commit()
            cursor.execute(
                "SELECT points FROM user_points WHERE group_id = ? AND user_id = ?",
                (group_key, user_id),
            )
            row = cursor.fetchone()
            return int(row["points"]) if row else 0

    async def deduct_points(
        self,
        user_id: str,
        amount: int,
        group_id: str | None = None,
        nickname: str = "",
        config: dict[str, Any] | None = None,
    ) -> bool:
        if amount <= 0:
            return True
        gkey = self.resolve_group_key(group_id, config)
        uid = str(user_id).strip()
        init_pts = int(config.get("initial_points", 0)) if config else 0
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._deduct_points_sync, gkey, uid, amount, nickname, init_pts
        )

    def _deduct_points_sync(
        self, group_key: str, user_id: str, amount: int, nickname: str, init_pts: int
    ) -> bool:
        self._get_user_info_sync(group_key, user_id, nickname, init_pts)
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT points FROM user_points WHERE group_id = ? AND user_id = ?",
                (group_key, user_id),
            )
            row = cursor.fetchone()
            current = int(row["points"]) if row else 0
            if current < amount:
                return False

            cursor.execute(
                """
                UPDATE user_points
                SET points = points - ?,
                    total_points_spent = total_points_spent + ?,
                    updated_at = ?
                WHERE group_id = ? AND user_id = ?
            """,
                (amount, amount, int(time.time()), group_key, user_id),
            )
            conn.commit()
            return True

    async def set_points(
        self,
        user_id: str,
        amount: int,
        group_id: str | None = None,
        nickname: str = "",
        config: dict[str, Any] | None = None,
    ) -> int:
        gkey = self.resolve_group_key(group_id, config)
        uid = str(user_id).strip()
        init_pts = int(config.get("initial_points", 0)) if config else 0
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            self._set_points_sync,
            gkey,
            uid,
            max(0, int(amount)),
            nickname,
            init_pts,
        )

    def _set_points_sync(
        self, group_key: str, user_id: str, amount: int, nickname: str, init_pts: int
    ) -> int:
        self._get_user_info_sync(group_key, user_id, nickname, init_pts)
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE user_points SET points = ?, updated_at = ? WHERE group_id = ? AND user_id = ?",
                (amount, int(time.time()), group_key, user_id),
            )
            conn.commit()
            return amount

    # ================= 护盾相关 =================

    async def add_shield(
        self,
        user_id: str,
        count: int = 1,
        group_id: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> int:
        gkey = self.resolve_group_key(group_id, config)
        uid = str(user_id).strip()
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._add_shield_sync, gkey, uid, count)

    def _add_shield_sync(self, group_key: str, user_id: str, count: int) -> int:
        self._get_user_info_sync(group_key, user_id, "", 0)
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE user_points
                SET shields = shields + ?, updated_at = ?
                WHERE group_id = ? AND user_id = ?
            """,
                (count, int(time.time()), group_key, user_id),
            )
            conn.commit()
            cursor.execute(
                "SELECT shields FROM user_points WHERE group_id = ? AND user_id = ?",
                (group_key, user_id),
            )
            row = cursor.fetchone()
            return int(row["shields"]) if row else 0

    async def consume_shield(
        self,
        user_id: str,
        group_id: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> bool:
        gkey = self.resolve_group_key(group_id, config)
        uid = str(user_id).strip()
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._consume_shield_sync, gkey, uid)

    def _consume_shield_sync(self, group_key: str, user_id: str) -> bool:
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT shields FROM user_points WHERE group_id = ? AND user_id = ?",
                (group_key, user_id),
            )
            row = cursor.fetchone()
            current = int(row["shields"]) if row else 0
            if current > 0:
                cursor.execute(
                    """
                    UPDATE user_points
                    SET shields = shields - 1, updated_at = ?
                    WHERE group_id = ? AND user_id = ?
                """,
                    (int(time.time()), group_key, user_id),
                )
                conn.commit()
                return True
            return False

    async def get_shield_count(
        self,
        user_id: str,
        group_id: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> int:
        gkey = self.resolve_group_key(group_id, config)
        uid = str(user_id).strip()
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._get_shield_count_sync, gkey, uid)

    def _get_shield_count_sync(self, group_key: str, user_id: str) -> int:
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT shields FROM user_points WHERE group_id = ? AND user_id = ?",
                (group_key, user_id),
            )
            row = cursor.fetchone()
            return int(row["shields"]) if row else 0

    # ================= 每日禁言统计与上限 =================

    async def check_mute_limits(
        self,
        sender_id: str,
        target_id: str,
        group_id: str | None,
        duration_sec: int,
        config: dict[str, Any],
    ) -> tuple[bool, str]:
        gid = str(group_id or "").strip()
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            self._check_mute_limits_sync,
            sender_id,
            target_id,
            gid,
            duration_sec,
            config,
        )

    def _check_mute_limits_sync(
        self,
        sender_id: str,
        target_id: str,
        group_id: str,
        duration_sec: int,
        config: dict[str, Any],
    ) -> tuple[bool, str]:
        reset_hour = int(config.get("checkin_reset_hour", 0))
        today_date = self.get_current_business_date(reset_hour)

        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            # 1. 检查全群每日总禁言上限
            if group_id:
                group_mute_limit = int(config.get("group_daily_mute_total_limit", 50))
                if group_mute_limit > 0:
                    cursor.execute(
                        "SELECT total_count FROM group_daily_mute_total WHERE stat_date = ? AND group_id = ?",
                        (today_date, group_id),
                    )
                    row = cursor.fetchone()
                    if row and int(row["total_count"]) >= group_mute_limit:
                        return (
                            False,
                            f"今天本群的禁言总次数已达上限（{group_mute_limit} 次），为了群聊安宁，今日禁止再禁言喵~",
                        )

            # 2. 检查发起者每日发起次数上限
            sender_limit = int(config.get("daily_user_mute_limit", 5))
            if sender_limit > 0:
                cursor.execute(
                    "SELECT mute_done_count FROM daily_mute_stats WHERE stat_date = ? AND group_id = ? AND user_id = ?",
                    (today_date, group_id, sender_id),
                )
                row = cursor.fetchone()
                if row and int(row["mute_done_count"]) >= sender_limit:
                    return (
                        False,
                        f"你今天发起禁言的次数已达上限（{sender_limit} 次），不能再对群友施加封印啦喵~",
                    )

            # 3. 检查目标用户每日被禁言次数上限（防集火保护）
            target_muted_limit = int(config.get("daily_user_muted_limit", 5))
            if target_muted_limit > 0 and target_id != sender_id:
                cursor.execute(
                    "SELECT muted_count, muted_duration FROM daily_mute_stats WHERE stat_date = ? AND group_id = ? AND user_id = ?",
                    (today_date, group_id, target_id),
                )
                row = cursor.fetchone()
                if row:
                    muted_cnt = int(row["muted_count"])
                    if muted_cnt >= target_muted_limit:
                        return (
                            False,
                            f"@{target_id} 今天已经被禁言 {muted_cnt} 次，触发了【防集火保护上限】，今日免疫所有禁言喵！",
                        )

                    target_max_duration = int(
                        config.get("daily_user_muted_max_duration", 7200)
                    )
                    if target_max_duration > 0:
                        dur_today = int(row["muted_duration"])
                        if dur_today + duration_sec > target_max_duration:
                            rem_sec = max(0, target_max_duration - dur_today)
                            return (
                                False,
                                f"@{target_id} 今日累计被禁言时长已达/即将超过上限（最大 {target_max_duration // 60} 分钟，当前剩余额度 {rem_sec // 60} 分钟），今日无法施加此长禁言喵！",
                            )

        return True, ""

    async def record_mute_event(
        self,
        sender_id: str,
        target_id: str,
        group_id: str | None = None,
        duration_sec: int = 0,
        is_self: bool = False,
        reset_hour: int = 0,
        config: dict[str, Any] | None = None,
    ) -> None:
        gkey = self.resolve_group_key(group_id, config)
        gid = str(group_id or "").strip()
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            self._record_mute_sync,
            gkey,
            gid,
            sender_id,
            target_id,
            duration_sec,
            reset_hour,
        )

    def _record_mute_sync(
        self,
        group_key: str,
        raw_group_id: str,
        sender_id: str,
        target_id: str,
        duration_sec: int,
        reset_hour: int,
    ) -> None:
        today_date = self.get_current_business_date(reset_hour)
        now_ts = int(time.time())

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE user_points
                SET mute_count_done = mute_count_done + 1, updated_at = ?
                WHERE group_id = ? AND user_id = ?
            """,
                (now_ts, group_key, sender_id),
            )

            cursor.execute(
                """
                UPDATE user_points
                SET mute_count_received = mute_count_received + 1, updated_at = ?
                WHERE group_id = ? AND user_id = ?
            """,
                (now_ts, group_key, target_id),
            )

            cursor.execute(
                """
                INSERT INTO daily_mute_stats (stat_date, group_id, user_id, mute_done_count, muted_count, muted_duration)
                VALUES (?, ?, ?, 1, 0, 0)
                ON CONFLICT(stat_date, group_id, user_id) DO UPDATE SET
                    mute_done_count = mute_done_count + 1
            """,
                (today_date, raw_group_id, sender_id),
            )

            cursor.execute(
                """
                INSERT INTO daily_mute_stats (stat_date, group_id, user_id, mute_done_count, muted_count, muted_duration)
                VALUES (?, ?, ?, 0, 1, ?)
                ON CONFLICT(stat_date, group_id, user_id) DO UPDATE SET
                    muted_count = muted_count + 1,
                    muted_duration = muted_duration + ?
            """,
                (today_date, raw_group_id, target_id, duration_sec, duration_sec),
            )

            if raw_group_id:
                cursor.execute(
                    """
                    INSERT INTO group_daily_mute_total (stat_date, group_id, total_count)
                    VALUES (?, ?, 1)
                    ON CONFLICT(stat_date, group_id) DO UPDATE SET
                        total_count = total_count + 1
                """,
                    (today_date, raw_group_id),
                )

            conn.commit()

    # ================= 排行榜查询 =================

    async def get_points_ranking(
        self,
        group_id: str | None = None,
        limit: int = 10,
        config: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        gkey = self.resolve_group_key(group_id, config)
        is_global = (config and config.get("rank_scope") == "global") or (
            group_id is None
        )
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._get_points_ranking_sync, gkey, is_global, limit
        )

    def _get_points_ranking_sync(
        self, group_key: str, is_global: bool, limit: int
    ) -> list[dict[str, Any]]:
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            if is_global and group_key == "_global_":
                cursor.execute(
                    """
                    SELECT user_id, nickname, MAX(points) as points, MAX(continuous_checkin_days) as continuous_checkin_days
                    FROM user_points
                    GROUP BY user_id
                    ORDER BY points DESC
                    LIMIT ?
                """,
                    (limit,),
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM user_points
                    WHERE group_id = ?
                    ORDER BY points DESC
                    LIMIT ?
                """,
                    (group_key, limit),
                )
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    async def get_streak_ranking(
        self,
        group_id: str | None = None,
        limit: int = 10,
        config: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        gkey = self.resolve_group_key(group_id, config)
        is_global = (config and config.get("rank_scope") == "global") or (
            group_id is None
        )
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._get_streak_ranking_sync, gkey, is_global, limit
        )

    def _get_streak_ranking_sync(
        self, group_key: str, is_global: bool, limit: int
    ) -> list[dict[str, Any]]:
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            if is_global and group_key == "_global_":
                cursor.execute(
                    """
                    SELECT user_id, nickname, MAX(points) as points, MAX(continuous_checkin_days) as continuous_checkin_days
                    FROM user_points
                    GROUP BY user_id
                    ORDER BY continuous_checkin_days DESC
                    LIMIT ?
                """,
                    (limit,),
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM user_points
                    WHERE group_id = ?
                    ORDER BY continuous_checkin_days DESC
                    LIMIT ?
                """,
                    (group_key, limit),
                )
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    # ================= Dashboard 页面后台管理 =================

    async def get_dashboard_stats(
        self, config: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        reset_hour = int(config.get("checkin_reset_hour", 0)) if config else 0
        today_date = self.get_current_business_date(reset_hour)
        return await loop.run_in_executor(
            None, self._get_dashboard_stats_sync, today_date
        )

    def _get_dashboard_stats_sync(self, today_date: str) -> dict[str, Any]:
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    COUNT(DISTINCT user_id) as total_unique_users,
                    COUNT(*) as total_user_group_records,
                    COALESCE(SUM(points), 0) as total_points_pool,
                    COALESCE(SUM(shields), 0) as total_shields_pool,
                    COALESCE(SUM(total_points_earned), 0) as total_earned,
                    COALESCE(SUM(total_points_spent), 0) as total_spent
                FROM user_points
            """)
            summary_row = cursor.fetchone()

            cursor.execute(
                "SELECT COUNT(*) as today_checkins FROM user_points WHERE last_checkin_date = ?",
                (today_date,),
            )
            today_checkin_row = cursor.fetchone()

            cursor.execute(
                "SELECT COALESCE(SUM(total_count), 0) as today_mutes FROM group_daily_mute_total WHERE stat_date = ?",
                (today_date,),
            )
            today_mute_row = cursor.fetchone()

            cursor.execute(
                "SELECT COUNT(DISTINCT group_id) as total_groups FROM user_points WHERE group_id != '_global_'"
            )
            groups_row = cursor.fetchone()

            return {
                "total_unique_users": int(summary_row["total_unique_users"])
                if summary_row
                else 0,
                "total_records": int(summary_row["total_user_group_records"])
                if summary_row
                else 0,
                "total_points_pool": int(summary_row["total_points_pool"])
                if summary_row
                else 0,
                "total_shields_pool": int(summary_row["total_shields_pool"])
                if summary_row
                else 0,
                "total_earned": int(summary_row["total_earned"]) if summary_row else 0,
                "total_spent": int(summary_row["total_spent"]) if summary_row else 0,
                "today_checkins": int(today_checkin_row["today_checkins"])
                if today_checkin_row
                else 0,
                "today_mutes": int(today_mute_row["today_mutes"])
                if today_mute_row
                else 0,
                "total_groups": int(groups_row["total_groups"]) if groups_row else 0,
            }

    async def get_all_active_groups(self) -> list[str]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._get_all_active_groups_sync)

    def _get_all_active_groups_sync(self) -> list[str]:
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT DISTINCT group_id FROM user_points WHERE group_id != '_global_' ORDER BY group_id"
            )
            rows = cursor.fetchall()
            return [str(r["group_id"]) for r in rows]

    async def search_users(
        self,
        search: str = "",
        group_id: str = "",
        page: int = 1,
        page_size: int = 15,
        sort_by: str = "points",
        sort_order: str = "desc",
    ) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            self._search_users_sync,
            search,
            group_id,
            max(1, page),
            max(1, min(100, page_size)),
            sort_by,
            sort_order,
        )

    def _search_users_sync(
        self,
        search: str,
        group_id: str,
        page: int,
        page_size: int,
        sort_by: str,
        sort_order: str,
    ) -> dict[str, Any]:
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            valid_sort_fields = {
                "points": "points",
                "shields": "shields",
                "continuous_checkin_days": "continuous_checkin_days",
                "total_checkin_count": "total_checkin_count",
                "updated_at": "updated_at",
                "last_checkin_timestamp": "last_checkin_timestamp",
                "mute_count_done": "mute_count_done",
                "mute_count_received": "mute_count_received",
            }
            order_col = valid_sort_fields.get(sort_by, "points")
            order_dir = "ASC" if str(sort_order).lower() == "asc" else "DESC"

            where_clauses = []
            params: list[Any] = []

            if group_id:
                where_clauses.append("group_id = ?")
                params.append(group_id)

            if search:
                s = f"%{search.strip()}%"
                where_clauses.append("(user_id LIKE ? OR nickname LIKE ?)")
                params.extend([s, s])

            where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

            cursor.execute(
                f"SELECT COUNT(*) as total FROM user_points {where_sql}", params
            )
            total_count = int(cursor.fetchone()["total"])

            offset = (page - 1) * page_size
            query_sql = f"""
                SELECT * FROM user_points
                {where_sql}
                ORDER BY {order_col} {order_dir}
                LIMIT ? OFFSET ?
            """
            cursor.execute(query_sql, params + [page_size, offset])
            rows = cursor.fetchall()
            items = [dict(r) for r in rows]

            return {
                "items": items,
                "total": total_count,
                "page": page,
                "page_size": page_size,
                "total_pages": math.ceil(total_count / page_size)
                if total_count > 0
                else 1,
            }

    async def modify_user_admin(
        self,
        group_id: str,
        user_id: str,
        action: str,
        value: int,
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._modify_user_admin_sync, group_id, user_id, action, value
        )

    def _modify_user_admin_sync(
        self, group_id: str, user_id: str, action: str, value: int
    ) -> dict[str, Any]:
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM user_points WHERE group_id = ? AND user_id = ?",
                (group_id, user_id),
            )
            row = cursor.fetchone()
            if not row:
                return {
                    "success": False,
                    "msg": f"未找到群 {group_id} 下用户 {user_id} 的记录",
                }

            now_ts = int(time.time())
            if action == "add_points":
                cursor.execute(
                    "UPDATE user_points SET points = points + ?, total_points_earned = total_points_earned + ?, updated_at = ? WHERE group_id = ? AND user_id = ?",
                    (value, max(0, value), now_ts, group_id, user_id),
                )
            elif action == "sub_points":
                cursor.execute(
                    "UPDATE user_points SET points = MAX(0, points - ?), updated_at = ? WHERE group_id = ? AND user_id = ?",
                    (value, now_ts, group_id, user_id),
                )
            elif action == "set_points":
                cursor.execute(
                    "UPDATE user_points SET points = ?, updated_at = ? WHERE group_id = ? AND user_id = ?",
                    (max(0, value), now_ts, group_id, user_id),
                )
            elif action == "set_shields":
                cursor.execute(
                    "UPDATE user_points SET shields = ?, updated_at = ? WHERE group_id = ? AND user_id = ?",
                    (max(0, value), now_ts, group_id, user_id),
                )
            elif action == "set_streak":
                cursor.execute(
                    "UPDATE user_points SET continuous_checkin_days = ?, updated_at = ? WHERE group_id = ? AND user_id = ?",
                    (max(0, value), now_ts, group_id, user_id),
                )
            elif action == "reset_checkin":
                cursor.execute(
                    "UPDATE user_points SET last_checkin_date = '', today_luck = '', today_luck_desc = '', updated_at = ? WHERE group_id = ? AND user_id = ?",
                    (now_ts, group_id, user_id),
                )
            else:
                return {"success": False, "msg": f"未知操作: {action}"}

            conn.commit()
            cursor.execute(
                "SELECT * FROM user_points WHERE group_id = ? AND user_id = ?",
                (group_id, user_id),
            )
            updated_row = dict(cursor.fetchone())
            return {"success": True, "msg": "操作成功", "user": updated_row}
