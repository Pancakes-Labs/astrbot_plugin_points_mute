"""插件生命周期与初始化服务模块。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from astrbot.api import logger

from ..core.storage.points_repository import PointsRepository
from ..core.storage.sqlite_db import SqliteDatabase
from ..core.utils.banner import print_banner

if TYPE_CHECKING:
    from ..main import PointsMutePlugin


class PluginLifecycleService:
    """负责插件的初始化装配、横幅打印与退出持久化。"""

    def __init__(self, plugin: PointsMutePlugin):
        self.plugin = plugin
        self.db = SqliteDatabase(plugin_name=self.plugin.plugin_name)
        self.repo = PointsRepository(self.db)

    async def on_initialize(self) -> None:
        """插件启动初始化流程。"""
        # 1. 打印 ASCII Art 横幅
        print_banner()

        # 2. 初始化 SQLite 数据库与表结构
        await self.db.initialize()
        logger.info("[积分禁言] 插件生命周期初始化就绪喵")

    async def on_terminate(self) -> None:
        """插件卸载与终止流程。"""
        logger.info("[积分禁言] 插件已安全停用喵")
