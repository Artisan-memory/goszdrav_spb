from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, status

from goszdrav_bot.core.districts import DISTRICTS, DISTRICT_BY_CODE
from goszdrav_bot.schemas.catalog import (
    DistrictOption,
    DoctorOption,
    DoctorScheduleSnapshot,
    OrganizationOption,
    SpecialtyOption,
)
from goszdrav_bot.scraper.errors import GorzdravMaintenanceError, GorzdravScraperError

from goszdrav_bot.api.routes.profile import get_identity

router = APIRouter(prefix="/api/v1/catalog", tags=["catalog"])


@router.get("/districts", response_model=list[DistrictOption])
async def list_districts() -> list[DistrictOption]:
    return [DistrictOption(code=code, title=title) for code, title in DISTRICTS]


@router.get("/organizations", response_model=list[OrganizationOption])
async def list_organizations(
    request: Request,
    district_code: str = Query(...),
    query: str | None = Query(default=None),
) -> list[OrganizationOption]:
    get_identity(request)
    if district_code not in DISTRICT_BY_CODE:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неизвестный район.")
    scraper = request.app.state.scraper
    try:
        result = await scraper.list_organizations(district_code, query)
    except GorzdravMaintenanceError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except GorzdravScraperError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return [OrganizationOption(**item) for item in result]


@router.get("/specialties", response_model=list[SpecialtyOption])
async def list_specialties(
    request: Request,
    district_code: str = Query(...),
    organization_label: str = Query(...),
    organization_external_id: str | None = Query(default=None),
) -> list[SpecialtyOption]:
    get_identity(request)
    if district_code not in DISTRICT_BY_CODE:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неизвестный район.")
    scraper = request.app.state.scraper
    try:
        result = await scraper.list_specialties(
            district_code,
            organization_label,
            organization_external_id=organization_external_id,
        )
    except GorzdravMaintenanceError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except GorzdravScraperError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return [SpecialtyOption(**item) for item in result]


@router.get("/doctors", response_model=list[DoctorOption])
async def list_doctors(
    request: Request,
    district_code: str = Query(...),
    organization_label: str = Query(...),
    specialty_label: str = Query(...),
    organization_external_id: str | None = Query(default=None),
    specialty_external_id: str | None = Query(default=None),
) -> list[DoctorOption]:
    get_identity(request)
    if district_code not in DISTRICT_BY_CODE:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неизвестный район.")
    scraper = request.app.state.scraper
    try:
        result = await scraper.list_doctors(
            district_code,
            organization_label,
            specialty_label,
            organization_external_id=organization_external_id,
            specialty_external_id=specialty_external_id,
        )
    except GorzdravMaintenanceError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except GorzdravScraperError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return [DoctorOption(**item) for item in result]


@router.get("/schedule", response_model=DoctorScheduleSnapshot)
async def get_schedule(
    request: Request,
    district_code: str = Query(...),
    organization_label: str = Query(...),
    specialty_label: str = Query(...),
    doctor_label: str = Query(...),
    organization_external_id: str | None = Query(default=None),
    specialty_external_id: str | None = Query(default=None),
    doctor_external_id: str | None = Query(default=None),
) -> DoctorScheduleSnapshot:
    get_identity(request)
    if district_code not in DISTRICT_BY_CODE:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неизвестный район.")
    scraper = request.app.state.scraper
    try:
        result = await scraper.get_doctor_schedule(
            district_code,
            organization_label,
            specialty_label,
            doctor_label,
            organization_external_id=organization_external_id,
            specialty_external_id=specialty_external_id,
            doctor_external_id=doctor_external_id,
        )
    except GorzdravMaintenanceError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except GorzdravScraperError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return DoctorScheduleSnapshot(**result)
