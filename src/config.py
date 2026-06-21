from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="B2C_", extra="ignore")

    database_url: str = "sqlite:///./b2c.db"
    b2b_url: str = "http://b2b:8000"
    b2b_service_key: str = "dev-b2c-to-b2b-key"
    jwt_secret_key: str = "secret"
    jwt_algorithm: str = "HS256"


settings = Settings()
