"""每日签到与运势业务服务模块。"""

from __future__ import annotations

import asyncio
import random
import time
from typing import Any

from ..models.entities import LUCK_LIST
from ..storage.points_repository import PointsRepository


class CheckinService:
    """签到核心业务逻辑服务。"""

    def __init__(self, repo: PointsRepository):
        self.repo = repo

    def generate_luck(self) -> dict[str, Any]:
        weights = [item["weight"] for item in LUCK_LIST]
        return random.choices(LUCK_LIST, weights=weights, k=1)[0]

    async def process_checkin(
        self,
        user_id: str,
        group_id: str | None,
        nickname: str,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        gkey = self.repo.resolve_group_key(group_id, config)
        uid = str(user_id).strip()
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._process_checkin_sync, gkey, group_id, uid, nickname, config
        )

    def _process_checkin_sync(
        self,
        group_key: str,
        raw_group_id: str | None,
        user_id: str,
        nickname: str,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        init_pts = int(config.get("initial_points", 0))
        u = self.repo._get_user_info_sync(group_key, user_id, nickname, init_pts)

        reset_hour = int(config.get("checkin_reset_hour", 0))
        today_date = self.repo.get_current_business_date(reset_hour)
        yesterday_date = self.repo.get_previous_business_date(reset_hour)

        if u.get("last_checkin_date") == today_date:
            return {
                "success": False,
                "msg": "今天已经签到过啦，明天再来找人家玩吧喵~",
                "user_info": u,
            }

        # 连续签到天数计算
        last_date = u.get("last_checkin_date", "")
        if last_date == yesterday_date:
            continuous_days = int(u.get("continuous_checkin_days", 0)) + 1
        else:
            continuous_days = 1

        # 基础随机积分
        min_pts = int(config.get("checkin_min_points", 10))
        max_pts = int(config.get("checkin_max_points", 50))
        if max_pts < min_pts:
            max_pts = min_pts
        base_points = random.randint(min_pts, max_pts)

        # 连续签到加成
        streak_bonus = 0
        if config.get("checkin_streak_enabled", True):
            bonus_per_day = int(config.get("checkin_streak_bonus_per_day", 3))
            max_bonus = int(config.get("checkin_streak_max_bonus", 60))
            streak_bonus = min((continuous_days - 1) * bonus_per_day, max_bonus)

        # 群签到排名顺位奖励
        rank_bonus = 0
        rank_title = ""
        rank_num = 0
        actual_gid = str(raw_group_id or "").strip()
        if actual_gid:
            with self.repo.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT COUNT(*) as cnt FROM daily_group_checkin WHERE group_id = ? AND checkin_date = ?",
                    (actual_gid, today_date),
                )
                rank_num = int(cursor.fetchone()["cnt"]) + 1
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO daily_group_checkin (group_id, checkin_date, user_id, rank_num, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """,
                    (actual_gid, today_date, user_id, rank_num, int(time.time())),
                )
                conn.commit()

            if rank_num == 1:
                rank_bonus = int(config.get("checkin_first_bonus", 20))
                rank_title = "🥇 今天的群内首签状元！"
            elif rank_num == 2:
                rank_bonus = int(config.get("checkin_second_bonus", 10))
                rank_title = "🥈 今天的群内榜眼！"
            elif rank_num == 3:
                rank_bonus = int(config.get("checkin_third_bonus", 5))
                rank_title = "🥉 今天的群内探花！"
            else:
                rank_title = f"第 {rank_num} 位签到"

        # 运势吉凶
        luck = self.generate_luck()
        luck_name = luck["name"]
        luck_desc = luck["desc"]
        luck_multiplier = (
            luck["multiplier"]
            if config.get("checkin_luck_affects_points", True)
            else 1.0
        )

        # 计算本次总计获得
        total_gained = int((base_points + streak_bonus + rank_bonus) * luck_multiplier)
        total_gained = max(1, total_gained)

        # 更新数据库
        now_ts = int(time.time())
        with self.repo.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE user_points
                SET points = points + ?,
                    total_points_earned = total_points_earned + ?,
                    total_checkin_count = total_checkin_count + 1,
                    continuous_checkin_days = ?,
                    last_checkin_date = ?,
                    last_checkin_timestamp = ?,
                    today_luck = ?,
                    today_luck_desc = ?,
                    updated_at = ?
                WHERE group_id = ? AND user_id = ?
            """,
                (
                    total_gained,
                    total_gained,
                    continuous_days,
                    today_date,
                    now_ts,
                    luck_name,
                    luck_desc,
                    now_ts,
                    group_key,
                    user_id,
                ),
            )
            conn.commit()

        u = self.repo._get_user_info_sync(group_key, user_id, nickname, init_pts)

        return {
            "success": True,
            "base_points": base_points,
            "streak_bonus": streak_bonus,
            "rank_bonus": rank_bonus,
            "rank_num": rank_num,
            "rank_title": rank_title,
            "luck_name": luck_name,
            "luck_desc": luck_desc,
            "luck_multiplier": luck_multiplier,
            "total_gained": total_gained,
            "continuous_days": continuous_days,
            "total_checkin_count": u["total_checkin_count"],
            "current_points": u["points"],
            "user_info": u,
        }
