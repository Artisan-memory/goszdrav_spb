import pytest
from pydantic import ValidationError

from goszdrav_bot.schemas.profile import ProfilePatch


def test_profile_patch_accepts_known_district() -> None:
    patch = ProfilePatch(district_code="nevskiy")

    assert patch.district_code == "nevskiy"


def test_profile_patch_rejects_unknown_district() -> None:
    with pytest.raises(ValidationError):
        ProfilePatch(district_code="unknown")

