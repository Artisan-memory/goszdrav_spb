from goszdrav_bot.scraper.selenium_client import GorzdravMaintenanceError, GorzdravSeleniumScraper


class DummyBody:
    def __init__(self, text: str) -> None:
        self.text = text


class DummyDriver:
    def __init__(self, text: str) -> None:
        self.text = text

    def find_element(self, by, value):
        return DummyBody(self.text)


def test_raise_if_maintenance_detects_portal_message() -> None:
    scraper = GorzdravSeleniumScraper("https://gorzdrav.spb.ru/service-free-schedule")
    driver = DummyDriver(
        "В связи с проведением регламентных работ запись к врачу на портале временно недоступна"
    )

    try:
        scraper._raise_if_maintenance(driver)
    except GorzdravMaintenanceError:
        return

    raise AssertionError("Expected maintenance error to be raised.")
