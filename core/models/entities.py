"""实体与数据常量定义模块。"""

from __future__ import annotations

from typing import Any, TypedDict

LUCK_LIST = [
    {
        "name": "超大吉",
        "desc": "运势逆天，诸神眷顾！心想事成喵！",
        "multiplier": 1.5,
        "weight": 5,
    },
    {
        "name": "大吉",
        "desc": "万事顺意，福星高照，今天会有好事发生喵！",
        "multiplier": 1.25,
        "weight": 20,
    },
    {
        "name": "中吉",
        "desc": "平安喜乐，顺遂无忧，保持好心情喵~",
        "multiplier": 1.1,
        "weight": 35,
    },
    {
        "name": "小吉",
        "desc": "微风拂面，小有收获，平平淡淡才是真喵~",
        "multiplier": 1.05,
        "weight": 25,
    },
    {
        "name": "平",
        "desc": "波澜不惊，宜静宜动，适合喝杯奶茶休息喵~",
        "multiplier": 1.0,
        "weight": 10,
    },
    {
        "name": "末吉",
        "desc": "潜龙在渊，蓄势待发，下午会有小惊喜喵！",
        "multiplier": 0.95,
        "weight": 4,
    },
    {
        "name": "凶",
        "desc": "出门小心绊脚，凡事多加谨慎喵...",
        "multiplier": 0.9,
        "weight": 1,
    },
]


class CheckinResult(TypedDict, total=False):
    success: bool
    msg: str
    base_points: int
    streak_bonus: int
    rank_bonus: int
    rank_num: int
    rank_title: str
    luck_name: str
    luck_desc: str
    luck_multiplier: float
    total_gained: int
    continuous_days: int
    total_checkin_count: int
    current_points: int
    user_info: dict[str, Any]
