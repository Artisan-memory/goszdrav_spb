from __future__ import annotations

from goszdrav_bot.scraper.api_client import GorzdravApiClient
from goszdrav_bot.scraper.models import OrganizationRecord


def test_filter_organizations_by_numeric_fragment() -> None:
    organizations = [
        OrganizationRecord(label='СПб ГБУЗ "Городская поликлиника №8"', address="ул. Новоселов, д. 45"),
        OrganizationRecord(label='СПб ГБУЗ "Детская городская поликлиника №45"', address="пр. Товарищеский, д. 10"),
    ]

    result = GorzdravApiClient._filter_organizations_by_query(organizations, "45")

    assert len(result) == 2
    assert result[0].label == 'СПб ГБУЗ "Детская городская поликлиника №45"'


def test_filter_organizations_by_split_tokens() -> None:
    organizations = [
        OrganizationRecord(label='СПб ГБУЗ "Городская поликлиника №8"', address="ул. Новоселов, д. 45"),
        OrganizationRecord(label='СПб ГБУЗ "Детская городская поликлиника №45"', address="пр. Товарищеский, д. 10"),
    ]

    result = GorzdravApiClient._filter_organizations_by_query(organizations, "детская 45")

    assert len(result) == 1
    assert result[0].label == 'СПб ГБУЗ "Детская городская поликлиника №45"'


def test_filter_organizations_by_address_token() -> None:
    organizations = [
        OrganizationRecord(label='СПб ГБУЗ "Городская поликлиника №8"', address="ул. Новоселов, д. 45"),
        OrganizationRecord(label='СПб ГБУЗ "Детская городская поликлиника №45"', address="пр. Товарищеский, д. 10"),
    ]

    result = GorzdravApiClient._filter_organizations_by_query(organizations, "товарищеский")

    assert len(result) == 1
    assert result[0].label == 'СПб ГБУЗ "Детская городская поликлиника №45"'
