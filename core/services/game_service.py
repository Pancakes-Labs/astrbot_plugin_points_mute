"""小游戏与对决服务模块（俄罗斯轮盘赌）。"""

from __future__ import annotations

import random
from typing import Any

from astrbot.api.event import AstrMessageEvent

from ..storage.points_repository import PointsRepository
from ..utils.message_helper import MessageHelper
from ..utils.mute_engine import MuteEngine


class GameService:
    """负责处理禁言俄罗斯轮盘赌等小游戏逻辑。"""

    def __init__(self, repo: PointsRepository):
        self.repo = repo

    async def handle_roulette_command(
        self, event: AstrMessageEvent, config: dict[str, Any]
    ):
        """处理俄罗斯轮盘赌对决。"""
        group_id = event.get_group_id()
        if not group_id:
            yield MessageHelper.reply(event, "轮盘赌只能在群聊中进行喵~", config)
            return

        sender_id = event.get_sender_id()
        curr_name = config.get("currency_name", "喵币")
        target_id, bet_val = MuteEngine.extract_target_and_params(event, is_time=False)

        if not target_id or target_id == sender_id:
            yield MessageHelper.reply(
                event,
                "请 @ 一位群友作为轮盘决斗对手喵！\n用法：/轮盘赌 @某人 [下注积分]",
                config,
            )
            return

        min_bet = int(config.get("roulette_min_bet", 10))
        max_bet = int(config.get("roulette_max_bet", 200))
        bet = bet_val if bet_val else min_bet
        bet = max(min_bet, min(bet, max_bet))

        sender_pts = await self.repo.get_user_points(
            sender_id, group_id=group_id, config=config
        )
        if sender_pts < bet:
            yield MessageHelper.reply(
                event,
                f"下注需要 {bet} {curr_name}，你当前只有 {sender_pts} {curr_name} 喵！",
                config,
            )
            return

        win_rate = float(config.get("roulette_win_rate", 0.5))
        base_dur = int(config.get("roulette_base_duration", 60))
        punish_sec = base_dur + (bet // 2)

        await self.repo.deduct_points(sender_id, bet, group_id=group_id, config=config)

        lines = [
            "🎰 ─── 俄罗斯轮盘赌开盘 ─── 🎰",
            f"🔫 挑战者：@{sender_id}",
            f"🎯 迎战者：@{target_id}",
            f"💰 决斗赌注：{bet} {curr_name}",
            "咔哒... 扳机扣动中！",
        ]

        if random.random() < win_rate:
            ok, err = await MuteEngine.execute_mute(event, target_id, punish_sec)
            reward = bet * 2
            await self.repo.add_points(
                sender_id, reward, group_id=group_id, config=config
            )
            dur_fmt = MuteEngine.format_duration(punish_sec)
            lines.extend(
                [
                    "──────────────",
                    f"💥 砰！子弹击中了 @{target_id}！",
                    f"🏆 挑战者 @{sender_id} 获得胜利！赢取彩金 +{reward} {curr_name}！",
                ]
            )
            if ok:
                lines.append(f"⏱️ 败者已被施加 {dur_fmt} 禁言封印喵！")
            else:
                lines.append(f"⚠️ 败者禁言受阻：{err}")
        else:
            ok, err = await MuteEngine.execute_mute(event, sender_id, punish_sec)
            dur_fmt = MuteEngine.format_duration(punish_sec)
            lines.extend(
                [
                    "──────────────",
                    f"💥 砰！枪管炸膛，反噬了挑战者 @{sender_id}！",
                    f"💀 挑战失败，输掉了 {bet} {curr_name} 赌注！",
                ]
            )
            if ok:
                lines.append(f"⏱️ 发起者已被反噬禁言 {dur_fmt} 喵！")
            else:
                lines.append(f"⚠️ 发起者禁言受阻：{err}")

        yield MessageHelper.reply(event, "\n".join(lines), config)
