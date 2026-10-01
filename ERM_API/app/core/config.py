from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str                     # Add DATABASE_URL to settings
    SECRET_KEY: str
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int
    DB_SCHEMA: str                             # Add DB_SCHEMA to settings
    
    FERNET_KEY: str

    MAIN_URL: str

    class Config:
        env_file = ".env"              # Load environment variables from .env file
        extra = "ignore"


settings = Settings()