"""积分签到与禁言插件主入口（模块化架构）。"""

from __future__ import annotations

from astrbot.api import AstrBotConfig
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

from .core.services.admin_service import AdminService
from .core.services.checkin_service import CheckinService
from .core.services.game_service import GameService
from .core.services.mute_service import MuteService
from .core.services.shop_service import ShopService
from .core.utils.message_helper import MessageHelper
from .plugin.plugin_lifecycle_service import PluginLifecycleService
from .plugin.plugin_web_service import PluginWebService

PLUGIN_NAME = "astrbot_plugin_points_mute"


@register(
    "astrbot_plugin_points_mute",
    "Aloys23",
    "丰富有趣的签到领积分与积分禁言/自闭/护盾/轮盘赌系统（基于SQLite数据库与群隔离）喵~",
    "1.0.0",
    "https://github.com/Pancakes-Labs/astrbot_plugin_points_mute",
)
class PointsMutePlugin(Star):
    """签到得积分与积分禁言核心插件（模块化入口壳）。"""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.plugin_name = PLUGIN_NAME

        # 1. 初始化生命周期与存储仓储
        self.lifecycle = PluginLifecycleService(self)
        self.repo = self.lifecycle.repo

        # 2. 装配业务子服务
        self.checkin_service = CheckinService(self.repo)
        self.mute_service = MuteService(self.repo)
        self.game_service = GameService(self.repo)
        self.shop_service = ShopService(self.repo)
        self.admin_service = AdminService(self.repo)

        # 3. 注册 Dashboard 插件 Pages Web API
        self.web_service = PluginWebService(self, self.repo)
        self.web_service.register_routes()

    async def initialize(self):
        """插件加载初始化。"""
        await self.lifecycle.on_initialize()

    async def terminate(self):
        """插件卸载或重启时。"""
        await self.lifecycle.on_terminate()

    # ================= 辅助工具方法 =================

    def _curr_name(self) -> str:
        return str(self.config.get("currency_name", "喵币"))

    def _curr_unit(self) -> str:
        return str(self.config.get("currency_unit", "个"))

    def _format_curr(self, amount: int) -> str:
        return f"{amount} {self._curr_name()}"

    def _check_permission(self, event: AstrMessageEvent) -> tuple[bool, str]:
        return MessageHelper.check_permission(event, self.config)

    def _reply(self, event: AstrMessageEvent, text: str):
        return MessageHelper.reply(event, text, self.config)

    # ================= 签到系统 =================

    @filter.command("checkin", alias={"签到", "打卡", "每日签到", "早安"})
    async def cmd_checkin(self, event: AstrMessageEvent):
        """每日签到领积分"""
        allowed, msg = self._check_permission(event)
        if not allowed:
            if "黑名单" in msg or "白名单" in msg:
                yield self._reply(event, msg)
            return

        is_group = bool(event.get_group_id())
        if not is_group and not self.config.get("allow_private_checkin", True):
            yield self._reply(
                event, "主人，当前配置已禁止私聊签到哦，请在群聊中签到喵~"
            )
            return

        sender_id = event.get_sender_id()
        group_id = event.get_group_id()
        sender_name = event.get_sender_name() or f"用户_{sender_id}"

        res = await self.checkin_service.process_checkin(
            user_id=sender_id,
            group_id=group_id,
            nickname=sender_name,
            config=self.config,
        )

        if not res["success"]:
            yield self._reply(
                event,
                f"{res['msg']}\n当前剩余：{self._format_curr(res['user_info']['points'])}",
            )
            return

        # 组织精美签到卡片
        title = self.config.get("custom_checkin_title", "✨ 签到成功 ✨")
        lines = [f"{title}"]

        if self.config.get("checkin_luck_enabled", True):
            lines.append(f"🔮 今日运势：【{res['luck_name']}】")
            lines.append(f"💬 签语：{res['luck_desc']}")
            lines.append("──────────────")

        lines.append(f"🎁 基础奖励：+{res['base_points']} {self._curr_name()}")

        if res["streak_bonus"] > 0:
            lines.append(
                f"🔥 连签奖励：+{res['streak_bonus']} {self._curr_name()} (连续 {res['continuous_days']} 天)"
            )
        else:
            lines.append(f"📅 连续签到：{res['continuous_days']} 天")

        if res["rank_bonus"] > 0:
            lines.append(
                f"{res['rank_title']} 额外：+{res['rank_bonus']} {self._curr_name()}"
            )
        elif res["rank_num"] > 0:
            lines.append(f"🏃 今日排名：{res['rank_title']}")

        if (
            self.config.get("checkin_luck_affects_points", True)
            and res["luck_multiplier"] != 1.0
        ):
            percent = int((res["luck_multiplier"] - 1.0) * 100)
            sign = "+" if percent > 0 else ""
            lines.append(f"✨ 运势加成：{sign}{percent}%")

        lines.append("──────────────")
        lines.append(f"🎉 本次共得：+{res['total_gained']} {self._curr_name()}")
        lines.append(f"💰 当前余额：{self._format_curr(res['current_points'])}")
        lines.append(f"📊 累计签到：{res['total_checkin_count']} 天")

        yield self._reply(event, "\n".join(lines))

    # ================= 积分查询与排行榜 =================

    @filter.command("points", alias={"积分", "查积分", "我的积分", "我的喵币", "钱包"})
    async def cmd_points(self, event: AstrMessageEvent):
        """查询个人积分和资产明细"""
        allowed, msg = self._check_permission(event)
        if not allowed:
            if "黑名单" in msg or "白名单" in msg:
                yield self._reply(event, msg)
            return

        sender_id = event.get_sender_id()
        group_id = event.get_group_id()
        sender_name = event.get_sender_name() or f"用户_{sender_id}"
        u = await self.repo.get_user_info(
            sender_id, group_id=group_id, nickname=sender_name, config=self.config
        )

        lines = [
            f"🌟 【{sender_name}】的个人资产卡片 🌟",
            f"💰 当前{self._curr_name()}：{u['points']} {self._curr_unit()}",
            f"🛡️ 禁言护盾：{u['shields']} 张",
            "──────────────",
            f"📅 连续签到：{u['continuous_checkin_days']} 天",
            f"📊 累计签到：{u['total_checkin_count']} 天",
        ]
        if u.get("today_luck"):
            lines.append(f"🔮 今日运势：【{u['today_luck']}】")
        lines.extend(
            [
                "──────────────",
                f"⚔️ 禁言他人：{u['mute_count_done']} 次",
                f"🤕 被禁言过：{u['mute_count_received']} 次",
                f"📈 历史总赚取：{u['total_points_earned']} {self._curr_name()}",
                f"📉 历史总消耗：{u['total_points_spent']} {self._curr_name()}",
            ]
        )

        yield self._reply(event, "\n".join(lines))

    @filter.command("points_rank", alias={"积分榜", "积分排行", "富豪榜"})
    async def cmd_points_rank(self, event: AstrMessageEvent):
        """查看积分排行榜"""
        allowed, msg = self._check_permission(event)
        if not allowed:
            if "黑名单" in msg or "白名单" in msg:
                yield self._reply(event, msg)
            return

        async for r in self.admin_service.handle_points_rank(event, self.config):
            yield r

    @filter.command("streak_rank", alias={"签到榜", "连签榜", "肝帝榜"})
    async def cmd_streak_rank(self, event: AstrMessageEvent):
        """查看连续签到排行榜"""
        allowed, msg = self._check_permission(event)
        if not allowed:
            if "黑名单" in msg or "白名单" in msg:
                yield self._reply(event, msg)
            return

        async for r in self.admin_service.handle_streak_rank(event, self.config):
            yield r

    # ================= 积分禁言与自闭玩法 =================

    @filter.command("mute", alias={"禁言", "口球", "封印"})
    async def cmd_mute(self, event: AstrMessageEvent):
        """花费积分禁言群成员：/mute @某人 [时长/分钟]"""
        allowed, msg = self._check_permission(event)
        if not allowed:
            if "黑名单" in msg or "白名单" in msg:
                yield self._reply(event, msg)
            return

        async for r in self.mute_service.handle_mute_command(event, self.config):
            yield r

    @filter.command("selfmute", alias={"自闭", "冷静", "静心", "闭关"})
    async def cmd_selfmute(self, event: AstrMessageEvent):
        """自闭/自我禁言：/自闭 [时长] (享受半价折扣)"""
        allowed, msg = self._check_permission(event)
        if not allowed:
            if "黑名单" in msg or "白名单" in msg:
                yield self._reply(event, msg)
            return

        if not self.config.get("self_mute_enabled", True):
            yield self._reply(event, "当前群已关闭自闭功能喵~")
            return

        from .core.utils.mute_engine import MuteEngine

        _, parsed_sec = MuteEngine.extract_target_and_params(event)
        async for r in self.mute_service.handle_self_mute_command(
            event, parsed_sec, self.config
        ):
            yield r

    @filter.command("unmute", alias={"解禁", "解救", "赎身"})
    async def cmd_unmute(self, event: AstrMessageEvent):
        """花费积分赎身/解除禁言：/unmute @某人"""
        allowed, msg = self._check_permission(event)
        if not allowed:
            if "黑名单" in msg or "白名单" in msg:
                yield self._reply(event, msg)
            return

        if not self.config.get("unmute_enabled", True):
            yield self._reply(event, "当前未开启积分赎身解禁功能喵~")
            return

        async for r in self.mute_service.handle_unmute_command(event, self.config):
            yield r

    # ================= 护盾商城与转账 =================

    @filter.command("buy_shield", alias={"买护盾", "购买护盾", "护盾"})
    async def cmd_buy_shield(self, event: AstrMessageEvent, count: int = 1):
        """购买禁言护盾：/buy_shield [数量]"""
        allowed, msg = self._check_permission(event)
        if not allowed:
            if "黑名单" in msg or "白名单" in msg:
                yield self._reply(event, msg)
            return

        if not self.config.get("shield_enabled", True):
            yield self._reply(event, "当前未开启护盾道具功能喵~")
            return

        async for r in self.shop_service.handle_buy_shield_command(
            event, count, self.config
        ):
            yield r

    @filter.command("my_shield", alias={"我的护盾", "查护盾"})
    async def cmd_my_shield(self, event: AstrMessageEvent):
        """查看自己拥有的护盾数量"""
        allowed, msg = self._check_permission(event)
        if not allowed:
            if "黑名单" in msg or "白名单" in msg:
                yield self._reply(event, msg)
            return

        async for r in self.shop_service.handle_my_shield_command(event, self.config):
            yield r

    @filter.command("transfer", alias={"转账", "赠送", "转积分", "赠送积分"})
    async def cmd_transfer(self, event: AstrMessageEvent):
        """转账/赠送积分：/transfer @某人 数量"""
        allowed, msg = self._check_permission(event)
        if not allowed:
            if "黑名单" in msg or "白名单" in msg:
                yield self._reply(event, msg)
            return

        if not self.config.get("transfer_enabled", True):
            yield self._reply(event, "积分转账功能暂未开放喵~")
            return

        async for r in self.shop_service.handle_transfer_command(event, self.config):
            yield r

    # ================= 轮盘赌小游戏 =================

    @filter.command("roulette", alias={"轮盘赌", "禁言轮盘", "俄罗斯轮盘"})
    async def cmd_roulette(self, event: AstrMessageEvent):
        """禁言俄罗斯轮盘赌：/roulette @某人 [下注积分]"""
        allowed, msg = self._check_permission(event)
        if not allowed:
            if "黑名单" in msg or "白名单" in msg:
                yield self._reply(event, msg)
            return

        if not self.config.get("roulette_enabled", True):
            yield self._reply(event, "轮盘赌小游戏暂未开放喵~")
            return

        async for r in self.game_service.handle_roulette_command(event, self.config):
            yield r

    # ================= 管理员管理指令 =================

    @filter.command("add_points", alias={"加积分", "充值积分", "增加积分"})
    async def cmd_add_points(self, event: AstrMessageEvent):
        """【管理员】增加指定成员积分：/加积分 @某人 100"""
        if not MessageHelper.is_admin(event):
            yield self._reply(event, "权限不足，只有管理员才能使用该指令喵！")
            return

        async for r in self.admin_service.handle_add_points(event, self.config):
            yield r

    @filter.command("sub_points", alias={"扣积分", "扣除积分"})
    async def cmd_sub_points(self, event: AstrMessageEvent):
        """【管理员】扣除指定成员积分：/扣积分 @某人 50"""
        if not MessageHelper.is_admin(event):
            yield self._reply(event, "权限不足，只有管理员才能使用该指令喵！")
            return

        async for r in self.admin_service.handle_sub_points(event, self.config):
            yield r

    @filter.command("set_points", alias={"设积分", "设置积分"})
    async def cmd_set_points(self, event: AstrMessageEvent):
        """【管理员】直接设置成员积分：/设积分 @某人 500"""
        if not MessageHelper.is_admin(event):
            yield self._reply(event, "权限不足，只有管理员才能使用该指令喵！")
            return

        async for r in self.admin_service.handle_set_points(event, self.config):
            yield r

    # ================= 帮助菜单 =================

    @filter.command("points_help", alias={"积分帮助", "签到帮助", "积分菜单"})
    async def cmd_help(self, event: AstrMessageEvent):
        """查看积分与禁言插件帮助菜单"""
        allowed, msg = self._check_permission(event)
        if not allowed:
            if "黑名单" in msg or "白名单" in msg:
                yield self._reply(event, msg)
            return

        curr = self._curr_name()
        cost_per_min = self.config.get("mute_cost_per_minute", 5)
        shield_price = self.config.get("shield_price", 80)
        lines = [
            "✨ ─── 积分与禁言系统指令清单 ─── ✨",
            "🪙 基础玩法：",
            f"• 签到 / 打卡 ➜ 每日签到赚取 {curr} (连签与首签有加成！)",
            "• 查积分 / 钱包 ➜ 查询个人资产、连续签到与护盾明细",
            "• 积分榜 / 签到榜 ➜ 查看群内或全局风云排行",
            "",
            "⚔️ 禁言与自闭玩法：",
            f"• 禁言 @某人 [时长] ➜ 消耗 {curr} 封印群友 ({cost_per_min}{curr}/分钟)",
            "• 自闭 [时长] ➜ 自我禁言冷静专注 (享半价折扣！)",
            f"• 解禁 @某人 ➜ 消耗 {curr} 为被封印的群友赎身",
            "• 轮盘赌 @某人 [赌注] ➜ 刺激的 50% 概率禁言决斗",
            "• ⚠️ 保护机制：支持单人每日禁言上限/防集火保护与累计时长上限",
            "",
            "🛡️ 道具与转账：",
            f"• 买护盾 [数量] ➜ 购买禁言护盾 ({shield_price}{curr}/张，可抵挡/反弹禁言)",
            "• 我的护盾 ➜ 查看当前持有的护盾库存",
            f"• 转账 @某人 [数量] ➜ 赠送 {curr} 给好友",
            "",
            "⚙️ 管理员指令：",
            "• 加积分 / 扣积分 / 设积分 @某人 [数量]",
            "───────────────────",
            "快输入 签到 开启今天的好运吧喵~",
        ]
        yield self._reply(event, "\n".join(lines))

    # ================= 无前缀自然语言兼容监听器 =================

    @filter.event_message_type(filter.EventMessageType.ALL, priority=50)
    async def handle_no_prefix_intercept(self, event: AstrMessageEvent):
        """兼容无斜杠前缀的常用指令（如直接发“签到”、“查积分”、“积分榜”等）。"""
        allowed, _ = self._check_permission(event)
        if not allowed or not self.config.get("allow_no_prefix", True):
            return

        text = (event.message_str or "").strip()
        if not text:
            return

        first_token = text.split()[0].lower().lstrip("/")

        if first_token in {"签到", "打卡", "每日签到", "早安"}:
            async for r in self.cmd_checkin(event):
                yield r
            event.stop_event()
        elif first_token in {"查积分", "我的积分", "我的喵币", "钱包", "积分"}:
            async for r in self.cmd_points(event):
                yield r
            event.stop_event()
        elif first_token in {"积分榜", "积分排行", "富豪榜"}:
            async for r in self.cmd_points_rank(event):
                yield r
            event.stop_event()
        elif first_token in {"签到榜", "连签榜", "肝帝榜"}:
            async for r in self.cmd_streak_rank(event):
                yield r
            event.stop_event()
        elif first_token in {"积分帮助", "签到帮助", "积分菜单"}:
            async for r in self.cmd_help(event):
                yield r
            event.stop_event()
        elif first_token in {"自闭", "冷静", "静心", "闭关"}:
            async for r in self.cmd_selfmute(event):
                yield r
            event.stop_event()
        elif first_token in {"买护盾", "购买护盾", "护盾商城"}:
            async for r in self.cmd_buy_shield(event):
                yield r
            event.stop_event()
        elif first_token in {"我的护盾", "查护盾"}:
            async for r in self.cmd_my_shield(event):
                yield r
            event.stop_event()
