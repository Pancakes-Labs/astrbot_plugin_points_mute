"""插件启动 Banner 打印模块。"""

from __future__ import annotations

from astrbot.api import logger

BANNER_TEXT = r"""
  ____       _       _         __  __       _
 |  _ \ ___ (_)_ __ | |_ ___  |  \/  |_   _| |_ ___
 | |_) / _ \| | '_ \| __/ __| | |\/| | | | | __/ _ \
 |  __/ (_) | | | | | |_\__ \ | |  | | |_| | ||  __/
 |_|   \___/|_|_| |_|\__|___/ |_|  |_|\__,_|\__\___|
       -- AstrBot Points & Mute System v1.0.0 --
"""


def print_banner() -> None:
    """打印彩色 ASCII Banner 到终端。"""
    try:
        print("\033[1;36m" + BANNER_TEXT + "\033[0m")
    except Exception:
        logger.info("[积分禁言] AstrBot Points Mute Plugin Loaded!")
