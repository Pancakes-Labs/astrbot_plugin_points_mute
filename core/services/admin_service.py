"""管理员操作与排行榜查询服务模块。"""

from __future__ import annotations

from typing import Any

from astrbot.api.event import AstrMessageEvent

from ..storage.points_repository import PointsRepository
from ..utils.message_helper import MessageHelper
from ..utils.mute_engine import MuteEngine


class AdminService:
    """负责管理员积分管理与排行榜生成。"""

    def __init__(self, repo: PointsRepository):
        self.repo = repo

    async def handle_points_rank(self, event: AstrMessageEvent, config: dict[str, Any]):
        """生成积分排行榜。"""
        group_id = event.get_group_id()
        scope = config.get("rank_scope", "group")
        limit = int(config.get("rank_page_size", 10))
        curr_name = config.get("currency_name", "喵币")

        ranking = await self.repo.get_points_ranking(
            group_id=group_id if scope == "group" else None, limit=limit, config=config
        )
        title = f"🏆 {'本群' if scope == 'group' and group_id else '全局'} {curr_name} 排行榜 Top {len(ranking)}"

        if not ranking:
            yield MessageHelper.reply(
                event, "目前还没有排行榜数据喵~ 赶紧签到赚积分吧！", config
            )
            return

        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        lines = [title, "──────────────"]
        for idx, item in enumerate(ranking):
            icon = medals[idx] if idx < len(medals) else f"{idx + 1}."
            name = item.get("nickname") or f"用户_{item['user_id'][-4:]}"
            pts = item.get("points", 0)
            lines.append(f"{icon} {name} ➜ {pts} {curr_name}")

        yield MessageHelper.reply(event, "\n".join(lines), config)

    async def handle_streak_rank(self, event: AstrMessageEvent, config: dict[str, Any]):
        """生成连续签到排行榜。"""
        group_id = event.get_group_id()
        scope = config.get("rank_scope", "group")
        limit = int(config.get("rank_page_size", 10))

        ranking = await self.repo.get_streak_ranking(
            group_id=group_id if scope == "group" else None, limit=limit, config=config
        )
        title = f"🔥 {'本群' if scope == 'group' and group_id else '全局'} 连续签到榜 Top {len(ranking)}"

        if not ranking:
            yield MessageHelper.reply(event, "目前还没有签到排行数据喵~", config)
            return

        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        lines = [title, "──────────────"]
        for idx, item in enumerate(ranking):
            icon = medals[idx] if idx < len(medals) else f"{idx + 1}."
            name = item.get("nickname") or f"用户_{item['user_id'][-4:]}"
            days = item.get("continuous_checkin_days", 0)
            lines.append(f"{icon} {name} ➜ 连续 {days} 天")

        yield MessageHelper.reply(event, "\n".join(lines), config)

    async def handle_add_points(self, event: AstrMessageEvent, config: dict[str, Any]):
        """加积分指令。"""
        group_id = event.get_group_id()
        curr_name = config.get("currency_name", "喵币")
        target_id, parsed_val = MuteEngine.extract_target_and_params(
            event, is_time=False
        )
        if not target_id or not parsed_val:
            yield MessageHelper.reply(event, "格式：/加积分 @某人 数量", config)
            return

        new_total = await self.repo.add_points(
            target_id, parsed_val, group_id=group_id, config=config
        )
        yield MessageHelper.reply(
            event,
            f"✅ 已成功为 @{target_id} 充值 +{parsed_val} {curr_name}，其当前总余额为 {new_total} {curr_name} 喵~",
            config,
        )

    async def handle_sub_points(self, event: AstrMessageEvent, config: dict[str, Any]):
        """扣积分指令。"""
        group_id = event.get_group_id()
        curr_name = config.get("currency_name", "喵币")
        target_id, parsed_val = MuteEngine.extract_target_and_params(
            event, is_time=False
        )
        if not target_id or not parsed_val:
            yield MessageHelper.reply(event, "格式：/扣积分 @某人 数量", config)
            return

        await self.repo.deduct_points(
            target_id, parsed_val, group_id=group_id, config=config
        )
        curr = await self.repo.get_user_points(
            target_id, group_id=group_id, config=config
        )
        yield MessageHelper.reply(
            event,
            f"✅ 已成功扣除 @{target_id} 的 {parsed_val} {curr_name}，剩余 {curr} {curr_name} 喵~",
            config,
        )

    async def handle_set_points(self, event: AstrMessageEvent, config: dict[str, Any]):
        """设积分指令。"""
        group_id = event.get_group_id()
        curr_name = config.get("currency_name", "喵币")
        target_id, parsed_val = MuteEngine.extract_target_and_params(
            event, is_time=False
        )
        if not target_id or parsed_val is None:
            yield MessageHelper.reply(event, "格式：/设积分 @某人 数量", config)
            return

        new_pts = await self.repo.set_points(
            target_id, parsed_val, group_id=group_id, config=config
        )
        yield MessageHelper.reply(
            event,
            f"✅ 已将 @{target_id} 的 {curr_name} 调整为 {new_pts} {curr_name} 喵~",
            config,
        )
