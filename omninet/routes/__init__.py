"""
API routes package.
"""
from omninet.routes.auth import router as auth_router
from omninet.routes.users import router as users_router
from omninet.routes.modules import router as modules_router
from omninet.routes.teams import router as teams_router
from omninet.routes.battles import router as battles_router
from omninet.routes.seasons import router as seasons_router
from omninet.routes.admin import router as admin_router
from omninet.routes.shop import router as shop_router

__all__ = [
    "auth_router",
    "users_router",
    "modules_router",
    "teams_router",
    "battles_router",
    "seasons_router",
    "admin_router",
    "shop_router",
]
