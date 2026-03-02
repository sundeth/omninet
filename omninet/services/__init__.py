"""
Services package.
"""
from omninet.services.auth import AuthService
from omninet.services.battle import BattleService
from omninet.services.device import DeviceService
from omninet.services.email import EmailService
from omninet.services.logging import LoggingService
from omninet.services.module import ModuleService
from omninet.services.season import SeasonService
from omninet.services.shop import ShopService, get_shop_service
from omninet.services.team import TeamService
from omninet.services.user import UserService

__all__ = [
    "AuthService",
    "UserService",
    "DeviceService",
    "ModuleService",
    "TeamService",
    "BattleService",
    "SeasonService",
    "LoggingService",
    "EmailService",
    "ShopService",
    "get_shop_service",
]
