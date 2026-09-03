"""积分禁言、自闭与赎身核心业务服务模块。"""

from __future__ import annotations

import math
import random
from typing import Any

from astrbot.api.event import AstrMessageEvent

from ..storage.points_repository import PointsRepository
from ..utils.message_helper import MessageHelper
from ..utils.mute_engine import MuteEngine


class MuteService:
    """负责处理禁言扣费、上限保护、自闭优惠、护盾防御与解禁赎身。"""

    def __init__(self, repo: PointsRepository):
        self.repo = repo

    async def handle_mute_command(
        self, event: AstrMessageEvent, config: dict[str, Any]
    ):
        """处理普通禁言指令。"""
        group_id = event.get_group_id()
        if not group_id:
            yield MessageHelper.reply(event, "禁言功能只能在群聊中使用哦喵~", config)
            return

        sender_id = event.get_sender_id()
        curr_name = config.get("currency_name", "喵币")
        target_id, parsed_sec = MuteEngine.extract_target_and_params(event)

        if not target_id:
            cost_per_min = config.get("mute_cost_per_minute", 5)
            yield MessageHelper.reply(
                event,
                f"指令格式错误喵！\n用法：/禁言 @群友 [时长]\n例如：/禁言 @群友 5分钟 (每分钟消耗 {cost_per_min} {curr_name})",
                config,
            )
            return

        # 检查是否试图禁言机器人自身 (神罚防卫反噬)
        bot_ids = MuteEngine.get_bot_ids(event)
        if target_id in bot_ids:
            if config.get("mute_bot_defense", True):
                defense_sec = int(config.get("mute_bot_defense_duration", 180))
                penalty = int(config.get("mute_cost_per_minute", 5)) * (
                    defense_sec // 60
                )
                await self.repo.deduct_points(
                    sender_id, penalty, group_id=group_id, config=config
                )
                ok, _ = await MuteEngine.execute_mute(event, sender_id, defense_sec)
                dur_str = MuteEngine.format_duration(defense_sec)
                if ok:
                    yield MessageHelper.reply(
                        event,
                        f"⚡ 愚蠢的凡人！竟敢妄图禁言本喵Bot！\n⚡ 魔法神罚反噬启动，已反弹禁言你 {dur_str}，并没收惩罚金 {penalty} {curr_name} 喵！",
                        config,
                    )
                else:
                    yield MessageHelper.reply(
                        event,
                        f"⚡ 竟敢试图禁言本喵！虽然反噬被神秘力量阻挡，但已没收你 {penalty} {curr_name} 喵！",
                        config,
                    )
                return
            else:
                yield MessageHelper.reply(event, "哼，不可以禁言本喵哦！", config)
                return

        # 自我禁言转接
        if target_id == sender_id:
            async for r in self.handle_self_mute_command(event, parsed_sec, config):
                yield r
            return

        # 计算时长与消耗
        default_sec = int(config.get("mute_default_duration", 60))
        min_sec = int(config.get("mute_min_duration", 60))
        max_sec = int(config.get("mute_max_duration", 3600))
        allow_custom = config.get("mute_allow_custom_duration", True)

        duration_sec = (
            max(min_sec, min(parsed_sec, max_sec))
            if parsed_sec and allow_custom
            else default_sec
        )
        cost_per_min = int(config.get("mute_cost_per_minute", 5))
        minutes = math.ceil(duration_sec / 60)
        total_cost = max(1, minutes * cost_per_min)

        # 管理员免消耗
        if MessageHelper.is_admin(event) and config.get("admin_bypass_cost", False):
            total_cost = 0

        # 余额校验
        sender_pts = await self.repo.get_user_points(
            sender_id, group_id=group_id, config=config
        )
        if sender_pts < total_cost:
            dur_fmt = MuteEngine.format_duration(duration_sec)
            yield MessageHelper.reply(
                event,
                f"你的 {curr_name} 不足喵！\n本次禁言 {dur_fmt} 需要消耗 {total_cost} {curr_name}，当前余额为 {sender_pts} {curr_name}，快去签到赚积分吧喵~",
                config,
            )
            return

        # 上限校验
        allowed, limit_reason = await self.repo.check_mute_limits(
            sender_id=sender_id,
            target_id=target_id,
            group_id=group_id,
            duration_sec=duration_sec,
            config=config,
        )
        if not allowed:
            yield MessageHelper.reply(
                event, f"🚫 触发禁言上限保护：\n{limit_reason}", config
            )
            return

        # 护盾判定与反弹
        target_shields = await self.repo.get_shield_count(
            target_id, group_id=group_id, config=config
        )
        if target_shields > 0 and config.get("shield_enabled", True):
            await self.repo.consume_shield(target_id, group_id=group_id, config=config)
            if total_cost > 0:
                await self.repo.deduct_points(
                    sender_id, total_cost, group_id=group_id, config=config
                )

            shield_msg = config.get(
                "custom_shield_broken_msg",
                "🛡️ 嗡！{target} 身上爆发出一道金光，禁言护盾生效并抵挡了本次禁言！",
            ).format(target=f"@{target_id}", sender=f"@{sender_id}")

            reflect_chance = float(config.get("shield_reflect_chance", 0.3))
            if random.random() < reflect_chance:
                ref_ok, _ = await MuteEngine.execute_mute(
                    event, sender_id, duration_sec
                )
                if ref_ok:
                    dur_fmt = MuteEngine.format_duration(duration_sec)
                    yield MessageHelper.reply(
                        event,
                        f"{shield_msg}\n💥 并且护盾触发了【绝对反弹】，反弹禁言了施术者 {dur_fmt} 喵！",
                        config,
                    )
                    return
            yield MessageHelper.reply(
                event, f"{shield_msg}\n剩余护盾：{target_shields - 1} 张喵！", config
            )
            return

        # 扣款与执行
        if total_cost > 0:
            await self.repo.deduct_points(
                sender_id, total_cost, group_id=group_id, config=config
            )

        success, err_msg = await MuteEngine.execute_mute(event, target_id, duration_sec)
        if not success:
            if total_cost > 0 and config.get("mute_refund_on_fail", True):
                await self.repo.add_points(
                    sender_id, total_cost, group_id=group_id, config=config
                )
                yield MessageHelper.reply(
                    event,
                    f"❌ {err_msg}\n已全额退还扣除的 {total_cost} {curr_name} 喵~",
                    config,
                )
            else:
                yield MessageHelper.reply(event, f"❌ {err_msg}", config)
            return

        # 记录统计
        await self.repo.record_mute_event(
            sender_id=sender_id,
            target_id=target_id,
            group_id=group_id,
            duration_sec=duration_sec,
            reset_hour=int(config.get("checkin_reset_hour", 0)),
            config=config,
        )

        dur_fmt = MuteEngine.format_duration(duration_sec)
        success_tmpl = config.get(
            "custom_mute_success_msg",
            "🎯 成功对 {target} 施加了 {duration} 的禁言封印！",
        )
        msg_out = success_tmpl.format(
            sender=f"@{sender_id}",
            target=f"@{target_id}",
            duration=dur_fmt,
            cost=total_cost,
            currency=curr_name,
        )
        remaining = await self.repo.get_user_points(
            sender_id, group_id=group_id, config=config
        )
        yield MessageHelper.reply(
            event,
            f"{msg_out}\n消耗：{total_cost} {curr_name} | 剩余：{remaining} {curr_name} 喵~",
            config,
        )

    async def handle_self_mute_command(
        self, event: AstrMessageEvent, parsed_sec: int | None, config: dict[str, Any]
    ):
        """处理自闭自我禁言指令。"""
        group_id = event.get_group_id()
        if not group_id:
            yield MessageHelper.reply(event, "自闭功能只能在群聊中使用哦喵~", config)
            return

        sender_id = event.get_sender_id()
        curr_name = config.get("currency_name", "喵币")
        default_sec = int(config.get("mute_default_duration", 60))
        max_self_dur = int(config.get("self_mute_max_duration", 86400))
        duration_sec = parsed_sec if parsed_sec else default_sec
        duration_sec = max(60, min(duration_sec, max_self_dur))

        cost_per_min = int(config.get("mute_cost_per_minute", 5))
        discount = float(config.get("self_mute_discount", 0.5))
        minutes = math.ceil(duration_sec / 60)
        total_cost = max(1, int(minutes * cost_per_min * discount))

        sender_pts = await self.repo.get_user_points(
            sender_id, group_id=group_id, config=config
        )
        if sender_pts < total_cost:
            dur_fmt = MuteEngine.format_duration(duration_sec)
            yield MessageHelper.reply(
                event,
                f"你的 {curr_name} 不够自闭喵！\n自闭 {dur_fmt} 需要 {total_cost} {curr_name} (已享 {int(discount * 10)} 折优惠)，当前只有 {sender_pts} {curr_name} 喵~",
                config,
            )
            return

        await self.repo.deduct_points(
            sender_id, total_cost, group_id=group_id, config=config
        )

        success, err_msg = await MuteEngine.execute_mute(event, sender_id, duration_sec)
        if not success:
            if config.get("mute_refund_on_fail", True):
                await self.repo.add_points(
                    sender_id, total_cost, group_id=group_id, config=config
                )
                yield MessageHelper.reply(
                    event,
                    f"❌ 自闭失败：{err_msg}\n已退还 {total_cost} {curr_name} 喵~",
                    config,
                )
            else:
                yield MessageHelper.reply(event, f"❌ 自闭失败：{err_msg}", config)
            return

        dur_fmt = MuteEngine.format_duration(duration_sec)
        remaining = await self.repo.get_user_points(
            sender_id, group_id=group_id, config=config
        )
        yield MessageHelper.reply(
            event,
            f"🧘 闭关成功！已为你施加 {dur_fmt} 静心封印，祝你专注高效喵！\n花费：{total_cost} {curr_name} | 剩余：{remaining} {curr_name}",
            config,
        )

    async def handle_unmute_command(
        self, event: AstrMessageEvent, config: dict[str, Any]
    ):
        """处理赎身解禁指令。"""
        group_id = event.get_group_id()
        if not group_id:
            yield MessageHelper.reply(event, "解禁功能只能在群聊中使用哦喵~", config)
            return

        sender_id = event.get_sender_id()
        curr_name = config.get("currency_name", "喵币")
        target_id, _ = MuteEngine.extract_target_and_params(event)
        if not target_id:
            target_id = sender_id

        cost = int(config.get("unmute_cost", 50))
        sender_pts = await self.repo.get_user_points(
            sender_id, group_id=group_id, config=config
        )
        if sender_pts < cost:
            yield MessageHelper.reply(
                event,
                f"赎身需要 {cost} {curr_name}，你当前只有 {sender_pts} {curr_name} 喵！",
                config,
            )
            return

        await self.repo.deduct_points(sender_id, cost, group_id=group_id, config=config)

        ok, err_msg = await MuteEngine.execute_unmute(event, target_id)
        if not ok:
            if config.get("mute_refund_on_fail", True):
                await self.repo.add_points(
                    sender_id, cost, group_id=group_id, config=config
                )
                yield MessageHelper.reply(
                    event,
                    f"❌ 解禁失败：{err_msg}\n已退还 {cost} {curr_name} 喵~",
                    config,
                )
            else:
                yield MessageHelper.reply(event, f"❌ 解禁失败：{err_msg}", config)
            return

        target_str = "你自己" if target_id == sender_id else f"@{target_id}"
        remaining = await self.repo.get_user_points(
            sender_id, group_id=group_id, config=config
        )
        yield MessageHelper.reply(
            event,
            f"🕊️ 善哉善哉！成功为 {target_str} 解除封印！\n消耗赎金：{cost} {curr_name} | 剩余：{remaining} {curr_name} 喵~",
            config,
        )
