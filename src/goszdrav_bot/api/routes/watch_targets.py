from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from goszdrav_bot.api.routes.profile import get_identity
from goszdrav_bot.schemas.watch import WatchScanResultView, WatchTargetCreate, WatchTargetUpdate, WatchTargetView
from goszdrav_bot.services.monitoring import MonitoringService
from goszdrav_bot.services.profile import ProfileService
from goszdrav_bot.services.watch_targets import WatchTargetService

router = APIRouter(prefix="/api/v1/watch-targets", tags=["watch-targets"])


@router.get("", response_model=list[WatchTargetView])
async def list_watch_targets(request: Request) -> list[WatchTargetView]:
    identity = get_identity(request)
    db = request.app.state.db
    async with db.session() as session:
        service = WatchTargetService(session)
        return await service.list_for_user(identity.telegram_id)


@router.post("", response_model=WatchTargetView)
async def create_watch_target(request: Request, payload: WatchTargetCreate) -> WatchTargetView:
    identity = get_identity(request)
    db = request.app.state.db
    cipher = request.app.state.cipher

    async with db.session() as session:
        profile_service = ProfileService(session, cipher)
        watch_service = WatchTargetService(session)
        user = await profile_service.ensure_user(identity)
        profile = await profile_service.get_profile(identity.telegram_id)
        if profile is None or not profile.district_code or not profile.organization_label:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Сначала заполните профиль: район и медорганизацию.",
            )
        try:
            return await watch_service.create_for_user(user, profile, payload)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.patch("/{target_id}", response_model=WatchTargetView)
async def update_watch_target(
    request: Request,
    target_id: int,
    payload: WatchTargetUpdate,
) -> WatchTargetView:
    identity = get_identity(request)
    db = request.app.state.db
    async with db.session() as session:
        service = WatchTargetService(session)
        target = await service.update_for_user(identity.telegram_id, target_id, payload)
        if target is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Наблюдение не найдено.")
        return target


@router.delete("/{target_id}")
async def delete_watch_target(request: Request, target_id: int) -> dict[str, str]:
    identity = get_identity(request)
    db = request.app.state.db
    async with db.session() as session:
        service = WatchTargetService(session)
        deleted = await service.delete_for_user(identity.telegram_id, target_id)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Наблюдение не найдено.")
        return {"status": "deleted"}


@router.post("/{target_id}/scan", response_model=WatchScanResultView)
async def scan_watch_target(request: Request, target_id: int) -> WatchScanResultView:
    identity = get_identity(request)
    db = request.app.state.db
    cipher = request.app.state.cipher
    scraper = request.app.state.scraper
    settings = request.app.state.settings

    async with db.session() as session:
        watch_service = WatchTargetService(session)
        target = await watch_service.get_for_user(identity.telegram_id, target_id)
        if target is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Наблюдение не найдено.")
        monitoring = MonitoringService(session, scraper=scraper, cipher=cipher, settings=settings)
        return await monitoring.scan_target(target, send_notification=False, allow_booking=False)
