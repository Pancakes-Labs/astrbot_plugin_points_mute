"""消息构建与权限辅助工具模块。"""

from __future__ import annotations

from typing import Any

from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import At, Plain


class MessageHelper:
    """消息与权限辅助工具。"""

    @staticmethod
    def is_admin(event: AstrMessageEvent) -> bool:
        """判断发送者是否具有管理员或群主权限。"""
        try:
            if hasattr(event, "is_admin") and callable(event.is_admin):
                return bool(event.is_admin())
            if hasattr(event, "message_obj") and hasattr(event.message_obj, "sender"):
                sender = event.message_obj.sender
                role = getattr(sender, "role", "") or getattr(sender, "permission", "")
                if role in ("admin", "owner", "administrator", "ADMIN", "OWNER"):
                    return True
        except Exception:
            pass
        return False

    @staticmethod
    def check_permission(
        event: AstrMessageEvent, config: dict[str, Any]
    ) -> tuple[bool, str]:
        """检查群聊与用户黑白名单权限。"""
        if not config.get("enabled", True):
            return False, "插件已禁用"

        group_id = str(event.get_group_id() or "").strip()
        sender_id = str(event.get_sender_id() or "").strip()

        # 1. 检查群黑白名单
        if group_id:
            blacklist_groups = [
                str(g).strip()
                for g in config.get("blacklist_groups", [])
                if str(g).strip()
            ]
            if group_id in blacklist_groups:
                return False, "本群已被列入积分系统黑名单喵~"

            whitelist_groups = [
                str(g).strip()
                for g in config.get("whitelist_groups", [])
                if str(g).strip()
            ]
            if whitelist_groups and group_id not in whitelist_groups:
                return False, "本群不在积分系统白名单内喵~"

        # 2. 检查用户黑名单
        if sender_id:
            blacklist_users = [
                str(u).strip()
                for u in config.get("blacklist_users", [])
                if str(u).strip()
            ]
            if sender_id in blacklist_users:
                return False, "你已被管理员列入积分系统黑名单，无法使用相关功能喵！"

        return True, ""

    @staticmethod
    def reply(event: AstrMessageEvent, text: str, config: dict[str, Any]):
        """统一构建回复消息链（根据配置决定是否 At 发送者）。"""
        sender_id = event.get_sender_id()
        is_group = bool(event.get_group_id())
        show_at = config.get("show_sender_at", True)

        if is_group and show_at and sender_id:
            chain = [
                At(qq=sender_id),
                Plain(f" \n{text}"),
            ]
            return event.chain_result(chain)
        return event.plain_result(text)
