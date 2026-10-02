"""Unit tests for :mod:`resolve.config`.

Each test runs in a scratch working directory (via the ``_isolate_dotenv``
fixture) that contains no ``.env`` file, so configuration is driven purely by the
environment variables set with ``monkeypatch``. This keeps the tests hermetic and
makes them behave identically locally (where a real ``.env`` exists) and in CI.
"""

import pytest
from pydantic import SecretStr, ValidationError

from resolve.config import Settings, get_settings


@pytest.fixture(autouse=True)
def _isolate_dotenv(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Run each test in an empty directory so no real ``.env`` is read."""
    monkeypatch.chdir(tmp_path)


def _set_required(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set the two mandatory secret keys to dummy values."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")


def test_loads_required_keys_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_required(monkeypatch)

    settings = Settings()

    assert isinstance(settings.gemini_api_key, SecretStr)
    assert settings.gemini_api_key.get_secret_value() == "test-gemini-key"
    assert settings.groq_api_key.get_secret_value() == "test-groq-key"


def test_model_defaults_match_free_tier(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_required(monkeypatch)

    settings = Settings()

    assert settings.router_model == "gemini/gemini-3.8-flash"
    assert settings.drafter_model == "gemini/gemini-3.8-flash"
    assert settings.judge_model == "groq/openai/gpt-oss-120b"


def test_env_overrides_model_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_required(monkeypatch)
    monkeypatch.setenv("JUDGE_MODEL", "gemini/gemini-3.8-flash")

    settings = Settings()

    assert settings.judge_model == "gemini/gemini-3.8-flash"


def test_secrets_are_redacted_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_required(monkeypatch)

    settings = Settings()

    # SecretStr must never leak the raw value through repr/str.
    assert "test-gemini-key" not in repr(settings)
    assert "test-gemini-key" not in str(settings.gemini_api_key)


def test_missing_required_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("GEMINI_API_KEY", "GROQ_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(var, raising=False)

    with pytest.raises(ValidationError):
        Settings()


def test_get_settings_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_required(monkeypatch)
    get_settings.cache_clear()

    first = get_settings()
    second = get_settings()

    assert first is second
    get_settings.cache_clear()  # leave no cached instance for other tests
