from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", hide_input_in_errors=True
    )

    telegram_bot_token: SecretStr
    sectors_api_key: SecretStr
    sectors_offline: bool = False
    database_url: str = "sqlite:///sectors_hackathon.db"
    llm_base_url: str = ""
    llm_api_key: SecretStr = SecretStr("")
    llm_model: str = ""
    llm_timeout: float = 180
