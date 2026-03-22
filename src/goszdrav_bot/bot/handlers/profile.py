from __future__ import annotations

from datetime import date, datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from pydantic import ValidationError

from goszdrav_bot.bot.keyboards.common import (
    district_keyboard,
    organization_keyboard,
    profile_actions_keyboard,
)
from goszdrav_bot.bot.states.profile import ProfileSetupStates
from goszdrav_bot.config import Settings
from goszdrav_bot.core.districts import DISTRICT_BY_CODE
from goszdrav_bot.db.session import Database
from goszdrav_bot.schemas.profile import ProfilePatch, ProfileView, TelegramIdentity
from goszdrav_bot.scraper.service import AsyncGorzdravScraper
from goszdrav_bot.services.crypto import FieldCipher
from goszdrav_bot.services.profile import ProfileService

router = Router(name=__name__)


def identity_from_message(message: Message) -> TelegramIdentity:
    user = message.from_user
    if user is None:
        raise ValueError("Message does not have Telegram user data.")
    return TelegramIdentity(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        language_code=user.language_code,
    )


def identity_from_callback(callback: CallbackQuery) -> TelegramIdentity:
    user = callback.from_user
    return TelegramIdentity(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        language_code=user.language_code,
    )


async def ensure_profile(message: Message, db: Database, cipher: FieldCipher) -> ProfileView:
    async with db.session() as session:
        service = ProfileService(session, cipher)
        identity = identity_from_message(message)
        await service.ensure_user(identity)
        profile = await service.get_profile(identity.telegram_id)
    if profile is None:
        raise RuntimeError("Profile must exist after ensure_user().")
    return profile


def mask_email(email: str | None) -> str:
    if not email:
        return "Не указана"
    local, _, domain = email.partition("@")
    if len(local) <= 2:
        return f"{local[0]}***@{domain}" if local else email
    return f"{local[:2]}***@{domain}"


