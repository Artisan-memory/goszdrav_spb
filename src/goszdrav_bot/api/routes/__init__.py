from goszdrav_bot.api.routes.catalog import router as catalog_router
from goszdrav_bot.api.routes.health import router as health_router
from goszdrav_bot.api.routes.profile import router as profile_router
from goszdrav_bot.api.routes.watch_targets import router as watch_targets_router

__all__ = ["catalog_router", "health_router", "profile_router", "watch_targets_router"]
