from __future__ import annotations

import re
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver import ChromeOptions
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium_stealth import stealth

from goszdrav_bot.scraper.errors import GorzdravMaintenanceError, GorzdravScraperError
from goszdrav_bot.scraper.models import (
    AppointmentSlotRecord,
    BookingResultRecord,
    CalendarDayRecord,
    DoctorRecord,
    DoctorScheduleRecord,
    OrganizationRecord,
    ScheduleDayRecord,
    SpecialtyRecord,
)

TIME_RE = re.compile(r"\b\d{2}:\d{2}\b")
SLOTS_RE = re.compile(r"Доступных номерков:\s*(\d+)", re.IGNORECASE)
MONTH_RE = re.compile(
    r"(Январ[ья]|Феврал[ья]|Март|Апрел[ья]|Ма[йя]|Июн[ья]|Июл[ья]|Август|Сентябр[ья]|Октябр[ья]|Ноябр[ья]|Декабр[ья])\s+\d{4}",
    re.IGNORECASE,
)
DAY_RE = re.compile(r"^(Пн|Вт|Ср|Чт|Пт|Сб|Вс),?\s+\d{1,2}")
MAINTENANCE_MARKERS = (
    "В связи с проведением регламентных работ запись к врачу на портале временно недоступна",
    "Приносим извинения за временные неудобства",
)
class GorzdravSeleniumScraper:
    def __init__(
        self,
        base_url: str,
        headless: bool = True,
        timeout_seconds: int = 20,
        chrome_binary: str | None = None,
        proxy_url: str | None = None,
    ) -> None:
        self.base_url = base_url
        self.headless = headless
        self.timeout_seconds = timeout_seconds
        self.chrome_binary = chrome_binary
        self.proxy_url = proxy_url

    def list_organizations(self, district_title: str, query: str | None = None) -> list[dict]:
        with self._driver_session() as driver:
            self._open_start_page(driver)
            self._choose_district(driver, district_title)
            if query:
                self._apply_search(driver, query)
            records = self._parse_organization_cards(driver)
        return [asdict(record) for record in records]

    def list_specialties(
        self,
        district_title: str,
        organization_label: str,
    ) -> list[dict]:
        with self._driver_session() as driver:
            self._open_start_page(driver)
            self._choose_district(driver, district_title)
            self._choose_list_item(driver, organization_label)
            records = self._parse_specialty_cards(driver)
        return [asdict(record) for record in records]

    def list_doctors(
        self,
        district_title: str,
        organization_label: str,
        specialty_label: str,
    ) -> list[dict]:
        with self._driver_session() as driver:
            self._open_start_page(driver)
            self._choose_district(driver, district_title)
            self._choose_list_item(driver, organization_label)
            self._choose_list_item(driver, specialty_label)
            records = self._parse_doctor_cards(driver)
        return [asdict(record) for record in records]

    def get_doctor_schedule(
        self,
        district_title: str,
        organization_label: str,
        specialty_label: str,
        doctor_label: str,
    ) -> dict:
        with self._driver_session() as driver:
            self._open_start_page(driver)
            self._choose_district(driver, district_title)
            self._choose_list_item(driver, organization_label)
            self._choose_list_item(driver, specialty_label)
            self._open_doctor_schedule(driver, doctor_label)
            preview_days = self._parse_schedule_preview(driver)
            month_label = self._try_get_month_label(driver)
            calendar_days = self._parse_calendar_days(driver)
            slots = self._parse_slots(driver)
            snapshot = DoctorScheduleRecord(
                page_url=driver.current_url,
                month_label=month_label,
                preview_days=preview_days,
                calendar_days=calendar_days,
                slots=slots,
            )
        return asdict(snapshot)

    def attempt_book_first_available_slot(
        self,
        district_title: str,
        organization_label: str,
        specialty_label: str,
        doctor_label: str,
        *,
        full_name: str | None,
        birth_date: str | None,
        email: str | None,
        preferred_slot_time: str | None = None,
    ) -> dict:
        with self._driver_session() as driver:
            self._open_start_page(driver)
            self._choose_district(driver, district_title)
            self._choose_list_item(driver, organization_label)
            self._choose_list_item(driver, specialty_label)
            self._open_doctor_schedule(driver, doctor_label)
            slots = self._parse_slots(driver)
            if not slots:
                return asdict(
                    BookingResultRecord(
                        status="no_slots",
                        direct_url=driver.current_url,
                        details="Свободные талоны не найдены.",
                    )
                )

            clicked_slot = self._click_preferred_slot(driver, preferred_slot_time)
            if clicked_slot is None:
                return asdict(
                    BookingResultRecord(
                        status="slot_click_failed",
                        direct_url=driver.current_url,
                        details=(
                            "Не удалось кликнуть по выбранному талону."
                            if preferred_slot_time
                            else "Не удалось кликнуть по доступному талону."
                        ),
                    )
                )

            self._click_book_button(driver)
            self._fill_booking_form(
                driver,
                full_name=full_name,
                birth_date=birth_date,
                email=email,
            )
            self._click_confirm_button_if_present(driver)
            status, details = self._detect_booking_status(driver)
            return asdict(
                BookingResultRecord(
                    status=status,
                    slot_time=clicked_slot,
                    direct_url=driver.current_url,
                    details=details,
                )
            )

    @contextmanager
    def _driver_session(self):
        driver = self._build_driver()
        try:
            yield driver
        finally:
            driver.quit()

    def _build_driver(self):
        options = ChromeOptions()
        if self.headless:
            options.add_argument("--headless=new")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--window-size=1600,1200")
        options.add_argument("--lang=ru-RU")
        if self.proxy_url:
            options.add_argument(f"--proxy-server={self.proxy_url}")
        if self.chrome_binary:
            options.binary_location = self.chrome_binary

        service = Service()
        driver = webdriver.Chrome(service=service, options=options)
        driver.set_page_load_timeout(self.timeout_seconds)
        driver.implicitly_wait(1)
        stealth(
            driver,
            languages=["ru-RU", "ru"],
            vendor="Google Inc.",
            platform="Win32",
            webgl_vendor="Intel Inc.",
            renderer="Intel Iris OpenGL Engine",
            fix_hairline=True,
        )
        return driver

    def _open_start_page(self, driver) -> None:
        driver.get(self.base_url)
        self._wait_for_any(
            driver,
            [
                (
                    By.XPATH,
                    "//input[contains(@placeholder, 'Введите название или адрес')]",
                ),
                (
                    By.XPATH,
                    "//*[contains(normalize-space(), 'регламентных работ') or contains(normalize-space(), 'временно недоступна')]",
                ),
            ],
        )
        self._raise_if_maintenance(driver)

    def _choose_district(self, driver, district_title: str) -> None:
        self._click_text_button(driver, district_title)
        self._wait(driver).until(
            EC.presence_of_element_located(
                (
                    By.XPATH,
                    f"//*[contains(normalize-space(), 'Район:') and contains(normalize-space(), '{district_title}')]",
                )
            )
        )

    def _apply_search(self, driver, query: str) -> None:
        search = self._wait(driver).until(
            EC.element_to_be_clickable(
                (
                    By.XPATH,
                    "//input[contains(@placeholder, 'Введите название или адрес')]",
                )
            )
        )
        search.clear()
        search.send_keys(query)
        try:
            button = driver.find_element(
                By.XPATH,
                "//button[.//*[name()='svg'] or contains(normalize-space(), 'Поиск')]",
            )
            self._safe_click(driver, button)
        except Exception:
            search.submit()

    def _choose_list_item(self, driver, label: str) -> None:
        cards = self._collect_selectable_cards(driver)
        target_button = None
        needle = self._normalize_text(label)
        for button, container in cards:
            text = self._normalize_text(container.text)
            if needle in text:
                target_button = button
                break
        if target_button is None:
            raise GorzdravScraperError(f"Не удалось найти элемент списка: {label}")
        self._safe_click(driver, target_button)

    def _open_doctor_schedule(self, driver, doctor_label: str) -> None:
        cards = self._collect_doctor_cards(driver)
        target = None
        needle = self._normalize_text(doctor_label)
        for container in cards:
            text = self._normalize_text(container.text)
            if needle in text:
                target = container
                break
        if target is None:
            raise GorzdravScraperError(f"Не удалось найти врача: {doctor_label}")

        schedule_buttons = target.find_elements(
            By.XPATH,
            ".//button[contains(normalize-space(), 'Расписание')]",
        )
        if schedule_buttons:
            self._safe_click(driver, schedule_buttons[0])
            self._wait_for_any(
                driver,
                [
                    (By.XPATH, "//*[contains(normalize-space(), 'Предыдущая неделя')]"),
                    (By.XPATH, "//*[contains(normalize-space(), 'Следующая неделя')]"),
                    (By.XPATH, "//*[contains(normalize-space(), 'Март') or contains(normalize-space(), '202')]"),
                ],
            )

        choose_buttons = target.find_elements(
            By.XPATH,
            ".//button[contains(normalize-space(), 'Выбрать')]",
        )
        if choose_buttons:
            self._safe_click(driver, choose_buttons[0])
            self._wait_for_any(
                driver,
                [
                    (By.XPATH, "//*[contains(normalize-space(), 'Записаться')]"),
                    (By.XPATH, "//*[contains(normalize-space(), 'свободно')]"),
                ],
            )

    def _parse_organization_cards(self, driver) -> list[OrganizationRecord]:
        cards = self._collect_selectable_cards(driver)
        organizations: list[OrganizationRecord] = []
        seen: set[str] = set()
        for button, container in cards:
            lines = self._clean_lines(container.text)
            if not lines:
                continue
            label = next(
                (
                    line
                    for line in lines
                    if "выбрать" not in line.lower() and "+7" not in line and not line.startswith("Район:")
                ),
                None,
            )
            if not label:
                continue
            key = self._normalize_text(label)
            if key in seen:
                continue
            seen.add(key)
            organizations.append(
                OrganizationRecord(
                    label=label,
                    external_id=self._extract_external_id(button),
                    address=next((line for line in lines if "санкт-петербург" in line.lower()), None),
                    phone=next((line for line in lines if "+7" in line), None),
                )
            )
        return organizations

    def _parse_specialty_cards(self, driver) -> list[SpecialtyRecord]:
        cards = self._collect_selectable_cards(driver)
        specialties: list[SpecialtyRecord] = []
        seen: set[str] = set()
        for button, container in cards:
            lines = self._clean_lines(container.text)
            if not lines:
                continue
            label = next(
                (
                    line
                    for line in lines
                    if "доступных номерков" not in line.lower() and "выбрать" not in line.lower()
                ),
                None,
            )
            if not label:
                continue
            key = self._normalize_text(label)
            if key in seen:
                continue
            seen.add(key)
            specialties.append(
                SpecialtyRecord(
                    label=label,
                    external_id=self._extract_external_id(button),
                    available_slots=self._extract_slots(container.text),
                )
            )
        return specialties

    def _parse_doctor_cards(self, driver) -> list[DoctorRecord]:
        cards = self._collect_doctor_cards(driver)
        doctors: list[DoctorRecord] = []
        seen: set[str] = set()
        for container in cards:
            lines = self._clean_lines(container.text)
            if not lines:
                continue
            label = next(
                (
                    line
                    for line in lines
                    if "доступных номерков" not in line.lower()
                    and "расписание" not in line.lower()
                    and "выбрать" not in line.lower()
                ),
                None,
            )
            if not label:
                continue
            key = self._normalize_text(label)
            if key in seen:
                continue
            seen.add(key)
            doctors.append(
                DoctorRecord(
                    label=label,
                    available_slots=self._extract_slots(container.text),
                    has_schedule_button=bool(
                        container.find_elements(
                            By.XPATH,
                            ".//button[contains(normalize-space(), 'Расписание')]",
                        )
                    ),
                )
            )
        return doctors

    def _parse_schedule_preview(self, driver) -> list[ScheduleDayRecord]:
        elements = driver.find_elements(
            By.XPATH,
            "//*[contains(normalize-space(), 'Информация о расписании отсутствует') or contains(normalize-space(), 'Номерки') or starts-with(normalize-space(), 'Пн,') or starts-with(normalize-space(), 'Вт,') or starts-with(normalize-space(), 'Ср,') or starts-with(normalize-space(), 'Чт,') or starts-with(normalize-space(), 'Пт,') or starts-with(normalize-space(), 'Сб,') or starts-with(normalize-space(), 'Вс,')]",
        )
        previews: list[ScheduleDayRecord] = []
        seen: set[str] = set()
        for element in elements:
            text = element.text.strip()
            lines = self._clean_lines(text)
            if len(lines) < 2:
                continue
            title = lines[0]
            if not DAY_RE.search(title):
                continue
            joined = " | ".join(lines)
            if joined in seen:
                continue
            seen.add(joined)
            slot_times = TIME_RE.findall(text)
            previews.append(
                ScheduleDayRecord(
                    title=title,
                    summary="\n".join(lines[1:]),
                    slot_times=slot_times,
                    has_slots=bool(slot_times),
                    missing_info="Информация о расписании отсутствует" in text,
                )
            )
        return previews

    def _try_get_month_label(self, driver) -> str | None:
        candidates = driver.find_elements(By.XPATH, "//*[contains(normalize-space(), '202')]")
        for candidate in candidates:
            text = candidate.text.strip()
            if MONTH_RE.search(text):
                return MONTH_RE.search(text).group(0)
        return None

    def _parse_calendar_days(self, driver) -> list[CalendarDayRecord]:
        day_elements = driver.find_elements(
            By.XPATH,
            "//*[self::button or self::div or self::span][normalize-space() and string-length(normalize-space()) <= 3]",
        )
        days: list[CalendarDayRecord] = []
        seen: set[str] = set()
        for element in day_elements:
            label = element.text.strip()
            if not label.isdigit():
                continue
            if label in seen:
                continue
            seen.add(label)
            classes = (element.get_attribute("class") or "").lower()
            days.append(
                CalendarDayRecord(
                    day_number=label,
                    label=label,
                    is_available=not any(flag in classes for flag in ("disabled", "inactive")),
                    is_selected=any(flag in classes for flag in ("selected", "active", "current")),
                )
            )
        return days

    def _parse_slots(self, driver) -> list[AppointmentSlotRecord]:
        slot_elements = driver.find_elements(
            By.XPATH,
            "//*[contains(normalize-space(), 'свободно') and contains(normalize-space(), ':')]",
        )
        slots: list[AppointmentSlotRecord] = []
        seen: set[str] = set()
        for element in slot_elements:
            text = " ".join(self._clean_lines(element.text))
            if not TIME_RE.search(text):
                continue
            if text in seen:
                continue
            seen.add(text)
            time = TIME_RE.search(text).group(0)
            slots.append(
                AppointmentSlotRecord(
                    time=time,
                    status="свободно" if "свободно" in text.lower() else None,
                    address=text.split(", ", maxsplit=2)[-1] if "," in text else None,
                )
            )
        return slots

    def _click_preferred_slot(self, driver, preferred_slot_time: str | None) -> str | None:
        preferred_date, preferred_time = self._split_slot_datetime(preferred_slot_time)
        if preferred_date:
            self._try_select_calendar_day(driver, preferred_date)

        slot_elements = self._collect_free_slot_elements(driver)
        if not slot_elements:
            return None

        if preferred_time:
            for element, time_value in slot_elements:
                if time_value == preferred_time:
                    self._safe_click(driver, element)
                    return (
                        f"{preferred_date} {preferred_time}"
                        if preferred_date
                        else preferred_time
                    )

        latest_element, latest_time = max(
            slot_elements,
            key=lambda item: self._time_sort_key(item[1]),
        )
        self._safe_click(driver, latest_element)
        return f"{preferred_date} {latest_time}" if preferred_date else latest_time

    def _collect_free_slot_elements(self, driver) -> list[tuple[WebElement, str]]:
        slot_elements = driver.find_elements(
            By.XPATH,
            "//*[contains(normalize-space(), 'свободно') and contains(normalize-space(), ':')]",
        )
        available: list[tuple[WebElement, str]] = []
        seen: set[str] = set()
        for element in slot_elements:
            text = " ".join(self._clean_lines(element.text))
            match = TIME_RE.search(text)
            if not match:
                continue
            key = f"{match.group(0)}|{text}"
            if key in seen:
                continue
            seen.add(key)
            available.append((element, match.group(0)))
        return available

    def _try_select_calendar_day(self, driver, raw_date: str) -> bool:
        parsed_date = self._parse_supported_date(raw_date)
        if parsed_date is None:
            return False

        day_number = str(parsed_date.day)
        candidates = driver.find_elements(
            By.XPATH,
            f"//*[self::button or self::div or self::span][normalize-space()='{day_number}']",
        )
        if not candidates:
            return False

        visible_candidates: list[WebElement] = []
        for element in candidates:
            try:
                if not element.is_displayed():
                    continue
            except Exception:
                continue
            classes = (element.get_attribute("class") or "").lower()
            if any(flag in classes for flag in ("disabled", "inactive")):
                continue
            visible_candidates.append(element)

        if not visible_candidates:
            return False

        for element in visible_candidates:
            classes = (element.get_attribute("class") or "").lower()
            if any(flag in classes for flag in ("selected", "active", "current")):
                return True

        self._safe_click(driver, visible_candidates[0])
        try:
            self._wait(driver).until(
                lambda current_driver: bool(self._collect_free_slot_elements(current_driver))
            )
        except Exception:
            return False
        return True

    @staticmethod
    def _split_slot_datetime(raw_value: str | None) -> tuple[str | None, str | None]:
        if not raw_value:
            return None, None
        text = " ".join(raw_value.split())
        time_match = TIME_RE.search(text)
        time_value = time_match.group(0) if time_match else None
        date_match = re.search(r"\b\d{2}\.\d{2}\.\d{4}\b|\b\d{4}-\d{2}-\d{2}\b", text)
        date_value = date_match.group(0) if date_match else None
        return date_value, time_value

    @staticmethod
    def _parse_supported_date(raw_value: str | None) -> datetime | None:
        if not raw_value:
            return None
        for pattern in ("%d.%m.%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(raw_value, pattern)
            except ValueError:
                continue
        return None

    @staticmethod
    def _time_sort_key(raw_value: str) -> tuple[int, int]:
        try:
            hour_text, minute_text = raw_value.split(":", maxsplit=1)
            return int(hour_text), int(minute_text)
        except ValueError:
            return (0, 0)

    def _click_book_button(self, driver) -> None:
        candidates = driver.find_elements(
            By.XPATH,
            "//*[self::button or self::a][contains(normalize-space(), 'Записаться')]",
        )
        if not candidates:
            raise GorzdravScraperError("Не найдена кнопка 'Записаться'.")
        self._safe_click(driver, candidates[0])

    def _fill_booking_form(
        self,
        driver,
        *,
        full_name: str | None,
        birth_date: str | None,
        email: str | None,
    ) -> None:
        if full_name:
            self._fill_input_by_keywords(driver, ["фио", "пациент", "фамилия", "имя"], full_name)
        if birth_date:
            self._fill_input_by_keywords(driver, ["дата рождения", "рождения"], birth_date)
        if email:
            self._fill_input_by_keywords(driver, ["email", "почта"], email)
        self._check_consent_if_present(driver)

    def _fill_input_by_keywords(self, driver, keywords: list[str], value: str) -> None:
        lowered_keywords = [item.lower() for item in keywords]
        inputs = driver.find_elements(By.XPATH, "//input | //textarea")
        for input_element in inputs:
            attrs = " ".join(
                filter(
                    None,
                    [
                        input_element.get_attribute("name"),
                        input_element.get_attribute("placeholder"),
                        input_element.get_attribute("id"),
                        input_element.get_attribute("aria-label"),
                    ],
                )
            ).lower()
            try:
                parent_text = (self._closest_card(driver, input_element).text or "").lower()
            except Exception:
                parent_text = ""
            haystack = f"{attrs} {parent_text}"
            if any(keyword in haystack for keyword in lowered_keywords):
                input_element.clear()
                input_element.send_keys(value)
                return

    def _check_consent_if_present(self, driver) -> None:
        checkboxes = driver.find_elements(By.XPATH, "//input[@type='checkbox']")
        for checkbox in checkboxes:
            try:
                if not checkbox.is_selected():
                    self._safe_click(driver, checkbox)
            except Exception:
                continue

    def _click_confirm_button_if_present(self, driver) -> None:
        candidates = driver.find_elements(
            By.XPATH,
            "//*[self::button or self::a][contains(normalize-space(), 'Подтверд') or contains(normalize-space(), 'Оформ') or contains(normalize-space(), 'Продолжить') or contains(normalize-space(), 'Записаться')]",
        )
        for candidate in candidates:
            try:
                self._safe_click(driver, candidate)
                return
            except Exception:
                continue

    def _detect_booking_status(self, driver) -> tuple[str, str]:
        page_text = " ".join(self._clean_lines(driver.find_element(By.TAG_NAME, "body").text))
        normalized = page_text.lower()
        if any(marker in normalized for marker in ("запись оформлена", "вы записаны", "успешно")):
            return "success", page_text[:600]
        if any(marker in normalized for marker in ("подтверд", "оформление записи", "проверьте данные")):
            return "pending_confirmation", page_text[:600]
        if any(marker in normalized for marker in ("ошибка", "недоступно", "не удалось")):
            return "failed", page_text[:600]
        return "unknown", page_text[:600]

    def _collect_selectable_cards(self, driver) -> list[tuple[WebElement, WebElement]]:
        self._wait(driver).until(
            EC.presence_of_element_located(
                (By.XPATH, "//button[contains(normalize-space(), 'Выбрать')]")
            )
        )
        buttons = driver.find_elements(By.XPATH, "//button[contains(normalize-space(), 'Выбрать')]")
        cards: list[tuple[WebElement, WebElement]] = []
        for button in buttons:
            container = self._closest_card(driver, button)
            cards.append((button, container))
        return cards

    def _collect_doctor_cards(self, driver) -> list[WebElement]:
        cards = self._collect_selectable_cards(driver)
        return [container for _, container in cards]

    def _closest_card(self, driver, element: WebElement) -> WebElement:
        script = """
        let node = arguments[0];
        while (node) {
          const text = (node.innerText || '').trim();
          const buttons = node.querySelectorAll('button').length;
          if (text && buttons >= 1 && text.length > 20) {
            return node;
          }
          node = node.parentElement;
        }
        return arguments[0];
        """
        return driver.execute_script(script, element)

    def _extract_external_id(self, element: WebElement) -> str | None:
        for attribute in ("data-id", "data-value", "value"):
            value = element.get_attribute(attribute)
            if value:
                return value
        onclick = element.get_attribute("onclick") or ""
        return onclick or None

    def _click_text_button(self, driver, text: str) -> None:
        targets = [
            (By.XPATH, f"//a[normalize-space()='{text}']"),
            (By.XPATH, f"//button[normalize-space()='{text}']"),
            (By.XPATH, f"//td[normalize-space()='{text}']"),
            (By.XPATH, f"//*[self::span or self::div][normalize-space()='{text}']"),
        ]
        for by, value in targets:
            elements = driver.find_elements(by, value)
            if not elements:
                continue
            self._safe_click(driver, elements[0])
            return
        raise GorzdravScraperError(f"Не удалось кликнуть по тексту: {text}")

    def _safe_click(self, driver, element: WebElement) -> None:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
        driver.execute_script("arguments[0].click();", element)

    def _raise_if_maintenance(self, driver) -> None:
        body_text = driver.find_element(By.TAG_NAME, "body").text
        if any(marker in body_text for marker in MAINTENANCE_MARKERS):
            raise GorzdravMaintenanceError(
                "Портал gorzdrav.spb.ru временно недоступен из-за регламентных работ. "
                "Каталог и свободные номерки сейчас нельзя получить автоматически."
            )

    def _wait(self, driver) -> WebDriverWait:
        return WebDriverWait(driver, self.timeout_seconds)

    def _wait_for_any(self, driver, locators: list[tuple[str, str]]) -> None:
        timeout_error = None
        for by, value in locators:
            try:
                self._wait(driver).until(EC.presence_of_element_located((by, value)))
                return
            except TimeoutException as exc:
                timeout_error = exc
        if timeout_error is not None:
            raise timeout_error

    @staticmethod
    def _clean_lines(text: str) -> list[str]:
        lines: list[str] = []
        for raw in text.splitlines():
            line = " ".join(raw.split()).strip()
            if line and line not in lines:
                lines.append(line)
        return lines

    @staticmethod
    def _extract_slots(text: str) -> int | None:
        match = SLOTS_RE.search(text)
        return int(match.group(1)) if match else None

    @staticmethod
    def _normalize_text(text: str) -> str:
        return " ".join(text.lower().split())
