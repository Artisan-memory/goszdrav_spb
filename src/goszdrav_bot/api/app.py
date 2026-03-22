from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from goszdrav_bot.api.routes.catalog import router as catalog_router
from goszdrav_bot.api.routes.health import router as health_router
from goszdrav_bot.api.routes.profile import router as profile_router
from goszdrav_bot.api.routes.watch_targets import router as watch_targets_router
from goszdrav_bot.config import get_settings
from goszdrav_bot.core.logging import setup_logging
from goszdrav_bot.db.session import Database
from goszdrav_bot.scraper.service import AsyncGorzdravScraper
from goszdrav_bot.services.crypto import FieldCipher

BASE_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = BASE_DIR / "webapp" / "static"
TEMPLATES_DIR = BASE_DIR / "webapp" / "templates"


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)
    db = Database(settings.database_url)
    cipher = FieldCipher(
        secret=settings.field_encryption_secret.get_secret_value(),
        salt=settings.field_encryption_salt.get_secret_value(),
    )
    scraper = AsyncGorzdravScraper(settings)
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = settings
        app.state.db = db
        app.state.cipher = cipher
        app.state.scraper = scraper
        app.state.templates = templates
        yield
        await scraper.close()
        await db.dispose()

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.include_router(health_router)
    app.include_router(profile_router)
    app.include_router(catalog_router)
    app.include_router(watch_targets_router)
    return app
