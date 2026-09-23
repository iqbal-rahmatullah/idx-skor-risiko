import pytest
from pydantic import ValidationError

from bot.config import Settings


def test_missing_setting_error_does_not_leak_secrets(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setenv("SECTORS_API_KEY", "rahasia-uji-123")

    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None)

    assert "rahasia-uji-123" not in str(exc.value)


def test_secret_not_in_repr(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token-uji-456")
    monkeypatch.setenv("SECTORS_API_KEY", "rahasia-uji-123")

    settings = Settings(_env_file=None)

    assert "token-uji-456" not in repr(settings)
    assert settings.telegram_bot_token.get_secret_value() == "token-uji-456"