def parse_birth_date_input(raw_value: str) -> date:
    value = raw_value.strip()
    for pattern in ("%d.%m.%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            continue
    raise ValueError("unsupported birth date format")


def format_birth_date(value: date | None) -> str:
    if value is None:
        return "Не указана"
    return value.strftime("%d.%m.%Y")


def render_profile(profile: ProfileView) -> str:
    lines = [
        "<b>Ваш профиль</b>",
        f"Telegram ID: <code>{profile.telegram_id}</code>",
        f"Статус: {'готов к созданию наблюдений' if profile.is_complete else 'заполнен не полностью'}",
        "",
        f"ФИО: {profile.full_name or 'Не указано'}",
        f"Email: {mask_email(str(profile.email) if profile.email else None)}",
        f"Дата рождения: {format_birth_date(profile.birth_date)}",
        f"Район: {profile.district_title or 'Не выбран'}",
        f"Медорганизация: {profile.organization_label or 'Не выбрана'}",
        "",
        "Специальности, врачей и режим автозаписи теперь лучше настраивать через наблюдения в Mini App.",
    ]
    return "\n".join(lines)


def render_organization_matches(matches: list[dict]) -> str:
    preview_lines = []
    for index, item in enumerate(matches, start=1):
        address = item.get("address") or "адрес не указан"
        preview_lines.append(f"{index}. <b>{item['label']}</b>\n{address}")
    return (
        "Нашёл подходящие медорганизации. Выберите вариант кнопкой ниже.\n\n"
        + "\n\n".join(preview_lines)
    )


async def finalize_profile_setup(
    *,
    identity: TelegramIdentity,
    state: FSMContext,
    db: Database,
    cipher: FieldCipher,
    organization_label: str,
    organization_external_id: str | None,
) -> ProfileView:
    data = await state.get_data()
    profile_patch = ProfilePatch(
        full_name=data["full_name"],
        email=data["email"],
        birth_date=date.fromisoformat(data["birth_date"]),
        district_code=data["district_code"],
        organization_label=organization_label,
        organization_external_id=organization_external_id,
    )
    async with db.session() as session:
        service = ProfileService(session, cipher)
        await service.ensure_user(identity)
        profile = await service.upsert_profile(
            identity.telegram_id,
            profile_patch,
            identity=identity,
        )
    await state.clear()
    return profile


@router.message(Command("profile"))
@router.message(F.text.casefold() == "профиль")
async def command_profile(
    message: Message,
    settings: Settings,
    db: Database,
    cipher: FieldCipher,
) -> None:
    profile = await ensure_profile(message, db, cipher)
    await message.answer(render_profile(profile), reply_markup=profile_actions_keyboard(settings))


@router.message(Command("cancel"))
@router.message(F.text.casefold() == "отмена")
async def command_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Редактирование профиля остановлено.")


@router.callback_query(F.data == "profile:start_setup")
async def callback_start_setup(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None:
        await callback.answer("Сообщение для ответа не найдено.", show_alert=True)
        return
    await state.clear()
    await state.set_state(ProfileSetupStates.full_name)
    await callback.message.answer(
        "Шаг 1/5. Отправьте ФИО так, как оно указано на сайте Госздрава.\n"
        "Для отмены можно написать <code>Отмена</code>."
    )
    await callback.answer()


@router.message(ProfileSetupStates.full_name)
async def process_full_name(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("Нужно отправить текст с ФИО.")
        return
    try:
        patch = ProfilePatch(full_name=message.text)
    except ValidationError:
        await message.answer("ФИО выглядит некорректно. Попробуйте еще раз.")
        return

    await state.update_data(full_name=patch.full_name)
    await state.set_state(ProfileSetupStates.email)
    await message.answer("Шаг 2/5. Отправьте email.")


@router.message(ProfileSetupStates.email)
async def process_email(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("Нужно отправить email текстом.")
        return
    try:
        patch = ProfilePatch(email=message.text)
    except ValidationError:
        await message.answer("Не удалось распознать email. Пример: <code>name@example.com</code>")
        return

    await state.update_data(email=str(patch.email))
    await state.set_state(ProfileSetupStates.birth_date)
    await message.answer(
        "Шаг 3/5. Отправьте дату рождения в привычном формате <code>DD.MM.YYYY</code>.\n"
        "Например: <code>16.06.2000</code>"
    )


@router.message(ProfileSetupStates.birth_date)
async def process_birth_date(message: Message, state: FSMContext) -> None:
    try:
        birth_date = parse_birth_date_input(message.text or "")
        ProfilePatch(birth_date=birth_date)
    except ValueError:
        await message.answer(
            "Дата не распознана. Используйте формат <code>DD.MM.YYYY</code>.\n"
            "Например: <code>16.06.2000</code>"
        )
        return
    except ValidationError:
        await message.answer("Дата рождения указана некорректно.")
        return

    await state.update_data(birth_date=birth_date.isoformat())
    await state.set_state(ProfileSetupStates.district)
    await message.answer("Шаг 4/5. Выберите район.", reply_markup=district_keyboard())


@router.callback_query(ProfileSetupStates.district, F.data.startswith("district:"))
async def process_district(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None:
        await callback.answer("Сообщение для ответа не найдено.", show_alert=True)
        return
    _, district_code = callback.data.split(":", maxsplit=1)
    try:
        patch = ProfilePatch(district_code=district_code)
    except ValidationError:
        await callback.answer("Неизвестный район.", show_alert=True)
        return

    district_title = DISTRICT_BY_CODE[patch.district_code]
    await state.update_data(district_code=patch.district_code)
    await state.set_state(ProfileSetupStates.organization_label)
    await callback.message.answer(
        f"Шаг 5/5. Напишите часть названия или адрес медорганизации для района «{district_title}».\n"
        "Я покажу живые варианты из каталога Госздрава прямо в чате."
    )
    await callback.answer("Район сохранен.")


@router.message(ProfileSetupStates.organization_label)
async def process_organization_label(
    message: Message,
    state: FSMContext,
    scraper: AsyncGorzdravScraper,
    db: Database,
    cipher: FieldCipher,
) -> None:
    value = (message.text or "").strip()
    if not value:
        await message.answer("Напишите часть названия медорганизации или адрес.")
        return

    data = await state.get_data()
    district_code = data.get("district_code")
    if not district_code:
        await message.answer("Сначала выберите район.")
        return

    try:
        organizations = await scraper.list_organizations(district_code, value)
    except Exception as exc:
        await message.answer(f"Не удалось получить список медорганизаций: {exc}")
        return

    if not organizations:
        await message.answer(
            "Ничего не нашёл. Попробуйте часть названия, номер поликлиники или кусок адреса."
        )
        return

    if len(organizations) == 1:
        selected = organizations[0]
        profile = await finalize_profile_setup(
            identity=identity_from_message(message),
            state=state,
            db=db,
            cipher=cipher,
            organization_label=selected["label"],
            organization_external_id=selected.get("external_id"),
        )
        await message.answer("Профиль обновлен.")
        await message.answer(render_profile(profile))
        return

    matches = organizations[:8]
    keyboard_items = [
        (str(item.get("external_id") or ""), item["label"])
        for item in matches
        if item.get("external_id")
    ]
    if not keyboard_items:
        await message.answer(
            "Нашёл варианты, но не удалось собрать кнопки выбора. Попробуйте открыть Mini App или уточнить запрос."
        )
        return

    await state.update_data(
        organization_matches={
            str(item.get("external_id") or ""): {
                "label": item["label"],
                "external_id": item.get("external_id"),
            }
            for item in matches
            if item.get("external_id")
        }
    )
    await message.answer(
        render_organization_matches(matches),
        reply_markup=organization_keyboard(keyboard_items),
    )


@router.callback_query(ProfileSetupStates.organization_label, F.data.startswith("profile:org:"))
async def process_organization_choice(
    callback: CallbackQuery,
    state: FSMContext,
    settings: Settings,
    db: Database,
    cipher: FieldCipher,
) -> None:
    if callback.message is None:
        await callback.answer("Сообщение для ответа не найдено.", show_alert=True)
        return

    external_id = callback.data.split(":", maxsplit=2)[-1]
    data = await state.get_data()
    matches = data.get("organization_matches") or {}
    selected = matches.get(external_id)
    if not selected:
        await callback.answer("Список вариантов устарел. Отправьте запрос заново.", show_alert=True)
        return

    profile = await finalize_profile_setup(
        identity=identity_from_callback(callback),
        state=state,
        db=db,
        cipher=cipher,
        organization_label=selected["label"],
        organization_external_id=selected.get("external_id"),
    )

    await callback.message.answer("Профиль обновлен.")
    await callback.message.answer(render_profile(profile), reply_markup=profile_actions_keyboard(settings))
    await callback.answer("Медорганизация сохранена.")
