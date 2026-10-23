from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/MassERS"
    SECRET_KEY: str = "default_secret_key_for_testing_purposes_only_32_bytes_long!"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    DB_SCHEMA: str = "ers"
    FERNET_KEY: str = "cw0Hk-N0_xLdG8Z2vQ8Y9P-7L0xR4q1W8k6T5m2P4rA="
    MAIN_URL: str = "http://localhost:8088"

    class Config:
        env_file = ".env"              # Load environment variables from .env file
        extra = "ignore"


settings = Settings()