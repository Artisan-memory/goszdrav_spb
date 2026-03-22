from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx

from goszdrav_bot.core.districts import DISTRICT_API_ID_BY_CODE, DISTRICT_BY_CODE, DISTRICT_CODE_BY_TITLE
from goszdrav_bot.scraper.errors import GorzdravScraperError
from goszdrav_bot.scraper.models import (
    AppointmentSlotRecord,
    CalendarDayRecord,
    DoctorRecord,
    DoctorScheduleRecord,
    OrganizationRecord,
    ScheduleDayRecord,
    SpecialtyRecord,
)

TIME_RE = re.compile(r"(?<!\d)(\d{2}:\d{2})(?!:\d)")
DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{2}\.\d{2}\.\d{4}\b")

logger = logging.getLogger(__name__)


class GorzdravApiClient:
    def __init__(
        self,
        *,
        api_base_url: str,
        public_base_url: str,
        timeout_seconds: int = 20,
        proxy_url: str | None = None,
    ) -> None:
        self.public_base_url = public_base_url.rstrip("/")
        transport = httpx.AsyncHTTPTransport(
            local_address="0.0.0.0",
            retries=1,
            proxy=proxy_url,
        )
        self._client = httpx.AsyncClient(
            base_url=api_base_url.rstrip("/"),
            timeout=timeout_seconds,
            follow_redirects=True,
            headers={"Accept": "application/json"},
            transport=transport,
        )
        self._token: str | None = None

    async def close(self) -> None:
        await self._client.aclose()

    async def list_organizations(self, district_key: str, query: str | None = None) -> list[dict]:
        district_code = self._normalize_district_code(district_key)
        district_api_id = DISTRICT_API_ID_BY_CODE[district_code]
        payload = await self._get_json(f"/v2/shared/district/{district_api_id}/lpus")
        organizations = [
            OrganizationRecord(
                label=self._pick_string(
                    item,
                    "lpuFullName",
                    "lpuShortName",
                    "name",
                    "fullName",
                    "shortName",
                    "description",
                ) or "Без названия",
                external_id=self._stringify(item.get("id")),
                address=self._pick_string(item, "address", "adres", "lpuAddress"),
                phone=self._pick_string(item, "phone", "phoneNumber"),
                category=self._pick_string(item, "lpuType", "typeName", "type"),
            )
            for item in self._ensure_list(payload)
        ]
        if query:
            organizations = self._filter_organizations_by_query(organizations, query)
        return [asdict(item) for item in organizations]

    async def list_specialties(
        self,
        district_key: str,
        organization_label: str,
        *,
        organization_external_id: str | None = None,
    ) -> list[dict]:
        district_code = self._normalize_district_code(district_key)
        lpu_id = organization_external_id or await self._resolve_organization_id(district_code, organization_label)
        payload = await self._get_json(f"/v2/schedule/lpu/{quote(lpu_id, safe='')}/specialties")
        specialties = [
            SpecialtyRecord(
                label=self._pick_string(item, "name", "specialityName", "specialtyName") or "Без названия",
                external_id=self._stringify(item.get("id")),
                available_slots=self._pick_int(
                    item,
                    "countFreeParticipant",
                    "countFreeTicket",
                    "countFreeAppointments",
                    "freeCount",
                    "freeSlots",
                    "count",
                ),
            )
            for item in self._ensure_list(payload)
        ]
        return [asdict(item) for item in specialties]

    async def list_doctors(
        self,
        district_key: str,
        organization_label: str,
        specialty_label: str,
        *,
        organization_external_id: str | None = None,
        specialty_external_id: str | None = None,
    ) -> list[dict]:
        district_code = self._normalize_district_code(district_key)
        lpu_id = organization_external_id or await self._resolve_organization_id(district_code, organization_label)
        speciality_id = specialty_external_id or await self._resolve_specialty_id(
            district_code,
            organization_label,
            specialty_label,
            organization_external_id=organization_external_id,
        )
        payload = await self._get_json(
            f"/v2/schedule/lpu/{quote(lpu_id, safe='')}/speciality/{quote(speciality_id, safe='')}/doctors"
        )
        doctors = [
            DoctorRecord(
                label=self._doctor_label(item),
                external_id=self._stringify(item.get("id")),
                available_slots=self._pick_int(
                    item,
                    "countFreeParticipant",
                    "countFreeTicket",
                    "countFreeAppointments",
                    "freeCount",
                    "freeSlots",
                    "count",
                ),
                has_schedule_button=True,
            )
            for item in self._ensure_list(payload)
        ]
        return [asdict(item) for item in doctors]

    async def get_doctor_schedule(
        self,
        district_key: str,
        organization_label: str,
        specialty_label: str,
        doctor_label: str,
        *,
        organization_external_id: str | None = None,
        specialty_external_id: str | None = None,
        doctor_external_id: str | None = None,
    ) -> dict:
        district_code = self._normalize_district_code(district_key)
        lpu_id = organization_external_id or await self._resolve_organization_id(district_code, organization_label)
        doctor_id = doctor_external_id or await self._resolve_doctor_id(
            district_code,
            organization_label,
            specialty_label,
            doctor_label,
            organization_external_id=organization_external_id,
            specialty_external_id=specialty_external_id,
        )
        timetable_payload = await self._get_json(
            f"/v2/schedule/lpu/{quote(lpu_id, safe='')}/doctor/{quote(doctor_id, safe='')}/timetable"
        )
        appointments_payload = await self._get_json(
            f"/v2/schedule/lpu/{quote(lpu_id, safe='')}/doctor/{quote(doctor_id, safe='')}/appointments"
        )

        slots = self._extract_slots(appointments_payload)
        preview_days = self._build_preview_days(slots, timetable_payload)
        calendar_days = self._build_calendar_days(preview_days)
        snapshot = DoctorScheduleRecord(
            page_url=self._build_public_url(district_code),
            month_label=self._extract_month_label(slots),
            preview_days=preview_days,
            calendar_days=calendar_days,
            slots=slots,
        )
        return asdict(snapshot)

    async def _resolve_organization_id(self, district_code: str, organization_label: str) -> str:
        organizations = await self.list_organizations(district_code)
        return self._resolve_id_by_label(
            organizations,
            organization_label,
            item_label_key="label",
            item_id_key="external_id",
            item_type="медорганизацию",
        )

    async def _resolve_specialty_id(
        self,
        district_code: str,
        organization_label: str,
        specialty_label: str,
        *,
        organization_external_id: str | None = None,
    ) -> str:
        specialties = await self.list_specialties(
            district_code,
            organization_label,
            organization_external_id=organization_external_id,
        )
        return self._resolve_id_by_label(
            specialties,
            specialty_label,
            item_label_key="label",
            item_id_key="external_id",
            item_type="специальность",
        )

    async def _resolve_doctor_id(
        self,
        district_code: str,
        organization_label: str,
        specialty_label: str,
        doctor_label: str,
        *,
        organization_external_id: str | None = None,
        specialty_external_id: str | None = None,
    ) -> str:
        doctors = await self.list_doctors(
            district_code,
            organization_label,
            specialty_label,
            organization_external_id=organization_external_id,
            specialty_external_id=specialty_external_id,
        )
        return self._resolve_id_by_label(
            doctors,
            doctor_label,
            item_label_key="label",
            item_id_key="external_id",
            item_type="врача",
        )

    async def _get_json(self, path: str) -> Any:
        headers = {}
        if self._token:
            headers["token"] = self._token
        try:
            response = await self._client.get(path, headers=headers)
        except httpx.HTTPError as exc:
            error_name = exc.__class__.__name__
            logger.warning("Gorzdrav API request failed: path=%s error=%r", path, exc)
            raise GorzdravScraperError(
                f"Ошибка запроса к API Госздрава: {error_name}"
            ) from exc

        token = response.headers.get("token")
        if token:
            self._token = token

        if response.status_code >= 400:
            body_preview = response.text[:300].replace("\n", " ").replace("\r", " ").strip()
            logger.warning(
                "Gorzdrav API returned error status: path=%s status=%s body=%s",
                path,
                response.status_code,
                body_preview,
            )
            raise GorzdravScraperError(
                f"API Госздрава вернул статус {response.status_code} для {path}. "
                f"Ответ: {body_preview or 'пусто'}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            body_preview = response.text[:300].replace("\n", " ").replace("\r", " ").strip()
            logger.warning(
                "Gorzdrav API returned invalid JSON: path=%s body=%s",
                path,
                body_preview,
            )
            raise GorzdravScraperError("API Госздрава вернул невалидный JSON.") from exc

        if isinstance(payload, dict):
            if payload.get("success") is False:
                logger.warning(
                    "Gorzdrav API returned success=false: path=%s message=%s payload=%s",
                    path,
                    payload.get("message"),
                    payload,
                )
                raise GorzdravScraperError(payload.get("message") or "API Госздрава вернул success=false.")
            if "result" in payload:
                return payload["result"]
        return payload

    def _build_public_url(self, district_code: str) -> str:
        district_id = DISTRICT_API_ID_BY_CODE[district_code]
        state = quote(json.dumps([{"district": district_id}], separators=(",", ":")))
        return f"{self.public_base_url}#{state}"

    @staticmethod
    def _normalize_text(value: str) -> str:
        return " ".join((value or "").lower().split())

    @classmethod
    def _tokenize_query(cls, value: str) -> list[str]:
        return [token for token in re.split(r"[^0-9a-zа-яё]+", cls._normalize_text(value)) if token]

    @classmethod
    def _organization_haystack(cls, organization: OrganizationRecord) -> str:
        return cls._normalize_text(
            " ".join(
                part
                for part in (
                    organization.label,
                    organization.address or "",
                    organization.phone or "",
                    organization.category or "",
                )
                if part
            )
        )

    @classmethod
    def _organization_search_score(cls, organization: OrganizationRecord, query: str) -> int:
        normalized_query = cls._normalize_text(query)
        if not normalized_query:
            return 1

        label = cls._normalize_text(organization.label)
        address = cls._normalize_text(organization.address or "")
        haystack = cls._organization_haystack(organization)
        tokens = cls._tokenize_query(query)

        if label == normalized_query:
            return 500
        if address == normalized_query:
            return 450
        if label.startswith(normalized_query):
            return 400
        if normalized_query in label:
            return 320
        if normalized_query in address:
            return 260
        if tokens and all(token in label for token in tokens):
            return 220
        if tokens and all(token in haystack for token in tokens):
            return 180
        if tokens and any(token in haystack for token in tokens):
            return 100
        return 0

    @classmethod
    def _filter_organizations_by_query(
        cls,
        organizations: list[OrganizationRecord],
        query: str,
    ) -> list[OrganizationRecord]:
        ranked = [
            (cls._organization_search_score(organization, query), organization)
            for organization in organizations
        ]
        ranked = [entry for entry in ranked if entry[0] > 0]
        ranked.sort(
            key=lambda entry: (
                -entry[0],
                cls._normalize_text(entry[1].label),
                cls._normalize_text(entry[1].address or ""),
            )
        )
        return [organization for _, organization in ranked]

    def _normalize_district_code(self, district_key: str) -> str:
        if district_key in DISTRICT_BY_CODE:
            return district_key
        if district_key in DISTRICT_CODE_BY_TITLE:
            return DISTRICT_CODE_BY_TITLE[district_key]
        normalized = self._normalize_text(district_key)
        for title, code in DISTRICT_CODE_BY_TITLE.items():
            if self._normalize_text(title) == normalized:
                return code
        raise GorzdravScraperError(f"Неизвестный район: {district_key}")

    @staticmethod
    def _ensure_list(payload: Any) -> list[dict]:
        if payload is None:
            return []
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            if isinstance(payload.get("items"), list):
                return [item for item in payload["items"] if isinstance(item, dict)]
            return [payload]
        return []

    def _resolve_id_by_label(
        self,
        items: list[dict],
        expected_label: str,
        *,
        item_label_key: str,
        item_id_key: str,
        item_type: str,
    ) -> str:
        needle = self._normalize_text(expected_label)
        exact_match = next(
            (
                item
                for item in items
                if self._normalize_text(str(item.get(item_label_key) or "")) == needle
                and item.get(item_id_key)
            ),
            None,
        )
        if exact_match:
            return str(exact_match[item_id_key])

        partial_match = next(
            (
                item
                for item in items
                if needle in self._normalize_text(str(item.get(item_label_key) or ""))
                and item.get(item_id_key)
            ),
            None,
        )
        if partial_match:
            return str(partial_match[item_id_key])

        raise GorzdravScraperError(f"Не удалось найти {item_type}: {expected_label}")

    @staticmethod
    def _pick_string(payload: dict[str, Any], *keys: str) -> str | None:
        for key in keys:
            value = payload.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
        return None

    @staticmethod
    def _pick_int(payload: dict[str, Any], *keys: str) -> int | None:
        for key in keys:
            value = payload.get(key)
            if value in (None, ""):
                continue
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
        return None

    def _doctor_label(self, payload: dict[str, Any]) -> str:
        direct = self._pick_string(payload, "name", "fio", "doctorName")
        if direct:
            return direct
        parts = [
            self._pick_string(payload, "surname", "lastName"),
            self._pick_string(payload, "nameInitials", "firstName"),
            self._pick_string(payload, "patronymic", "middleName"),
        ]
        label = " ".join(part for part in parts if part)
        return label or "Без имени"

    def _extract_slots(self, payload: Any) -> list[AppointmentSlotRecord]:
        slots: list[AppointmentSlotRecord] = []
        seen: set[tuple[str, str | None, str | None]] = set()
        for node in self._walk(payload):
            if not isinstance(node, dict):
                continue
            time_value = self._extract_time(node)
            if not time_value:
                continue
            date_value = self._extract_date(node)
            address_value = self._pick_string(
                node,
                "address",
                "lpuAddress",
                "room",
                "cabinet",
                "cabinetName",
                "filialAddress",
            )
            key = (time_value, date_value, address_value)
            if key in seen:
                continue
            seen.add(key)
            status = "свободно"
            if node.get("busy") is True or node.get("isBusy") is True:
                status = "занято"
            elif node.get("free") is False or node.get("isFree") is False:
                status = "занято"
            slots.append(
                AppointmentSlotRecord(
                    time=time_value if not date_value else f"{self._format_date_short(date_value)} {time_value}",
                    status=status,
                    address=address_value,
                )
            )
        return slots

    def _build_preview_days(
        self,
        slots: list[AppointmentSlotRecord],
        timetable_payload: Any,
    ) -> list[ScheduleDayRecord]:
        grouped: dict[str, list[str]] = defaultdict(list)
        for slot in slots:
            date_match = DATE_RE.search(slot.time)
            time_match = TIME_RE.search(slot.time)
            if time_match:
                key = date_match.group(0) if date_match else "Доступные номерки"
                grouped[key].append(time_match.group(0))

        if grouped:
            preview_days = []
            for key, times in grouped.items():
                preview_days.append(
                    ScheduleDayRecord(
                        title=self._format_date_short(key) if key != "Доступные номерки" else key,
                        summary="Номерки доступны",
                        slot_times=times[:10],
                        has_slots=True,
                        missing_info=False,
                    )
                )
            return preview_days

        preview_from_timetable: list[ScheduleDayRecord] = []
        for node in self._walk(timetable_payload):
            if not isinstance(node, dict):
                continue
            date_value = self._extract_date(node)
            if not date_value:
                continue
            start_time = self._extract_time(node)
            end_time = self._extract_time(
                {key: node.get(key) for key in ("visitEnd", "endTime", "finishTime", "timeTo", "end")}
            )
            summary_parts = [part for part in (start_time, end_time) if part]
            preview_from_timetable.append(
                ScheduleDayRecord(
                    title=self._format_date_short(date_value),
                    summary=" - ".join(summary_parts) if summary_parts else "Информация о расписании получена",
                    slot_times=[],
                    has_slots=False,
                    missing_info=False,
                )
            )
        unique: dict[str, ScheduleDayRecord] = {}
        for day in preview_from_timetable:
            unique.setdefault(day.title, day)
        return list(unique.values())[:14]

    @staticmethod
    def _build_calendar_days(preview_days: list[ScheduleDayRecord]) -> list[CalendarDayRecord]:
        calendar: list[CalendarDayRecord] = []
        for day in preview_days:
            parts = re.findall(r"\d{1,2}", day.title)
            if not parts:
                continue
            day_number = parts[0]
            calendar.append(
                CalendarDayRecord(
                    day_number=day_number,
                    label=day.title,
                    is_available=day.has_slots,
                    is_selected=False,
                )
            )
        return calendar

    @staticmethod
    def _extract_month_label(slots: list[AppointmentSlotRecord]) -> str | None:
        for slot in slots:
            match = DATE_RE.search(slot.time)
            if match:
                date_value = GorzdravApiClient._parse_date(match.group(0))
                if date_value:
                    return date_value.strftime("%m.%Y")
        return None

    @staticmethod
    def _extract_time(payload: dict[str, Any]) -> str | None:
        for key in (
            "time",
            "appointmentTime",
            "beginTime",
            "startTime",
            "timeFrom",
            "start",
            "visitTime",
            "visitStart",
            "visitEnd",
        ):
            value = payload.get(key)
            if isinstance(value, str):
                parsed = GorzdravApiClient._parse_datetime(value)
                if parsed is not None:
                    return parsed.strftime("%H:%M")
                match = TIME_RE.search(value)
                if match:
                    return match.group(1)
        return None

    @staticmethod
    def _extract_date(payload: dict[str, Any]) -> str | None:
        for key in (
            "date",
            "appointmentDate",
            "day",
            "startDate",
            "workDate",
            "visitDate",
            "visitStart",
            "visitEnd",
        ):
            value = payload.get(key)
            if isinstance(value, str):
                parsed = GorzdravApiClient._parse_datetime(value)
                if parsed is not None:
                    return parsed.strftime("%Y-%m-%d")
                match = DATE_RE.search(value)
                if match:
                    return match.group(0)
        return None

    @staticmethod
    def _parse_date(raw_value: str) -> datetime | None:
        for pattern in ("%Y-%m-%d", "%d.%m.%Y", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(raw_value, pattern)
            except ValueError:
                continue
        return None

    @staticmethod
    def _parse_datetime(raw_value: str) -> datetime | None:
        try:
            return datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
        except ValueError:
            return None

    @classmethod
    def _format_date_short(cls, raw_value: str) -> str:
        parsed = cls._parse_date(raw_value)
        if parsed is None:
            return raw_value
        return parsed.strftime("%d.%m.%Y")

    @classmethod
    def _walk(cls, node: Any):
        if isinstance(node, dict):
            yield node
            for value in node.values():
                yield from cls._walk(value)
            return
        if isinstance(node, list):
            for item in node:
                yield from cls._walk(item)

    @staticmethod
    def _stringify(value: Any) -> str | None:
        if value in (None, ""):
            return None
        return str(value)
