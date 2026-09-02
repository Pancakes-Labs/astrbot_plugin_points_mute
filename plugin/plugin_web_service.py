"""Dashboard Web API 服务模块。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from astrbot.api import logger
from astrbot.api.web import error_response, json_response, request

from ..core.storage.points_repository import PointsRepository

if TYPE_CHECKING:
    from ..main import PointsMutePlugin


class PluginWebService:
    """负责处理 Dashboard 插件 Pages 发起的 RESTful 请求。"""

    def __init__(self, plugin: PointsMutePlugin, repo: PointsRepository):
        self.plugin = plugin
        self.repo = repo

    def register_routes(self) -> None:
        """注册 Dashboard 的全部后端 Web API。"""
        pname = self.plugin.plugin_name
        ctx = self.plugin.context

        ctx.register_web_api(
            f"/{pname}/stats", self.api_stats, ["GET"], "获取积分大盘统计"
        )
        ctx.register_web_api(
            f"/{pname}/users", self.api_users, ["GET"], "分页搜索与查询群友积分数据"
        )
        ctx.register_web_api(
            f"/{pname}/user/modify",
            self.api_user_modify,
            ["POST"],
            "管理员修改用户积分/护盾/连签",
        )
        ctx.register_web_api(
            f"/{pname}/groups", self.api_groups, ["GET"], "获取所有活跃群组列表"
        )
        ctx.register_web_api(
            f"/{pname}/config", self.api_get_config, ["GET"], "获取当前插件核心配置"
        )
        ctx.register_web_api(
            f"/{pname}/config/save",
            self.api_save_config,
            ["POST"],
            "在Dashboard直接保存配置",
        )

    async def api_stats(self):
        """返回大盘统计数据。"""
        try:
            stats = await self.repo.get_dashboard_stats(self.plugin.config)
            stats["currency_name"] = str(
                self.plugin.config.get("currency_name", "喵币")
            )
            stats["currency_unit"] = str(self.plugin.config.get("currency_unit", "个"))
            stats["isolation_mode"] = self.plugin.config.get(
                "points_isolation_mode", "group_isolated"
            )
            return json_response(stats)
        except Exception as e:
            logger.error(f"[积分签到] api_stats 错误: {e}")
            return error_response(f"获取统计失败: {e}", status_code=500)

    async def api_users(self):
        """分页与条件查询用户。"""
        try:
            search = request.query.get("search", "")
            group_id = request.query.get("group_id", "")
            page = request.query.get("page", 1, type=int)
            page_size = request.query.get("page_size", 15, type=int)
            sort_by = request.query.get("sort_by", "points")
            sort_order = request.query.get("sort_order", "desc")

            res = await self.repo.search_users(
                search=search,
                group_id=group_id,
                page=page,
                page_size=page_size,
                sort_by=sort_by,
                sort_order=sort_order,
            )
            return json_response(res)
        except Exception as e:
            logger.error(f"[积分签到] api_users 错误: {e}")
            return error_response(f"查询用户失败: {e}", status_code=500)

    async def api_user_modify(self):
        """管理员修改用户数据。"""
        try:
            payload = await request.json(default={})
            group_id = str(payload.get("group_id", "")).strip()
            user_id = str(payload.get("user_id", "")).strip()
            action = str(payload.get("action", "")).strip()
            value = int(payload.get("value", 0))

            if not group_id or not user_id or not action:
                return error_response(
                    "缺少必要参数 (group_id, user_id, action)", status_code=400
                )

            res = await self.repo.modify_user_admin(
                group_id, user_id, action, value, self.plugin.config
            )
            if not res.get("success"):
                return error_response(res.get("msg", "操作失败"), status_code=400)
            return json_response(res)
        except Exception as e:
            logger.error(f"[积分签到] api_user_modify 错误: {e}")
            return error_response(f"修改失败: {e}", status_code=500)

    async def api_groups(self):
        """获取所有群组。"""
        try:
            groups = await self.repo.get_all_active_groups()
            return json_response({"groups": groups})
        except Exception as e:
            logger.error(f"[积分签到] api_groups 错误: {e}")
            return error_response(f"获取群组列表失败: {e}", status_code=500)

    async def api_get_config(self):
        """获取当前核心配置。"""
        try:
            cfg = self.plugin.config
            return json_response(
                {
                    "currency_name": cfg.get("currency_name", "喵币"),
                    "currency_unit": cfg.get("currency_unit", "个"),
                    "points_isolation_mode": cfg.get(
                        "points_isolation_mode", "group_isolated"
                    ),
                    "initial_points": cfg.get("initial_points", 0),
                    "checkin_min_points": cfg.get("checkin_min_points", 10),
                    "checkin_max_points": cfg.get("checkin_max_points", 50),
                    "checkin_streak_enabled": cfg.get("checkin_streak_enabled", True),
                    "checkin_streak_bonus_per_day": cfg.get(
                        "checkin_streak_bonus_per_day", 3
                    ),
                    "mute_cost_per_minute": cfg.get("mute_cost_per_minute", 5),
                    "mute_default_duration": cfg.get("mute_default_duration", 60),
                    "shield_price": cfg.get("shield_price", 80),
                    "shield_max_hold": cfg.get("shield_max_hold", 3),
                    "daily_user_mute_limit": cfg.get("daily_user_mute_limit", 5),
                    "daily_user_muted_limit": cfg.get("daily_user_muted_limit", 5),
                    "daily_user_muted_max_duration": cfg.get(
                        "daily_user_muted_max_duration", 7200
                    ),
                    "group_daily_mute_total_limit": cfg.get(
                        "group_daily_mute_total_limit", 50
                    ),
                }
            )
        except Exception as e:
            return error_response(f"读取配置失败: {e}", status_code=500)

    async def api_save_config(self):
        """保存配置。"""
        try:
            payload = await request.json(default={})
            cfg = self.plugin.config
            for k, v in payload.items():
                if k in cfg:
                    cfg[k] = v
            if hasattr(cfg, "save_config") and callable(cfg.save_config):
                cfg.save_config()
            return json_response(
                {"success": True, "msg": "配置已成功保存并实时生效喵~"}
            )
        except Exception as e:
            logger.error(f"[积分签到] api_save_config 错误: {e}")
            return error_response(f"保存配置失败: {e}", status_code=500)
