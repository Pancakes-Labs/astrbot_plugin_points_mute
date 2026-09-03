"""道具商城与积分转账服务模块。"""

from __future__ import annotations

from typing import Any

from astrbot.api.event import AstrMessageEvent

from ..storage.points_repository import PointsRepository
from ..utils.message_helper import MessageHelper
from ..utils.mute_engine import MuteEngine


class ShopService:
    """负责处理护盾购买、查询与积分转账。"""

    def __init__(self, repo: PointsRepository):
        self.repo = repo

    async def handle_buy_shield_command(
        self, event: AstrMessageEvent, count: int, config: dict[str, Any]
    ):
        """购买护盾指令。"""
        if count <= 0:
            count = 1

        sender_id = event.get_sender_id()
        group_id = event.get_group_id()
        curr_name = config.get("currency_name", "喵币")
        current_shields = await self.repo.get_shield_count(
            sender_id, group_id=group_id, config=config
        )
        max_hold = int(config.get("shield_max_hold", 3))

        if current_shields >= max_hold:
            yield MessageHelper.reply(
                event,
                f"你的背包已经装不下更多护盾啦喵！最多持有 {max_hold} 张（当前已有 {current_shields} 张）。",
                config,
            )
            return

        can_buy = min(count, max_hold - current_shields)
        price = int(config.get("shield_price", 80))
        total_price = can_buy * price

        sender_pts = await self.repo.get_user_points(
            sender_id, group_id=group_id, config=config
        )
        if sender_pts < total_price:
            yield MessageHelper.reply(
                event,
                f"你的 {curr_name} 不足喵！购买 {can_buy} 张护盾需要 {total_price} {curr_name}，当前只有 {sender_pts} {curr_name}。",
                config,
            )
            return

        await self.repo.deduct_points(
            sender_id, total_price, group_id=group_id, config=config
        )
        total_shields = await self.repo.add_shield(
            sender_id, can_buy, group_id=group_id, config=config
        )
        remaining = await self.repo.get_user_points(
            sender_id, group_id=group_id, config=config
        )

        yield MessageHelper.reply(
            event,
            f"🛡️ 购买成功！获得 {can_buy} 张禁言护盾！\n花费：{total_price} {curr_name}\n当前背包护盾：{total_shields} 张\n剩余余额：{remaining} {curr_name} 喵~",
            config,
        )

    async def handle_my_shield_command(
        self, event: AstrMessageEvent, config: dict[str, Any]
    ):
        """查询持有的护盾。"""
        sender_id = event.get_sender_id()
        group_id = event.get_group_id()
        curr_name = config.get("currency_name", "喵币")
        count = await self.repo.get_shield_count(
            sender_id, group_id=group_id, config=config
        )
        price = config.get("shield_price", 80)
        max_hold = config.get("shield_max_hold", 3)
        yield MessageHelper.reply(
            event,
            f"🛡️ 你当前拥有 【{count}/{max_hold}】 张禁言护盾喵！\n单价：{price} {curr_name}/张\n可在商城发送 /买护盾 补充防御喵~",
            config,
        )

    async def handle_transfer_command(
        self, event: AstrMessageEvent, config: dict[str, Any]
    ):
        """转账/赠送积分。"""
        sender_id = event.get_sender_id()
        group_id = event.get_group_id()
        curr_name = config.get("currency_name", "喵币")
        target_id, parsed_amount = MuteEngine.extract_target_and_params(
            event, is_time=False
        )

        if not target_id or not parsed_amount:
            yield MessageHelper.reply(
                event, "转账格式错误喵！\n用法：/转账 @某人 数量", config
            )
            return

        if target_id == sender_id:
            yield MessageHelper.reply(
                event, "不能给自己转账哦，左手倒右手会被本喵没收的喵~", config
            )
            return

        min_trans = int(config.get("transfer_min_amount", 10))
        if parsed_amount < min_trans:
            yield MessageHelper.reply(
                event, f"单次转账最低不得少于 {min_trans} {curr_name} 喵~", config
            )
            return

        sender_pts = await self.repo.get_user_points(
            sender_id, group_id=group_id, config=config
        )
        if sender_pts < parsed_amount:
            yield MessageHelper.reply(
                event, f"你的余额不足喵！当前只有 {sender_pts} {curr_name}。", config
            )
            return

        fee_rate = float(config.get("transfer_fee_rate", 0.05))
        fee = int(parsed_amount * fee_rate)
        actual_received = parsed_amount - fee

        await self.repo.deduct_points(
            sender_id, parsed_amount, group_id=group_id, config=config
        )
        await self.repo.add_points(
            target_id, actual_received, group_id=group_id, config=config
        )

        remaining = await self.repo.get_user_points(
            sender_id, group_id=group_id, config=config
        )
        yield MessageHelper.reply(
            event,
            f"💸 转账成功！\n赠予：@{target_id}\n实际到账：{actual_received} {curr_name}\n手续费(回收)：{fee} {curr_name}\n你当前剩余：{remaining} {curr_name} 喵~",
            config,
        )
