import pytest
from pydantic import ValidationError

from app.core.config import Settings


@pytest.mark.parametrize(
    "secret_key",
    [
        "",
        "change-me",
        "replace-with-at-least-32-random-bytes",
        "too-short-for-production",
    ],
)
def test_production_rejects_insecure_secret_keys(secret_key: str):
    with pytest.raises(ValidationError, match="SECRET_KEY must be a non-placeholder value"):
        Settings(
            environment="production",
            local_create_schema=False,
            secret_key=secret_key,
        )


def test_deployed_database_mode_rejects_default_secret_even_if_environment_is_mislabelled():
    with pytest.raises(ValidationError, match="SECRET_KEY must be a non-placeholder value"):
        Settings(
            environment="development",
            local_create_schema=False,
            secret_key="change-me",
        )


def test_production_accepts_a_long_non_placeholder_secret():
    settings = Settings(
        environment="production",
        local_create_schema=False,
        secret_key="correct-horse-battery-staple-with-extra-entropy",
    )

    assert settings.secret_key == "correct-horse-battery-staple-with-extra-entropy"


def test_local_development_can_still_boot_with_the_default_secret():
    settings = Settings(
        environment="development",
        local_create_schema=True,
        secret_key="change-me",
    )

    assert settings.secret_key == "change-me"
