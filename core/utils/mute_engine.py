"""多消息平台禁言适配执行引擎与自然语言时间提取模块。"""

from __future__ import annotations

import re

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import At


class MuteEngine:
    """跨平台禁言操作执行器。"""

    @staticmethod
    def parse_time_to_seconds(text: str) -> int | None:
        """从自然语言字符串中解析禁言秒数。"""
        if not text:
            return None

        clean_text = text.strip()

        # 1. 匹配纯数字 (默认单位: 分钟)
        if clean_text.isdigit():
            val = int(clean_text)
            return val * 60 if val > 0 else None

        # 2. 正则匹配复杂复合格式
        total_seconds = 0
        matched = False

        day_match = re.search(r"(\d+)\s*(?:天|d|day|days)", clean_text, re.IGNORECASE)
        if day_match:
            total_seconds += int(day_match.group(1)) * 86400
            matched = True

        hour_match = re.search(
            r"(\d+)\s*(?:小时|时|h|hour|hours)", clean_text, re.IGNORECASE
        )
        if hour_match:
            total_seconds += int(hour_match.group(1)) * 3600
            matched = True

        min_match = re.search(
            r"(\d+)\s*(?:分钟|分|m|min|mins|minute|minutes)", clean_text, re.IGNORECASE
        )
        if min_match:
            total_seconds += int(min_match.group(1)) * 60
            matched = True

        sec_match = re.search(
            r"(\d+)\s*(?:秒钟|秒|s|sec|secs|second|seconds)", clean_text, re.IGNORECASE
        )
        if sec_match:
            total_seconds += int(sec_match.group(1))
            matched = True

        if matched and total_seconds > 0:
            return total_seconds

        return None

    @staticmethod
    def extract_target_and_params(
        event: AstrMessageEvent,
    ) -> tuple[str | None, int | None]:
        """从事件中提取被 @ 的目标 QQ 号以及附带的时间/数值参数。"""
        target_id: str | None = None
        param_value: int | None = None

        # 1. 遍历消息链提取 At 组件
        if hasattr(event, "message_obj") and hasattr(event.message_obj, "message"):
            for comp in event.message_obj.message:
                if isinstance(comp, At):
                    if hasattr(comp, "qq") and comp.qq:
                        target_id = str(comp.qq).strip()
                        break
                    elif hasattr(comp, "target") and comp.target:
                        target_id = str(comp.target).strip()
                        break

        # 2. 解析纯文本内容中的参数
        msg_str = (event.message_str or "").strip()
        tokens = msg_str.split()

        for token in tokens:
            token = token.strip()
            if not token:
                continue

            if not target_id and token.startswith("@"):
                raw_at = token.lstrip("@").strip()
                if raw_at.isdigit():
                    target_id = raw_at
                    continue

            parsed_sec = MuteEngine.parse_time_to_seconds(token)
            if parsed_sec is not None and param_value is None:
                param_value = parsed_sec
                continue

            if token.isdigit() and param_value is None:
                param_value = int(token)

        return target_id, param_value

    @staticmethod
    def format_duration(seconds: int) -> str:
        """将秒数格式化为人类友好的时长字符串。"""
        if seconds <= 0:
            return "0秒"

        parts = []
        days = seconds // 86400
        seconds %= 86400
        hours = seconds // 3600
        seconds %= 3600
        minutes = seconds // 60
        secs = seconds % 60

        if days > 0:
            parts.append(f"{days}天")
        if hours > 0:
            parts.append(f"{hours}小时")
        if minutes > 0:
            parts.append(f"{minutes}分钟")
        if secs > 0:
            parts.append(f"{secs}秒")

        return "".join(parts) if parts else "0秒"

    @staticmethod
    async def execute_mute(
        event: AstrMessageEvent, target_id: str, duration_sec: int
    ) -> tuple[bool, str]:
        """跨平台执行群成员禁言。"""
        group_id = event.get_group_id()
        if not group_id:
            return False, "只能在群聊中执行禁言操作喵~"

        # 1. OneBot v11 (aiocqhttp) 适配器
        try:
            if hasattr(event, "bot") and event.bot:
                client = event.bot
                if hasattr(client, "set_group_ban"):
                    await client.set_group_ban(
                        group_id=int(group_id),
                        user_id=int(target_id),
                        duration=duration_sec,
                    )
                    return True, "OneBot set_group_ban 执行成功"

                if hasattr(client, "call_action"):
                    await client.call_action(
                        "set_group_ban",
                        group_id=int(group_id),
                        user_id=int(target_id),
                        duration=duration_sec,
                    )
                    return True, "OneBot call_action 执行成功"

                if hasattr(client, "api") and hasattr(client.api, "call_action"):
                    await client.api.call_action(
                        "set_group_ban",
                        group_id=int(group_id),
                        user_id=int(target_id),
                        duration=duration_sec,
                    )
                    return True, "OneBot api.call_action 执行成功"
        except Exception as e:
            logger.warning(f"[MuteEngine] OneBot 禁言执行异常: {e}")
            return False, f"禁言失败（机器人可能不是管理员或权限不足喵）: {e}"

        # 2. Satori 适配器
        try:
            if hasattr(event, "adapter") and hasattr(event.adapter, "client"):
                satori_client = event.adapter.client
                if hasattr(satori_client, "guild_member_mute"):
                    await satori_client.guild_member_mute(
                        guild_id=group_id,
                        user_id=target_id,
                        duration=duration_sec * 1000,
                    )
                    return True, "Satori guild_member_mute 执行成功"
        except Exception as e:
            logger.warning(f"[MuteEngine] Satori 禁言执行异常: {e}")
            return False, f"Satori 禁言失败: {e}"

        return False, "当前聊天平台或协议端不支持禁言接口喵~"

    @staticmethod
    async def execute_unmute(
        event: AstrMessageEvent, target_id: str
    ) -> tuple[bool, str]:
        """解除指定群成员的禁言（duration=0）。"""
        return await MuteEngine.execute_mute(event, target_id, 0)
