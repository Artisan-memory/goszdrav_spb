from goszdrav_bot.db.models import UserProfile
from goszdrav_bot.services.profile import ProfileService


def test_reset_dependent_fields_on_district_change() -> None:
    profile = UserProfile(
        district_code="nevskiy",
        organization_external_id="org-1",
        organization_label="Поликлиника 100",
    )

    ProfileService._reset_dependent_fields(profile, {"district_code": "moskovskiy"})

    assert profile.organization_external_id is None
    assert profile.organization_label is None


def test_reset_external_id_on_district_change_even_if_label_reused() -> None:
    profile = UserProfile(
        district_code="nevskiy",
        organization_external_id="org-1",
        organization_label="Поликлиника 100",
    )

    ProfileService._reset_dependent_fields(
        profile,
        {
            "district_code": "moskovskiy",
            "organization_label": "Поликлиника 100",
        },
    )

    assert profile.organization_external_id is None
    assert profile.organization_label == "Поликлиника 100"


def test_reset_dependent_fields_on_organization_clear() -> None:
    profile = UserProfile(
        district_code="nevskiy",
        organization_external_id="org-1",
        organization_label="Поликлиника 100",
    )

    ProfileService._reset_dependent_fields(profile, {"organization_label": None})

    assert profile.organization_external_id is None
    assert profile.organization_label == "Поликлиника 100"
