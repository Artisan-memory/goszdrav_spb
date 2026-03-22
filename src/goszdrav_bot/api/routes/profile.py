from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from goszdrav_bot.core.districts import DISTRICTS
from goszdrav_bot.schemas.profile import ProfilePatch, ProfileView, TelegramIdentity
from goszdrav_bot.services.profile import ProfileService
from goszdrav_bot.services.telegram_webapp import (
    TelegramWebAppInitDataError,
    parse_and_validate_init_data,
)

router = APIRouter(tags=["profile"])


def get_init_data(request: Request) -> str:
    init_data = request.headers.get("X-Telegram-Init-Data")
    if not init_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Нужен заголовок X-Telegram-Init-Data.",
        )
    return init_data


def get_debug_telegram_id(request: Request) -> int | None:
    settings = request.app.state.settings
    if not settings.webapp_dev_mode:
        return None

    raw_value = (
        request.headers.get("X-Debug-Telegram-Id")
        or request.query_params.get("debug_telegram_id")
    )
    if raw_value:
        try:
            return int(raw_value)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Некорректный debug Telegram ID.",
            ) from exc

    if settings.webapp_dev_telegram_id is not None:
        return settings.webapp_dev_telegram_id
    if settings.bot_admin_ids:
        return settings.bot_admin_ids[0]
    return None


def get_identity(request: Request) -> TelegramIdentity:
    settings = request.app.state.settings
    init_data = request.headers.get("X-Telegram-Init-Data")
    if not init_data:
        debug_telegram_id = get_debug_telegram_id(request)
        if debug_telegram_id is not None:
            return TelegramIdentity(telegram_id=debug_telegram_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Нужен Telegram initData. Для локальной отладки включите WEBAPP_DEV_MODE "
                "и передайте debug Telegram ID."
            ),
        )
    try:
        return parse_and_validate_init_data(
            init_data=init_data,
            bot_token=settings.bot_token.get_secret_value(),
            max_age_seconds=settings.webapp_session_ttl_seconds,
        )
    except TelegramWebAppInitDataError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


@router.get("/webapp/profile")
async def profile_webapp(request: Request):
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name="profile.html",
        context={
            "title": "Профиль пациента",
            "districts": DISTRICTS,
            "gorzdrav_base_url": request.app.state.settings.gorzdrav_base_url,
            "webapp_dev_mode": request.app.state.settings.webapp_dev_mode,
            "webapp_dev_telegram_id": request.app.state.settings.webapp_dev_telegram_id,
            "webapp_default_debug_telegram_id": (
                request.app.state.settings.webapp_dev_telegram_id
                or (request.app.state.settings.bot_admin_ids[0] if request.app.state.settings.bot_admin_ids else None)
            ),
        },
    )


@router.get("/api/v1/profile/me", response_model=ProfileView)
async def get_profile(request: Request) -> ProfileView:
    identity = get_identity(request)
    db = request.app.state.db
    cipher = request.app.state.cipher

    async with db.session() as session:
        service = ProfileService(session, cipher)
        await service.ensure_user(identity)
        profile = await service.get_profile(identity.telegram_id)

    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Профиль не найден.")
    return profile


@router.post("/api/v1/profile/me", response_model=ProfileView)
async def update_profile(request: Request, payload: ProfilePatch) -> ProfileView:
    identity = get_identity(request)
    db = request.app.state.db
    cipher = request.app.state.cipher

    async with db.session() as session:
        service = ProfileService(session, cipher)
        await service.ensure_user(identity)
        profile = await service.upsert_profile(identity.telegram_id, payload, identity=identity)

    return profile
